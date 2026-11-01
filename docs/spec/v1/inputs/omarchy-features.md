# Omarchy feature inventory (research, 2026-10-14)

Primary sources: shallow clone of github.com/omacom/omarchy (moved from basecamp/omarchy), default branch `quattro`, HEAD 84cfb93 (2026-10-14, `version` = 4.0.0.alpha); in-repo `manual/`; GitHub releases feed; omarchy-iso README. Latest release **v4.0.4 (2026-09-15)**; v4.0.0 "Quattro" 2026-08-14. **Licence: MIT** ("Copyright (c) David Heinemeier Hansson"); omarchy-iso MIT (Anton Hvornum). Reuse needs notice retained; wallpapers/logo/branding and omarchy-pkgs apps may carry other rights (UNVERIFIED).

## Architecture shift in v4
The desktop shell is now **one Quickshell process** (`shell/shell.qml`, plugins: agents, background, bar, clipboard, dock, emojis, image-picker, lock, menu, notifications, osd, panels, polkit, reminders), replacing Waybar, Walker, Mako, SwayOSD, hyprlock, hypridle, swaybg and polkit-gnome. Hyprland config is Lua (`default/hypr/*.lua`, user `~/.config/hypr/{hyprland,bindings,autostart,input,looknfeel,monitors}.lua`). Settings in `~/.config/omarchy/shell.json`, IPC via `omarchy-shell`. Quickshell is in Arch `extra`.

## Features
| Feature | Implementation | Behaviour |
|---|---|---|
| Installer/ISO | omarchy-iso, "Omarchy Configurator" driving **archinstall**; bundled mirror; signed ISO + sha256; nightly ISO and qcow2 | full-disk or free-space dual boot; Secure Boot/TPM off; 1–5 min; deferred "install for another owner"; unattended config from 2nd drive; 50 UI languages |
| LUKS | default on (opt-out); user password = LUKS password; `omarchy-drive-password`, rekey | btrfs |
| Autologin after LUKS | SDDM autologin conf on encrypted installs; QML SDDM theme | unlock once at boot → desktop |
| Plymouth | per-theme unlock screen (`omarchy-plymouth-*`) | Style > Unlock |
| Bootloader/snapshots | **Limine + limine-snapper-sync + limine-mkinitcpio-hook**, UKIs on ESP; snapper root (limit 5, timeline off); `omarchy-snapshot create/restore` | snapshot every update; snapshot entries in boot menu; restore prompt after booting a snapshot (root only); Direct Boot option; factory Reset to baseline snapshot |
| Kernel | `linux-omarchy` default since v4.0.4; `linux-t2` | desktop/gaming tuning |
| Menu | `omarchy-menu` → shell plugin; JSONC definition + user extensions | **Super+Space**; Apps, Learn, Trigger, Style, Setup, Install, Remove, Update, About, System; **Super+Esc** system menu (screensaver/lock/suspend/hibernate/logout/reboot/firmware/shutdown) |
| Keybinding help | `omarchy-menu-keybindings` | Super+K |
| Launcher | shell menu / app grid | Super+Space / Super+Alt+Space |
| Notifications | shell plugin | Super+, dismiss; +Shift all; +Ctrl DND; history |
| OSD | shell plugin | Alt+key = 1% steps |
| Lock/idle | shell lock; idle in shell.json (screensaver 150 s, lock 300 s) | Super+Ctrl+L lock; Super+Ctrl+I stay awake |
| Screensaver | `omarchy-screensaver`: terminaltexteffects ASCII art in a terminal | custom PNG/SVG logo → ASCII |
| Night light | hyprsunset | Super+Ctrl+N 4000K/6500K |
| Capture | grim+slurp; gpu-screen-recorder (desktop audio, mic, webcam overlay); OCR (tesseract); QR (zbar) | Print, Alt+Print record, Super+Ctrl+Print OCR, Super+Ctrl+C capture menu |
| Colour picker | hyprpicker | Super+Print |
| Emoji/clipboard | shell plugins, XCompose | Super+Ctrl+E / Super+Ctrl+V; Super+C/V unified copy/paste |
| Power profiles | power-profiles-daemon, AC/battery memory, auto-switch | Super+Ctrl+P |
| Battery | low-battery notification + hooks | Super+Ctrl+Alt+B |
| Hibernation | btrfs `/swap` subvolume `mkswapfile` sized to RAM + resume | System menu |
| Fingerprint | fprintd for sudo, polkit, lock | Setup > Security |
| FIDO2 | pam-u2f for sudo/polkit | Setup > Security |
| Security defaults | ufw default-deny + ufw-docker; sshd off until enabled (rate-limited); user not in docker group; timed passwordless sudo with red bar; pacman guard blocks raw `-Syu` | |
| Themes | 23 themes; `colors.toml`, backgrounds, preview, unlock image, icons, neovim/vscode/keyboard RGB; `omarchy-theme-set` renders `default/themed/*.tpl` for terminals, btop, chromium, hyprland, editors, shell; user `.tpl` overrides; `omarchy-theme-install <git>` **strips code (lua, terminal configs, vscode.json)**; Aether GUI theme maker | Super+Ctrl+Shift+Space theme picker; Super+Ctrl+Space background |
| Web apps | `omarchy-webapp-install` → .desktop running Chromium `--app` | Super+Shift+letter binds |
| TUI apps | `omarchy-tui-install` | btop, lazygit, etc. |
| Updates | `omarchy-update`: space check → snapshot → keyring → packages → **`omarchy-migrate`** (169 timestamped migrations) → orphans → service restarts → hooks → mise → AUR → boot verification | channels stable/rc/edge/dev (stable = Arch mirror held one month behind) |
| Reset | `omarchy-refresh-config <path>` (backs up), reinstall configs, full reset; fwupd firmware | |
| Dev env | `omarchy-install-dev-env <lang>` via mise; docker DBs on 127.0.0.1 | |
| Gaming | Install > Gaming: Steam, RetroArch, Lutris, Heroic, Minecraft, cloud gaming, Xbox controllers; lib32 GPU libs; Moonlight | |
| AI | lazy mise stubs for claude, codex, opencode, copilot, etc.; default agent setting; bar agents panel (subscription usage meters, account switching); coredump → agent crash diagnosis; Omarchy skill in `~/.claude/skills`; Install > AI (desktop apps, LM Studio, Ollama); agent picker Super+Shift+Ctrl+A; dictation (voxtype/superwhisper) | |
| Hardware | lspci NVIDIA: GSP → nvidia-open-dkms, older → nvidia-580xx-dkms; early KMS; hybrid via supergfxctl toggle; vendor scripts (Framework, ASUS ROG, Dell XPS, Surface, Tuxedo, Intel IPU7, Broadcom wl, Apple T2, DDC brightness, lid, VM detection) | |
| Other v4 | plugin system, dock, reminders, world clock, i18n, lifecycle hooks (`omarchy-hook`), factory reset/hand-over, unattended install, Windows VM, Tailscale/LocalSend sharing, transcode, in-guest acceptance tests | |

UNVERIFIED: Apple Silicon support; hibernation default; omarchy.org site; UKI use throughout; limine.conf details.
