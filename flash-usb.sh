#!/usr/bin/env bash
set -euo pipefail

ISO_PATH="/home/aelkholy/Dev_Lab/AE_ARCH/output/SecLegion-OS-2026.10.08-x86_64.iso"
TARGET_DRIVE="/dev/sdb"

GREEN="\033[1;32m"
CYAN="\033[1;36m"
RED="\033[1;31m"
RESET="\033[0m"

echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN}    SecLegion OS — USB Flashing Protocol                            ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"

MODEL=$(lsblk -dn -o MODEL "$TARGET_DRIVE" 2>/dev/null || true)
TRAN=$(lsblk -dn -o TRAN "$TARGET_DRIVE" 2>/dev/null || true)
SIZE=$(lsblk -dn -o SIZE "$TARGET_DRIVE" 2>/dev/null || true)

echo -e " Target Drive:   ${CYAN}${TARGET_DRIVE}${RESET} (${MODEL}, ${SIZE}, Transport: ${TRAN})"
echo -e " Source ISO:     ${CYAN}${ISO_PATH}${RESET}"

if [[ "$TARGET_DRIVE" == "/dev/sda" ]]; then
    echo -e "${RED}[FATAL ERROR] Refusing to flash /dev/sda (Internal HDD). Aborting!${RESET}"
    exit 1
fi

if [[ "$TRAN" != "usb" ]]; then
    echo -e "${RED}[FATAL ERROR] ${TARGET_DRIVE} is not a USB device (Transport: ${TRAN}). Aborting!${RESET}"
    exit 1
fi

echo -e "\n[1/3] Unmounting partitions on ${TARGET_DRIVE}..."
umount ${TARGET_DRIVE}* 2>/dev/null || true

echo -e "\n[2/3] Writing SecLegion OS to ${TARGET_DRIVE} (this takes ~1-2 minutes)..."
dd if="$ISO_PATH" of="$TARGET_DRIVE" bs=4M status=progress oflag=sync conv=fsync

echo -e "\n[3/3] Flushing buffers with sync..."
sync

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} ✅ FLASH COMPLETE! Your SecLegion OS USB is ready to boot!         ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
