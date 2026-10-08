#!/usr/bin/env bash
# =============================================================================
# ae-welcome.sh — SecLegion OS First-Login Setup Wizard
# SecLegion Edition | Ammar Elkholy
# Runs once automatically on first login, guides the user through setup
# =============================================================================

DONE_FLAG="$HOME/.config/.ae-welcome-done"
[[ -f "$DONE_FLAG" ]] && exit 0

# ── Colors ────────────────────────────────────────────────────────────────────
C_RESET='\033[0m'
C_CYAN='\033[38;2;0;240;255m'
C_GREEN='\033[38;2;0;255;136m'
C_BLUE='\033[38;2;88;166;255m'
C_WHITE='\033[1;37m'
C_DIM='\033[2;37m'
C_YELLOW='\033[38;2;255;200;0m'
C_RED='\033[38;2;255;60;100m'

# ── Banner ────────────────────────────────────────────────────────────────────
banner() {
    clear
    echo
    echo -e "${C_CYAN} ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄${C_RESET}"
    echo -e "${C_CYAN} █${C_GREEN}  ██████ ███████  ██████     ${C_CYAN}SECLEGION OS  █${C_RESET}"
    echo -e "${C_CYAN} █${C_GREEN}  ██     ██      ██          ${C_CYAN}SecLegion Ed.  █${C_RESET}"
    echo -e "${C_CYAN} █${C_GREEN}  ███████ █████  ██          ${C_DIM}by Ammar Elkholy${C_CYAN} █${C_RESET}"
    echo -e "${C_CYAN} █${C_GREEN}       ██ ██     ██                         █${C_RESET}"
    echo -e "${C_CYAN} █${C_GREEN}  ███████ ███████  ██████                   █${C_RESET}"
    echo -e "${C_CYAN} ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀${C_RESET}"
    echo
}

# ── Step header ───────────────────────────────────────────────────────────────
step() {
    local num="$1" title="$2"
    echo
    echo -e "${C_CYAN}  ┌──────────────────────────────────────────┐${C_RESET}"
    echo -e "${C_CYAN}  │${C_GREEN}  STEP ${num} ${C_WHITE}— ${title}${C_CYAN}$(printf '%*s' $((39 - ${#title} - ${#num} - 8)) '')│${C_RESET}"
    echo -e "${C_CYAN}  └──────────────────────────────────────────┘${C_RESET}"
    echo
}

info()    { echo -e "  ${C_BLUE}→${C_RESET} $*"; }
success() { echo -e "  ${C_GREEN}✓${C_RESET} $*"; }
warn()    { echo -e "  ${C_YELLOW}!${C_RESET} $*"; }
ask()     { echo -en "  ${C_CYAN}?${C_RESET} $* "; }

# ── Main ──────────────────────────────────────────────────────────────────────
banner
echo -e "  ${C_WHITE}Welcome to SecLegion OS Linux.${C_RESET}"
echo -e "  ${C_DIM}This wizard runs once to help you personalize your system.${C_RESET}"
echo -e "  ${C_DIM}Press Enter to skip any step you want to do later.${C_RESET}"
echo
ask "Press Enter to begin..."; read -r

# ── STEP 1 — Hostname ─────────────────────────────────────────────────────────
banner
step "1/6" "Hostname — Your Machine's Identity"
info "This is the name that appears in your terminal prompt and on the network."
info "Current hostname: ${C_WHITE}$(hostnamectl hostname)${C_RESET}"
echo
ask "Enter new hostname (leave blank to keep current):"; read -r NEW_HOSTNAME

if [[ -n "$NEW_HOSTNAME" ]]; then
    sudo hostnamectl set-hostname "$NEW_HOSTNAME"
    # Update /etc/hosts
    if grep -q "127.0.1.1" /etc/hosts; then
        sudo sed -i "s/127.0.1.1.*/127.0.1.1\t${NEW_HOSTNAME}/" /etc/hosts
    else
        echo "127.0.1.1	${NEW_HOSTNAME}" | sudo tee -a /etc/hosts > /dev/null
    fi
    success "Hostname set to: ${C_WHITE}${NEW_HOSTNAME}${C_RESET}"
else
    info "Skipped — keeping: ${C_WHITE}$(hostnamectl hostname)${C_RESET}"
fi

# ── STEP 2 — Timezone ─────────────────────────────────────────────────────────
banner
step "2/6" "Timezone"
info "Current timezone: ${C_WHITE}$(timedatectl show --property=Timezone --value)${C_RESET}"
info "Common options: Africa/Cairo  |  Europe/London  |  America/New_York  |  Asia/Dubai"
echo
ask "Enter your timezone (leave blank to keep current):"; read -r NEW_TZ

if [[ -n "$NEW_TZ" ]]; then
    if timedatectl set-timezone "$NEW_TZ" 2>/dev/null; then
        sudo timedatectl set-ntp true
        success "Timezone set to: ${C_WHITE}${NEW_TZ}${C_RESET}"
    else
        warn "Invalid timezone. Skipped. (Run: timedatectl list-timezones)"
    fi
else
    info "Skipped — keeping: ${C_WHITE}$(timedatectl show --property=Timezone --value)${C_RESET}"
fi

# ── STEP 3 — Git Identity ─────────────────────────────────────────────────────
banner
step "3/6" "Git Identity"
info "Your name and email will appear on all your git commits."
CURRENT_GIT_NAME=$(git config --global user.name 2>/dev/null || echo "")
CURRENT_GIT_EMAIL=$(git config --global user.email 2>/dev/null || echo "")
[[ -n "$CURRENT_GIT_NAME" ]]  && info "Current name:  ${C_WHITE}${CURRENT_GIT_NAME}${C_RESET}"
[[ -n "$CURRENT_GIT_EMAIL" ]] && info "Current email: ${C_WHITE}${CURRENT_GIT_EMAIL}${C_RESET}"
echo
ask "Your full name (leave blank to skip):"; read -r GIT_NAME
ask "Your email address (leave blank to skip):"; read -r GIT_EMAIL

[[ -n "$GIT_NAME" ]]  && git config --global user.name "$GIT_NAME"  && success "Git name set."
[[ -n "$GIT_EMAIL" ]] && git config --global user.email "$GIT_EMAIL" && success "Git email set."
[[ -z "$GIT_NAME" && -z "$GIT_EMAIL" ]] && info "Skipped."

# ── STEP 4 — SSH Key ──────────────────────────────────────────────────────────
banner
step "4/6" "SSH Key"
if [[ -f "$HOME/.ssh/id_ed25519.pub" ]]; then
    info "An SSH key already exists."
    success "Public key: ${C_DIM}$(cat ~/.ssh/id_ed25519.pub | cut -c1-60)...${C_RESET}"
else
    info "No SSH key found. Generating one is recommended for GitHub, servers, etc."
    echo
    ask "Generate a new ed25519 SSH key? (y/N):"; read -r DO_SSH
    if [[ "${DO_SSH,,}" == "y" ]]; then
        ask "Email for SSH key (used as label):"; read -r SSH_EMAIL
        SSH_EMAIL="${SSH_EMAIL:-${GIT_EMAIL:-${USER}@$(hostnamectl hostname)}}"
        ssh-keygen -t ed25519 -C "$SSH_EMAIL" -f "$HOME/.ssh/id_ed25519" -N ""
        eval "$(ssh-agent -s)" > /dev/null
        ssh-add "$HOME/.ssh/id_ed25519" 2>/dev/null
        echo
        success "SSH key generated."
        echo
        echo -e "  ${C_YELLOW}Your public key (copy this to GitHub / servers):${C_RESET}"
        echo
        echo -e "  ${C_DIM}$(cat ~/.ssh/id_ed25519.pub)${C_RESET}"
        echo
        ask "Press Enter to continue..."; read -r
    else
        info "Skipped."
    fi
fi

# ── STEP 5 — Wallpaper ────────────────────────────────────────────────────────
banner
step "5/6" "Wallpaper"
info "Wallpapers are stored in ~/Pictures/Wallpapers/ and /usr/share/backgrounds/"
info "In Hyprland: press  ${C_WHITE}Super + Shift + W${C_RESET}  to pick a wallpaper via Yazi"
info "In Hyprland: press  ${C_WHITE}Super + Ctrl + W${C_RESET}   to set a live/animated wallpaper"
info "In GNOME: right-click desktop → Change Background"
echo
ask "Press Enter to continue..."; read -r

# ── STEP 6 — AUR Helper (yay) ─────────────────────────────────────────────────
banner
step "6/6" "AUR Helper (yay)"
if command -v yay &>/dev/null; then
    success "yay is already installed."
else
    info "yay lets you install community packages from the AUR (Arch User Repository)."
    info "Most third-party software lives there: Discord, VS Code, Spotify, etc."
    echo
    ask "Install yay now? (y/N):"; read -r DO_YAY
    if [[ "${DO_YAY,,}" == "y" ]]; then
        info "Cloning yay..."
        git clone https://aur.archlinux.org/yay.git /tmp/yay-install 2>/dev/null \
            && cd /tmp/yay-install \
            && makepkg -si --noconfirm \
            && success "yay installed. Use: yay -S <package-name>" \
            || warn "Build failed. Check your internet connection and try manually."
        cd "$HOME"
    else
        info "Skipped. To install later:"
        echo -e "  ${C_DIM}git clone https://aur.archlinux.org/yay.git /tmp/yay${C_RESET}"
        echo -e "  ${C_DIM}cd /tmp/yay && makepkg -si${C_RESET}"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
banner
echo -e "  ${C_GREEN}All done.${C_RESET} Your system is personalized and ready."
echo
echo -e "  ${C_WHITE}Quick reference:${C_RESET}"
echo -e "  ${C_DIM}› Full setup guide:${C_RESET}  ${C_CYAN}cat ~/SETUP.md${C_RESET}"
echo -e "  ${C_DIM}› Keybinds:${C_RESET}          ${C_CYAN}Super + D${C_RESET} to launch anything"
echo -e "  ${C_DIM}› Wallpaper:${C_RESET}         ${C_CYAN}Super + Shift + W${C_RESET}"
echo -e "  ${C_DIM}› Lock screen:${C_RESET}       ${C_CYAN}Super + Shift + L${C_RESET}"
echo -e "  ${C_DIM}› Power menu:${C_RESET}        ${C_CYAN}Super + Escape${C_RESET}"
echo -e "  ${C_DIM}› Notifications:${C_RESET}     ${C_CYAN}Super + N${C_RESET}"
echo
echo -e "  ${C_DIM}Engineered by Ammar Elkholy — SecLegion Edition${C_RESET}"
echo

# Mark as done
touch "$DONE_FLAG"
ask "Press Enter to close..."; read -r
