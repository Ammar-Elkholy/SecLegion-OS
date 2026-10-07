# SecLegion OS: Diagnostics, Audit & Fixes Ledger
**System:** SecLegion OS (Arch Linux Base)  
**Lead:** Ammar Elkholy (SecLegion Edition)  
**Audit Date:** 2026-10-07  
**Tracking File:** `seclegion_diagnostics_and_fixes.md`

---

## 1. Base System Audit Findings & Gap Analysis

### A. Kernel & Hardware Profile
- **Kernel Version:** Linux 7.2.7-arch1-1 (x86_64, PREEMPT_DYNAMIC)
- **Integrated GPU:** AMD Renoir (Vega Mobile) — Driver: `amdgpu`
- **Discrete GPU:** NVIDIA GeForce GTX 1650 Mobile (TU117M) — Driver: `nvidia` (Proprietary 550+ Prime Hybrid)
- **Wi-Fi Controller:** Realtek RTL8822CE 802.11ac PCIe — Driver: `rtw88_8822ce`
- **Audio Subsystem:** AMD Ryzen HD Audio + AMD ACP DSP — Driver: `snd_hda_intel` / PipeWire 1.x
- **Storage Layout:** 
  - NVMe Root (`/` on LVM2 `ArchinstallVg-root`, ext4, 84GB free)
  - NVMe EFI (`/boot`, vfat 31A6-36F7, 740MB free)
  - Swap: `zram0` (dynamic zram compressed RAM swap)
  - Storage Mounts: `/mnt/Main_disk` & `/mnt/Dev_Lab` (NTFS with ntfs-3g)

### B. Display Manager & Session Segregation
- **Active Service:** `gdm.service` (GNOME Display Manager)
- **Wayland Compositor:** Hyprland (Primary offsec workstation environment)
- **Fallback Desktop:** GNOME Wayland/X11 (Resilient administrative fallback)
- **Integrity Status:** Clean session separation. No environment variable bleed between GDM and Hyprland. Polkit agent is `polkit-gnome`.

### C. Modern CLI Utilities Gap Analysis
| Utility | Role | Status on Host | Priority | Action |
|:---|:---|:---:|:---:|:---|
| `bat` | Cat clone with syntax highlighting & git integration | **Missing** | High | Include in Upgrade Menu |
| `fd` | Ultra-fast user-friendly find replacement | **Missing** | High | Include in Upgrade Menu |
| `zoxide` | Smarter cd command tracking frecency | **Missing** | High | Include in Upgrade Menu |
| `btop` | Modern GPU/CPU/Network resource monitor | **Missing** | High | Include in Upgrade Menu |
| `lazygit` | Terminal UI git client | **Missing** | Medium | Include in Upgrade Menu |
| `tmux` | Terminal multiplexer with session persistence | **Missing** | High | Include in Upgrade Menu |
| `eza` | Modern ls replacement with icons | Present | OK | Pre-configured |
| `rg` | Ripgrep code searcher | Present | OK | Pre-configured |
| `fzf` | Fuzzy command finder | Present | OK | Pre-configured |
| `yazi` | GPU terminal file manager | Present | OK | Pre-configured |

---

## 2. InfoSec & Cybersecurity Suite (BlackArch Linux Integration)

SecLegion OS leverages the official **BlackArch Linux** repository containing over 2,800+ penetration testing and security tools.

### Official BlackArch Bootstrap Protocol (`strap.sh`)
To safely integrate BlackArch into the local system and distro builds:

```bash
# 1. Fetch official strap.sh
curl -O https://blackarch.org/strap.sh

# 2. Verify SHA1 checksum (must match official BlackArch release)
echo "5ea40d49ecd14c2e024deecf90605426db97ea0c strap.sh" | sha1sum -c

# 3. Grant execute permissions and run bootstrap
chmod +x strap.sh
sudo ./strap.sh

# 4. Synchronize BlackArch package database
sudo pacman -Syy
```

### BlackArch Curated Meta-Packages for Local & ISO Deployment
Rather than installing 2,800 tools indiscriminately (which inflates the OS by ~50GB), SecLegion OS recommends 8 focused meta-packages matching Kali Linux capability tiers:

1. **`blackarch-scanner`** (Nmap, Masscan, ZMap, Amass, Nikto, WPScan)
2. **`blackarch-webapp`** (BurpSuite, Sqlmap, Gobuster, Ffuf, Commix, WhatWeb)
3. **`blackarch-wireless`** (Aircrack-ng, Kismet, Wifite, Reaver, Bettercap)
4. **`blackarch-exploitation`** (Metasploit, Searchsploit, Pwntools, ExploitDB)
5. **`blackarch-crypto`** (Hashcat, John the Ripper, Hydra, Medusa, Hash-identifier)
6. **`blackarch-networking`** (Wireshark, Tshark, Tcpdump, Responder, Mitmproxy)
7. **`blackarch-reversing`** (Ghidra, Radare2, GDB-PEDA, Cutter, Binary Ninja CLI)
8. **`blackarch-forensic`** (Autopsy, Sleuthkit, Volatility 3, Binwalk, Foremost)

---

## 3. Shortcut & Window Manager Conflict Resolution Matrix

| Shortcut | Action | Target Binary | Conflict Status | Final Resolution |
|:---|:---|:---|:---:|:---|
| `Super + Return` | Open Terminal | `kitty` | Clean | Verified |
| `Super + E` / `Super + ث` | File Manager | `thunar` | Resolved | Set to Thunar with 0.75 opacity |
| `Super + Y` | CLI File Manager | `yazi` | Clean | Opens Kitty with Yazi |
| `Super + D` / `Super + R` | App Launcher | `rofi -show drun` | Clean | Styled with SecLegion cyber palette |
| `Super + L` / `Super + م` | Logout / Power Menu | `wlogout` | **RESOLVED** | Removed Vim navigation collision; toggleable |
| `Super + Shift + L` | Screen Lock | `hyprlock` | **RESOLVED** | Overwrite bug fixed; locks immediately |
| `Super + S` / `Super + س` | Toggle Scratchpad | `magic` | Clean | Verified |
| `Super + Shift + A` | Move to Scratchpad | `scratchpad-send.sh` | Clean | Added OSD notification popup |
| `Super + Z` / `Super + ئ` | Restore from Scratchpad | `scratchpad-restore.sh`| **RESOLVED** | Invalid workspace current fixed with monitor API |
| `Super + Ctrl + W` | Live Wallpaper Picker | `live-wallpaper-yazi.sh`| **RESOLVED** | Auto-folder creation, awww GIF/video fallback |

---

## 4. Archiso Profile Validation & Host Theming Hotfix Report

### 1. mkarchiso Validation Resolution
- **Bootmodes:** Replaced deprecated 'bios.syslinux.mbr' and 'uefi-x64.systemd-boot.esp' with modern 'bios.syslinux' and 'uefi.systemd-boot'.
- **Structure Rebase:** Bootloader directories ('efiboot/', 'syslinux/', 'grub/') pulled from '/usr/share/archiso/configs/releng/' and customized for SecLegion OS.
- **Packages:** Added 'syslinux', 'edk2-ovmf', 'edk2-shell', 'memtest86+', 'memtest86+-efi', and 'chafa' into 'packages.x86_64'.
- **Validation Test:** 'mkarchiso -v /home/aelkholy/Dev_Lab/AE_ARCH' executes with zero errors.

### 2. Local Host Theming Resolution
- **Rofi App Launcher:** Replaced old '#9C6A7A' border with Matrix Green ('#00FF88') and Dark Teal ('#0B1E1C') background on active selections in '~/.config/rofi/rofi-window.rasi' and 'config.rasi'.
- **Host OS-Release:** Updated host '/etc/os-release' to NAME="SecLegion OS", ID=seclegion, LOGO=seclegion.
- **Fastfetch Branding:** Configured 'kitty-direct' with 'seclegion-logo-transparent.png' and replaced ASCII art with SecLegion OS workstation banner.

---

## 5. Master Architecture v2.0 Quality Engineering & Final Audit Closure (2026-10-08)

| Component | Diagnostic Issue | Resolution Applied | Verification Status |
| :--- | :--- | :--- | :---: |
| **Virtualization** | Missing non-root libvirt access & polkit rule | Created `/etc/polkit-1/rules.d/50-libvirt.rules`, `/etc/libvirt/libvirtd.conf`, enabled `libvirtd.service` in Calamares & Tier-2 scripts | **VALIDATED** |
| **Multi-GPU KMS** | Hardcoded `/dev/dri/card1:/dev/dri/card0` causing single-GPU failures | Deployed `/etc/profile.d/seclegion-gpu.sh` with dynamic display detection, updated `hyprland.lua`, and created `/usr/local/bin/seclegion-gpu-run` | **VALIDATED** |
| **Dual-Booting** | `os-prober` omitted & Windows RTC time drift | Added `os-prober` to `packages.x86_64`, enabled `GRUB_DISABLE_OS_PROBER=false` in `/etc/default/grub`, added `timedatectl set-local-rtc 1` | **VALIDATED** |
| **CLI Utilities** | `bat`, `fd`, `zoxide`, `btop`, `lazygit`, `tmux` missing from base | Embedded automated installation in `seclegion-bootstrap-tier2.sh` | **VALIDATED** |
| **BlackArch Lab** | Unstructured tool installation bloating disk by 50GB | Injected 8 curated Kali-tier meta-package categories in interactive Tier-2 provisioner | **VALIDATED** |
| **File Manager** | Yazi 26+ `theme.toml` crash on `name = "*.sh"` | Updated all file rules to `url = "*.sh"` in `theme.toml` across host and airootfs | **VALIDATED** |
| **Terminal Fetch** | Overlapping/wrapping fastfetch banner on standard terminals | Scaled designs to <= 41 cols, compacted fastfetch modules to 71 cols, added adaptive top layout | **VALIDATED** |
| **Wallpapers** | SecLegion wallpapers absent from `~/Pictures/Wallpapers` in Yazi | Synchronized all 5 official branded wallpapers alongside 50+ personal wallpapers in `Pictures/Wallpapers` | **VALIDATED** |
| **Repository** | Potential accidental commits of 3.7GB ISO | Formulated strict production `.gitignore` with asset whitelisting | **VALIDATED** |
