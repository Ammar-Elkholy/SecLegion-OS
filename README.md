# AE_ARCH Linux 🚀
> A curated, high-performance, and futuristic Arch Linux distribution designed for Cybersecurity, Penetration Testing, and Power Users.

---

## 🌟 Highlights & Features

### 🖥️ 1. Dual Desktop Session (GNOME + Hyprland)
* **GNOME Wayland:** Clean, elegant dark mode with `Catppuccin-Mocha` styling, `Tela-circle-dracula` icons, and `Teal` accent colors.
* **Hyprland Compositor:** Fluid Wayland tiling window manager featuring:
  * **Waybar:** Custom system status bar with audio, network, battery, and workspace indicators.
  * **Rofi-Wayland:** Fast application launcher and wallpaper switcher.
  * **Wallust:** Dynamic pywal-style color palette generation based on active wallpapers.
  * **SwayNC & Wlogout:** Modern notification center and sleek lock/power dashboard.

### ⚡ 2. Terminal & OffSec Operator HUD
* **Kitty GPU Terminal:** 85% opacity with Gaussian background blur, smooth cursor shaders, and ligatures.
* **Shell (Zsh):** Pre-configured with **Starship** & **Powerlevel10k**, featuring:
  * **Live Pentest Badges:** Displays active `tun0` VPN IP (HackTheBox / TryHackMe / WireGuard) and target IP locks directly in the prompt.
  * **Modern CLI Suite:** `eza` (replaces `ls` with file icons), `bat` (syntax highlighted `cat`), `fzf` (fuzzy search), and `zoxide` (`z` smart jumper).
  * **System Banner:** Custom `fastfetch` system specs banner on launch.

### 🎮 3. Multi-GPU & Hardware Portability
* **AMD Radeon:** Full open-source Mesa + RADV Vulkan support.
* **Intel:** Modern Intel Iris Xe & HD Graphics with VA-API hardware acceleration.
* **NVIDIA:** NVIDIA Open-DKMS with `nvidia-prime` support for laptop hybrid graphics switching.
* **Universal Audio:** Complete **PipeWire** stack with WirePlumber and high-fidelity Bluetooth codecs (LDAC, aptX, SBC-XQ).
* **Laptop Microphones:** `sof-firmware` included for modern laptop audio DSP compatibility.

### 📁 4. Clean File Management
* **GUI:** **Nautilus** (standardized across GNOME and Hyprland with dark GTK theme).
* **CLI:** **Yazi** (blazing-fast terminal file manager with in-terminal image previews).

### 🛠️ 5. Installer Options
* **Calamares GUI Installer:** 1-click graphical installer with custom branding, language, partitioning, and user setup.
* **Archinstall:** Native guided CLI installer with customizable profiles.

---

## 📁 Repository Structure

```text
AE_ARCH/
├── build.sh                  # One-command ISO build script
├── clean_host_system.sh      # De-bloat and system cleanup script
├── packages.x86_64           # Curated list of all official packages
├── pacman.conf               # Pacman configuration (multilib enabled)
├── profiledef.sh             # ISO metadata, bootmodes, and permissions
└── airootfs/                 # Root filesystem overlay
    ├── etc/
    │   ├── skel/             # Universal user blueprint (Hyprland, Kitty, Zsh, Wallpapers)
    │   ├── dconf/            # Global GNOME defaults (Catppuccin, Dark Mode)
    │   └── calamares/        # Calamares graphical installer configuration
    └── usr/share/
        ├── backgrounds/      # 140MB+ curated wallpaper collection
        ├── themes/           # 13 GTK themes (Catppuccin, Tokyo Night, Graphite Mono)
        └── icons/            # Tela-circle icon packs and Bibata cursors
```

---

## 🔨 How to Build the ISO

### Prerequisites
Ensure `archiso` is installed on your host system:
```bash
sudo pacman -S --needed archiso
```

### Build the ISO
Run the automated build script with root privileges:
```bash
sudo bash build.sh
```
The finished ISO image (`AE_ARCH-YYYY.MM.DD-x86_64.iso`) will be saved in the `./output/` directory alongside its SHA256 checksum.

---

## 💾 Burning to a USB Drive (32GB+)

### Option A: Direct Write (`dd`)
```bash
sudo dd if=output/AE_ARCH-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
```
*(Replace `/dev/sdX` with your USB drive identifier from `lsblk`).*

### Option B: Ventoy (Recommended)
1. Install [Ventoy](https://www.ventoy.net/) onto your USB drive.
2. Drag and drop `AE_ARCH-*.iso` directly into the USB drive.

---

## ⌨️ Hyprland Default Keybindings

| Keybinding | Action |
| :--- | :--- |
| `Super + Return` | Open Kitty Terminal |
| `Super + Space` | Open Rofi App Launcher |
| `Super + E` | Open Nautilus File Manager |
| `Super + Q` | Close Active Window |
| `Super + V` | Toggle Floating Window |
| `Super + F` | Toggle Fullscreen |
| `Super + M` | Open Wlogout Power Menu |
| `Super + W` | Cycle / Select Wallpaper via Yazi |
| `Super + 1..9` | Switch to Workspace 1..9 |
| `Super + Shift + 1..9` | Move Window to Workspace 1..9 |

---

## 📄 License
Released under the [MIT License](LICENSE).
