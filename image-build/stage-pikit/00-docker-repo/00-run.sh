#!/bin/bash -e
# Add Docker's official apt repository so docker-ce can be installed into the image at build time.
install -d -m 0755 "${ROOTFS_DIR}/etc/apt/keyrings"
curl -fsSL https://download.docker.com/linux/debian/gpg -o "${ROOTFS_DIR}/etc/apt/keyrings/docker.asc"
chmod a+r "${ROOTFS_DIR}/etc/apt/keyrings/docker.asc"
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" \
  > "${ROOTFS_DIR}/etc/apt/sources.list.d/docker.list"
on_chroot << CHEOF
apt-get update
CHEOF
