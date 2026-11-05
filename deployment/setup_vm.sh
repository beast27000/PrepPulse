#!/usr/bin/env bash
set -euo pipefail
# Dedicated LUN 0 only. Never format a system disk or a disk with existing data.
disk=/dev/disk/azure/scsi1/lun0
test -b "$disk"
if ! sudo blkid "$disk" >/dev/null 2>&1; then
  test "$(sudo lsblk -n -o MOUNTPOINT "$disk" | tr -d '[:space:]')" = ""
  sudo mkfs.ext4 -L preppulse-data "$disk"
fi
sudo mkdir -p /data /etc/preppulse /opt/preppulse
uuid=$(sudo blkid -s UUID -o value "$disk")
if ! grep -q "$uuid" /etc/fstab; then
  printf 'UUID=%s /data ext4 defaults,nofail 0 2\n' "$uuid" | sudo tee -a /etc/fstab >/dev/null
fi
mountpoint -q /data || sudo mount /data
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo mkdir -p /data/private /data/models /data/mongo /data/caddy
sudo chown -R 10001:10001 /data/private /data/models
sudo chown -R "$USER:$USER" /opt/preppulse
sudo chmod 700 /etc/preppulse
