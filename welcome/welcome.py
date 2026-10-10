#!/usr/bin/env python3
"""Shown automatically when the Pi desktop starts: setup progress, IP address, links and logins."""
import json
import os
import socket
import subprocess
import tkinter as tk
from tkinter import ttk

CFG_DIR = os.path.expanduser("~/.config/pi-kit")
SKIP_FLAG = os.path.join(CFG_DIR, "no-welcome")
CRED_FILE = os.path.join(CFG_DIR, "credentials.json")
DONE_FLAG = "/var/lib/pi-kit/done"
LOG = "/var/log/pi-kit-install.log"


def ips():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout.split()
    except Exception:
        out = []
    return [i for i in out if "." in i]  # IPv4 only


def creds():
    try:
        with open(CRED_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def last_log_line():
    try:
        with open(LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 600))
            lines = f.read().decode(errors="replace").strip().splitlines()
        return lines[-1][:90] if lines else ""
    except Exception:
        return ""


def open_url(url):
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if os.path.exists(SKIP_FLAG) and os.path.exists(DONE_FLAG):
        return
    host = socket.gethostname()
    root = tk.Tk()
    root.title("Pi Hub")
    root.geometry("660x560")
    root.attributes("-topmost", True)
    frm = ttk.Frame(root, padding=18)
    frm.pack(fill="both", expand=True)

    title = ttk.Label(frm, font=("sans", 20, "bold"))
    title.pack(anchor="w")
    status = ttk.Label(frm, font=("sans", 10), foreground="gray", wraplength=620)
    status.pack(anchor="w", pady=(2, 6))
    ip_label = ttk.Label(frm, font=("sans", 16))
    ip_label.pack(anchor="w", pady=(4, 12))

    services = [
        ("Pi Hub  (robot + alarm clock)", 8080),
        ("Nextcloud  (files)", 8081),
        ("Home Assistant", 8123),
    ]
    link_frame = ttk.Frame(frm)
    link_frame.pack(fill="x")
    buttons = []
    for name, port in services:
        row = ttk.Frame(link_frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=name, width=30).pack(side="left")
        b = ttk.Button(row, text="Open", command=lambda p=port: open_url(f"http://localhost:{p}"))
        b.pack(side="left")
        buttons.append(b)
        ttk.Label(row, text=f"  other devices: http://{host}.local:{port}", foreground="gray").pack(side="left")

    box = ttk.LabelFrame(frm, text="Logins", padding=10)
    box.pack(fill="x", pady=14)
    logins = ttk.Label(box, font=("monospace", 10), justify="left")
    logins.pack(anchor="w")

    skip = tk.BooleanVar()
    ttk.Checkbutton(frm, text="Don't show this at startup", variable=skip).pack(anchor="w")

    def close():
        if skip.get():
            os.makedirs(CFG_DIR, exist_ok=True)
            open(SKIP_FLAG, "w").close()
        root.destroy()

    ttk.Button(frm, text="Close", command=close).pack(anchor="e", pady=8)
    root.protocol("WM_DELETE_WINDOW", close)

    def refresh():
        done = os.path.exists(DONE_FLAG)
        title.config(text="Your Pi is ready" if done else "Setting up your Pi...")
        status.config(text="" if done else "This runs by itself and can take 10 to 30 minutes. Do not unplug the Pi.   " + last_log_line())
        for b in buttons:
            b.state(["!disabled"] if done else ["disabled"])
        found = ips()
        ip_label.config(text=("IP address:  " + "   ".join(found)) if found else "No network yet. Plug in Ethernet or join Wi-Fi (top right).")
        c = creds()
        if done and c:
            logins.config(text="\n".join([
                f"Nextcloud:   {c.get('nextcloud_user', 'admin')}  /  {c.get('nextcloud_password', '')}",
                f"File share:  \\\\{host}\\storage   {c.get('samba_user', '')}  /  {c.get('samba_password', '')}",
                "Home Assistant:  create your account the first time you open it",
            ]))
        else:
            logins.config(text="Passwords appear here when setup finishes.")
        root.after(3000, refresh)

    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
