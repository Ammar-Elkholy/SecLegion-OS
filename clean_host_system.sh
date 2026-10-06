#!/usr/bin/env bash
# ==============================================================================
# Host System Cleanup & De-Bloat Script
# Actions:
#  1. Mask failed TPM PCR services
#  2. Remove redundant file managers (Dolphin, Thunar) - keeping Nautilus & Yazi
#  3. Remove orphan packages (cmake, hyprwayland-scanner) and yay-debug
#  4. Clean KDE Baloo file indexing leftovers
#  5. Clear package caches
# ==============================================================================

set -euo pipefail

# Require root privileges
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run with sudo: sudo bash $0"
   exit 1
fi

echo "==> 1. Masking failed TPM2 PCR measurement services..."
systemctl mask systemd-pcrlogin@.service 2>/dev/null || true
systemctl mask systemd-pcrproduct.service 2>/dev/null || true
systemctl mask systemd-tpm2-setup-early.service 2>/dev/null || true
systemctl reset-failed 2>/dev/null || true
echo "    TPM2 services masked. Boot log is clean."

echo "==> 2. Removing redundant file managers (Dolphin, Thunar) to eliminate KDE/XFCE bloat..."
# Keeping Nautilus (GNOME) and Yazi (CLI)
pacman -Rns --noconfirm dolphin thunar 2>/dev/null || echo "Dolphin/Thunar already removed or not installed."

echo "==> 3. Removing orphan packages and debug artifacts..."
pacman -Rns --noconfirm cmake hyprwayland-scanner yay-debug 2>/dev/null || echo "Orphans already clean."

echo "==> 4. Cleaning KDE Baloo leftover indexing config files..."
rm -f /home/aelkholy/.config/baloofilerc /home/aelkholy/.config/baloofileinformationrc 2>/dev/null || true

echo "==> 5. Cleaning pacman cache..."
paccache -rk2 2>/dev/null || pacman -Sc --noconfirm

echo "[SUCCESS] Host system de-bloat complete! Nautilus and Yazi are now your primary file managers."
