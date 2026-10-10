#!/usr/bin/env bash
# Pi Kit installer - run once on a fresh Raspberry Pi OS (64-bit, with desktop).
# Safe to re-run: every step checks before changing anything.
# Used two ways: by hand (sudo bash install.sh) or automatically on first boot by the prebuilt image.
set -euo pipefail

KIT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR=/opt/pi-kit
LOG=/var/log/pi-kit-install.log
exec > >(tee -a "$LOG") 2>&1

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash $0"; exit 1
fi

echo "=== Pi Kit install started $(date) ==="

# ---- sanity checks -------------------------------------------------------
ARCH=$(dpkg --print-architecture)
[[ "$ARCH" == "arm64" ]] || { echo "Need 64-bit Raspberry Pi OS (arm64), found $ARCH"; exit 1; }

# Internet is only needed if something is missing; the prebuilt image already contains everything.
have_net() { curl -fsI --max-time 5 https://deb.debian.org >/dev/null 2>&1; }
wait_net() {
  for i in $(seq 1 120); do have_net && return 0; echo "Waiting for internet ($i/120)..."; sleep 5; done
  return 1
}

# Main user = first normal user (uid 1000); on a prebuilt image it may appear a little late
MAIN_USER=""
for i in $(seq 1 60); do
  MAIN_USER=$(getent passwd 1000 | cut -d: -f1 || true)
  [[ -n "$MAIN_USER" ]] && break
  sleep 3
done
[[ -n "$MAIN_USER" ]] || { echo "No uid-1000 user found"; exit 1; }
HOME_DIR=$(getent passwd "$MAIN_USER" | cut -d: -f6)
echo "Main user: $MAIN_USER"

# ---- packages (skipped when already in the image) ------------------------
export DEBIAN_FRONTEND=noninteractive
PKGS="curl ca-certificates openssl samba avahi-daemon python3 python3-flask python3-tk mpg123 alsa-utils xdg-utils"
MISSING=0
for p in $PKGS; do dpkg -s "$p" >/dev/null 2>&1 || MISSING=1; done
if [[ $MISSING -eq 1 ]]; then
  wait_net || { echo "No internet and packages are missing"; exit 1; }
  apt-get update
  apt-get install -y --no-install-recommends $PKGS
fi

# Docker (already in the prebuilt image; otherwise the official convenience script)
if ! command -v docker >/dev/null 2>&1; then
  wait_net || { echo "No internet and Docker is missing"; exit 1; }
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "$MAIN_USER"
systemctl enable --now docker
for i in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done

# ---- files ---------------------------------------------------------------
mkdir -p "$KIT_DIR" /srv/storage
if [[ "$KIT_SRC" != "$KIT_DIR" ]]; then
  cp -a "$KIT_SRC/." "$KIT_DIR/"
fi
chmod 755 /srv/storage
chown "$MAIN_USER":"$MAIN_USER" /srv/storage

# Secrets: generated once, kept on the Pi only
if [[ ! -f "$KIT_DIR/.env" ]]; then
  {
    echo "DB_ROOT_PASSWORD=$(openssl rand -hex 16)"
    echo "DB_PASSWORD=$(openssl rand -hex 16)"
    echo "NEXTCLOUD_ADMIN_USER=admin"
    echo "NEXTCLOUD_ADMIN_PASSWORD=$(openssl rand -hex 6)"
    echo "TZ=$(cat /etc/timezone 2>/dev/null || echo UTC)"
  } > "$KIT_DIR/.env"
  chmod 600 "$KIT_DIR/.env"
fi
NC_USER=$(grep '^NEXTCLOUD_ADMIN_USER=' "$KIT_DIR/.env" | cut -d= -f2)
NC_PW=$(grep '^NEXTCLOUD_ADMIN_PASSWORD=' "$KIT_DIR/.env" | cut -d= -f2)

# ---- Samba file share, with an automatically generated password -----------
CFG_DIR="$HOME_DIR/.config/pi-kit"
CRED="$CFG_DIR/credentials.json"
mkdir -p "$CFG_DIR"
if [[ -f "$CRED" ]]; then
  SMB_PW=$(python3 -c "import json;print(json.load(open('$CRED')).get('samba_password',''))")
else
  SMB_PW=""
fi
if [[ -z "$SMB_PW" ]]; then
  SMB_PW=$(openssl rand -hex 5)
fi
if ! grep -q '^\[storage\]' /etc/samba/smb.conf; then
  cat >> /etc/samba/smb.conf <<EOF

[storage]
   path = /srv/storage
   browseable = yes
   read only = no
   valid users = $MAIN_USER
   create mask = 0664
   directory mask = 0775
EOF
fi
(echo "$SMB_PW"; echo "$SMB_PW") | smbpasswd -a -s "$MAIN_USER"
systemctl enable --now smbd nmbd || true

cat > "$CRED" <<EOF
{"nextcloud_user": "$NC_USER", "nextcloud_password": "$NC_PW", "samba_user": "$MAIN_USER", "samba_password": "$SMB_PW"}
EOF
chown -R "$MAIN_USER":"$MAIN_USER" "$CFG_DIR"
chmod 600 "$CRED"

# ---- IP address on the text login screen (updates itself when the network changes)
install -m 755 "$KIT_DIR/system/pi-kit-ip" /usr/local/bin/pi-kit-ip
install -m 644 "$KIT_DIR/system/pi-kit-ip.service" /etc/systemd/system/pi-kit-ip.service
if [[ -d /etc/NetworkManager/dispatcher.d ]]; then
  install -m 755 "$KIT_DIR/system/90-pi-kit-ip" /etc/NetworkManager/dispatcher.d/90-pi-kit-ip
fi
systemctl daemon-reload
systemctl enable pi-kit-ip.service
/usr/local/bin/pi-kit-ip || true

# ---- Desktop welcome window (IP + links + logins) and shortcuts -----------
install -m 644 "$KIT_DIR/system/pi-kit-welcome.desktop" /etc/xdg/autostart/pi-kit-welcome.desktop
bash "$KIT_DIR/system/make-shortcuts.sh" "$MAIN_USER"

# ---- containers (Nextcloud + Home Assistant) -----------------------------
cd "$KIT_DIR"
# Load the app images that ship inside the prebuilt image (no download needed)
if compgen -G "$KIT_DIR/images/*.tar.gz" >/dev/null; then
  for f in "$KIT_DIR"/images/*.tar.gz; do
    echo "Loading $f ..."
    docker load -i "$f" && rm -f "$f"
  done
fi
docker compose --env-file .env up -d

# Nextcloud refuses addresses it doesn't know ("untrusted domain"). Wait for its first-run
# setup to finish, then trust localhost, the .local name and the current IP.
echo "Waiting for Nextcloud first-time setup (can take a few minutes)..."
for i in $(seq 1 60); do
  if docker compose --env-file .env exec -T -u www-data nextcloud php occ status 2>/dev/null | grep -q 'installed: true'; then
    break
  fi
  sleep 10
done
/usr/local/bin/pi-kit-ip || true

# Boot straight into the desktop (auto-login) so the welcome window with the IP appears by itself
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_boot_behaviour B4 || true
fi

# ---- Pi Hub (robot + alarm clock control) --------------------------------
cat > /etc/systemd/system/pi-hub.service <<EOF
[Unit]
Description=Pi Hub (robot + alarm clock control)
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$MAIN_USER
SupplementaryGroups=audio
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u "$MAIN_USER")
WorkingDirectory=$KIT_DIR/hub
ExecStart=/usr/bin/python3 $KIT_DIR/hub/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
mkdir -p "$KIT_DIR/hub/data"
chown -R "$MAIN_USER":"$MAIN_USER" "$KIT_DIR/hub"
systemctl daemon-reload
systemctl enable --now pi-hub.service

# ---- summary -------------------------------------------------------------
IP=$(hostname -I | awk '{print $1}')
HOST=$(hostname)
cat > "$HOME_DIR/PI-KIT-INFO.txt" <<EOF
Pi Kit is installed.

IP address                   : $IP   (also shown in the welcome window at startup)
Pi Hub (robot + alarm clock) : http://$HOST.local:8080   (or http://$IP:8080)
Nextcloud                    : http://$HOST.local:8081   (or http://$IP:8081)
   user: $NC_USER   password: $NC_PW
Home Assistant               : http://$HOST.local:8123   (or http://$IP:8123)
File share                   : \\\\$HOST\\storage   user: $MAIN_USER   password: $SMB_PW

Optional voice assistant: sudo bash /opt/pi-kit/voice/install-voice.sh
Install log: $LOG
EOF
chown "$MAIN_USER":"$MAIN_USER" "$HOME_DIR/PI-KIT-INFO.txt"
cat "$HOME_DIR/PI-KIT-INFO.txt"

mkdir -p /var/lib/pi-kit && touch /var/lib/pi-kit/done
echo "=== Pi Kit install finished $(date) ==="
