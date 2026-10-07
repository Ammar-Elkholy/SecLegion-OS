# SecLegion OS

**An advanced, production-grade Offensive Security Linux distribution built upon Arch Linux by Ammar Elkholy.**

*Official SecLegion Edition · Cyberpunk Matrix Architecture · Hyprland + GNOME · Universal Multi-GPU*

---

## 🎨 Official Brand Identity & Color Palette

SecLegion OS adheres strictly to an aggressive cyber-security aesthetic:
- **Glitch White (`#FFFFFF`):** High-contrast typography and icon highlights
- **Matrix Green (`#00FF88`):** Active window borders, success indicators, primary operational accent
- **Cyberpunk Cyan (`#00F0FF`):** Focus rings, interactive elements, section headers
- **Dark Teal Carbon (`#0B1E1C`):** Panels, inactive borders, card backgrounds
- **Matrix Obsidian (`#050F0E`):** Base workspace canvas, terminal backdrop

---

## What makes it different

### 🛡️ Two-Tier Software Provisioning Model

To ensure blistering speed without bloat, SecLegion OS employs a two-tier provisioning strategy:

- **Tier 1 (Base ISO & Core System):**
  - Ultra-fast live environment and minimal installer footprint.
  - Complete Hyprland Wayland suite + GNOME fallback.
  - Essential CLI offensive security tools: `nmap`, `tcpdump`, `sqlmap`, `aircrack-ng`, `hydra`, `john`, `radare2`, `socat`, `netcat`.
  - High-performance terminal tools: `kitty`, `bat`, `eza`, `zoxide`, `btop`, `yazi`, `fzf`, `starship`.
  - **Raw Arch Boot (No Plymouth):** Maximum startup speed with diagnostic kernel messages in high-visibility Matrix Green.

- **Tier 2 (Post-Install Infrastructure Bootstrap):**
  - Execute `seclegion-bootstrap-tier2.sh` after installation to pull heavy lab infrastructure on demand:
    - **KVM/QEMU/Libvirt Lab Hypervisor:** Full hardware virtualization with `virt-manager`, `ovmf`, and automated NAT network bridge (`virbr0`).
    - **Heavy GUI InfoSec Suites:** Burp Suite, Wireshark (packet capture permissions pre-granted), Metasploit framework with PostgreSQL, and wordlists (`rockyou.txt`).
    - **Privacy Browser:** Brave Browser (`brave-bin`).
    - **Full BlackArch Repository:** 2,800+ penetration testing tools synchronized via official `strap.sh`.

### Dual Desktop — GNOME & Hyprland

Both desktops come pre-configured out of the box, so you can pick whatever fits your mood:

- **GNOME** runs Catppuccin-Mocha dark theme with Tela-circle icons — clean and polished for when you need focus
- **Hyprland** is a fluid tiling compositor built around speed and aesthetics, featuring:
  - **Waybar** — custom status bar with audio, network, battery and workspace indicators
  - **Rofi** — instant application launcher
  - **Wallust** — automatically generates a matching color palette from your wallpaper
  - **SwayNC** — slide-in notification center and control panel
  - **Wlogout** — sleek lock/power screen
  - **AE-OSD** — branded neon popups for volume, brightness, and media (no annoying notification banners)

### Terminal & OffSec Operator HUD

- **Kitty** — GPU-accelerated terminal with background blur, opacity, and font ligatures
- **Zsh + Starship** — shows your active tun0 VPN IP, HackTheBox/TryHackMe target, and WireGuard status right in the prompt
- **Modern CLI tools:** `eza` (better ls), `bat` (syntax-highlighted cat), `fzf`, `zoxide`, `fastfetch`

### Hardware Portability — Any Laptop Works

No tuning needed regardless of your GPU:

- **AMD Radeon** — Mesa + RADV Vulkan, fully open source
- **Intel** — Iris Xe / HD Graphics with VA-API hardware decoding
- **NVIDIA** — Open-DKMS with nvidia-prime for hybrid laptop switching
- **Audio** — Complete PipeWire stack with LDAC and aptX Bluetooth codecs

### File Management

- **GUI:** Thunar — lightweight, custom 0.75 opacity, and custom terminal actions (Nautilus also included for GNOME)
- **CLI:** Yazi — terminal file manager with inline image previews

### Installer

- **Calamares** — graphical installer with SecLegion branding, one click to set up
- **Archinstall** — guided CLI installer for those who prefer the terminal

---

## Repository Structure

```
AE_ARCH/
├── build.sh                  ← builds the ISO in one command
├── clean_host_system.sh      ← removes bloat from a live Arch host
├── packages.x86_64           ← the full package list
├── pacman.conf               ← pacman config (multilib enabled)
├── profiledef.sh             ← ISO metadata and boot modes
├── EDGE_CASES.md             ← documented issues and fixes
└── airootfs/                 ← root filesystem overlay
    ├── etc/
    │   ├── skel/             ← default config for every new user
    │   │   └── .config/
    │   │       ├── hypr/     ← Hyprland config, keybinds, OSD scripts
    │   │       ├── dunst/    ← neon OSD notification theme
    │   │       ├── waybar/   ← status bar
    │   │       ├── rofi/     ← app launcher
    │   │       ├── kitty/    ← terminal
    │   │       ├── yazi/     ← file manager
    │   │       └── swaync/   ← notification center
    │   ├── dconf/            ← GNOME global defaults
    │   └── calamares/        ← GUI installer + SecLegion branding
    └── usr/share/
        ├── backgrounds/      ← curated wallpaper collection
        ├── themes/           ← GTK themes (Catppuccin, Tokyo Night, Graphite...)
        └── icons/            ← Tela-circle icons + Bibata cursors
```

---

## Building the ISO

You need `archiso` installed on a running Arch Linux host:

```bash
sudo pacman -S --needed archiso
```

Then just run the build script:

```bash
sudo bash build.sh
```

The finished ISO lands in `./output/` alongside a `sha256sum.txt` for verification.

> **About size:** The ISO is roughly **3–4 GB**. You only need an **8 GB USB drive** — that is the minimum and it is enough. Anything larger works fine too, and if you go with 16 GB or more you can throw multiple ISOs on a Ventoy drive and boot whichever you need.

---

## Flashing to USB

Pick the method that matches your platform:

---

### Linux — dd

```bash
# See your drives
lsblk

# Write the ISO (replace sdX with your drive, e.g. sdb — NOT the partition)
sudo dd if=output/AE_ARCH-*.iso of=/dev/sdX bs=4M status=progress oflag=sync && sync
```

> Double-check the drive letter before running. `dd` will silently overwrite whatever is there.

---

### Linux — Ventoy *(recommended if you use multiple ISOs)*

```bash
# Install Ventoy onto the USB once
sudo bash ventoy -i /dev/sdX

# Then just drop the ISO onto the drive
cp output/AE_ARCH-*.iso /run/media/$USER/Ventoy/
```

---

### macOS — dd

```bash
# List disks
diskutil list

# Unmount before writing (replace diskN, e.g. disk2)
diskutil unmountDisk /dev/diskN

# Flash — use rdiskN (raw device), it's ~10× faster than diskN
sudo dd if=output/AE_ARCH-*.iso of=/dev/rdiskN bs=4m
```

---

### macOS — Balena Etcher *(easier)*

1. Download [Balena Etcher](https://etcher.balena.io/) — free and open source
2. Flash from file → pick the `.iso`
3. Select your USB → Flash

---

### Windows — Rufus *(recommended)*

1. Download [Rufus](https://rufus.ie/) — portable, no install needed
2. Select your USB under **Device**
3. Click **SELECT** and choose the `.iso`
4. Set **Partition scheme** to GPT and **Target system** to UEFI (non-CSM)
5. Hit **START** — when asked, choose **DD Image mode**
6. Wait for "READY"

---

### Windows — Balena Etcher *(simpler)*

1. Download [Balena Etcher](https://etcher.balena.io/)
2. Flash from file → select `.iso` → select USB → Flash

---

### All Platforms — Ventoy *(best for power users)*

[Ventoy](https://www.ventoy.net/) runs on Linux, macOS, and Windows. Install it once, then just copy ISO files onto the drive — no re-flashing needed. Boot from USB and pick any ISO from a menu.

---

## Hyprland Keybindings

### Apps

| Keys | Action |
| :--- | :--- |
| `Super + Return` | Open terminal (Kitty) |
| `Super + T` | Open terminal (alternate) |
| `Super + E` | Open file manager (Thunar) |
| `Super + Y` | Open Yazi (terminal file manager) |
| `Super + B` | Open browser (Brave / Firefox) |
| `Super + D` or `Super + R` | Open app launcher (Rofi) |

### Window Management

| Keys | Action |
| :--- | :--- |
| `Super + Q` or `Super + C` | Close active window |
| `Super + F` | Toggle fullscreen |
| `Super + V` or `Super + W` | Toggle floating |
| `Super + P` | Toggle pseudo-tiling |
| `Super + J` | Swap split direction |
| `Super + G` | Toggle window group (tabs) |
| `Super + Tab` / `Super + Shift + Tab` | Next / previous tab in group |

### Workspaces & Scratchpad

| Keys | Action |
| :--- | :--- |
| `Super + 1–9, 0` | Switch to workspace 1–10 |
| `Super + Shift + 1–9, 0` | Move window to workspace |
| `Super + S` | Show / hide scratchpad |
| `Super + Shift + A` | Send window to scratchpad |
| `Super + Z` | Pull window back from scratchpad to current workspace |

### Focus & Moving Windows

| Keys | Action |
| :--- | :--- |
| `Super + Arrows` | Move focus |
| `Super + H / L / K / M` | Move focus (Vim-style) |
| `Super + Shift + Arrows` | Move window |
| `Super + Shift + H / L / K / J` | Move window (Vim-style) |

### System

| Keys | Action |
| :--- | :--- |
| `Super + Space` | Switch keyboard language |
| `Super + N` | Open notification center |
| `Super + L` / `Escape` / `Backspace` | Logout & power menu (Wlogout) |
| `Super + Shift + L` | Lock screen |
| `Super + Shift + B` | Toggle Waybar |
| `Super + Shift + V` | Open clipboard manager (CopyQ) |
| `Super + Shift + W` | Pick wallpaper via Yazi |
| `Super + Ctrl + W` | Set live wallpaper |

### Screenshots

| Keys | Action |
| :--- | :--- |
| `Print` or `Super + Shift + S` | Capture area → clipboard + file |
| `Shift + Print` | Capture area → open in Swappy for annotation |
| `Super + Print` | Capture active window |
| `Ctrl + Print` | Capture full screen |

### Media & Volume (with OSD popups)

| Keys | Action |
| :--- | :--- |
| Volume Up / Down / Mute | Volume with neon popup |
| Mic Mute | Microphone toggle popup |
| Brightness Up / Down | Brightness with neon popup |
| Play / Next / Prev media keys | Media control popup |
| `Super + F10 / F11 / F12` | Play / Previous / Next (no media keys needed) |

---

## 📚 Core Documentation & Guides

Comprehensive documentation is provided across dedicated manuals:

1. **[Universal Installation Guide (INSTALL.md)](INSTALL.md)**:
   Covers both **Method A (Standard USB Media via Calamares)** and **Method B (USB-Less Local Partition Deployment via `install-from-existing.sh`)**, BIOS/UEFI firmware settings, multi-GPU kernel KMS flags, Windows dual-boot probing, and post-install Tier-2 lab bootstrapping.

2. **[Keyboard Shortcuts Reference (SHORTCUTS.md)](SHORTCUTS.md)**:
   Complete keybindings cheat sheet for Hyprland, window management, scratchpad workflow (`Super+S`, `Super+Shift+A`, `Super+Z`), power controls (`Super+L`), media OSD popups, and Arabic layout aliases.

3. **[First-Time Personalization Guide (SETUP.md)](SETUP.md)**:
   Post-installation customization manual covering hostname, timezone, Git identity, SSH keys, AUR package management (`yay`), and hardware tuning.

---

## License

Released under the [MIT License](LICENSE).
