#!/bin/bash
# Creates menu + desktop shortcuts for the three web apps. Usage: make-shortcuts.sh <username>
set -e
USER_NAME="$1"
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
mk() {  # name, url, filename, icon
  cat > "/usr/share/applications/$3.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$1
Exec=xdg-open $2
Icon=$4
Terminal=false
Categories=Network;
EOF
  if [ -d "$HOME_DIR/Desktop" ] || mkdir -p "$HOME_DIR/Desktop"; then
    cp "/usr/share/applications/$3.desktop" "$HOME_DIR/Desktop/$3.desktop"
    chmod +x "$HOME_DIR/Desktop/$3.desktop"
    chown "$USER_NAME":"$USER_NAME" "$HOME_DIR/Desktop" "$HOME_DIR/Desktop/$3.desktop"
  fi
}
mk "Pi Hub"         "http://localhost:8080" pi-hub        applications-system
mk "Nextcloud"      "http://localhost:8081" pi-nextcloud  folder-cloud
mk "Home Assistant" "http://localhost:8123" pi-homeassistant user-home
