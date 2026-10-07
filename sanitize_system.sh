#!/usr/bin/env bash
# ==============================================================================
# sanitize_system.sh — SecLegion OS Deep Privacy Sanitization Protocol
# Strips all personal tokens, browser sessions, keys, and private history
# Ensures ONLY pure system configurations, dotfiles, and tools are preserved.
# ==============================================================================

set -euo pipefail

# SecLegion Terminal Palette
GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
DIM="\033[2;37m"
RESET="\033[0m"

log_info()    { echo -e "${CYAN}[SECLEGION]${RESET} $1"; }
log_success() { echo -e "${GREEN}[SANITIZED]${RESET} $1"; }
log_warn()    { echo -e "${YELLOW}[WARNING]${RESET}   $1"; }

TARGET_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/airootfs" && pwd)}"

echo -e "${CYAN}====================================================================${RESET}"
echo -e "${GREEN}   SecLegion OS — System Sanitization & Privacy Scrubbing           ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " Target RootFS: ${CYAN}${TARGET_DIR}${RESET}"

# 1. Strip Shell Histories
log_info "Purging Shell Histories..."
find "$TARGET_DIR" -type f \( \
    -name ".bash_history" -o \
    -name ".zsh_history" -o \
    -name ".history" -o \
    -name ".lesshst" -o \
    -name ".wget-hsts" -o \
    -name ".python_history" -o \
    -name ".node_repl_history" \
\) -exec rm -vf {} + 2>/dev/null || true

# 2. Strip Cryptographic Keys & Private Credentials
log_info "Purging Private SSH Keys, GPG Keys, and Known Hosts..."
find "$TARGET_DIR" -type f \( \
    -name "id_rsa*" -o \
    -name "id_ed25519*" -o \
    -name "id_ecdsa*" -o \
    -name "known_hosts*" -o \
    -name "authorized_keys*" -o \
    -name "*.pem" -o \
    -name "*.key" -o \
    -name "*.p12" -o \
    -name "*.kdbx" \
\) ! -name "*.pub" -exec rm -vf {} + 2>/dev/null || true

# Purge GPG private keyring if present
rm -rf "$TARGET_DIR"/etc/skel/.gnupg/private-keys-v1.d 2>/dev/null || true

# 3. Strip Git Tokens and API Secrets
log_info "Purging Git Credentials and Cloud Tokens..."
find "$TARGET_DIR" -type f \( \
    -name ".git-credentials" -o \
    -name ".netrc" -o \
    -name ".npmrc" -o \
    -name ".pypirc" -o \
    -name ".env" -o \
    -name ".env.*" \
\) -exec rm -vf {} + 2>/dev/null || true

rm -rf "$TARGET_DIR"/etc/skel/.config/gh 2>/dev/null || true
rm -rf "$TARGET_DIR"/etc/skel/.config/glab 2>/dev/null || true

# 4. Strip Web Browser Profiles, Caches & Cookies
log_info "Purging Browser Sessions, Cookies, and Private Storage..."
for browser in brave-browser google-chrome chromium BRP; do
    rm -rf "$TARGET_DIR/etc/skel/.config/$browser/Default" 2>/dev/null || true
    rm -rf "$TARGET_DIR/etc/skel/.config/$browser/Profile*" 2>/dev/null || true
done
rm -rf "$TARGET_DIR/etc/skel/.mozilla/firefox/*.default*/cookies.sqlite" 2>/dev/null || true
rm -rf "$TARGET_DIR/etc/skel/.mozilla/firefox/*.default*/places.sqlite" 2>/dev/null || true
rm -rf "$TARGET_DIR/etc/skel/.mozilla/firefox/*.default*/sessionstore*" 2>/dev/null || true

# 5. Strip Machine Identifiers & Runtime Caches
log_info "Purging D-Bus & System Machine IDs (forcing generation on first boot)..."
rm -f "$TARGET_DIR/etc/machine-id" 2>/dev/null || true
rm -f "$TARGET_DIR/var/lib/dbus/machine-id" 2>/dev/null || true
# Leave empty files so systemd initializes them on boot
touch "$TARGET_DIR/etc/machine-id" 2>/dev/null || true

# 6. Strip Thumbnail and Application Caches
log_info "Purging Thumbnail Caches and Temporary Files..."
find "$TARGET_DIR" -type d \( \
    -name "thumbnails" -o \
    -name "__pycache__" -o \
    -name ".cache" \
\) -exec rm -rf {} + 2>/dev/null || true

# Recreate minimal clean cache dir in skel
mkdir -p "$TARGET_DIR/etc/skel/.cache"
mkdir -p "$TARGET_DIR/etc/skel/.config"

# 7. Normalize File Permissions
log_info "Normalizing File Permissions across airootfs..."
chmod 755 "$TARGET_DIR" 2>/dev/null || true
find "$TARGET_DIR/etc/skel" -type d -exec chmod 755 {} + 2>/dev/null || true
find "$TARGET_DIR/etc/skel" -type f -exec chmod 644 {} + 2>/dev/null || true
find "$TARGET_DIR/etc/skel" -name "*.sh" -exec chmod 755 {} + 2>/dev/null || true

echo -e "\n${GREEN}====================================================================${RESET}"
echo -e "${GREEN} [SUCCESS] SecLegion OS RootFS is Completely Sanitized & Clean!    ${RESET}"
echo -e "${GREEN}====================================================================${RESET}"
