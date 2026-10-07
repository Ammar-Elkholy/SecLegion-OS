# SecLegion OS — Installation Guide

> **"We develop Mindsets — Securing Minds & Systems."**  
> Author & Lead Architect: **Ammar Elkholy**  
> GitHub Repository: [https://github.com/Ammar-Elkholy/SecLegion-OS](https://github.com/Ammar-Elkholy/SecLegion-OS)

Welcome to **SecLegion OS**! This guide is designed to be crystal clear so you can get up and running in minutes.

---

## Quick Start: 3-Step Installation

### Step 1: Get the ISO
You have two easy choices:
- **🌐 Web Download:** Download `SecLegion-OS-*.iso` from [GitHub Releases](https://github.com/Ammar-Elkholy/SecLegion-OS/releases) or the community mirror.
- **🤖 Automated Build (1 Command):** If you are running Arch Linux:
  ```bash
  git clone https://github.com/Ammar-Elkholy/SecLegion-OS.git
  cd SecLegion-OS
  sudo bash build.sh
  ```
  *(The 3.7GB release ISO will compile cleanly into `./output/`)*

---

### Step 2: Put it on a USB Drive (8GB+)
Pick the tool that matches your computer:

- **Easiest Everywhere — Ventoy (Recommended):**
  1. Install [Ventoy](https://www.ventoy.net/) onto your USB drive.
  2. Drag and drop `SecLegion-OS-*.iso` directly onto the USB drive. Done!

- **On Windows — Rufus:**
  1. Open [Rufus](https://rufus.ie/).
  2. Select your USB drive and the `SecLegion-OS-*.iso` file.
  3. Set Partition scheme to **GPT** and Target system to **UEFI**.
  4. Click **Start** (choose *Write in DD Image mode* if prompted).

- **On Linux / macOS — Terminal `dd`:**
  ```bash
  sudo dd if=output/SecLegion-OS-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
  ```
  *(Replace `/dev/sdX` with your USB drive letter, e.g., `/dev/sdb`)*

---

### Step 3: Boot & Install (One-Click GUI)
1. Plug the USB into your PC and reboot.
2. Press your boot key (`F12`, `F11`, `F9`, or `Esc`) to open the Boot Menu and select your USB.
   > **Important:** Secure Boot must be disabled in your BIOS/UEFI settings.
3. Select **SecLegion OS** from the boot menu.
4. Once the live desktop loads, open the **Calamares GUI Installer**:
   - Double-click **"Install SecLegion OS"** on the desktop, or press `Super + Space` and search for installer.
5. Follow the visual wizard: pick your language, timezone, drive partition, and set your username and password.
6. Click **Install**. When done, reboot into your fresh SecLegion OS!

---

## Alternative Method: Install Without a USB Drive

Don't have a USB drive? If you already have Linux running and want to install SecLegion OS directly onto a secondary drive or partition:

```bash
# 1. Clone this repository
git clone https://github.com/Ammar-Elkholy/SecLegion-OS.git
cd SecLegion-OS

# 2. Run the offline installer as root
sudo bash install-from-existing.sh
```
Follow the interactive prompts to pick your target partition (`/dev/nvme0n1pX`), format it, copy the system, and register the UEFI bootloader automatically!

---

## 🤖 Automated Lab Bootstrap (Tier 2)

Out of the box, SecLegion OS is lightweight and blazing fast (Tier 1). When you're ready to deploy heavy pentesting labs, open a terminal and run:

```bash
seclegion-bootstrap-tier2.sh
```
This automatically sets up:
- **KVM/QEMU Hypervisor:** Hardware virtualization with `virt-manager` and `virbr0` NAT bridge.
- **OffSec Tools:** Burp Suite, Metasploit Framework, Wireshark (packet capture permissions pre-granted), and wordlists (`rockyou.txt`).
- **Brave Browser:** Privacy-hardened browser.
- **BlackArch Repository:** Synchronizes access to 2,800+ penetration testing tools.

---

## Dual-Booting with Windows: Quick Tips

1. **Fix Clock Drift (Sync Linux & Windows Time):**
   ```bash
   timedatectl set-local-rtc 1
   ```

2. **Auto-Detect Windows in GRUB Menu:**
   ```bash
   sudo pacman -S --needed os-prober
   sudo sed -i 's/#GRUB_DISABLE_OS_PROBER=false/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
   sudo grub-mkconfig -o /boot/grub/grub.cfg
   ```
