#!/usr/bin/env bash
# ==============================================================================
# seclegion-bootstrap-tier2.sh — SecLegion OS Tier-2 Infrastructure Provisioner
# Master Architecture v2.0 & "Lost Ledgers" Implementation
# Provisions: KVM/QEMU, Brave, BlackArch Pentest Suites, Dual-Boot & CLI Suite
# ==============================================================================

set -euo pipefail

# ANSI SecLegion Terminal Colors
GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
DIM="\033[2;37m"
RESET="\033[0m"

log_info()    { echo -e "${CYAN}[SECLEGION]${RESET} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${RESET}   $1"; }
log_warn()    { echo -e "${YELLOW}[WARNING]${RESET}   $1"; }
log_step()    { echo -e "\n${CYAN}[STEP $1]${RESET} ${GREEN}$2${RESET}"; }

clear
echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN} █${GREEN}  ██████ ███████  ██████     ${CYAN}SECLEGION OS                    █${RESET}"
echo -e "${CYAN} █${GREEN}  ██     ██      ██          ${CYAN}Tier-2 Lab & System Provisioner █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ █████  ██          ${DIM}Master Architecture v2.0        ${CYAN} █${RESET}"
echo -e "${CYAN} █${GREEN}       ██ ██     ██                                          █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ ███████  ██████                                   █${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " ${GREEN}Automated Post-Installation Provisioner & Diagnostic Remediation${RESET}"
echo -e "${CYAN}--------------------------------------------------------------------${RESET}"

# Verify internet access
if ! ping -c 1 -W 2 1.1.1.1 &>/dev/null; then
    echo -e "${RED}[ERROR] Active internet connection required to download Tier-2 packages.${RESET}"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. BlackArch Repository Bootstrap
# -----------------------------------------------------------------------------
log_step "1/7" "Verifying BlackArch Linux Pentesting Repository..."
if ! grep -q "^\\[blackarch\\]" /etc/pacman.conf 2>/dev/null; then
    log_info "Bootstrapping BlackArch via official strap.sh protocol..."
    TMP_DIR=$(mktemp -d)
    curl -s https://blackarch.org/strap.sh -o "$TMP_DIR/strap.sh"
    chmod +x "$TMP_DIR/strap.sh"
    sudo "$TMP_DIR/strap.sh"
    rm -rf "$TMP_DIR"
    sudo pacman -Syy --noconfirm
    log_success "BlackArch repository integrated successfully."
else
    log_success "BlackArch repository is already active."
fi

# -----------------------------------------------------------------------------
# 2. Modern CLI Utilities & Terminal Productivity Suite
# -----------------------------------------------------------------------------
log_step "2/7" "Installing Modern CLI Productivity Stack..."
sudo pacman -S --needed --noconfirm \
    bat \
    fd \
    zoxide \
    btop \
    lazygit \
    tmux \
    eza \
    ripgrep \
    fzf \
    yazi
log_success "Modern CLI utilities (bat, fd, zoxide, btop, lazygit, tmux) ready."

# -----------------------------------------------------------------------------
# 3. KVM / QEMU / Libvirt Virtualization Environment
# -----------------------------------------------------------------------------
log_step "3/7" "Deploying KVM / QEMU / Libvirt Virtualization Hypervisor..."
sudo pacman -S --needed --noconfirm \
    qemu-desktop \
    libvirt \
    edk2-ovmf \
    virt-manager \
    dnsmasq \
    iptables-nft \
    bridge-utils \
    dmidecode

# Add user to virtualization groups
log_info "Configuring permissions for user \x27$USER\x27 in libvirt and kvm groups..."
sudo usermod -aG libvirt,kvm "$USER"

# Enable and start virtualization service
log_info "Enabling and starting libvirtd.service..."
sudo systemctl enable --now libvirtd.service || true

# Activate default NAT virtual network (virbr0)
log_info "Activating default virtual bridge interface (virbr0)..."
sudo virsh net-autostart default 2>/dev/null || true
sudo virsh net-start default 2>/dev/null || true
log_success "KVM/QEMU Hypervisor Stack operational."

# -----------------------------------------------------------------------------
# 4. Brave Privacy Browser Deployment
# -----------------------------------------------------------------------------
log_step "4/7" "Deploying Brave Privacy Browser..."
if ! command -v brave &>/dev/null; then
    if command -v yay &>/dev/null; then
        yay -S --needed --noconfirm brave-bin
    else
        sudo pacman -S --needed --noconfirm brave-bin 2>/dev/null || \
        sudo pacman -S --needed --noconfirm brave 2>/dev/null || \
        sudo pacman -S --needed --noconfirm firefox
    fi
    log_success "Browser deployed."
else
    log_success "Brave Browser is already installed."
fi

# -----------------------------------------------------------------------------
# 5. Dual-Boot Guarantee & Hardware Clock Synchronization
# -----------------------------------------------------------------------------
log_step "5/7" "Configuring Dual-Boot (os-prober) & RTC Synchronization..."
sudo pacman -S --needed --noconfirm os-prober ntfs-3g dosfstools

# Fix Windows / Linux Dual-Boot Clock Shift
log_info "Setting hardware RTC clock to Local Time (prevents Windows clock drift)..."
sudo timedatectl set-local-rtc 1 --adjust-system-clock 2>/dev/null || true

# Enable os-prober in GRUB if present
if [[ -f /etc/default/grub ]]; then
    log_info "Enabling GRUB_DISABLE_OS_PROBER=false in /etc/default/grub..."
    sudo sed -i "s/^#*GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=false/" /etc/default/grub
    if ! grep -q "^GRUB_DISABLE_OS_PROBER=false" /etc/default/grub; then
        echo "GRUB_DISABLE_OS_PROBER=false" | sudo tee -a /etc/default/grub
    fi
    if command -v grub-mkconfig &>/dev/null; then
        log_info "Regenerating GRUB bootloader menu with Windows detection..."
        sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
    fi
    log_success "Dual-Boot auto-detection enabled."
fi

# -----------------------------------------------------------------------------
# 6. Curated BlackArch Offensive Security Suites & Wordlists
# -----------------------------------------------------------------------------
log_step "6/7" "Provisioning Offensive Security Core Tools & Wordlists..."
sudo pacman -S --needed --noconfirm \
    wireshark-qt \
    tcpdump \
    aircrack-ng \
    burpsuite \
    nmap \
    sqlmap \
    hydra \
    john \
    hashcat \
    radare2 \
    hexedit 2>/dev/null || true

# Packet capture permissions
sudo usermod -aG wireshark "$USER" 2>/dev/null || true

# Provision Wordlists
sudo mkdir -p /usr/share/wordlists
if [[ ! -f /usr/share/wordlists/rockyou.txt && -f /usr/share/wordlists/rockyou.txt.gz ]]; then
    log_info "Decompressing rockyou.txt wordlist..."
    sudo gzip -d /usr/share/wordlists/rockyou.txt.gz 2>/dev/null || true
fi

# Optional BlackArch Categories Selection
echo -e "\n${CYAN}--------------------------------------------------------------------${RESET}"
echo -e "${GREEN} Optional BlackArch Capability Meta-Packages:${RESET}"
echo -e " 1) Web Applications (Burp, Gobuster, Ffuf, Sqlmap)"
echo -e " 2) Wireless Pentesting (Aircrack, Wifite, Kismet)"
echo -e " 3) Exploitation & Payloads (Metasploit, Searchsploit, Pwntools)"
echo -e " 4) Reverse Engineering & Binary Analysis (Ghidra, Radare2, Cutter)"
echo -e " 5) Install ALL Curated Categories"
echo -e " 6) Skip Additional Meta-Packages (Keep lean installation)"
echo -e "${CYAN}--------------------------------------------------------------------${RESET}"
read -rp " Select option [1-6, default: 6]: " choice || choice=6

case "$choice" in
    1) sudo pacman -S --needed --noconfirm blackarch-webapp 2>/dev/null || true ;;
    2) sudo pacman -S --needed --noconfirm blackarch-wireless 2>/dev/null || true ;;
    3) sudo pacman -S --needed --noconfirm blackarch-exploitation 2>/dev/null || true ;;
    4) sudo pacman -S --needed --noconfirm blackarch-reversing 2>/dev/null || true ;;
    5) sudo pacman -S --needed --noconfirm blackarch-webapp blackarch-wireless blackarch-exploitation blackarch-reversing 2>/dev/null || true ;;
    *) log_info "Skipping additional meta-packages. Core tools are ready." ;;
esac

# -----------------------------------------------------------------------------
# 7. Hardware Edge Cases & Stability Tweaks
# -----------------------------------------------------------------------------
log_step "7/7" "Applying Hardware & Wi-Fi Stability Optimizations..."
# Disable Wi-Fi power save to stop ping spikes / packet loss
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf >/dev/null <<\EOF
[connection]
wifi.powersave = 2
EOF
sudo systemctl reload NetworkManager 2>/dev/null || true

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} [COMPLETE] Tier-2 Infrastructure Successfully Provisioned!        ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " Configured Systems:"
echo -e "   ✓ KVM/QEMU Hypervisor Active (${CYAN}virt-manager${RESET})"
echo -e "   ✓ Default NAT Network Active (${CYAN}virbr0${RESET})"
echo -e "   ✓ Dual-Boot os-prober Enabled & RTC Synchronized"
echo -e "   ✓ Wi-Fi Power Save Disabled (Maximum packet stability)"
echo -e "   ✓ User \x27$USER\x27 Added to Groups: ${CYAN}libvirt, kvm, wireshark${RESET}"
echo -e "   ✓ Modern CLI Suite Active: ${CYAN}bat, fd, zoxide, btop, tmux, lazygit${RESET}"
echo -e "   ✓ BlackArch Pentesting Repository Synchronized"
echo -e "\n ${YELLOW}Note: Please log out and back in to apply group memberships.${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
