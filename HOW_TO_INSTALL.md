# SecLegion OS — Step-by-Step Installation Guide

> **"We develop Mindsets — Securing Minds & Systems"**  
> Author & Lead Architect: **Ammar Elkholy**  
> Official Repository: [https://github.com/Ammar-Elkholy/SecLegion-OS](https://github.com/Ammar-Elkholy/SecLegion-OS)

---

## Quick Navigation Index

* **[Step 0: How to Get the ISO (Google Drive or Build from Source)](#step-0)**
* **[Do You Need to Format Your Drive First?](#formatting-faq)**
* **[Step 1: Flash the ISO to Your USB Drive](#step-1)**
  * [Windows (Rufus)](#windows-rufus)
  * [Windows (Ventoy)](#windows-ventoy)
  * [Linux (Terminal dd)](#linux-dd)
  * [Linux (Ventoy)](#linux-ventoy)
  * [macOS (Terminal dd)](#macos-dd)
* **[Step 2: How to Boot from Your USB Drive](#step-2)**
* **[Step 3: Installing on the Live Desktop (Calamares GUI)](#step-3)**
* **[Alternative Method: Install Without a USB Drive](#step-usb-less)**
* **[Post-Installation: Helpful Next Steps](#step-post-install)**

---

<a id="step-0"></a>
## Step 0: How to Get the SecLegion OS ISO

You have two easy choices:

### Choice 1: Download from Google Drive (Ready-to-Use ISO)
If you just want the pre-built ISO without compiling anything:
* **Google Drive Download Link:** **[Download SecLegion OS 2026.10 ISO](https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE)** *(File: `SecLegion-OS-2026.10.08-x86_64.iso`, Size: 3.7 GB)*
* **SHA256 Checksum:** `9d964eebfb1b40fae3322e2b201375aa65c3c4e666b344bfa45fd6f37a4b39d2`

---

### Choice 2: Build the ISO Yourself in 1 Command (If You Prefer Making It)
If you don't want to download the 3.7GB file and you are running an Arch Linux system, you can compile the entire ISO locally:

```bash
# 1. Clone the repository
git clone https://github.com/Ammar-Elkholy/SecLegion-OS.git
cd SecLegion-OS

# 2. Install the archiso toolchain
sudo pacman -S --needed archiso

# 3. Build the ISO in one command
sudo bash build.sh
```
The finished ISO file will be created in `./output/SecLegion-OS-2026.10.08-x86_64.iso`.

---

<a id="formatting-faq"></a>
## Do You Need to Format Your Drive First?

### 1. Your USB Drive:
* **Short Answer: No.**
* When you write the ISO using Rufus, Ventoy, or `dd`, the tool **automatically wipes and reformats the USB drive** sector-by-sector. You do not need to format it beforehand.
* **If your USB has errors or old stubborn partitions and you want to clean it first:**
  * **On Windows:** Open *File Explorer* -> Right-click your USB drive -> Select **Format...** -> File System: **FAT32** -> Click **Start**.
  * **On Linux:** Run `sudo wipefs -a /dev/sdb` and `sudo mkfs.vfat -F 32 -I /dev/sdb` *(change `sdb` to your USB letter)*.
  * **On macOS:** Run `diskutil eraseDisk FAT32 SECLEGION /dev/disk2` *(change `disk2` to your disk number)*.

### 2. Your Computer's Internal SSD / Hard Drive:
* **Short Answer: No pre-formatting needed.**
* The visual installer (**Calamares**) handles drive formatting for you automatically:
  * If you choose **"Erase disk"**, it automatically formats the entire drive with the correct Linux partitions (`ext4`/`btrfs` and EFI).
  * If you choose **"Install alongside"** (Dual-boot with Windows), it safely shrinks your Windows partition and formats the newly created space automatically.

---

<a id="step-1"></a>
## Step 1: Flash the ISO to Your USB Drive

Select the platform you are currently using:

---

<a id="windows-rufus"></a>
### Windows — Method A: Rufus (Step-by-Step Button Clicks)

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

> **Next Step:** Finished flashing on Windows?  
> 👉 **[Click here to Jump directly to Step 2: How to Boot from Your USB Drive](#step-2)**

---

<a id="windows-ventoy"></a>
### Windows — Method B: Ventoy (Drag-and-Drop)

1. Download `ventoy-*-windows.zip` from [ventoy.net](https://www.ventoy.net/).
2. Extract the zip file, open the folder, and run `Ventoy2Disk.exe`.
3. Select your USB drive and click **Install** (confirm the warnings).
4. Open Windows File Explorer, open your USB drive, and drag and drop `SecLegion-OS-*.iso` directly into the USB drive. Done!

> **Next Step:** Finished copying the ISO?  
> 👉 **[Click here to Jump directly to Step 2: How to Boot from Your USB Drive](#step-2)**

---

<a id="linux-dd"></a>
### Linux — Method A: Terminal `dd`

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
*(Only change `sdb` to your USB drive letter. If the ISO is in your Downloads folder, use `if=~/Downloads/SecLegion-OS-*.iso`)*

Wait until `dd` finishes and returns to your terminal prompt. Your USB is ready!

> **Next Step:** Finished flashing on Linux?  
> 👉 **[Click here to Jump directly to Step 2: How to Boot from Your USB Drive](#step-2)**

---

<a id="linux-ventoy"></a>
### Linux — Method B: Ventoy

```bash
# 1. On Arch Linux:
sudo pacman -S --needed ventoy

# 2. Format USB with Ventoy (only change sdb to your USB letter):
sudo ventoy -i /dev/sdb

# 3. Mount the USB and copy the ISO file:
cp SecLegion-OS-*.iso /run/media/$USER/Ventoy/
```

> **Next Step:** Finished copying the ISO?  
> 👉 **[Click here to Jump directly to Step 2: How to Boot from Your USB Drive](#step-2)**

---

<a id="macos-dd"></a>
### macOS — Terminal `dd`

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

> **Next Step:** Finished flashing on macOS?  
> 👉 **[Click here to Jump directly to Step 2: How to Boot from Your USB Drive](#step-2)**

---

<a id="step-2"></a>
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
2. Go to the **Security** tab -> Set **Secure Boot** to **Disabled**.
3. Go to the **Configuration / Storage** tab -> Ensure SATA Controller is set to **AHCI** (disable Intel RST/RAID).
4. Press `F10` to save changes and restart.

> **Next Step:** Live desktop loaded?  
> 👉 **[Click here to Jump directly to Step 3: Installing on the Live Desktop](#step-3)**

---

<a id="step-3"></a>
## Step 3: Installing on the Live Desktop (Calamares GUI)

Once the live desktop appears:

1. Connect to Wi-Fi if needed (click the network icon in the top bar or run `nmtui` in the terminal).
2. Launch the installer:
   * Double-click **"Install SecLegion OS"** on the desktop, or
   * Press `Super + Space` (Windows key + Space) and select **Install SecLegion OS**.
3. **Welcome Screen:** Select your language -> Click **Next**.
4. **Location Screen:** Click on your country or region on the map -> Click **Next**.
5. **Keyboard Screen:** Select your keyboard layout (e.g. English US) -> Click **Next**.
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
8. **Summary Screen:** Review your settings -> Click **Install** -> Click **Install now** on the confirmation box.
9. Wait for the progress bar to complete (takes 3 to 5 minutes).
10. Check **Restart now** -> Click **Done**.
11. Unplug the USB drive when the screen prompts you to remove installation media and press **Enter**.

> **Next Step:** Booted into your new SecLegion OS?  
> 👉 **[Click here to Jump directly to Post-Installation: Helpful Next Steps](#step-post-install)**

---

<a id="step-usb-less"></a>
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

> **Next Step:** Finished USB-less install?  
> 👉 **[Click here to Jump directly to Post-Installation: Helpful Next Steps](#step-post-install)**

---

<a id="step-post-install"></a>
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
