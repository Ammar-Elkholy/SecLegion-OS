# SecLegion OS — Step-by-Step Installation Guide

> **"We develop Mindsets — Securing Minds & Systems"**  
> Author & Lead Architect: **Ammar Elkholy**  
> Official Repository: [https://github.com/Ammar-Elkholy/SecLegion-OS](https://github.com/Ammar-Elkholy/SecLegion-OS)

This guide takes you through installing SecLegion OS step by step. Every command is ready to copy and paste, with only small values (like your USB drive letter) to adjust.

---

## What You Need Before Starting

1. **A USB Flash Drive:** 8 GB minimum (16 GB or 32 GB works great too).
   > **Warning:** Backup any files on this USB drive before proceeding. Writing the OS will erase the USB drive.
2. **The SecLegion OS ISO file:** Download `SecLegion-OS-*.iso` from the official repository or mirrors.
3. **Your Computer:** Intel or AMD 64-bit computer (NVIDIA GeForce/RTX and AMD Radeon GPUs are fully supported).

---

## Step 1: Flash the ISO to Your USB Drive

Choose your current operating system below:

---

### If You Are on Windows

#### Method A: Rufus (Step-by-Step Button Clicks)
1. Download [Rufus Portable](https://rufus.ie/) (no installation required).
2. Plug in your USB drive (8 GB+) and open Rufus.
3. Under **Device**, select your USB flash drive.
4. Next to **Boot selection**, click the **SELECT** button and pick the `SecLegion-OS-*.iso` file.
5. Under **Partition scheme**, select **GPT**.
6. Under **Target system**, verify it says **UEFI (non CSM)**.
7. Click the **START** button at the bottom.
8. A popup will ask for the write mode: select **Write in DD Image mode** and click **OK**.
9. A confirmation warning will appear: *"WARNING: ALL DATA ON DEVICE WILL BE DESTROYED"*. Click **OK**.
10. Wait 2 to 4 minutes until the progress bar reaches 100% and displays **READY** in green.
11. Click the **CLOSE** button. Your USB is ready!

#### Method B: Ventoy on Windows (Drag-and-Drop)
1. Download `ventoy-*-windows.zip` from [ventoy.net](https://www.ventoy.net/).
2. Extract the zip file, open the folder, and run `Ventoy2Disk.exe`.
3. Select your USB drive and click **Install** (confirm the warnings).
4. Open Windows File Explorer, open your USB drive, and drag and drop `SecLegion-OS-*.iso` directly into the USB drive. Done!

---

### If You Are on Linux

#### 1. Find Your USB Drive Name
Plug in your USB drive, open a terminal, and run:
```bash
lsblk
```
Look at the output to find your USB drive size (e.g. `7.5G`, `14.9G`, `29.8G`).
Note down the drive name (for example `sdb` or `sdc`).
> **Important Safety Rule:** Never choose `sda` or `nvme0n1` if that is your main hard drive!

#### 2. Unmount the USB Drive Partitions
```bash
sudo umount /dev/sdb* 2>/dev/null || true
```
*(Only change `sdb` to your USB drive letter from `lsblk`)*

#### 3. Write the ISO to the USB
```bash
sudo dd if=SecLegion-OS-2026.10.08-x86_64.iso of=/dev/sdb bs=4M status=progress oflag=sync
```
*(Only change `sdb` to your USB drive letter. If you are not in the folder where the ISO was downloaded, put the full path like `if=~/Downloads/SecLegion-OS-*.iso`)*

Wait until `dd` finishes and returns to your terminal prompt. Your USB is ready!

#### Alternative: Ventoy on Linux
If you prefer Ventoy:
```bash
# On Arch Linux:
sudo pacman -S --needed ventoy

# Format USB with Ventoy (only change sdb to your USB letter):
sudo ventoy -i /dev/sdb

# Mount the USB and copy the ISO file:
cp SecLegion-OS-*.iso /run/media/$USER/Ventoy/
```

---

### If You Are on macOS

1. Open **Terminal** (press `Command + Space`, type `Terminal`, and press Enter).
2. List your connected disks:
   ```bash
   diskutil list
   ```
   Find your USB drive identifier (for example `/dev/disk2` or `/dev/disk3` matching your 8GB/16GB drive).
3. Unmount the USB drive:
   ```bash
   diskutil unmountDisk /dev/disk2
   ```
   *(Only change `disk2` to your USB disk number)*
4. Write the ISO to the USB:
   ```bash
   sudo dd if=SecLegion-OS-2026.10.08-x86_64.iso of=/dev/rdisk2 bs=4m
   ```
   *(Notice `rdisk2` with an 'r' — this uses the raw disk interface and is 10 times faster than disk2. Only change the number `2` to your disk number)*
5. Wait for the terminal prompt to return. Your USB is ready!

---

## Step 2: How to Boot from Your USB Drive

1. Turn off your computer completely.
2. Insert your prepared USB drive into a USB 3.0 port (blue port).
3. Turn on your computer and **immediately press your computer brand's Boot Menu key repeatedly** (tap it once every second until a menu appears):

| Computer Brand | Boot Menu Key | BIOS Setup Key |
| :--- | :--- | :--- |
| **ASUS** | `F8` or `Esc` | `F2` or `Del` |
| **Lenovo** | `F12` or `Fn + F12` (or Novo button) | `F2` or `Fn + F2` |
| **Dell** | `F12` | `F2` |
| **HP** | `F9` or `Esc` | `F10` |
| **Acer** | `F12` | `F2` or `Del` |
| **MSI** | `F11` | `Del` |
| **Gigabyte / ASRock** | `F12` | `Del` |
| **Apple (Intel Mac)** | Hold `Option` (`Alt`) on power up | Hold `Option` |

4. When the Boot Menu appears, select **UEFI: [Your USB Brand Name]** and press Enter.
5. In the cyber boot menu, select the first option: **SecLegion OS**.

### If Your USB Does Not Boot (BIOS Settings Check)
If your computer bypasses the USB or gives a security error:
1. Restart your PC and tap your **BIOS Setup Key** (`F2` or `Del`).
2. Go to the **Security** tab $\rightarrow$ Set **Secure Boot** to **Disabled**.
3. Go to the **Configuration / Storage** tab $\rightarrow$ Ensure SATA Controller is set to **AHCI** (disable Intel RST/RAID).
4. Press `F10` to save changes and restart.

---

## Step 3: Installing on the Live Desktop (Calamares GUI)

Once the live desktop appears:

1. Connect to Wi-Fi if needed (click the network icon in the top bar or run `nmtui` in the terminal).
2. Launch the installer:
   * Double-click **"Install SecLegion OS"** on the desktop, or
   * Press `Super + Space` (Windows key + Space) and select **Install SecLegion OS**.
3. **Welcome Screen:** Select your language $\rightarrow$ Click **Next**.
4. **Location Screen:** Click on your country or region on the map $\rightarrow$ Click **Next**.
5. **Keyboard Screen:** Select your keyboard layout (e.g. English US) $\rightarrow$ Click **Next**.
6. **Partitions Screen:** Choose how you want to install:
   * **Erase disk:** Completely wipes the drive and installs SecLegion OS as your sole operating system.
   * **Install alongside:** Keeps your existing Windows or Linux installation and automatically splits free space for dual-booting.
   * **Manual partitioning:** For advanced users who want custom mount points (`/`, `/boot/efi`, `/home`).
   * Click **Next**.
7. **User Setup Screen:**
   * Enter your name.
   * Enter your login username.
   * Enter your password twice.
   * *(Optional)* Check "Log in automatically" if you want to skip the login screen.
   * Click **Next**.
8. **Summary Screen:** Review your settings $\rightarrow$ Click **Install** $\rightarrow$ Click **Install now** on the confirmation box.
9. Wait for the progress bar to complete (takes 3 to 5 minutes).
10. Check **Restart now** $\rightarrow$ Click **Done**.
11. Unplug the USB drive when the screen prompts you to remove installation media and press **Enter**.

Welcome to SecLegion OS!

---

## Alternative Method: Install Without a USB Drive (`install-from-existing.sh`)

If you are already running an existing Linux distribution and have a spare drive or partition, you can deploy SecLegion OS directly to that partition without needing any USB drive:

1. Clone the repository and enter the directory:
   ```bash
   git clone https://github.com/Ammar-Elkholy/SecLegion-OS.git
   cd SecLegion-OS
   ```
2. Run the offline partition installer as root:
   ```bash
   sudo bash install-from-existing.sh
   ```
3. Follow the interactive prompts:
   * Select your target root partition (e.g. `/dev/nvme0n1p3` or `/dev/sdb2`).
   * Select your existing EFI partition (e.g. `/dev/nvme0n1p1` or `/dev/sdb1`).
   * Choose your filesystem (`ext4` or `btrfs`).
   * Set your username, password, and computer hostname.
4. The script formats the target partition, unpacks the live system, sets up `/etc/fstab`, and registers the **SecLegion** boot entry in your UEFI firmware.
5. Reboot your machine and select **SecLegion** from your boot menu.

---

## Post-Installation: Helpful Next Steps

### 1. Automated Security Lab Bootstrap (Tier 2)
To keep the base system fast and lightweight, heavy penetration testing suites are installed on demand. Open your terminal and run:
```bash
seclegion-bootstrap-tier2.sh
```
This automatically installs and configures:
* **KVM / QEMU Virtualization:** Full hardware virtualization with `virt-manager` and `virbr0` network bridge (pre-configured for non-root users).
* **Security Suites:** Burp Suite, Metasploit Framework, Wireshark (packet capture permissions pre-granted), and wordlists (`rockyou.txt`).
* **Brave Browser:** Privacy-hardened browser.
* **BlackArch Repository:** Synchronizes access to 2,800+ penetration testing tools.

---

### 2. Dual-Booting with Windows: Fix Time Difference
If your clock shifts by 2 to 3 hours after switching between Windows and Linux, run this command in your terminal:
```bash
timedatectl set-local-rtc 1
```

---

### 3. Dual-Booting with Windows: Add Windows to GRUB Menu
To have Windows automatically detected in your bootloader menu:
```bash
sudo pacman -S --needed os-prober
sudo sed -i 's/#GRUB_DISABLE_OS_PROBER=false/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
sudo grub-mkconfig -o /boot/grub/grub.cfg
```
