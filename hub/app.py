#!/usr/bin/env python3
"""Pi Hub: one small local web app for robot control and the alarm clock.

Private and self-contained: nothing here talks to the internet.

Robot side (ESP32): poll  GET  /api/robot/next   -> {"cmd": "forward", "args": {...}} or {}
                    report POST /api/robot/status -> any JSON, e.g. {"battery": 7.4}
Phone/browser:      open http://<pi>:8080 and use the buttons.
"""
import json
import os
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)
ALARMS_FILE = os.path.join(DATA, "alarms.json")
CONFIG_FILE = os.path.join(BASE, "config.json")
SOUND_FILE = os.path.join(DATA, "alarm.mp3")  # drop your own mp3 here

app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")
lock = threading.Lock()

# Commands the robot is allowed to receive. Add your own names here later.
ALLOWED_CMDS = {"forward", "backward", "left", "right", "stop", "wake", "speak", "custom"}

robot = {"queue": deque(maxlen=50), "last_seen": None, "status": {}}


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def load_alarms():
    try:
        with open(ALARMS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_alarms(alarms):
    tmp = ALARMS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(alarms, f, indent=2)
    os.replace(tmp, ALARMS_FILE)


def check_token():
    """If a token is set in config.json, robot endpoints require header X-Token."""
    token = load_config().get("robot_token", "")
    return (not token) or request.headers.get("X-Token") == token


def enqueue(cmd, args=None):
    with lock:
        robot["queue"].append({"id": uuid.uuid4().hex[:8], "cmd": cmd, "args": args or {}, "ts": time.time()})


# ---------------- pages ----------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


# ---------------- robot ----------------
@app.route("/api/robot/command", methods=["POST"])
def robot_command():
    body = request.get_json(silent=True) or {}
    cmd = body.get("cmd", "")
    if cmd not in ALLOWED_CMDS:
        return jsonify(error="unknown command"), 400
    enqueue(cmd, body.get("args"))
    return jsonify(ok=True)


@app.route("/api/robot/next")
def robot_next():
    if not check_token():
        return jsonify(error="bad token"), 403
    with lock:
        robot["last_seen"] = time.time()
        item = robot["queue"].popleft() if robot["queue"] else None
    return jsonify(item or {})


@app.route("/api/robot/status", methods=["POST"])
def robot_status():
    if not check_token():
        return jsonify(error="bad token"), 403
    with lock:
        robot["last_seen"] = time.time()
        robot["status"] = request.get_json(silent=True) or {}
    return jsonify(ok=True)


@app.route("/api/state")
def state():
    with lock:
        seen = robot["last_seen"]
        online = bool(seen and time.time() - seen < 15)
        return jsonify(
            robot_online=online,
            robot_status=robot["status"],
            queued=len(robot["queue"]),
            now=datetime.now().strftime("%H:%M:%S"),
        )


# ---------------- alarms ----------------
@app.route("/api/alarms", methods=["GET", "POST"])
def alarms():
    if request.method == "GET":
        return jsonify(load_alarms())
    body = request.get_json(silent=True) or {}
    t = str(body.get("time", ""))
    try:
        datetime.strptime(t, "%H:%M")
    except ValueError:
        return jsonify(error="time must be HH:MM"), 400
    alarm = {
        "id": uuid.uuid4().hex[:8],
        "time": t,
        "days": [d for d in body.get("days", [0, 1, 2, 3, 4, 5, 6]) if d in range(7)],  # 0=Mon
        "label": str(body.get("label", ""))[:60],
        "enabled": True,
        "robot_cmd": body.get("robot_cmd", "wake") if body.get("robot_cmd", "wake") in ALLOWED_CMDS else "wake",
        "sound": bool(body.get("sound", True)),
    }
    items = load_alarms()
    items.append(alarm)
    save_alarms(items)
    return jsonify(alarm)


@app.route("/api/alarms/<aid>", methods=["DELETE", "PATCH"])
def alarm_item(aid):
    items = load_alarms()
    if request.method == "DELETE":
        items = [a for a in items if a["id"] != aid]
    else:
        body = request.get_json(silent=True) or {}
        for a in items:
            if a["id"] == aid and "enabled" in body:
                a["enabled"] = bool(body["enabled"])
    save_alarms(items)
    return jsonify(ok=True)


@app.route("/api/alarms/<aid>/test", methods=["POST"])
def alarm_test(aid):
    for a in load_alarms():
        if a["id"] == aid:
            fire(a)
            return jsonify(ok=True)
    return jsonify(error="not found"), 404


ringing = {"active": False, "label": "", "since": None, "proc": None}


def play_sound():
    if os.path.exists(SOUND_FILE):
        cmd = ["mpg123", "-q", "--loop", "-1", SOUND_FILE]
    else:  # fall back to a plain beep
        cmd = ["speaker-test", "-t", "sine", "-f", "880"]
    try:
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return None


def stop_ringing():
    with lock:
        proc = ringing["proc"]
        ringing.update(active=False, proc=None, since=None)
    if proc and proc.poll() is None:
        proc.terminate()


def fire(alarm):
    print(f"[alarm] firing {alarm['time']} {alarm.get('label', '')}", flush=True)
    stop_ringing()
    proc = play_sound() if alarm.get("sound", True) else None
    with lock:
        ringing.update(active=True, label=alarm.get("label", ""), since=time.time(), proc=proc)
    if alarm.get("robot_cmd"):
        enqueue(alarm["robot_cmd"], {"alarm": alarm.get("label", "")})


def next_alarm():
    """Soonest enabled alarm within the next 7 days, or None."""
    now = datetime.now()
    best = None
    for a in load_alarms():
        if not a.get("enabled"):
            continue
        h, m = map(int, a["time"].split(":"))
        for offset in range(8):
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=offset)
            if cand > now and cand.weekday() in a.get("days", []):
                if best is None or cand < best[0]:
                    best = (cand, a)
                break
    return best


# Hooks for any alarm clock kit / display / ESP32: poll /api/alarm/state.
@app.route("/api/alarm/state")
def alarm_state():
    nxt = next_alarm()
    with lock:
        r = {"ringing": ringing["active"], "label": ringing["label"]}
    r["next"] = {"time": nxt[0].strftime("%Y-%m-%d %H:%M"), "label": nxt[1].get("label", "")} if nxt else None
    r["now"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(r)


@app.route("/api/alarm/dismiss", methods=["POST"])
def alarm_dismiss():
    stop_ringing()
    return jsonify(ok=True)


@app.route("/api/alarm/snooze", methods=["POST"])
def alarm_snooze():
    minutes = int((request.get_json(silent=True) or {}).get("minutes", 9))
    label = ringing["label"]
    stop_ringing()
    threading.Timer(minutes * 60, lambda: fire({"time": "snooze", "label": label, "sound": True, "robot_cmd": "wake"})).start()
    return jsonify(ok=True, minutes=minutes)


def alarm_loop():
    last_fired = None
    while True:
        now = datetime.now()
        key = now.strftime("%Y-%m-%d %H:%M")
        if key != last_fired:
            for a in load_alarms():
                if a.get("enabled") and a["time"] == now.strftime("%H:%M") and now.weekday() in a.get("days", []):
                    fire(a)
            last_fired = key
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=alarm_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, threaded=True)
