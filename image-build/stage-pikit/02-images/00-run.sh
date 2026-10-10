#!/bin/bash -e
# Copy the pre-downloaded app images (Nextcloud, MariaDB, Redis, Home Assistant) into the image.
install -d "${ROOTFS_DIR}/opt/pi-kit/images"
cp -a files/images/. "${ROOTFS_DIR}/opt/pi-kit/images/"
