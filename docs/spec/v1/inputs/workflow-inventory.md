# Owner's current desktop — raw migration inventory (2026-10-14)

Source: read-only audit of the owner's live machine (Hyprland 0.56.2, Lua config). No secrets recorded. This is the input for `docs/current-workflow-migration.md`. "S" = SUPER.

## 1. Keybinds (107 binds in `hyprctl binds`)
| Keys | Arabic alias | Action | Notes |
|---|---|---|---|
| S+Return / S+KP_Enter / S+T | Arabic_feh (T) | kitty | |
| S+Shift+Return / S+Shift+KP_Enter / S+I | — | antigravity-ide | AUR |
| S+E | Arabic_theh (E) | thunar | |
| S+B | — | `brave \|\| firefox` | brave-bin AUR |
| S+D / S+R | Arabic_yeh (D), Arabic_qaf (R) | toggle rofi drun | |
| S+Q / S+C | Arabic_dad (Q) | close window | S+C swallows kitty super+c |
| S+F | — | fullscreen | |
| S+V / S+W / S+Shift+F | Arabic_ra (V), Arabic_sad (W) | toggle-floating.sh (float+center) | S+V swallows kitty super+v |
| S+P | — | pseudo | |
| S+J | — | togglesplit **and** focus down | CONFLICT |
| S+Space | — | toggle-layout.sh (us↔ara + popup) | |
| S+G | — | group toggle | |
| S+Tab / S+] · S+Shift+Tab / S+[ | — | group next / prev | |
| S+Shift+W | — | wallpaper picker (yazi in kitty) | |
| S+Ctrl+W | — | live wallpaper picker | mpvpaper/wallust missing |
| S+Y | — | yazi in kitty | |
| S+Shift+V | Shift+Arabic_ra | copyq toggle | |
| S+N | Arabic_alef | swaync panel | BROKEN (swaync not running); alias wrong key (ا = H) |
| S+L / S+Escape / S+BackSpace | Arabic_meem (L) | wlogout power menu | blocks vim focus-right |
| S+Shift+L | Shift+Arabic_meem | lock (hyprlock) | no pidof guard |
| S+Shift+B | — | toggle waybar | |
| Print / S+Shift+S | — | area screenshot | |
| Shift+Print | — | area screenshot → swappy edit | |
| S+Print | — | active window screenshot | |
| Ctrl+Print | — | full screen screenshot | |
| S+arrows, S+H/K/J | — | focus | no S+L |
| S+Shift+arrows, S+Shift+H/K/J | — | move window | no S+Shift+L |
| S+1..0 / S+Shift+1..0 | — | workspace / move to workspace | |
| S+S | Arabic_seen (S) | toggle scratchpad "magic" | |
| S+Shift+A | Shift+Arabic_sheen (A) | scratchpad-send.sh | |
| S+Z | Arabic_hamza | scratchpad-restore.sh | alias wrong key (ء = X) |
| S+wheel | — | workspace next/prev | |
| S+LMB / S+RMB | — | drag / resize | |
| XF86 volume ±, mute, mic mute, brightness ±, play/next/prev | — | ae-osd.sh | work on lock screen, repeat on ± |
| S+F10 / F11 / F12 | — | play / prev / next | not lock-enabled |
| S+Shift+C | — | waybar clock 12h↔24h | |
| 3-finger horizontal swipe | — | workspace | |
Keys without Arabic alias: I, B, F, P, J, G, Y, C, H, K, Z(wrong), Shift+W, Shift+B, Shift+C, arrows, digits.

## 2. Notifications (dunst is what actually runs; swaync loses the D-Bus race and is dead)
**dunst look (the style to preserve):** top-right, offset (20,50), width 200–380, max height 150, limit 5; corner radius 12; frame 1px `#00ffcc`; padding 12 / horizontal 16; JetBrainsMono Nerd Font 11; format `<b>%s</b>\n%b`, left-aligned; icons left 32–48 px (Papirus-Dark not installed); progress bar 8 px radius 4; history 20; duplicates stacked; mouse left=close, middle=action+close, right=close all.
| Urgency | Background | Text | Frame | Timeout |
|---|---|---|---|---|
| low | `#0d1117` | `#00ffcc` | `#00e5ff` | 2 s |
| normal | `#0d1117` | `#e6f1ff` | `#00ffcc` | 5 s |
| critical | `#1a0010` | `#ff4488` | `#ff2266` | sticky |
**Intended OSD style** (dunst `[osd]` rule, mostly not applied because those keys are global-only): bottom-center, offset 80, 200–360 × 60–100, JBM 13, bg `#0a0f1aee`, text `#00ffcc`, frame `#00e5ff`, radius 14, progress 6 px, 2 s.
**swaync (inactive) intended setup:** top-right panel 400 px, timeouts normal 10 / low 5 / critical 0, widgets: MPRIS player with album art, inhibitors, title + clear, notifications, Do-Not-Disturb; blur + slide-right; stale beige wallust colours; missing fonts.

## 3. OSD (`ae-osd.sh`)
dunstify, low urgency, 2 s, one stack tag (popups replace each other), progress values. Volume ±5% (`wpctl`, capped 100%), mute/unmute with level, mic on/off, brightness ±5% (`brightnessctl -e4 -n2`), media play/pause/next/prev (`playerctl`) showing track title (40 chars). Also routes lock, power menu, waybar toggle, screenshots. No sounds. Logo icon missing.

## 4. Bar (waybar, top, 36 px)
Left: SecLegion logo launcher (→ rofi), workspaces (scroll). Center: media (`playerctl`, ♫ artist – title; click play/pause, scroll next/prev). Right: keyboard language (EN/AR, click toggles), network (wifi essid / Wired / Offline, click → nmtui), volume (click pavucontrol, scroll ±5, middle mute, muted red), brightness, battery (warning 30% `#ffcc66`, critical 15% `#ff6666`), clock (`%a %d %I:%M %p`, click toggles 12/24h, calendar tooltip).
Look: JetBrainsMono Nerd 14 bold, transparent bar, pills radius 8 bg rgba(0,0,0,.3), hover rgba(255,255,255,.15), active workspace white .2, launcher hover green .25. Neon theme.css not imported. No tray (nm-applet runs invisibly).

## 5. Launcher / power / lock / idle
- **rofi:** drun only, 600 px, radius 8, bg `#050F0EE6`, 2 px `#00FF88` border, "Search Apps", SecLegion logo (missing file), 7 rows, selected `#0B1E1C` + `#00FF88` text. Font Figtree 13 (not installed).
- **wlogout:** lock, hibernate, logout, shutdown, suspend, reboot; Catppuccin look, not neon.
- **hyprlock:** blurred wallpaper frame, time JBM 48 at (0,100), date 24 at (0,40), input 320×55 rounding 12 green outline `rgba(0,255,136,.8)`, red on fail, "Enter password...". No avatar or logo.
- **hypridle:** lock at 300 s only; no screen-off, suspend or lock-before-sleep.

## 6. Terminal / shell
- **kitty:** JetBrainsMono Nerd 12, opacity 0.6, padding 10, scrollback 5000, ligatures, copy-on-select, ctrl+c copy-or-interrupt, ctrl+v paste; every kitty window forced floating 800×500.
- **zsh:** autosuggestions, syntax highlighting, fzf, starship, zoxide (missing); history 50k shared; aliases ls/ll/la/lt/tree (eza), cat→bat (missing), top→btop (missing), df/free/mkdir helpers, `..` chain, reload. Functions: `target` (sets target IP for prompt), `vpn`, `myip`, `seclegion_fastfetch` (rotating SecLegion ASCII logos).
- **starship "OffSec Operator HUD":** two lines `╭─ [VPN IP] [TARGET] user host dir git docker python rust go duration status` / `╰─❯`; dark block segments, cyan user, red on error.
- **fastfetch:** SecLegion logo, "SecLegion OS (Rolling)", kernel, packages, terminal, shell, uptime, memory, disk, colour dots.

## 7. Window look & feel
gaps 5/20, border 2, rounding 10 (power 2), shadow range 4 power 3 `#1a1a1aee`, blur 3×1 vibrancy 0.17, dwindle + preserve_split, active border intended `#00FF88` / inactive `#0B1E1C` (currently broken: ARGB written as RGBA → invisible pink), fallback gradient `#33ccff→#00ff99` 45°.
Animations: curves easeOutQuint, easeInOutCubic, linear, almostLinear, quick, snapIn, bouncyLayer, bouncySlide, spring "easy" (1/250/25); windows spring + popin 75%/95%, layers slide bouncy, workspaces bouncySlide slidefade 10%, fades 1.2–2.5.
Rules: no maximize; floating pavucontrol 800×600, blueman 600×400, copyq 500×300, telegram 800×500, kitty 800×500; translucency for obsidian, thunar, discord, warp, protonvpn, brave, code.
Input: us,ara (script toggle), follow mouse, tap-to-click, middle-click emulation, natural scroll off. Monitor scale 1.2. Cursor 24 (GTK says 20). Env: MOZ_ENABLE_WAYLAND, ELECTRON_OZONE_PLATFORM_HINT=auto; no QT_QPA_PLATFORMTHEME.

## 8. Autostart
env import → polkit-gnome → dunst → swaync (fails) → hypridle → nm-applet → awww-daemon → copyq → restore-wallpaper. waybar via user systemd unit. Portals hyprland+gtk; secrets via gnome-keyring.

## 9. Scripts
ae-osd.sh (OSD + router) · screenshot.sh (grimblast AUR + swappy, saves ~/Pictures/Screenshots) · toggle-floating.sh · toggle-layout.sh · toggle-clock-format.sh · toggle-waybar.sh · scratchpad-send/restore.sh · wallpaper-yazi.sh (yazi picker, awww 45° wipe, wallust recolour, hyprlock frame) · live-wallpaper-yazi.sh (gif/webp via awww, video via mpvpaper) · restore-wallpaper.sh · ae-welcome.sh (6-step first-login wizard, never launched) · get_vpn_ip.sh / get_target_ip.sh (prompt) · seclegion-gpu-run (prime-run / DRI_PRIME) · unused: toggle-cava-bg, toggle-glava, toggle-quickshell (dangerous `pkill -f qs`).

## 10. File managers
Thunar: "Open Terminal Here". Yazi: neon theme (cwd `#00F0FF`, hover `#050F0E` on `#00FF88`), old `[manager]` section name. CopyQ: pin/tag commands.
GTK: Graphite-Mono, Tela-circle-grey icons, Bibata-Modern-Ice cursor, Cantarell 10 (missing). Qt: kvantum via qt6ct (likely inactive).

## 11. Broken / inconsistent today (fix in SecLegion, don't copy)
Two notification daemons (swaync dead, S+N broken) · OSD position keys ignored · missing icon theme, logos, fonts (Figtree, Inter Display, RobotoMono, Cantarell) · invisible active border (ARGB bug) · S+J double bind, no vim-L, wrong Arabic aliases for N and Z · S+C/S+V swallow kitty copy/paste · all kitty windows float · wallust/mpvpaper missing so theme sync never runs; stale colours in kitty/swaync/rofi · zoxide/bat/btop missing · hypridle has no screen-off/suspend/before-sleep lock · nm-applet without tray · waybar unit ordering · cursor 24 vs 20 · media F-keys not lock-enabled · ae-welcome never runs.
