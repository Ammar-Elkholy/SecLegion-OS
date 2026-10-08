#!/usr/bin/env bash
# ==============================================================================
# SecLegion OS — Universal Offensive Security ISO Builder
# Engineered by: Ammar Elkholy (SecLegion Edition)
# Target: Any Laptop (AMD Radeon, Intel, or NVIDIA GeForce/RTX Hybrid)
# Desktops: GNOME + Hyprland Dual Experience with Calamares Installer
# Edge Cases Handled: Disk-backed workdir (No RAM /tmp exhaustion), Multi-GPU KMS
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $EUID -eq 0 ]]; then
    WORK_DIR="/var/tmp/seclegion-build-work"
else
    WORK_DIR="/var/tmp/seclegion-build-work"
fi
OUT_DIR="$SCRIPT_DIR/output"

echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN}    SecLegion OS — Building Universal Offensive Security ISO         ${RESET}"
echo -e "${CYAN}    Engineered by: Ammar Elkholy (SecLegion Edition)                ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"

# 1. Install archiso if missing
if ! command -v mkarchiso &>/dev/null; then
    if [[ $EUID -eq 0 ]]; then
        log_info "Installing archiso..."
        pacman -S --needed --noconfirm archiso
    else
        log_error "mkarchiso is missing. Please install it first with 'sudo pacman -S archiso'."
        exit 1
    fi
fi

# 2. Prepare Output & Work Directories
mkdir -p "$OUT_DIR"
if [[ -d "$WORK_DIR" ]]; then
    log_info "Cleaning work directory: $WORK_DIR"
    chmod -R u+rwx "$WORK_DIR" 2>/dev/null || true
    unshare --map-auto --map-root-user rm -rf "$WORK_DIR" 2>/dev/null || rm -rf "$WORK_DIR" || true
fi
mkdir -p "$WORK_DIR"

log_info "Profile directory: $SCRIPT_DIR"
log_info "Work directory:    $WORK_DIR (disk-backed on /var/tmp)"
log_info "Output directory:  $OUT_DIR"

# Host OS-Release synchronization hook (if permitted)
if [[ -f "$SCRIPT_DIR/airootfs/etc/os-release" ]]; then
    cp -f "$SCRIPT_DIR/airootfs/etc/os-release" /etc/os-release 2>/dev/null || true
fi

# 3. Privacy Sanitization Protocol
log_info "Executing privacy sanitization protocol..."
bash "$SCRIPT_DIR/sanitize_system.sh" "$SCRIPT_DIR/airootfs"

# 4. Clean permissions for airootfs
log_info "Ensuring correct permissions in airootfs..."
chmod 755 "$SCRIPT_DIR/airootfs"
find "$SCRIPT_DIR/airootfs/etc/skel" -type d -exec chmod 755 {} + 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/etc/skel" -type f -exec chmod 644 {} + 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/etc/skel" -name "*.sh" -exec chmod 755 {} + 2>/dev/null || true
chmod 750 "$SCRIPT_DIR/airootfs/root" 2>/dev/null || true
chmod 755 "$SCRIPT_DIR/airootfs/usr/local/bin"/* 2>/dev/null || true
chmod -R 755 "$SCRIPT_DIR/airootfs/usr/share/applications" 2>/dev/null || true
chmod 400 "$SCRIPT_DIR/airootfs/etc/shadow" "$SCRIPT_DIR/airootfs/etc/gshadow" 2>/dev/null || true
chmod 440 "$SCRIPT_DIR/airootfs/etc/sudoers.d"/* 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/home/seclegion" -type d -exec chmod 755 {} + 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/home/seclegion" -type f -exec chmod 644 {} + 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/home/seclegion" -name "*.sh" -exec chmod 755 {} + 2>/dev/null || true
find "$SCRIPT_DIR/airootfs/home/seclegion" -name "*.desktop" -exec chmod 755 {} + 2>/dev/null || true

# 5. Run mkarchiso
log_info "Executing mkarchiso build..."
mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" "$SCRIPT_DIR"

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} ✅ SECLEGION OS ISO BUILT SUCCESSFULLY!                           ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"

ISO_FILE=$(ls -t "$OUT_DIR"/SecLegion-OS-*.iso 2>/dev/null | head -n1 || true)
if [[ -n "$ISO_FILE" ]]; then
    echo -e " ISO File:       ${GREEN}${ISO_FILE}${RESET}"
    echo -e " File Size:      $(du -h "$ISO_FILE" | cut -f1)"
    echo -e " Generating SHA256 checksum..."
    sha256sum "$ISO_FILE" | tee "$ISO_FILE.sha256"
fi
echo -e "${CYAN}====================================================================${RESET}"
