#!/usr/bin/env python3
"""Private voice assistant: everything runs on the Pi, nothing leaves your network.

Say the wake word, then a phrase from commands.json, e.g.
    "computer go forward"   "computer what time is it"   "computer stop"
Speech recognition: Vosk (offline). Speech output: espeak-ng.
"""
import json
import os
import queue
import subprocess
import sys
import urllib.request
from datetime import datetime

import sounddevice as sd
from vosk import KaldiRecognizer, Model

BASE = os.path.dirname(os.path.abspath(__file__))
HUB = os.environ.get("HUB_URL", "http://127.0.0.1:8080")
MODEL_DIR = os.path.join(BASE, "model")


def load_cfg():
    with open(os.path.join(BASE, "commands.json")) as f:
        return json.load(f)


def speak(text):
    print("[say]", text, flush=True)
    subprocess.Popen(["espeak-ng", "-s", "160", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def hub_post(path, body):
    req = urllib.request.Request(HUB + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as e:
        print("[hub error]", e, flush=True)


def run_action(action):
    kind = action.get("type")
    if kind == "robot":
        hub_post("/api/robot/command", {"cmd": action["cmd"]})
    elif kind == "alarm_dismiss":
        hub_post("/api/alarm/dismiss", {})
    elif kind == "alarm_snooze":
        hub_post("/api/alarm/snooze", {"minutes": action.get("minutes", 9)})
    elif kind == "time":
        speak("It is " + datetime.now().strftime("%-I:%M %p"))
    elif kind == "shell":  # only commands YOU put in commands.json can run
        subprocess.Popen(action["cmd"], shell=True)
    if action.get("reply"):
        speak(action["reply"])


def main():
    if not os.path.isdir(MODEL_DIR):
        sys.exit("Speech model missing. Run: sudo bash /opt/pi-kit/voice/install-voice.sh")
    cfg = load_cfg()
    wake = cfg.get("wake_word", "computer").lower()
    commands = {k.lower(): v for k, v in cfg["commands"].items()}

    model = Model(MODEL_DIR)
    rate = 16000
    rec = KaldiRecognizer(model, rate)
    audio_q = queue.Queue()

    def cb(indata, frames, t, status):
        audio_q.put(bytes(indata))

    speak("Voice assistant ready")
    with sd.RawInputStream(samplerate=rate, blocksize=8000, dtype="int16", channels=1, callback=cb):
        while True:
            data = audio_q.get()
            if not rec.AcceptWaveform(data):
                continue
            text = json.loads(rec.Result()).get("text", "").lower().strip()
            if not text:
                continue
            print("[heard]", text, flush=True)
            if wake not in text:
                continue
            phrase = text.split(wake, 1)[1].strip()
            for key, action in commands.items():
                if key in phrase:
                    run_action(action)
                    break
            else:
                if phrase:
                    speak("Sorry, I don't know that one")


if __name__ == "__main__":
    main()
