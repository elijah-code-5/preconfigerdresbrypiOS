#!/usr/bin/env bash
# Optional: installs the offline voice assistant. Needs a USB microphone and a speaker.
# Run:  sudo bash /opt/pi-kit/voice/install-voice.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
DIR=/opt/pi-kit/voice
USER_NAME=$(getent passwd 1000 | cut -d: -f1)

apt-get install -y --no-install-recommends python3-venv python3-pip libportaudio2 espeak-ng unzip curl
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet vosk sounddevice

if [[ ! -d "$DIR/model" ]]; then
  curl -fL -o /tmp/vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
  unzip -q /tmp/vosk-model.zip -d /tmp/vosk-model
  mv /tmp/vosk-model/vosk-model-small-en-us-0.15 "$DIR/model"
  rm -rf /tmp/vosk-model /tmp/vosk-model.zip
fi
chown -R "$USER_NAME":"$USER_NAME" "$DIR"

cat > /etc/systemd/system/pi-voice.service <<EOF
[Unit]
Description=Pi private voice assistant
After=pi-hub.service sound.target

[Service]
User=$USER_NAME
SupplementaryGroups=audio
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u "$USER_NAME")
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python $DIR/assistant.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now pi-voice.service
echo "Voice assistant running. Say: 'computer go forward'. Edit phrases in $DIR/commands.json then: sudo systemctl restart pi-voice"
