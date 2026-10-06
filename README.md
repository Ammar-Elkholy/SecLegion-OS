# AE_ARCH Linux 🚀

> A curated, high-performance Arch Linux distribution by **Ammar Elkholy** — built for Cybersecurity, Penetration Testing & Power Users.
> SecLegion Edition | Neon Cyberpunk Aesthetic | Hyprland + GNOME | Universal Hardware

---

## 🌟 Highlights & Features

### 🖥️ 1. Dual Desktop Session (GNOME + Hyprland)
- **GNOME Wayland:** Clean dark mode with `Catppuccin-Mocha` styling, `Tela-circle-dracula` icons.
- **Hyprland:** Fluid Wayland tiling WM with:
  - **Waybar** — custom system bar (audio, network, battery, workspaces)
  - **Rofi** — fast app launcher
  - **Wallust** — dynamic pywal-style palette from wallpaper
  - **SwayNC** — notification center & Control Panel
  - **Wlogout** — sleek power dashboard
  - **ae-osd** — branded neon OSD popups for volume/brightness/media

### ⚡ 2. Terminal & OffSec Operator HUD
- **Kitty** — GPU terminal with blur, opacity, shaders, ligatures
- **Zsh + Starship** — tun0 VPN badges, HackTheBox/TryHackMe prompt
- **Modern CLI:** `eza` (ls), `bat` (cat), `fzf`, `zoxide`, `fastfetch`

### 🎮 3. Multi-GPU & Hardware Portability
- **AMD Radeon** — Mesa + RADV Vulkan (open source, fully featured)
- **Intel** — Iris Xe / HD Graphics with VA-API
- **NVIDIA** — Open-DKMS + nvidia-prime for hybrid laptop switching
- **Audio** — Full PipeWire + WirePlumber + Bluetooth HiFi (LDAC, aptX)

### 📁 4. Clean File Management
- **GUI:** Nautilus (native GNOME, dark theme)
- **CLI:** Yazi (terminal file manager with image previews)

### 🛠️ 5. Installer Options
- **Calamares GUI** — 1-click graphical installer with SecLegion branding
- **Archinstall** — native guided CLI installer

---

## 📁 Repository Structure

```text
AE_ARCH/
├── build.sh                  # One-command ISO build script
├── clean_host_system.sh      # De-bloat and system cleanup
├── packages.x86_64           # All official packages
├── pacman.conf               # Pacman config (multilib enabled)
├── profiledef.sh             # ISO metadata, bootmodes, permissions
├── EDGE_CASES.md             # Documented issues & solutions matrix
└── airootfs/                 # Root filesystem overlay
    ├── etc/
    │   ├── skel/             # User blueprint (Hyprland, Kitty, Zsh, Dunst)
    │   │   └── .config/
    │   │       ├── hypr/     # Hyprland config + ae-osd.sh + scripts
    │   │       ├── dunst/    # Neon-branded OSD notification config
    │   │       ├── waybar/   # Status bar config
    │   │       ├── rofi/     # App launcher config
    │   │       ├── kitty/    # Terminal config
    │   │       ├── yazi/     # File manager config
    │   │       └── swaync/   # Notification center
    │   ├── dconf/            # GNOME global defaults
    │   └── calamares/        # GUI installer config + SecLegion branding
    └── usr/share/
        ├── backgrounds/      # Curated wallpaper collection
        ├── themes/           # GTK themes (Catppuccin, Tokyo Night, Graphite)
        └── icons/            # Tela-circle icon packs + Bibata cursors
```

---

## 🔨 Building the ISO

### Prerequisites
```bash
sudo pacman -S --needed archiso
```

### Build
```bash
cd /path/to/AE_ARCH
sudo bash build.sh
```
Output: `./output/AE_ARCH-YYYY.MM.DD-x86_64.iso` + `sha256sum.txt`

> **💡 Size Note:** The expected ISO size is **3–4 GB** (not 32 GB). A 32 GB USB is more than enough — even an 8 GB USB will work. 32 GB gives you room to put multiple ISOs on a Ventoy drive.

---

## 💾 Flashing to USB

Pick the method that matches your OS:

### 🐧 Linux — `dd` (Direct Write)
```bash
# Find your USB drive:
lsblk

# Flash it (replace sdX with your device, e.g. sdb):
sudo dd if=output/AE_ARCH-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
sync
```
> ⚠️ Triple-check the device path. `dd` will overwrite everything on it.

### 🐧 Linux — Ventoy (Recommended for multi-boot)
```bash
# Install Ventoy onto USB (replace sdX):
sudo bash ventoy -i /dev/sdX

# Then just copy the ISO into the USB drive:
cp output/AE_ARCH-*.iso /run/media/$USER/Ventoy/
```
Ventoy lets you put **multiple ISOs** on one USB — boot any of them from a menu.

### 🍎 macOS — `dd`
```bash
# Find your USB disk number:
diskutil list

# Unmount it first (replace diskN with your disk, e.g. disk2):
diskutil unmountDisk /dev/diskN

# Flash it:
sudo dd if=output/AE_ARCH-*.iso of=/dev/rdiskN bs=4m
```
> Use `/dev/rdiskN` (raw device) — it's ~10× faster on macOS.

### 🍎 macOS — Balena Etcher (GUI, easiest)
1. Download [Balena Etcher](https://etcher.balena.io/) — free, open source
2. Open Etcher → **Flash from file** → select the `.iso`
3. Select your USB drive → **Flash!**

### 🪟 Windows — Rufus (Recommended)
1. Download [Rufus](https://rufus.ie/) — free, portable, no install needed
2. Open Rufus → select your USB under **Device**
3. Click **SELECT** → choose the `.iso` file
4. **Partition scheme:** GPT | **Target system:** UEFI (non-CSM)
5. Click **START** → write in **DD Image mode** when asked
6. Wait for "READY" → done

### 🪟 Windows — Balena Etcher (GUI, simpler)
1. Download [Balena Etcher](https://etcher.balena.io/)
2. Flash from file → select `.iso` → select USB → Flash

### 🌐 All Platforms — Ventoy (Best for Power Users)
[Ventoy](https://www.ventoy.net/) works on Linux, macOS, and Windows:
- Install Ventoy to USB once
- Copy any `.iso` files into the USB (drag & drop)
- Boot from USB → pick your ISO from a beautiful menu
- Supports **multiple ISOs** on the same drive

---

## ⌨️ Hyprland Keybindings

### Core Apps
| Keybinding | Action |
| :--- | :--- |
| `Super + Return` | Open Kitty Terminal |
| `Super + T` | Open Kitty Terminal (alt) |
| `Super + E` | Open Nautilus File Manager |
| `Super + B` | Open Browser (Brave / Firefox) |
| `Super + D` / `Super + R` | Open Rofi App Launcher |
| `Super + Y` | Open Yazi File Manager (CLI) |

### Window Management
| Keybinding | Action |
| :--- | :--- |
| `Super + Q` / `Super + C` | Close Active Window |
| `Super + F` | Toggle Fullscreen |
| `Super + V` / `Super + W` | Toggle Floating |
| `Super + P` | Toggle Pseudo Tiling |
| `Super + J` | Toggle Split Direction |
| `Super + G` | Toggle Window Group (Tabs) |
| `Super + Tab` / `Super + Shift + Tab` | Next / Prev Tab in Group |

### Workspaces
| Keybinding | Action |
| :--- | :--- |
| `Super + 1–9, 0` | Switch to Workspace 1–10 |
| `Super + Shift + 1–9, 0` | Move Window to Workspace |
| `Super + S` | Toggle Scratchpad (special workspace) |
| `Super + Shift + A` | Move Window to Scratchpad |

### Focus & Move Windows
| Keybinding | Action |
| :--- | :--- |
| `Super + Arrow Keys` | Move Focus |
| `Super + H/L/K/M` | Move Focus (Vim style) |
| `Super + Shift + Arrow Keys` | Move Window |
| `Super + Shift + H/L/K/J` | Move Window (Vim style) |

### System
| Keybinding | Action |
| :--- | :--- |
| `Super + Space` | Toggle Keyboard Language |
| `Super + N` | Open Notification Center |
| `Super + Escape` / `Backspace` | Power Menu (Wlogout) |
| `Super + Shift + L` | Lock Screen (Hyprlock) |
| `Super + Shift + B` | Toggle Waybar |
| `Super + Shift + V` | Open Clipboard (CopyQ) |
| `Super + Shift + W` | Select Wallpaper (Yazi) |
| `Super + Ctrl + W` | Set Live Wallpaper |

### Screenshots
| Keybinding | Action |
| :--- | :--- |
| `Print` / `Super + Shift + S` | Screenshot Area → clipboard + save |
| `Shift + Print` | Screenshot Area → open in Swappy |
| `Super + Print` | Screenshot Active Window |
| `Ctrl + Print` | Screenshot Full Screen |

### Media & OSD (Branded Neon Popups)
| Keybinding | Action |
| :--- | :--- |
| Volume Up/Down/Mute keys | Volume OSD popup |
| Mic Mute key | Mic OSD popup |
| Brightness Up/Down keys | Brightness OSD popup |
| Play/Next/Prev keys | Media OSD popup |
| `Super + F10/F11/F12` | Media Play / Prev / Next |

---

## 📄 License
Released under the [MIT License](LICENSE).
