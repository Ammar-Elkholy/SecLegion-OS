# SecLegion OS: Asset Manifest & Placeholder Registry

This manifest establishes the decoupled asset pipeline for SecLegion OS. All system configurations, GRUB themes, Plymouth animations, Fastfetch visuals, and window manager stylesheets are hardcoded against these exact target filenames.

---

## 🎨 Official SecLegion Brand Palette
- **Glitch White:** `#FFFFFF`
- **Matrix Green:** `#00FF88` (Primary active accent, highlight, success)
- **Cyberpunk Cyan:** `#00F0FF` (Secondary accent, focus rings, headers)
- **Dark Teal Carbon:** `#0B1E1C` (Panels, inactive borders, card backgrounds)
- **Matrix Obsidian:** `#050F0E` (Base canvas, dark background, terminal surface)

---

## 📁 Asset Slots & Target Filenames

| Target File Path | Target Dimensions | Format | Description / System Consumer | Status |
|:---|:---:|:---:|:---|:---:|
| `assets/wallpapers/seclegion-wallpaper.png` | 1920×1080 / 3840×2160 | PNG | Default desktop wallpaper for Hyprland (`awww`), GNOME, and SDDM/GDM greeter | `[EMPTY SLOT]` |
| `assets/wallpapers/seclegion-grub.png` | 1920×1080 | PNG | High-resolution GRUB bootloader splash background | `[EMPTY SLOT]` |
| `assets/logos/seclegion-logo-transparent.png` | 512×512 | PNG | Transparent glitch circuit emblem for Calamares installer, Rofi, and SwayNC | `[EMPTY SLOT]` |
| `assets/logos/seclegion-avatar.png` | 256×256 | PNG | Default user avatar for GDM/SDDM greeters and lockscreen | `[EMPTY SLOT]` |
| `assets/themes/seclegion-spinner.png` | 128×128 | PNG | Centered animated spinner graphic for Plymouth boot splash | `[EMPTY SLOT]` |

---

## 🚀 Image Drop Instructions
Drop your image files directly into the paths above using these exact filenames:
1. `cp /path/to/your_wallpaper.png assets/wallpapers/seclegion-wallpaper.png`
2. `cp /path/to/your_grub_splash.png assets/wallpapers/seclegion-grub.png`
3. `cp /path/to/your_logo.png assets/logos/seclegion-logo-transparent.png`
4. `cp /path/to/your_avatar.png assets/logos/seclegion-avatar.png`
5. `cp /path/to/your_spinner.png assets/themes/seclegion-spinner.png`
