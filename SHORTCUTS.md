# SecLegion OS — Keyboard Shortcuts & Workflow Reference
**Architecture:** Hyprland Wayland Compositor (with Arabic layout aliases)  
**Lead Architect:** Ammar Elkholy (SecLegion Edition)  
**Tracking File:** `SHORTCUTS.md`

---

## ⚡ Core Applications

| Shortcut (US) | Arabic Key | Action | Binary / Script |
|:---|:---:|:---|:---|
| `Super + Return` / `KP_Enter` | `Super + ف` | Open GPU Terminal | `kitty` |
| `Super + T` | `Super + ف` | Open Terminal (Alternate) | `kitty` |
| `Super + E` | `Super + ث` | Open File Manager (0.75 Opacity) | `thunar` |
| `Super + Y` | `Super + غ` | Open Terminal File Manager | `yazi` |
| `Super + D` / `Super + R` | `Super + ي` / `Super + ق` | Open Cyber App Launcher (Rofi) | `rofi -show drun` |
| `Super + B` | `Super + لا` | Open Web Browser | `brave` / `firefox` |
| `Super + Shift + Return` | `Super + Shift + ف` | Open Primary IDE / Editor | `antigravity-ide` / `code` |

---

## 🔒 Power, Lock & Session Controls

| Shortcut | Arabic Key | Action | Notes |
|:---|:---:|:---|:---|
| **`Super + L`** | `Super + م` | **Open Logout & Power Menu (Wlogout)** | Pressing `Super + L` again closes it |
| **`Super + Shift + L`** | `Super + Shift + م` | **Lock Screen Immediately** | Triggers `hyprlock` |
| `Super + Escape` / `Backspace` | — | Backup Power Menu Shortcut | Calls `ae-osd.sh logout-menu` |

---

## 📥 Scratchpad (Special Workspace)

| Shortcut | Arabic Key | Action | OSD Popup |
|:---|:---:|:---|:---|
| **`Super + S`** | `Super + س` | Toggle Scratchpad Show / Hide | Slide animation |
| **`Super + Shift + A`** | `Super + Shift + ش` | Send Focused Window **Into** Scratchpad | 📥 *Sent to Scratchpad* |
| **`Super + Z`** | `Super + ئ` | Restore Window **Back to Active Workspace** | 📤 *Window Restored* |

---

## 🪟 Window Management & Tiling

| Shortcut | Action | Notes |
|:---|:---|:---|
| `Super + Q` / `Super + C` | Close Active Window | Closes focused client |
| `Super + F` | Toggle Fullscreen | Maximize display coverage |
| `Super + V` / `Super + W` | Toggle Floating Mode | Switch between tiled and floating |
| `Super + P` | Toggle Pseudo-Tiled Mode | Pin window aspect ratio |
| `Super + J` | Toggle Split Orientation | Switch horizontal / vertical split |
| `Super + Space` | Toggle Layout / Keyboard | Dual function (layout script / input toggle) |

---

## 🎯 Navigation & Window Movement

| Action | Arrow Keys | Vim-Style Keys |
|:---|:---|:---|
| **Move Focus** | `Super + Left / Right / Up / Down` | `Super + H` (left), `Super + K` (up), `Super + J` (down) |
| **Move Window** | `Super + Shift + Left / Right / Up / Down` | `Super + Shift + H / K / J` |
| **Switch Workspace** | `Super + 1` through `Super + 0` | Workspaces 1 through 10 |
| **Send to Workspace**| `Super + Shift + 1` through `Super + Shift + 0` | Moves client to workspace |

---

## 🎨 System HUD, Audio & Personalization

| Shortcut | Action | Feedback |
|:---|:---|:---|
| `Super + N` | Open SwayNC Notification Center & Control Panel | Slide-in panel |
| `Super + Shift + B` | Toggle Waybar Visibility | Show / Hide status bar |
| `Super + Shift + V` | Open CopyQ Clipboard History | Floating clipboard manager |
| `Super + Shift + W` | Static Wallpaper Selector (Yazi / Rofi) | Smooth 60 FPS wipe transition |
| `Super + Ctrl + W` | **Live / Animated Wallpaper Engine** | Plays `.gif`, `.webp` & `.mp4` loops |
| Volume Keys | Volume Up / Down / Mute | Neon cyber OSD pop-up |
| Brightness Keys| Brightness Up / Down | Neon cyber OSD pop-up |
| `Super + F10 / F11 / F12` | Media Play / Previous / Next | Cyber OSD pop-up |

---

## 📸 Screenshots & Annotation

| Shortcut | Action | Target |
|:---|:---|:---|
| `Print` or `Super + Shift + S` | Capture Selected Area | Clipboard + `~/Pictures/Screenshots/` |
| `Shift + Print` | Capture Selected Area & Open Annotator | `swappy` image markup editor |
| `Super + Print` | Capture Focused Window | Active client capture |
| `Ctrl + Print` | Capture Entire Display | Full monitor snapshot |
