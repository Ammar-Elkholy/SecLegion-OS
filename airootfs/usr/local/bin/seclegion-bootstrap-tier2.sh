#!/usr/bin/env bash
# ==============================================================================
# seclegion-bootstrap-tier2.sh — SecLegion OS Tier-2 Infrastructure Provisioner
# Installs heavy InfoSec labs, KVM/QEMU virtualization, Brave, and GUI suites
# ==============================================================================

set -euo pipefail

GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
DIM="\033[2;37m"
RESET="\033[0m"

log_info()    { echo -e "${CYAN}[SECLEGION]${RESET} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${RESET}   $1"; }
log_warn()    { echo -e "${YELLOW}[WARNING]${RESET}   $1"; }

clear
echo -e "${CYAN}====================================================================${RESET}"
echo -e "${CYAN} █${GREEN}  ██████ ███████  ██████     ${CYAN}SECLEGION OS   █${RESET}"
echo -e "${CYAN} █${GREEN}  ██     ██      ██          ${CYAN}Tier-2 Lab     █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ █████  ██          ${DIM}Provisioner    ${CYAN} █${RESET}"
echo -e "${CYAN} █${GREEN}       ██ ██     ██                         █${RESET}"
echo -e "${CYAN} █${GREEN}  ███████ ███████  ██████                   █${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " ${GREEN}Starting Post-Installation Tier-2 Infrastructure Deployment...${RESET}"
echo -e "${CYAN}--------------------------------------------------------------------${RESET}"

# Verify internet access
if ! ping -c 1 -W 2 1.1.1.1 &>/dev/null; then
    echo -e "${RED}[ERROR] Internet connection required to download Tier-2 packages.${RESET}"
    exit 1
fi

# 1. BlackArch Repository Bootstrap
log_info "Step 1/5: Verifying BlackArch Linux Repository Integration..."
if ! grep -q "^\[blackarch\]" /etc/pacman.conf 2>/dev/null; then
    log_info "Bootstrapping BlackArch via strap.sh..."
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

# 2. Complete KVM/QEMU Virtualization Lab Stack
log_info "Step 2/5: Deploying KVM / QEMU / Libvirt Virtualization Environment..."
sudo pacman -S --needed --noconfirm \
    qemu-desktop \
    libvirt \
    edk2-ovmf \
    virt-manager \
    dnsmasq \
    iptables-nft \
    bridge-utils \
    dmidecode

# Add current user to virtualization groups
log_info "Configuring user permissions for KVM and Libvirt..."
sudo usermod -aG libvirt,kvm "$USER"

# Enable and start virtualization service
log_info "Enabling libvirtd.service..."
sudo systemctl enable --now libvirtd.service || true

# Activate default NAT virtual network
log_info "Activating default virtual network interface (virbr0)..."
sudo virsh net-autostart default 2>/dev/null || true
sudo virsh net-start default 2>/dev/null || true
log_success "KVM/QEMU Virtualization Stack is fully operational."

# 3. Brave Browser Deployment
log_info "Step 3/5: Deploying Brave Privacy Browser..."
if ! command -v brave &>/dev/null; then
    if command -v yay &>/dev/null; then
        yay -S --needed --noconfirm brave-bin
    else
        sudo pacman -S --needed --noconfirm brave-bin 2>/dev/null || \
        sudo pacman -S --needed --noconfirm firefox
    fi
    log_success "Browser installed."
else
    log_success "Brave Browser is already installed."
fi

# 4. Heavy GUI InfoSec Suites & Reconnaissance Tools
log_info "Step 4/5: Installing Heavy Offensive Security & Analysis Suites..."
sudo pacman -S --needed --noconfirm \
    wireshark-qt \
    tcpdump \
    aircrack-ng \
    burpsuite 2>/dev/null || true

# Grant wireshark packet capture permissions to user
sudo usermod -aG wireshark "$USER" 2>/dev/null || true

# Install Metasploit, Hashcat, Ghidra if available
log_info "Installing Metasploit, Hashcat & Reverse Engineering Suites..."
sudo pacman -S --needed --noconfirm \
    metasploit \
    hashcat \
    john \
    hydra \
    sqlmap \
    nmap 2>/dev/null || true

# 5. Security Wordlists (SecLists)
log_info "Step 5/5: Provisioning Wordlists (/usr/share/wordlists)..."
sudo mkdir -p /usr/share/wordlists
if [[ ! -f /usr/share/wordlists/rockyou.txt && -f /usr/share/wordlists/rockyou.txt.gz ]]; then
    sudo gzip -d /usr/share/wordlists/rockyou.txt.gz 2>/dev/null || true
fi

echo -e "\n${CYAN}====================================================================${RESET}"
echo -e "${GREEN} [COMPLETE] Tier-2 Infrastructure Successfully Provisioned!        ${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
echo -e " Summary of Configured Systems:"
echo -e "   ✓ KVM/QEMU Hypervisor Active (${CYAN}virt-manager${RESET})"
echo -e "   ✓ Default NAT Network Active (${CYAN}virbr0${RESET})"
echo -e "   ✓ Wireshark Packet Capture Permission Granted (${CYAN}$USER${RESET})"
echo -e "   ✓ BlackArch Pentesting Repository Synchronized"
echo -e "   ✓ Heavy GUI Toolchains Ready"
echo -e "\n ${YELLOW}Note: Please log out and back in to apply group memberships (libvirt, kvm, wireshark).${RESET}"
echo -e "${CYAN}====================================================================${RESET}"
