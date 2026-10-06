# First-Time Setup Guide

Welcome to AE_ARCH Linux (SecLegion Edition) by Ammar Elkholy.

This guide walks you through everything to personalize **after your first login** — username, hostname, timezone, appearance, git identity, SSH keys, AUR packages, and hardware tweaks.

> **Need to install the OS first?** See the full [Installation & Setup Guide](INSTALL_GUIDE.md) for media flashing, BIOS configuration, and the Calamares installer walkthrough.

If you installed via Calamares (the graphical installer), your username and password are already set. Start from whichever section is still relevant.

---

## 1 — Username & Password

During Calamares installation you were asked to set these. If you need to change them after the fact:

```bash
# Change your username (while logged in as root or another user)
usermod -l newname oldname
usermod -d /home/newname -m newname

# Change your password
passwd yourusername
```

---

## 2 — Hostname (Your Computer's Name)

This is the name that appears in your terminal prompt and on the network.

```bash
# Set it permanently
sudo hostnamectl set-hostname your-hostname

# Verify
hostnamectl
```

Pick something short, lowercase, no spaces — e.g. `legion`, `ammar-pc`, `secbox`.

Also update `/etc/hosts` so it matches:

```bash
sudo nano /etc/hosts
```

Make sure this line exists (replace `your-hostname`):

```
127.0.1.1   your-hostname
```

---

## 3 — Timezone

```bash
# Find your timezone
timedatectl list-timezones | grep Cairo    # or your city

# Set it
sudo timedatectl set-timezone Africa/Cairo

# Sync hardware clock
sudo timedatectl set-ntp true
```

---

## 4 — Locale & Language

The system ships with `en_US.UTF-8`. If you want to add Arabic or another locale:

```bash
sudo nano /etc/locale.gen
# Uncomment the lines you want, e.g.:
#   ar_EG.UTF-8 UTF-8
#   en_US.UTF-8 UTF-8

sudo locale-gen
```

To set the system default language:

```bash
sudo localectl set-locale LANG=en_US.UTF-8
```

---

## 5 — Keyboard Layout

If your keyboard layout isn't set correctly after install:

```bash
# List available layouts
localectl list-keymaps

# Set your layout (e.g. us, ar, de)
sudo localectl set-keymap us
```

Inside Hyprland, the layout is toggled live with `Super + Space`. To change the default layout permanently, edit:

```
~/.config/hypr/modules/keybinds.lua   ← toggle-layout.sh is called from here
~/.config/hypr/hyprland.lua           ← look for "input" section, set kb_layout
```

---

## 6 — Wallpaper & Live Wallpapers

**Hyprland:**
- **Static Wallpapers (`Super + Shift + W`)**: Opens Yazi (or Rofi fallback) to select any wallpaper from `~/Pictures/Wallpapers/` with smooth wipe transitions.
- **Live / Video Wallpapers (`Super + Ctrl + W`)**: Opens the live wallpaper selector from `~/Videos/LiveWallpapers/`.
  - Supports animated **GIF** and **WebP** loops natively using `awww`.
  - Supports video files (**MP4**, **WebM**, **MKV**).
  - For hardware-accelerated 60 FPS video wallpaper playback, install `mpvpaper`:
    ```bash
    yay -S mpvpaper
    ```
  - If `mpvpaper` is not installed, AE_ARCH automatically optimizes the video loop using `ffmpeg` and plays it via the `awww` engine.

Your active wallpaper choice (static or live) is saved to `~/.cache/current_wallpaper` and restored on login automatically via `restore-wallpaper.sh`.

**GNOME:**
- Right-click the desktop → Change Background
- Or open Settings → Appearance

Static wallpapers are stored in `/usr/share/backgrounds/` and `~/Pictures/Wallpapers/`.
Live wallpapers are stored in `~/Videos/LiveWallpapers/`.

---

## 7 — GNOME Appearance

Open **GNOME Tweaks** (already installed):

```bash
gnome-tweaks
```

Key settings to personalize:
- **Appearance → Shell** — pick a GTK theme (Catppuccin-Mocha is the default)
- **Appearance → Icons** — Tela-circle-dracula is the default
- **Fonts** — JetBrainsMono Nerd Font is pre-installed
- **Window Titlebars** — button placement, double-click action

For GNOME extensions, open **Extension Manager** (also pre-installed).

---

## 8 — Terminal Prompt (Starship)

Your prompt is configured via Starship. Edit the config to add or remove modules:

```bash
nano ~/.config/starship.toml
```

The default prompt shows:
- Directory, git branch, git status
- Active tun0 VPN IP (auto-detected for HackTheBox/TryHackMe)
- Language versions (Python, Node, Rust, etc.)

---

## 9 — Default Shell

Zsh is the default. If you want to change it:

```bash
# List available shells
chsh -l

# Change your shell
chsh -s /usr/bin/zsh    # or /usr/bin/bash, /usr/bin/fish
```

---

## 10 — Git Identity

If you use Git, set your identity so commits are signed with your name:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global core.editor nvim    # or nano, code, etc.
```

---

## 11 — SSH Keys

```bash
# Generate a new key pair
ssh-keygen -t ed25519 -C "your@email.com"

# Add to ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Copy the public key to add to GitHub / servers
cat ~/.ssh/id_ed25519.pub
```

---

## 12 — Installing More Software

AUR packages (community packages not in the official repos) can be installed with:

```bash
# AUR helper isn't pre-installed — install yay first
git clone https://aur.archlinux.org/yay.git /tmp/yay
cd /tmp/yay && makepkg -si

# Then use yay like pacman
yay -S package-name
```

Official packages use pacman as normal:

```bash
sudo pacman -S package-name
```

---

## 13 — Hyprland Config Files

Everything about how Hyprland behaves lives in `~/.config/hypr/`. Key files:

| File | What it controls |
| :--- | :--- |
| `hyprland.lua` | Main config — monitors, input, general settings |
| `modules/keybinds.lua` | All keyboard shortcuts |
| `modules/autostart.lua` | Apps that launch on login |
| `modules/animations.lua` | Window animations and curves |
| `modules/windowrules.lua` | Per-app rules (floating, opacity, etc.) |
| `hyprlock.conf` | Lock screen appearance |
| `hyprpaper.conf` | Wallpaper settings |
| `hypridle.conf` | Idle/sleep timeout settings |

After editing any of these, reload Hyprland without logging out:

```bash
hyprctl reload
```

---

## 14 — Monitors & Display Setup

If you have multiple monitors or a specific resolution/refresh rate:

```bash
# List your connected outputs
hyprctl monitors
```

Then edit `~/.config/hypr/modules/monitor.lua` to set your layout. Example:

```lua
-- 1080p main monitor at 144hz, second monitor to the right
hl.monitor("eDP-1",   "1920x1080@144", "0x0",    1)
hl.monitor("HDMI-A-1","1920x1080@60",  "1920x0",  1)
```

---

## 15 — Auto-Login (Optional)

If you want to skip the login screen:

```bash
sudo nano /etc/gdm/custom.conf
```

Add under `[daemon]`:

```ini
AutomaticLoginEnable=true
AutomaticLogin=yourusername
```

---

## Summary — Minimum You Should Do

| Task | Command / Location |
| :--- | :--- |
| Set hostname | `sudo hostnamectl set-hostname name` |
| Set timezone | `sudo timedatectl set-timezone Region/City` |
| Set git identity | `git config --global user.name / user.email` |
| Generate SSH key | `ssh-keygen -t ed25519` |
| Pick wallpaper | `Super + Shift + W` in Hyprland |
| Adjust appearance | `gnome-tweaks` in GNOME |
| Edit keybinds | `~/.config/hypr/modules/keybinds.lua` |

Everything else is optional and can be done whenever you feel like it.
