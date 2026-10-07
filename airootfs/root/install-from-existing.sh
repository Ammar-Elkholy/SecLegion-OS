#!/usr/bin/env bash
# ==============================================================================
# install-from-existing.sh — SecLegion OS USB-Less Local Partition Installer
# Installs SecLegion OS directly onto any disk partition without a flash drive
# ==============================================================================

set -euo pipefail

GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
DIM="\033[2;37m"
RESET="\033[0m"

clear
echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN} █${GREEN}  ██████ ███████  ██████     ${CYAN}SECLEGION OS   █${RESET}"
echo -e "${CYAN} █${GREEN}  ██     ██      ██          ${CYAN}USB-Less Local █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ █████  ██          ${DIM}Deployer       ${CYAN} █${RESET}"
echo -e "${CYAN} █${GREEN}       ██ ██     ██                         █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ ███████  ██████                   █${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " ${GREEN}Automated Partition-to-Partition Deployment Engine${RESET}"
echo -e " ${DIM}Engineered by Ammar Elkholy — No USB Flash Drive Required${RESET}"
echo -e "${CYAN}--------------------------------------------------------------------${RESET}"

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR] This installer must be executed as root: sudo bash install-from-existing.sh${RESET}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AIROOTFS="$SCRIPT_DIR/airootfs"
MOUNT_POINT="/mnt/seclegion-target"

echo -e "\n${CYAN}[1/6] Available Disks and Partitions:${RESET}"
lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINTS,LABEL

echo -e "\n${CYAN}[2/6] Target Partition Selection:${RESET}"
read -rp " Enter TARGET ROOT partition to install to (e.g. /dev/nvme0n1p3, /dev/sda4): " TARGET_ROOT
if [[ ! -b "$TARGET_ROOT" ]]; then
    echo -e "${RED}[ERROR] Device $TARGET_ROOT does not exist! Aborting.${RESET}"
    exit 1
fi

read -rp " Enter EFI partition (e.g. /dev/nvme0n1p1) [Leave blank to skip bootloader]: " TARGET_EFI

read -rp " Choose Filesystem for $TARGET_ROOT (ext4/btrfs) [default: ext4]: " FS_TYPE
FS_TYPE="${FS_TYPE:-ext4}"

echo -e "\n${RED}⚠️  WARNING: ALL DATA ON ${TARGET_ROOT} WILL BE FORMATTED AS ${FS_TYPE}!${RESET}"
read -rp " Are you absolutely sure? Type 'YES' to proceed: " CONFIRM
if [[ "$CONFIRM" != "YES" ]]; then
    echo -e "${YELLOW}Installation cancelled by user.${RESET}"
    exit 0
fi

echo -e "\n${CYAN}[3/6] Target Identity Setup:${RESET}"
read -rp " Enter Username for SecLegion OS [default: operator]: " USERNAME
USERNAME="${USERNAME:-operator}"

read -s -rp " Enter Password for $USERNAME: " USER_PASS
echo
read -rp " Enter Computer Hostname [default: seclegion-box]: " HOSTNAME
HOSTNAME="${HOSTNAME:-seclegion-box}"

# Step 4: Formatting and Mounting
echo -e "\n${CYAN}[4/6] Formatting and Mounting Target Storage...${RESET}"
umount -R "$MOUNT_POINT" 2>/dev/null || true
mkdir -p "$MOUNT_POINT"

if [[ "$FS_TYPE" == "btrfs" ]]; then
    mkfs.btrfs -f "$TARGET_ROOT"
    mount "$TARGET_ROOT" "$MOUNT_POINT"
else
    mkfs.ext4 -F "$TARGET_ROOT"
    mount "$TARGET_ROOT" "$MOUNT_POINT"
fi

if [[ -n "$TARGET_EFI" && -b "$TARGET_EFI" ]]; then
    mkdir -p "$MOUNT_POINT/boot"
    mount "$TARGET_EFI" "$MOUNT_POINT/boot"
fi

# Step 5: Base System Deployment
echo -e "\n${CYAN}[5/6] Deploying SecLegion OS Base System & Dotfiles...${RESET}"
if command -v pacstrap &>/dev/null; then
    echo -e " Running pacstrap with core base packages..."
    pacstrap -K "$MOUNT_POINT" base base-devel linux linux-firmware networkmanager grub efibootmgr sudo
fi

# Overlay custom airootfs dotfiles, scripts, and SecLegion configurations
echo -e " Syncing SecLegion airootfs overlay..."
rsync -aAXv --exclude="/etc/shadow" --exclude="/etc/gshadow" "$AIROOTFS/" "$MOUNT_POINT/"

# Generate fstab
if command -v genfstab &>/dev/null; then
    echo -e " Generating /etc/fstab..."
    genfstab -U "$MOUNT_POINT" >> "$MOUNT_POINT/etc/fstab"
fi

# Step 6: Chroot Configuration
echo -e "\n${CYAN}[6/6] Finalizing Configuration Inside Target System...${RESET}"
arch-chroot "$MOUNT_POINT" /bin/bash <<CHROOT_EOF
# Set hostname
echo "$HOSTNAME" > /etc/hostname

# Set locale
echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen 2>/dev/null || true
echo "LANG=en_US.UTF-8" > /etc/locale.conf

# Create user and set password
useradd -m -G wheel,storage,power,network,video,audio,libvirt,kvm,wireshark -s /bin/zsh "$USERNAME" 2>/dev/null || true
echo "$USERNAME:$USER_PASS" | chpasswd
echo "root:$USER_PASS" | chpasswd

# Sudo privileges
echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/wheel

# Enable essential systemd services
systemctl enable NetworkManager.service 2>/dev/null || true
systemctl enable gdm.service 2>/dev/null || true
systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable libvirtd.service 2>/dev/null || true
systemctl enable virtlogd.service 2>/dev/null || true

# Install GRUB if EFI partition is mounted
if [[ -d /boot/EFI || -d /boot/efi || -n "$TARGET_EFI" ]]; then
    grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=SecLegion 2>/dev/null || true
    grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
fi
CHROOT_EOF

umount -R "$MOUNT_POINT" 2>/dev/null || true

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} ✅ SECLEGION OS USB-LESS INSTALLATION COMPLETED!                  ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " Installed Partition: ${GREEN}${TARGET_ROOT}${RESET}"
echo -e " Default User:        ${CYAN}${USERNAME}${RESET}"
echo -e " System Hostname:     ${CYAN}${HOSTNAME}${RESET}"
echo -e " You can now reboot and select 'SecLegion' from your UEFI boot menu."
echo -e "${CYAN}====================================================================${RESET}"
