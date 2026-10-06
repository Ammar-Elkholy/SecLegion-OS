# AE_ARCH Linux — Complete Installation & Setup Guide
### SecLegion Edition | Engineered by Ammar Elkholy

This guide takes you through the entire installation lifecycle of **AE_ARCH Linux** — from preparing your flash drive to your first boot into the SecLegion environment.

---

## 1. Prerequisites & Hardware Specifications

| Requirement | Minimum | Recommended | Notes |
|:---|:---|:---|:---|
| **USB Drive** | **8 GB** | 16 GB - 32 GB | 8 GB is completely sufficient; larger drives work just as well. |
| **RAM** | 4 GB | 8 GB+ | PipeWire, Hyprland, and GNOME run smoothly across memory tiers. |
| **Storage (Disk)** | 25 GB free | 50 GB - 100 GB+ | NVMe or SSD recommended for instantaneous boot times. |
| **Architecture** | 64-bit x86_64 | Multi-core Intel / AMD | Full KMS driver support for Intel, AMD Radeon, & NVIDIA GeForce/RTX. |
| **Firmware** | UEFI | UEFI (GPT) | Legacy BIOS is supported, but UEFI is strongly recommended. |

---

## 2. Preparing Your Installation Media

### A. Windows (Rufus or Ventoy)

#### Method 1: Rufus (Recommended)
1. Download [Rufus](https://rufus.ie/).
2. Insert your USB flash drive (8 GB or larger).
3. Select the `AE_ARCH` ISO file.
4. Set **Partition scheme** to **GPT** and **Target system** to **UEFI (non CSM)**.
5. Click **Start**. When prompted, choose **Write in DD Image mode**.
6. Wait for the process to complete.

#### Method 2: Ventoy (Multi-boot)
1. Install [Ventoy](https://www.ventoy.net/) onto your USB.
2. Drag and drop `AE_ARCH-*.iso` directly onto the USB partition.

---

### B. macOS (Terminal `dd`)

1. Open **Terminal**.
2. Identify your USB drive identifier:
   ```bash
   diskutil list
   ```
   *(Locate your external disk, e.g., `/dev/disk2` — never select your internal drive!)*
3. Unmount the disk:
   ```bash
   diskutil unmountDisk /dev/disk2
   ```
4. Flash the ISO using `dd` (use raw disk `rdisk` for high speed):
   ```bash
   sudo dd if=path/to/AE_ARCH-*.iso of=/dev/rdisk2 bs=4m status=progress
   ```
5. Eject when finished:
   ```bash
   diskutil eject /dev/disk2
   ```

---

### C. Linux (Terminal `dd`)

1. Plug in your USB drive and find its block name:
   ```bash
   lsblk
   ```
   *(Verify your device name, e.g., `/dev/sdb` or `/dev/sdc`)*
2. Flash the ISO:
   ```bash
   sudo dd if=AE_ARCH-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
   ```
   *(Replace `/dev/sdX` with your exact USB device)*

---

## 3. BIOS / UEFI Configuration

Before booting the USB, enter your computer's BIOS/UEFI setup (typically by pressing `F2`, `F12`, `Del`, or `Esc` during startup):

1. **Disable Secure Boot**: Arch Linux custom live kernels require Secure Boot disabled.
2. **SATA Controller**: Set to **AHCI** mode (do not use RAID or Intel RST).
3. **Fast Startup / Fast Boot**: Disable in BIOS (and inside Windows if dual-booting).
4. **Boot Priority**: Move USB to the top of the boot order, or select it directly via your motherboard's one-time boot menu (`F12` / `F11` / `F8`).

---

## 4. Booting into AE_ARCH

When your system boots from the USB, you will see the **SecLegion Cyber Boot Menu** (neon cyan `#00f0ff` & green `#00ff88` matrix styling):

```
┌────────────────────────────────────────────────────────────────────────┐
│   AE_ARCH Linux — Developed by Ammar Elkholy (SecLegion Edition)      │
└────────────────────────────────────────────────────────────────────────┘
  ▶ Boot AE_ARCH Linux (Universal: AMD / Intel / NVIDIA)
    Boot AE_ARCH Linux (NVIDIA Proprietary Driver Fallback)
    Boot AE_ARCH Linux (Safe Graphics / nomodeset)
    Run Memtest86+ (RAM Diagnostics)
    Reboot into Firmware Setup (UEFI)
```

- Select the **Default option** for virtually all machines (including hybrid graphics laptops).
- Select **NVIDIA Fallback** if your dedicated GPU requires early KMS modesetting.

---

## 5. The SecLegion Live Environment

Once booted, you land directly in the live environment.

### Connect to the Internet
An active internet connection is recommended during setup:
- **Graphical Wi-Fi**: Click the network icon in the top panel or Waybar.
- **Terminal Wi-Fi**: Open a terminal and run:
  ```bash
  nmtui
  ```
  Select your SSID, type your password, and connect.
- **Verify connection**:
  ```bash
  ping -c 2 1.1.1.1
  ```

### Launch the Installer
You have two ways to start the installation:
1. **Desktop Launcher**: Double-click **Install AE_ARCH Linux** on the desktop or launch it from the application menu.
2. **Terminal Helper**: Run:
   ```bash
   Installation_guide
   ```
   or launch directly:
   ```bash
   sudo -E calamares
   ```

---

## 6. Step-by-Step Calamares Installation Walkthrough

The installer features custom SecLegion dark matrix styling and an interactive slideshow.

### Step 1: Welcome Screen
- Select your primary installation language.
- Calamares verifies internet connectivity, storage space, and power connection.
- Click **Next**.

### Step 2: Location & Timezone
- Click your country/city on the world map or select your Region and Zone.
- This configures your system clock and timezone (`timedatectl`).

### Step 3: Keyboard Layout
- Choose your keyboard model and primary layout (e.g., English US).
- If you use Arabic or European layouts, test keys in the preview box. You can easily switch or add layouts post-install.

### Step 4: Partitioning & Disk Setup

You have two main paths:

#### Option A: Erase Disk (Dedicated System)
- Recommended if AE_ARCH will be the only OS on the drive.
- Calamares automatically creates:
  - `EFI System Partition` (`/boot/efi`, FAT32, ~512MB)
  - `Root Partition` (`/`, ext4 or btrfs)
  - `Swap space` (or swapfile)
- Select whether you want disk encryption (LUKS).

#### Option B: Manual Partitioning (Dual Boot with Windows)
- If you are installing alongside Windows:
  1. **Existing EFI Partition**: Locate the Windows EFI partition (FAT32, usually ~100MB-500MB). Assign mount point `/boot/efi` (do **NOT** format it).
  2. **Root Partition (`/`)**: Select your unallocated free space (created by shrinking Windows in Disk Management). Create a new partition:
     - File System: `ext4` or `btrfs`
     - Mount Point: `/`
     - Size: At least 30 GB (50 GB+ recommended).
  3. **Swap**: (Optional) 4 GB - 8 GB swap partition, or rely on systemd-zram post-install.

> **Caution:** Always back up your important Windows files before modifying partition tables.

### Step 5: User & Machine Identity
Configure your system credentials:
- **What is your name?**: Your display name (e.g., `Ammar Elkholy`).
- **What name do you want to use to log in?**: Your UNIX username (e.g., `ammar`).
- **What is the name of this computer?**: Your hostname (e.g., `seclegion-arch` or `ae-laptop`).
- **Choose a password**: Set your login password.
- Check **"Use the same password for the administrator account"** (enables `sudo`).
- Choose whether to enable automatic login.

### Step 6: Summary & Execution
- Calamares presents a final confirmation checklist showing all disk changes.
- Click **Install Now**.
- Watch the SecLegion presentation slides highlighting:
  - Dual Desktop workflow (GNOME + Hyprland)
  - GPU-accelerated Kitty terminal & cybersecurity HUD
  - PipeWire hi-fi audio engine
  - Universal multi-GPU switching

### Step 7: Completion
- When the progress bar hits 100%, check **Restart now** and click **Done**.
- Remove your USB drive when the screen prompts you, then press Enter.

---

## 7. First Boot & SecLegion Onboarding

1. **Display Manager (GDM)**:
   - Select your username and enter your password.
   - Click the gear icon in the bottom-right corner to pick your desktop:
     - **Hyprland**: Tiling Wayland compositor with custom Waybar, Rofi, SwayNC, and neon aesthetics.
     - **GNOME**: Polished, modern desktop environment.

2. **Automated Setup Wizard (`ae-welcome.sh`)**:
   - On your very first login, Kitty automatically launches the **SecLegion Setup Wizard**:
     - Hostname confirmation
     - Timezone and locale validation
     - Git identity (name & email)
     - SSH key creation (`ed25519`)
     - Wallpaper selection
     - AUR helper (`yay`) installation
   - Skip any step with Enter or complete them on the spot.

---

## 8. Post-Install Personalization

To further tailor your keybinds, display scaling, dotfiles, and terminal appearance:
- Read the dedicated personalization guide:
  ```bash
  cat ~/SETUP.md
  ```
  *(or view [SETUP.md](file:///home/aelkholy/Dev_Lab/AE_ARCH/SETUP.md))*

---

## 9. Troubleshooting & Edge Cases

| Issue | Cause | Solution |
|:---|:---|:---|
| **Black screen on boot (NVIDIA)** | Early KMS missing or Wayland lock | In GRUB, press `e` and append `nvidia_drm.modeset=1` to the linux kernel line. |
| **Wi-Fi device not recognized** | Missing proprietary firmware | Check `lspci -k` / `lsusb`. For Broadcom, install `broadcom-wl-dkms`. For Intel, install `linux-firmware`. |
| **Windows time offset (Dual Boot)** | Windows uses local time, Linux uses UTC | In AE_ARCH run: `timedatectl set-local-rtc 1 --adjust-system-clock` |
| **Calamares installer crash** | Insufficient live RAM or bad media | Check log: `cat ~/.cache/calamares/calamares.log`. Re-flash USB in DD mode. |
| **Scratchpad window hidden** | Window sent to special workspace | Press `Super + S` to show scratchpad, and `Super + Z` to pull it back to current workspace. |

---

*Engineered with precision by Ammar Elkholy — SecLegion Edition.*
