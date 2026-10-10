#!/bin/bash -e
# pi-gen stage: copy the Pi Kit into the image and arrange for it to install itself on first boot.
install -d "${ROOTFS_DIR}/opt/pi-kit"
cp -a files/pi-kit/. "${ROOTFS_DIR}/opt/pi-kit/"
chmod +x "${ROOTFS_DIR}/opt/pi-kit/install.sh"

install -m 644 files/pi-kit/system/pi-kit-firstboot.service "${ROOTFS_DIR}/etc/systemd/system/pi-kit-firstboot.service"
on_chroot << EOF
systemctl enable pi-kit-firstboot.service
EOF
