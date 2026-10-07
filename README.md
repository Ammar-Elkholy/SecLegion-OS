# SecLegion OS

> **"We develop Mindsets — Securing Minds & Systems."**

**SecLegion OS** is an advanced, production-grade Offensive Security & Penetration Testing workstation built upon Arch Linux by **Ammar Elkholy**.

Engineered with dual **Hyprland (Wayland)** and **GNOME** environments, native **BlackArch** security suites, complete **KVM/QEMU** hypervisor virtualization, and intelligent auto-detection built to unleash **full-power NVIDIA and AMD GPU hardware acceleration** out of the box with zero manual configuration.

---

## Brand Identity & Color Palette

SecLegion OS adheres strictly to an aggressive cyber-security aesthetic:
- **Glitch White (`#FFFFFF`):** High-contrast typography and icon highlights
- **Matrix Green (`#00FF88`):** Active window borders, success indicators, primary operational accent
- **Cyberpunk Cyan (`#00F0FF`):** Focus rings, interactive elements, section headers
- **Dark Teal Carbon (`#0B1E1C`):** Panels, inactive borders, card backgrounds
- **Matrix Obsidian (`#050F0E`):** Base workspace canvas, terminal backdrop

---

## What makes it different

### Two-Tier Software Provisioning Model

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

### Full-Power GPU Acceleration (NVIDIA & AMD Out-of-the-Box)

SecLegion OS automatically detects your hardware architecture at boot and runs your GPU at **100% full power** without manual xorg/modprobe tinkering:

- **NVIDIA GeForce / RTX (Full Power & Wayland Native):**
  - Native driver integration with `nvidia-open-dkms`, `nvidia-utils`, and 32-bit `lib32-nvidia-utils`.
  - Kernel modesetting enabled (`nvidia-drm.modeset=1 fbdev=1 NVreg_PreserveVideoMemoryAllocations=1`).
  - Seamless Wayland hardware acceleration across Hyprland with automatic `GBM_BACKEND=nvidia-drm` and `LIBVA_DRIVER_NAME=nvidia`.
  - On-demand high-performance discrete GPU offloading via `seclegion-gpu-run` and `prime-run`.
  - Full CUDA / OpenCL acceleration for Hashcat, John the Ripper, and cryptographic cracking suites.

- **AMD Radeon (Full Power Vulkan & ACO):**
  - High-performance Mesa stack with RADV Vulkan and AMD ACO shader compiler.
  - Automatic `DRI_PRIME=1` discrete GPU offload switching for dual-GPU laptops.
  - Zero-tear Wayland rendering and ultra-low latency display pipelines.

- **Intel Iris Xe / Arc:**
  - High-efficiency VA-API hardware decoding and modern Vulkan support.

- **Dynamic DRM Display Resolver (`seclegion-gpu.sh`):**
  - Automatically identifies primary and secondary DRM cards (`/dev/dri/card*`) at login and dynamically exports `AQ_DRM_DEVICES` in Hyprland, eliminating black screens and multi-monitor stutter.

- **Audio & Media:**
  - Complete PipeWire stack with WirePlumber, LDAC, and aptX Bluetooth codecs.

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


---

## Quick Start: Install in 3 Easy Steps

Getting SecLegion OS running takes just a few minutes:

### 1. Get the ISO (Download or Build)
* **🌐 Google Drive Download (Fastest — Ready to Use):**  
  👉 **[Download SecLegion OS 2026.10 ISO (Google Drive)](https://drive.google.com/file/d/11f2Hd-zPPgYxbT-jacdcGyo21b_tjsVs/view?usp=sharing)** *(File: `SecLegion-OS-2026.10.08-x86_64.iso`, Size: 3.7 GB)*  
  *(Also mirrored on [GitHub Releases](https://github.com/Ammar-Elkholy/SecLegion-OS/releases))*
* **🤖 Build from Source (If you prefer compiling it yourself):**  
  If you are running Arch Linux and don't want to download the ISO, build it in 1 command:
  ```bash
  git clone https://github.com/Ammar-Elkholy/SecLegion-OS.git
  cd SecLegion-OS
  sudo pacman -S --needed archiso
  sudo bash build.sh
  ```
  *(The 3.7GB release ISO compiles cleanly into `./output/`)*

### 2. Put it on a USB Drive (8GB+)
- **Easiest Everywhere (Ventoy — Recommended):** Install [Ventoy](https://www.ventoy.net/) on your USB and drag-and-drop the `.iso` file onto it.
- **Windows (Rufus):** Flash with [Rufus](https://rufus.ie/) (GPT / UEFI / DD Image mode).
- **Linux (dd):**
  ```bash
  sudo dd if=output/SecLegion-OS-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
  ```

### 3. Boot & Install (One-Click GUI)
1. Boot from your USB (ensure **Secure Boot is Disabled** in BIOS).
2. Select **SecLegion OS** from the cyber GRUB menu.
3. Launch the visual **Calamares Installer** from the desktop to install with a few clicks!

> **Need USB-less direct install, dual-boot setup, or advanced options?**  
> Check out the complete [Step-by-Step Installation Guide (HOW_TO_INSTALL.md)](HOW_TO_INSTALL.md).

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

## Documentation & Guides

Comprehensive documentation is provided across dedicated manuals:

1. **[Step-by-Step Installation Guide (HOW_TO_INSTALL.md)](HOW_TO_INSTALL.md)**:
   Covers both **Method A (Standard USB Media via Calamares)** and **Method B (USB-Less Local Partition Deployment via `install-from-existing.sh`)**, BIOS/UEFI firmware settings, multi-GPU kernel KMS flags, Windows dual-boot probing, and post-install Tier-2 lab bootstrapping.

2. **[Keyboard Shortcuts Reference (SHORTCUTS.md)](SHORTCUTS.md)**:
   Complete keybindings cheat sheet for Hyprland, window management, scratchpad workflow (`Super+S`, `Super+Shift+A`, `Super+Z`), power controls (`Super+L`), media OSD popups, and Arabic layout aliases.

3. **[First-Time Personalization Guide (SETUP.md)](SETUP.md)**:
   Post-installation customization manual covering hostname, timezone, Git identity, SSH keys, AUR package management (`yay`), and hardware tuning.

---

## License & Attribution

Copyright © 2026 **Ammar Elkholy**. All rights reserved.

SecLegion OS is published under the [SecLegion OS Source and Distribution License](LICENSE).
Personal, educational, and authorized offensive security research use is permitted. Redistribution, commercialization, re-branding, or derivative distribution is strictly prohibited without prior express written approval from **Ammar Elkholy**.
