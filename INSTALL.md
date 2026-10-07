# SecLegion OS — Universal Installation & Deployment Guide
### Release 2026.10 | Engineered by Ammar Elkholy

SecLegion OS offers two distinct deployment paths: **Standard USB Boot Media** and **USB-Less Direct Local Partition Installation**.

---

## 1. Hardware Specifications

| Component | Minimum Specification | Recommended Specification |
|:---|:---|:---|
| **Architecture** | 64-bit x86_64 | Modern Multi-Core Intel Core / AMD Ryzen |
| **RAM** | 4 GB | 16 GB+ (Required for KVM/QEMU lab virtualization) |
| **Storage** | 30 GB free | 80 GB - 120 GB+ NVMe SSD |
| **Graphics** | Intel / AMD / NVIDIA | Hybrid NVIDIA GeForce / RTX Prime laptops supported out of the box |
| **Firmware** | UEFI (GPT) | UEFI with Secure Boot disabled |

---

## 2. Firmware & BIOS Settings

Enter your machine's BIOS/UEFI setup (`F2`, `F12`, `Del`, or `Esc` during startup):

1. **Secure Boot:** Must be **Disabled**. Custom Arch kernels and DKMS modules require unsigned execution.
2. **Storage Controller:** Set to **AHCI Mode** (Disable Intel RST / RAID to prevent hidden NVMe drives).
3. **Fast Boot / Fast Startup:** **Disabled** in both BIOS and inside Windows (prevents NTFS partition locking).

---

## 3. Deployment Method A: Standard USB Media Installation

### Flashing Media (8GB minimum required)
- **Windows:** Use [Rufus](https://rufus.ie/) with Partition Scheme **GPT**, Target **UEFI**, and write in **DD Image Mode**. Or drag the ISO onto a [Ventoy](https://www.ventoy.net/) drive.
- **macOS / Linux:**
  ```bash
  sudo dd if=SecLegion-OS-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
  ```

### Live Boot & Installer Execution
1. Boot from the USB and select the default boot entry from the **SecLegion Cyber GRUB Menu**.
2. Connect to Wi-Fi: Click the network icon or run `nmtui` in the terminal.
3. Launch the installer:
   - Double-click **Install SecLegion OS** on the desktop, or
   - Run in terminal: `sudo -E calamares`

---

## 4. Deployment Method B: USB-Less Local Partition Deployment

If you are already running an existing Linux distribution on your laptop and have an unformatted or spare partition, you do not need a USB flash drive:

1. Clone or extract the SecLegion repository into your environment:
   ```bash
   cd /path/to/AE_ARCH
   ```
2. Execute the automated local deployment engine as root:
   ```bash
   sudo bash install-from-existing.sh
   ```
3. Follow the interactive CLI prompts:
   - Select your target root partition (e.g. `/dev/nvme0n1p3`).
   - Select your existing EFI partition (e.g. `/dev/nvme0n1p1`).
   - Choose filesystem (`ext4` or `btrfs`).
   - Set your username, password, and computer hostname.
4. The installer formats the partition, overlays SecLegion OS dotfiles, configures users, and registers the **SecLegion** boot entry directly with your UEFI firmware.
5. Reboot your machine—select **SecLegion** from your BIOS boot menu.

---

## 5. Multi-GPU Kernel Parameters & Display Drivers

SecLegion OS includes universal kernel KMS flags pre-configured for hybrid laptops:

| Architecture | Primary Kernel Flag | Notes |
|:---|:---|:---|
| **NVIDIA Hybrid (GTX / RTX)** | `nvidia-drm.modeset=1 fbdev=1` | Eliminates Wayland flickering and enforces DRM modesetting |
| **AMD Radeon (Vega / RDNA)** | `amdgpu.modeset=1` | Native open-source kernel driver with Vulkan support |
| **Intel Iris Xe / Arc** | `i915.modeset=1` | High-efficiency hardware media encoding/decoding |

*Note: For maximum boot speed, SecLegion OS executes a **Raw Arch Boot (No Plymouth)**, displaying kernel diagnostics directly in high-visibility Matrix Green.*

---

## 6. Dual-Boot Probing & Windows Synchronization

### Windows Dual-Boot Discovery (`os-prober`)
To automatically detect an existing Windows 10/11 installation and add it to your SecLegion GRUB menu:
```bash
sudo pacman -S --needed os-prober
sudo sed -i 's/#GRUB_DISABLE_OS_PROBER=false/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

### Windows Real-Time Clock (RTC) Drift Fix
Windows tracks hardware time in Local Time, while Linux tracks UTC. To eliminate the 2–3 hour clock offset when switching OSes:
```bash
timedatectl set-local-rtc 1 --adjust-system-clock
```

---

## 7. Two-Tier Software Provisioning: Tier-2 Deployment

After booting into your installed SecLegion OS, your system runs on **Tier 1 (Base System + Lightweight OffSec CLI)**.

To upgrade to the full **Tier 2 Offensive Security Infrastructure** (KVM/QEMU lab hypervisor, Brave Browser, Burp Suite, Wireshark packet capture, Metasploit, and wordlists):

```bash
seclegion-bootstrap-tier2.sh
```
*(Or execute: `sudo bash /usr/local/bin/seclegion-bootstrap-tier2.sh`)*

This automates:
- Enabling the complete **BlackArch** Linux repository
- Deploying `libvirtd` and activating the `virbr0` virtual NAT network for guest hacking labs
- Adding your user to the `libvirt`, `kvm`, and `wireshark` groups
- Unpacking `/usr/share/wordlists/rockyou.txt`

---


---

## 8. Distribution Pathways & Reproducibility

SecLegion OS provides two independent distribution pathways:

### Pathway A: Building from Source (100% Reproducible)
Anyone running an Arch Linux system can reproduce and compile this ISO bit-for-bit:
```bash
# 1. Clone the official repository
git clone https://github.com/aelkholy/SecLegion-OS.git
cd SecLegion-OS

# 2. Install archiso builder toolchain
sudo pacman -S --needed archiso

# 3. Compile the Release ISO (handles permissions, workdir, and compression)
sudo bash build.sh
```
The finished binary image is generated in `./output/SecLegion-OS-*.iso` along with its cryptographic `.sha256` verification hash.

### Pathway B: Direct Release Download
For users who do not run Arch Linux or wish to skip the compilation process:
1. Download the pre-compiled Release ISO and SHA256 checksum from:
   - **GitHub Releases:** `https://github.com/aelkholy/SecLegion-OS/releases`
   - **External Mirror / Cloud Storage:** (Direct download link on official release page)
2. Verify image integrity before flashing:
   ```bash
   sha256sum -c SecLegion-OS-*.iso.sha256
   ```

---

*Engineered with precision for offensive security professionals by Ammar Elkholy.*
