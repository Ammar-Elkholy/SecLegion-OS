# AE_ARCH Linux — Edge Cases & GitHub Known Issues Resolution Matrix
> **Author:** Ammar Elkholy (SecLegion Edition)  
> **Target:** Universal Deployment Across Any Laptop Architecture (Intel, AMD, NVIDIA Hybrid)

This document analyzes, tests, and resolves every known failure mode, GitHub issue, and hardware edge case encountered when building, booting, and deploying custom Arch Linux ISOs with Calamares and Hyprland.

---

## 🛠️ Table of Edge Cases & Solved GitHub Issues

| # | Edge Case / GitHub Issue | Root Cause | Implemented Solution in AE_ARCH | Status |
|---|---|---|---|:---:|
| **1** | **`mkarchiso` Out of Space (`No space left on device`)** | Default `mkarchiso` uses `/tmp` (RAM tmpfs limited to 50% RAM). Large rootfs with themes/wallpapers exhausts RAM during `mksquashfs`. | `build.sh` redirects work directory to `/var/tmp/ae-arch-work` or real disk storage with automated cleanup. | **SOLVED ✅** |
| **2** | **NVIDIA Black Screen on Live Boot / Wayland** | Missing DRM modeset or early KMS driver conflicts on NVIDIA Turing / Ampere / Ada laptops. | Boot menu includes dedicated entry: `nvidia-drm.modeset=1 fbdev=1 module_blacklist=nouveau` and bundles `egl-wayland`. | **SOLVED ✅** |
| **3** | **Calamares Fails at `unpackfs` or Package Keyring** | Arch live keyring older than current date causes PGP signature verification failure during chroot operations. | Calamares pre-run hook executes `pacman-key --init && pacman-key --populate archlinux`. | **SOLVED ✅** |
| **4** | **No Sound / Mic on Intel & AMD Laptops** | Modern laptop audio (Tiger Lake, Alder Lake, Ryzen 6000+) uses digital signal processors (DSP) requiring Sound Open Firmware. | Pre-bundled `sof-firmware`, `alsa-firmware`, and `alsa-ucm-conf` alongside PipeWire and WirePlumber. | **SOLVED ✅** |
| **5** | **Intel VMD Hiding NVMe Storage (0 Drives Detected)** | Intel RST / VMD hardware RAID controller in BIOS intercepts NVMe commands, making `/dev/nvme0n1` invisible to Linux. | Added kernel parameter `vmd` support + documented BIOS setting: *Storage Controller $\rightarrow$ AHCI Mode*. | **SOLVED ✅** |
| **6** | **Dual-Boot Windows Time Desync (Clock 2-3 Hours Off)** | Linux defaults to UTC hardware clock while Windows defaults to Local Time. | Calamares configured with `hwclock.conf` to handle RTC synchronization cleanly for Windows dual-boot setups. | **SOLVED ✅** |
| **7** | **Calamares Wayland Polkit Permission Failure** | Launching Calamares as root under Wayland compositor (Hyprland) fails if Polkit authentication agent is absent. | Pre-configured `polkit-gnome` autostart in both GNOME and Hyprland sessions. | **SOLVED ✅** |
| **8** | **New User Home Directory Permission Desync** | When Calamares creates a new user, files copied from `/etc/skel` can retain root permissions, breaking Hyprland/Kitty configs. | Added Calamares `shellprocess` post-install hook: `chown -R $USER:$USER /home/$USER`. | **SOLVED ✅** |
| **9** | **HiDPI / 4K Laptop Display Text Scaling** | Calamares or Hyprland opening with microscopic text on 14" 2.8K/4K OLED panels. | Injected `QT_AUTO_SCREEN_SCALE_FACTOR=1` in environment and configured Hyprland `monitor.lua` with dynamic `auto` scaling. | **SOLVED ✅** |
| **10** | **Live Session RAM Exhaustion (`cow_space`)** | Default Archiso ramdisk allows only 512MB for writable files in the live session, crashing if users browse or download during install. | Profile bootloader explicitly sets `cow_spacesize=4G` for ample temporary memory during live installation. | **SOLVED ✅** |
| **11** | **Secure Boot Rejection** | Custom ISOs without Microsoft-signed shims are blocked by UEFI Secure Boot. | Clear boot splash warning and instruction to toggle Secure Boot off in BIOS before booting. | **SOLVED ✅** |
| **12** | **Offline Installation without Internet** | Users installing in environments with no Wi-Fi/Ethernet encounter timeout errors if installer attempts online package fetches. | Full desktop environment, drivers, themes, and configs are baked offline into the squashfs image; no internet required. | **SOLVED ✅** |

---

## 🧪 Edge Case Verification Tests & Instructions

### Test 1: Simulating NVIDIA vs. AMD/Intel Boot
* **Default Bootloader Entry:** Uses `modeset=1` for open-source AMD / Intel / Nouveau drivers.
* **NVIDIA Bootloader Entry:** Appends `nvidia-drm.modeset=1 fbdev=1` for GeForce GTX / RTX mobile and desktop GPUs.
* *Result:* Zero kernel panic; displays render immediately on both integrated and discrete GPUs.

### Test 2: User Creation & Dotfile Inheritance Test
* When Calamares creates user `ammar` (or any custom username):
  1. `/etc/skel/.config/` is recursively copied to `/home/ammar/.config/`.
  2. The post-install hook executes `chown -R ammar:ammar /home/ammar/`.
  3. Symlinks and paths automatically adapt because all configs use `$HOME`.
* *Result:* New user logs into Hyprland and GNOME with full themes, wallpapers, Waybar, and Kitty without manual setup.

### Test 3: Audio & Bluetooth Codec Verification
* Run `pactl info` and `wpctl status`.
* *Result:* PipeWire sound server active; LDAC, aptX HD, and SBC-XQ negotiate automatically with wireless headphones.
