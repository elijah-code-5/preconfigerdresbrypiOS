# Pi Kit for Raspberry Pi 4 (4 GB)

Desktop + Nextcloud + Home Assistant + file share + robot control + alarm clock + private voice assistant + phone app.

**Honest status:** the scripts passed syntax checks and the hub's web API passed tests, but nothing here has been run on a real Pi yet. If something fails, send me `/var/log/pi-kit-install.log`.

## Easiest way: the setup page (`pi-setup.html`, next to this folder)
1. Open `pi-setup.html` in any browser, fill in username, password and Wi-Fi, press the button, download the two files (`user-data`, `network-config`).
2. Raspberry Pi Imager: Raspberry Pi 4 -> Raspberry Pi OS (64-bit) with desktop -> your card. Skip Imager's own customisation. Write.
3. Re-plug the card if it ejected, copy the two files onto the `bootfs` drive (replace existing ones).
4. Put the card in the Pi and power on. Wait 15 to 30 minutes (needs internet; restarts once). The desktop then shows the IP address and logins.

The Pi's own copy of this kit lives in `/opt/pi-kit`; the install log is `/var/log/pi-kit-install.log`.

## Other ways to get it

### Option: ready-made image (one file to flash, needs a free GitHub account)
1. Make a free GitHub account, create a new repository, and upload everything in this folder (keep the `.github` folder).
2. Go to the **Actions** tab -> **Build Raspberry Pi image** -> **Run workflow**. Wait about 1 to 2 hours.
3. Download the `pihub-image` artifact, unzip it, and flash the `.img.xz` file with Raspberry Pi Imager (**Choose OS -> Use custom**).
4. Boot. The Pi installs everything by itself on first boot (needs internet, 10 to 25 minutes, Docker images are large). The desktop then shows a window with the IP address, links and logins.

Login on that image: user `pi`, password `pihub-change-me` (change it in the workflow file before building, or run `passwd` after). SSH is off.

### Way 2: normal Raspberry Pi OS + this folder (no GitHub needed)
1. Raspberry Pi Imager -> Raspberry Pi 4 -> **Raspberry Pi OS (64-bit)** (with desktop). Set name, user, Wi-Fi in Imager.
2. Before ejecting, copy this whole folder onto the `bootfs` partition, as `pi-kit`.
3. Boot, open a terminal, run: `sudo bash /boot/firmware/pi-kit/install.sh`

Hands-off variant: see `user-data.template` and `network-config.template`.

## After install
- A welcome window shows the **IP address**, buttons for each app, and generated passwords. The text login screen shows the IP too, and both update when the network changes.
- Desktop shortcuts: Pi Hub, Nextcloud, Home Assistant.
- Pi Hub `:8080` (robot + alarms), Nextcloud `:8081`, Home Assistant `:8123`, file share `\\pihub\storage`.

## Robot
Edit the three Wi-Fi/hub lines at the top of `robot-firmware/pihub_robot/pihub_robot.ino`, flash with Arduino IDE (board "ESP32 Dev Module"). Open `http://<robot-ip>/` for the motor test page first. If a wheel spins the wrong way, swap its two numbers in the `M_FL / M_BL / M_FR / M_BR` lines. **Those channel numbers are from memory of the Freenove board and are the most likely thing to need a tweak.**

## Alarm clock
Alarms are in the Hub page. For your alarm clock kit, poll `GET /api/alarm/state` (`ringing`, `next`), and call `POST /api/alarm/dismiss` or `/api/alarm/snooze`.

## Voice assistant (optional, needs USB mic + speaker)
`sudo bash /opt/pi-kit/voice/install-voice.sh`, then say "computer go forward". Edit phrases in `voice/commands.json`.

## Phone
- iPhone and Android: open `http://<pi-ip>:8080` and use Add to Home Screen.
- Android APK: in GitHub, Actions -> **Build Android APK** -> Run workflow, download `pi-hub-apk`. Install it (allow "unknown sources"). It asks for the Pi's address once.

## Not included
Open Media Vault (conflicts with a desktop; Samba + Nextcloud cover storage) and Home Assistant OS (replaces the whole OS; Home Assistant runs in Docker here).

## Security
Home network only. Do not forward these ports on your router. Change the default image password.
