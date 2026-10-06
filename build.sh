#!/usr/bin/env bash
# ==============================================================================
# AE_ARCH — Universal Bootable ISO Builder
# Target: Any Laptop (AMD Radeon, Intel, or NVIDIA GeForce/RTX Hybrid)
# Desktops: GNOME + Hyprland Dual Experience with Calamares Installer
# ==============================================================================

set -euo pipefail

# ANSI Colors
CYAN="\033[1;36m"
GREEN="\033[1;32m"
BLUE="\033[1;34m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_error() { echo -e "${RED}[ERROR]${RESET} $1"; }

if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root: sudo bash build.sh"
   exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/ae-arch-work"
OUT_DIR="$SCRIPT_DIR/output"

echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN}    AE_ARCH Linux — Building Universal Bootable ISO                ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"

# 1. Install archiso if missing
if ! command -v mkarchiso &>/dev/null; then
    log_info "Installing archiso..."
    pacman -S --needed --noconfirm archiso
fi

# 2. Prepare Output Directory
mkdir -p "$OUT_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

log_info "Profile directory: $SCRIPT_DIR"
log_info "Work directory:    $WORK_DIR"
log_info "Output directory:  $OUT_DIR"

# 3. Clean permissions for airootfs
log_info "Ensuring correct permissions in airootfs..."
chmod 755 "$SCRIPT_DIR/airootfs"
find "$SCRIPT_DIR/airootfs/etc/skel" -type d -exec chmod 755 {} +
find "$SCRIPT_DIR/airootfs/etc/skel" -type f -exec chmod 644 {} +
find "$SCRIPT_DIR/airootfs/etc/skel" -name "*.sh" -exec chmod 755 {} +

# 4. Run mkarchiso
log_info "Executing mkarchiso build..."
mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" "$SCRIPT_DIR"

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} ✅ AE_ARCH ISO BUILT SUCCESSFULLY!                                ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"

ISO_FILE=$(ls -t "$OUT_DIR"/AE_ARCH-*.iso 2>/dev/null | head -n1 || true)
if [[ -n "$ISO_FILE" ]]; then
    echo -e " ISO File:       ${GREEN}${ISO_FILE}${RESET}"
    echo -e " File Size:      $(du -h "$ISO_FILE" | cut -f1)"
    echo -e " Generating SHA256 checksum..."
    sha256sum "$ISO_FILE" | tee "$ISO_FILE.sha256"
    echo -e "\n ${YELLOW}Burn to a 32GB USB Drive:${RESET}"
    echo -e "   sudo dd if=${ISO_FILE} of=/dev/sdX bs=4M status=progress oflag=sync"
    echo -e "   (Replace /dev/sdX with your USB drive letter)"
fi
echo -e "${CYAN}====================================================================${RESET}"
