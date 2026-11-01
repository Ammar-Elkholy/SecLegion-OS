<!-- SPDX-License-Identifier: MIT -->
# Plan R8 (Sec) — Omarchy parity, SecLegion Settings, desktop tweaks — 2026-10-15

Scope: owner requests of 2026-10-15 plus two additions (floating-window resize; file manager free space and look).
Builds on `plan-revision-r7.md` §3 (live-host protocol, binding) and `full-plan.md` / `addendum-draft.md`.
Omarchy was read as DATA ONLY from a shallow clone (commit 41d2f9d, `version` 4.0.0.alpha, MIT, github.com/basecamp/omarchy). No script was run. We write our own code; any copied idea gets a PROVENANCE.md line.

## 0. Findings from reading the live host (facts the plan relies on)

| # | Fact | Evidence |
|---|---|---|
| F1 | **Waybar workspace clicks are broken by Hyprland 0.56 Lua mode, not by waybar config.** Config already has `"on-click": "activate"`, `disable-scroll:false`. Waybar 0.15.0 sends the legacy socket string `dispatch workspace N`; Hyprland (Lua config) evaluates it as Lua and rejects it. | Sent `dispatch workspace 1` (the already-active workspace, a no-op) on `.socket.sock`: reply `error: [string "return hl.dispatch(workspace 1..."]:1: ')' expected`. `hyprctl dispatch 'hl.dsp.focus({ workspace = "1" })'` returns `ok`. Waybar binary contains only `dispatch workspace `, `focusworkspaceoncurrentmonitor`, `togglespecialworkspace` strings. |
| F2 | Scroll on the workspaces module uses the same legacy path, so it is broken too. | same binary strings |
| F3 | The bar reads persistence from Hyprland workspace rules ("Loading persistent workspaces from Hyprland workspace rules" in the journal). No rule is set today. | `journalctl --user` |
| F4 | Host binds: workspaces 1–10 on `SUPER+0..9` (key `i % 10`), `SUPER+SHIFT+N` move; `Super+Tab` / brackets = group next/prev; `Super+mouse:273` = resize (present); `Super+Space` layout toggle; `Super+N` swaync panel; `Super+L/Esc/BackSpace` logout menu; `Super+Shift+L` lock; `Super+W/V/Shift+F` float toggle. Free: `Super+period`, `Super+comma`, `Super+Ctrl+<digit>`, `Super+R` is TAKEN (rofi), `Super+Alt+<digit>`, `Super+equal/minus`. | `modules/keybinds.lua` |
| F5 | `hyprlock.conf`: `input-field` has `inner_color` dark (5,15,14,0.8), `outer_color` green, `text_color` set, **no `font_color`**. In hyprlock 0.9.6 the dots take `font_color` (default `rgb(200,200,200)` on some builds but the owner sees black), `text_color` is not a valid key there. The theme engine already renders `~/.local/state/seclegion/theme/current/hyprlock-colors.conf` with `$sl_*` as `rgba(rrggbbaa)` — but the live `current/` holds only `colors.css` (fallback), so the lock file must source the default copy when `current/` has none. | file reads; `render.py::_hyprlock`; `ls current/` |
| F6 | `hypridle.conf`: only `lock_cmd` and one 300 s lock listener (no dpms off, no suspend, no before/after_sleep). hypridle config is on the protocol's **forbidden** list. | file |
| F7 | Hardware: BAT0 + ADP0, `amdgpu_bl1` backlight, `mem_sleep` = `s2idle [deep]`. **No `charge_control_end_threshold`** on this laptop (only `charge_types`). No `power-profiles-daemon`, `tuned`, `tlp`, `hyprsunset`, `wlsunset`, `gammastep` installed. `brightnessctl`, `wpctl`, `nmcli`, `bluetoothctl`, `pkexec`, `upower` present. `/etc/systemd/logind.conf.d` absent. | probes |
| F8 | GTK4 4.24.1, libadwaita 1.10, python-gobject 3.58.1 installed. Quickshell not installed. | pacman |
| F9 | **Default file manager is Dolphin** (`xdg-mime query default inode/directory` = `org.kde.dolphin.desktop`) but the Super+E key launches **Thunar**. Nautilus, Thunar, Dolphin, yazi all installed; nemo, pcmanfm, ranger not. GTK theme is `Catppuccin-Mocha` (gsettings), `~/.config/gtk-4.0` is a symlink into `~/.themes/Graphite-Mono/gtk-4.0` (forbidden to write). `~/.config/gtk-3.0` is a real dir (`settings.ini`, `bookmarks`). `~/.config/yazi/theme.toml` exists, hand-coloured with the SecLegion hexes. `/` is 117 G, 72% used. | probes |
| F10 | Host `waybar/config.jsonc` in repo == installed. Workspace pills use `button` CSS from tokens; `colors.css` import already present. | diff |

## A. Omarchy parity table

Legend: status = covered (already planned for 1.0/1.0.1) · NEW (added by this plan) · SKIP (deliberate, reason). Release = 1.0 / 1.0.1 / 1.x. "SL" = SecLegion. Omarchy command names are `omarchy-*` from `bin/` (519 files); grouped where they are one feature family.

### A1. Menus, keys, launching

| Omarchy feature | What it does | SecLegion equivalent | Status | Rel |
|---|---|---|---|---|
| `omarchy-menu` (Super+Space) root: Apps, Learn, Trigger, Style, Setup, Install, Remove, Update, About, System | Hierarchical menu, JSONC definition + user extensions | `seclegion-menu` on Super+M (rofi, TOML, `menu.d`). Add entry **Settings** → `seclegion-settings`, and sub-entries deep-linking pages (`seclegion-settings --page power`) | covered + NEW link | 1.0 |
| System menu (Super+Esc, XF86PowerOff) | lock, suspend, hibernate, logout, reboot, shutdown | owner's logout menu (Super+L/Esc/BackSpace) stays; Settings "Power" page links to it | covered | 1.0 |
| `omarchy-menu-keybindings` (Super+K) | searchable cheat sheet | `seclegion-keys` Super+/ | covered | 1.0 |
| Menu: Learn (docs/links) | opens manuals, wiki | `seclegion-welcome` + menu "Learn" → local docs, tool catalog | NEW (menu entry only) | 1.0 |
| `omarchy-menu-emoji`, `-clipboard`, `-images`, `-file`, `-input`, `-select`, `-share`, `-timezone`, `-plugin` | pickers | emoji Super+Ctrl+E covered; clipboard = copyq (owner's Super+Shift+V) covered; timezone picker → Settings "Date & language"; share (LocalSend/Tailscale) SKIP | mixed | 1.0 |
| `omarchy-launch-or-focus`, `-webapp`, `-tui`, `-floating-terminal-with-presentation` | run-or-raise launchers | `seclegion-launch --focus-or-run CLASS CMD` (hyprctl clients + exec). Used by Super+X tools and menu items | NEW | 1.0.1 |
| `omarchy-launch-browser/editor/terminal-cwd/nautilus-cwd` | open in cwd | `seclegion-launch terminal-cwd` (reads focused kitty cwd via `kitty @`/`/proc`) bound Super+Ctrl+Return | NEW | 1.0.1 |
| Default-app setters (`default-browser/editor/terminal/agent`, `cmd-default-browser`) | set xdg defaults | Settings "Default apps" page (xdg-mime/xdg-settings) | NEW | 1.0.1 |
| Window management binds: close-all (Ctrl+Alt+Del), toggle gaps, transparency toggle, pop-out float+pin, tiled fullscreen, save/restore width, workspace layout cycle, scratchpad, group nav, monitor scaling up/down, zoom in/out | Hyprland helpers | owner already has float, group, scratchpad, layout toggle. NEW small set under Super+Ctrl+/Alt+: pop-out (float+pin), tiled fullscreen, gaps toggle, transparency toggle, cursor zoom (Super+Ctrl+Z / +Alt+Z), close-all. Keys chosen only from free keys at lint time | NEW | 1.0.1 |
| Super+C/V universal copy/paste, Super+A select-all, Super+X cut | maps to Ctrl(+Shift) | SKIP: conflicts with owner keys (Super+C/V/A/X are taken by SL) | SKIP | — |
| Calculator `omacalc`, XF86Calculator | calculator | rofi `calc` mode (rofi-calc) bound Super+Ctrl+Q? (Super+Q is owner's; use Super+Ctrl+equal) | NEW (low) | 1.0.1 |
| Dock + minimize-to-dock (Super+M) | dock | no target (owner uses waybar + scratchpad); Super+M is SL menu | SKIP | — |
| Reminders (Super+Ctrl+R), world clock, calendar panels | timers | `seclegion-remind` = `systemd-run --user --on-active` + notify; world clock/calendar: waybar clock tooltip already shows calendar | NEW (reminder only) | 1.x |
| Bar panels by number (Super+Ctrl+1..9) | toggles panel N | conflicts with preset-size binds (§C5); SKIP; panels open via bar clicks | SKIP | — |
| Panels: Audio/Bluetooth/Display/Network/Power/Activity binds (Super+Ctrl+A/B/D/W/P/T) | Quickshell panels | Settings app pages deep-linked; keys: Super+Ctrl+P power profile covered; Super+Ctrl+T btop in kitty float, Super+Ctrl+N is night light so network = Super+Ctrl+Alt+W (Super+Ctrl+W is the owner's live-wallpaper key), Super+Ctrl+B bluetooth (`blueman`/bluetui float), Super+Ctrl+D settings display page. Only after `seclegion-keys` decision (§F-D2) | NEW | 1.0.1 |

### A2. Notifications, OSD, lock, idle, screensaver

| Omarchy feature | What it does | SecLegion equivalent | Status | Rel |
|---|---|---|---|---|
| Notification shell plugin: dismiss one/all, DND, invoke last, history (Super+, family) | | swaync + Super+, family | covered | 1.0 |
| `omarchy-notification-send/-time/-battery/-weather/-wait/-dismiss` | helper notifications; show time/battery on keys | `seclegion-notify` thin wrapper; Super+Ctrl+Alt+T / +B (time, battery). Weather SKIP (network call, privacy) | NEW (time, battery) | 1.0.1 |
| `omarchy-toggle-notification-silencing` | DND | covered; Settings "Notifications" page toggles `swaync-client -d` | covered + page | 1.0 |
| OSD (`omarchy-osd`, brightness/audio OSD, Alt = 1% steps) | | swayosd, Alt fine steps (addendum §2) | covered | 1.0 |
| Lock (`omarchy-system-lock`, hyprlock-like plugin) | | hyprlock with themed tokens; **dots fix §C1** | covered + fix | 1.0 (host now) |
| `omarchy-toggle-idle`, `omarchy-system-lid-inhibit`, `-lid-close`, `hw-clamshell`, `hw-laptop-closed` | stay-awake; lid/clamshell with external monitor | Super+Ctrl+I covered; lid policy in Settings "Power" (logind drop-in) + clamshell: if external monitor, internal off (hyprland lid switch bind in `seclegion-keys`) | NEW | 1.0.1 |
| `omarchy-system-sleep-lock/-monitor`, `-wake` | lock before sleep, post-wake fixes | hypridle `before_sleep_cmd`/`after_sleep_cmd` generated by Settings (ISO) | covered (addendum) + Settings writes it | 1.0 (ISO) |
| Screensaver (`omarchy-screensaver`, tte ASCII, branding-screensaver, toggle-screensaver) | idle art | planned 1.0 if S7 green else 1.1 | covered | 1.0/1.1 |
| `omarchy-toggle-suspend`, hibernation setup/remove/available | suspend visible in menu; btrfs swapfile hibernate | Settings shows "Suspend" toggle in power menu (list). Hibernation | covered | 1.4 |
| `omarchy-update-stay-awake`, `-requires-free-space` | inhibit sleep during update | `seclegion-update` uses `systemd-inhibit` | NEW (tiny) | 1.0 |

### A3. Capture, input, hardware

| Omarchy feature | What it does | SecLegion equivalent | Status | Rel |
|---|---|---|---|---|
| `capture-screenshot/region/screenrecording(+webcam)/text(OCR)/qr/webcam-*`, colour picker | | capture menu, Alt+Print record, OCR, picker | covered | 1.0 |
| `hyprland-monitor-scaling`, `-clamshell`, `-internal(-mirror)`, `-focused`, `-watch`, `-modeless`, `hw-external-monitors`, `hw-display`, `hw-recover-internal-monitor` | multi-monitor scale, lid, mirroring | Settings "Display" page: scale, resolution/refresh via `hyprctl monitors`, mirror toggle writing `monitor.lua` fragment (ISO only; host = read-only/info + apply live with `hyprctl eval`) | NEW | 1.0.1 |
| `brightness-display(-ddc/-apple)`, `brightness-keyboard(-mute)` | brightness, kbd backlight | Settings "Display": slider via `brightnessctl`; kbd backlight slider if `*kbd_backlight` exists; DDC (ddcutil) SKIP 1.x | NEW | 1.0 |
| `toggle-nightlight`, `restart-hyprsunset` | night light | Super+Ctrl+N covered; Settings toggle + temperature (hyprsunset or wlsunset, whichever hwdetect picked) | covered + page | 1.0 |
| `audio-*` (output/input switch, volume, mute, tuning, sink availability) | | Settings "Sound": output/input device list, volume, mute, balance (wpctl); `audio-tuning` (pipewire quantum) SKIP | NEW | 1.0 |
| `bluetooth-power/-device`, `restart-bluetooth` | | Settings "Bluetooth": power switch + device list/connect via `bluetoothctl`; pairing UI → launch `blueman-manager` | NEW | 1.0 |
| `network-wifi-connected/-status/-band/-password/-qr/-speedtest`, `restart-wifi`, `dns` | | Settings "Network": Wi-Fi toggle, list, connect (`nmcli`), airplane mode (`rfkill`), share-password QR (`nmcli dev wifi show-password`), DNS preset (via NetworkManager connection, pkexec-free per-user? NM polkit allows for active session), speed test SKIP | NEW | 1.0 |
| `toggle-touchpad/-touchscreen`, `restart-trackpad`, `setup-input`, `toggle-input-device`, `hw-touchpad` | | Settings "Keyboard & mouse": touchpad tap, natural scroll, disable-while-typing (live via `hyprctl eval`, persisted to `~/.config/seclegion/input.lua` loaded from the ISO's user.lua), touchpad toggle key XF86TouchpadToggle | NEW | 1.0 |
| `setup-keyboard`, `language`, `i18n`, `locale-generate`, `menu-timezone`, XCompose | | Settings "Keyboard layout" (us/ara order, switch key), "Date & language" (timezone `timedatectl` via polkit, locale display). XCompose | NEW / XCompose 1.2 | 1.0 / 1.2 |
| `hw-*` vendor scripts (Framework, ASUS, Dell XPS, Surface, Apple, NVIDIA GSP, hybrid GPU, fingerprint) | quirks | `hwdetect` data-driven (spec); `toggle-hybrid-gpu` → Settings "Graphics" only when `supergfxctl`/PRIME offload present | covered (hwdetect) | 1.0 / 1.x |
| `setup-security-fido2/fingerprint`, `remove-*` | | covered | 1.4 |
| `battery-low/-present/-status`, `power-present`, `notification-battery` | battery alerts | covered 15 %/7 %; Settings shows state, health, cycle count, charge limit | covered + page | 1.0 |
| `powerprofiles-*` | | power-profiles-daemon; Super+Ctrl+P; Settings page | covered + page | 1.0 |
| `hyprland-toggle`, `toggle-animations`, `toggle-bar`, `toggle-fullscreen-desktop`, `toggle-crash-capture`, `toggle-theme-sync`, `menu-toggle` | toggles | Settings "Appearance": animations (reduced motion), bar visibility, gaps, rounding, transparency; Super+Shift+B bar toggle exists | NEW (page) | 1.0.1 |

### A4. Themes, fonts, wallpapers, branding

| Omarchy feature | What it does | SecLegion equivalent | Status | Rel |
|---|---|---|---|---|
| `theme-set/-list/-install/-update/-remove/-refresh/-current/-extras`, 23 themes, `themed/*.tpl` templates | renderer, picker | `seclegion-theme` renders from tokens + wallpaper (done). Picker = Settings "Appearance" > Theme (Default / From wallpaper; contrast normal/high). Install-from-git SKIP until 1.3 with code stripping | covered + page | 1.0 / 1.3 |
| `theme-set-browser/-foot/-gnome/-vscode/-obsidian/-keyboard/-tmux/-claude/...` | per-app hooks | hooks in `seclegion_theme/hooks.py` exist (kitty, rofi, waybar, swaync, swayosd, hyprlock, starship); NEW targets: GTK (§C7), yazi, Dolphin/KDE colour scheme, VS Code token override, Firefox userChrome (1.3) | NEW | 1.0.1 / 1.3 |
| `theme-bg-set/-next/-cache/-switcher/-install` | wallpapers | Settings "Appearance" > Wallpaper grid (reads owner's wallpaper dir, calls `seclegion-theme apply --wallpaper`); Super+Ctrl+Space style key = Super+Ctrl+W conflict → use Super+Ctrl+Shift+W | NEW | 1.0 |
| `font-set/-list/-current`, `dev-font`, `display-text-size`, `install-font` | | Settings "Appearance" > Fonts (mono + UI, size) writes a fontconfig/GTK/kitty include; text scale | NEW | 1.0.1 |
| `plymouth-*` | boot splash/theme | `seclegion-bits` (owner O12, 1.0); Settings shows read-only preview; changing = 1.x | covered | 1.0 |
| `branding-about`, `show-logo`, `ascii`, `launch-about`, `branding-screensaver` | fastfetch About with art | Settings "About" + `fastfetch` SL logo (covered) | covered + page | 1.0 |
| `hyprland-corners`, `window-transparency`, `window-gaps-toggle` | look knobs | Settings "Appearance": gaps, rounding, transparency sliders (live via `hyprctl eval`, persist to `appearance.lua` in ISO) | NEW | 1.0.1 |

### A5. Updates, system, packages, snapshots

| Omarchy feature | What it does | SecLegion equivalent | Status | Rel |
|---|---|---|---|---|
| `update`, `update-*` (pacman, aur, firmware, keyring, orphans, mise, analyze-logs, boot, confirm, restart, time, status, available, lock, guard) | updater | `seclegion-update` + `seclegion-migrate` + snapshot (covered); `update-available` → Settings "Updates" shows count (`checkupdates`), last update time, run button (opens kitty), snapshots link; `update-pacman-guard` (blocks raw -Syu) SKIP per R1 (A10 full pacman) | covered + page | 1.0 |
| `migrate` (169 timestamped) | | `seclegion-migrate` | covered | 1.0 |
| `snapshot`, `system-factory-reset(-finish)` | snapper create/restore, reset | baseline snapshot 1.0; Settings "Updates" lists snapshots read-only + "Open snapshot manager" (btrfs-assistant if present); reset UI 1.2 | covered / 1.2 | 1.0 / 1.2 |
| `refresh-*` (config, hyprland, waybar, pacman, plymouth, ...), `reinstall*` | reset a config to default with backup | `seclegion-refresh-config <component>` (backup → restore skeleton); Settings "Reset" buttons per component, each showing the diff first | covered (M7a) + page | 1.0 |
| `pkg-add/-drop/-install/-present/-missing/-aur-*`, `install*`, `remove*` (apps, gaming, services, editors, AI) | install menus | menu Install > categories via `seclegion-install` (1.2); gaming menu 1.0; installers for Steam, Lutris, RetroArch ... | covered / 1.2 | 1.0/1.2 |
| `install-dev-env`, `mise-install`, `install-docker-dbs` | dev stacks | mise dev envs 1.1 | covered | 1.1 |
| `install-ai-*`, `agent*`, `agent-usage-*`, `default-agent`, `dictation*`, `voxtype*` | AI | SecLegion AI + Super+A picker 1.0.1; usage-meter/accounts SKIP; dictation 1.2 | covered / SKIP | 1.0.1 |
| `install-service-1password/dropbox/nordvpn/tailscale/signal/spotify/sunshine/...`, `launch-*`, webapps (`webapp-install/remove`, `webapp-handler-*`) | app installers | webapps 1.2 (chromium/brave `--app`); proprietary services SKIP (not owner workflow; offered via App Center later) | covered 1.2 / SKIP | 1.2 |
| `tui-install/-remove`, `launch-tui`, `menu-herdr/tmux-keybindings` | TUIs | btop + lazygit installed; yazi default TUI; herdr SKIP | covered/SKIP | 1.0 |
| `security-functions`, `setup-security-sshd`, `-sudoless-docker`, `sudo-passwordless/-keepalive`, `remove-security-*` | | sshd off by default, ufw covered; timed passwordless sudo SKIP (weakens security, conflicts with polkit-based design); sudoless docker SKIP | covered / SKIP | 1.0 |
| `drive-*` (info, select, password), `disk-speedtest`, `tailscale-*`, `network-speedtest`, `transcode*` | disk utilities, sharing | Settings "Storage" read-only page: filesystems, free space, snapper usage (§B). Speedtests/transcode/tailscale SKIP | NEW (page) | 1.0.1 |
| `windows-vm`, `windows-key` | | no target | SKIP | — |
| `crash-*`, `debug`, `upload-log`, `agent-crash` | diagnostics | Settings "About" > "Copy diagnostics" (redacted; **no upload**); coredump → AI user-initiated 1.2 | NEW (copy only) | 1.0.1 |
| `version*`, `channel-*`, `upgrade-to-quattro` | | version + channel shown in About; channels 1.0.1 | covered | 1.0.1 |
| `plugin-*` (add/catalog/enable/validate), `hook*`, `lifecycle-dispatch` | plugin system, lifecycle hooks | SKIP plugins (security surface); lifecycle hooks (theme-set/post-update) 1.2 | SKIP / 1.2 | 1.2 |
| `dev-*` (benchmark, link, pkg-test, ui-preview) | Omarchy dev tools | SKIP (project-internal) | SKIP | — |
| `hyprland-reload-guard`, `session-locked/-stranded`, `restart-*` (app, audio, bluetooth, wifi, shell, hyprctl, xcompose...) | repair | Settings "Troubleshoot": restart audio (pipewire, wireplumber), Bluetooth, Wi-Fi, waybar, notifications daemon — each button shows the exact `systemctl --user restart` | NEW | 1.0.1 |
| `games-retro-*`, gaming installers | | gaming menu (covered) | covered | 1.0 |
| `clipboard-*`, `file-select`, `cmd-*`, `git-url-check`, `state` | internal helpers | not user features | SKIP | — |
| Installer ISO (archinstall configurator), unattended install, dual boot | | own installer (spec) | covered | 1.0 / 1.2 |
| LUKS, Limine, UKI | | LUKS option, systemd-boot (covered, Limine rejected) | covered | 1.0 |
| Docs (`manual/` 51 chapters) | in-OS manual | `seclegion-welcome` + docs site 1.0.2; Settings About links; keybinding chapter generated from `seclegion-keys` | covered | 1.0.2 |

Counts: of Omarchy's 519 binaries, ~140 are hardware/vendor quirks (handled by hwdetect data), ~110 are install/remove pairs (1.2 package experience), ~60 are internal helpers (not features), the rest map to the rows above. Nothing is silently dropped: any `omarchy-*` family not named above is an install/remove/hw-vendor/dev/agent-account item covered by the "SKIP"/hwdetect rows.

## B. SecLegion Settings (`seclegion-settings`) design

### B1. Toolkit decision

| Option | Light (no resident daemon) | Theming from `colors.css` | Beginner friendly | Expert transparency | Testable | Verdict |
|---|---|---|---|---|---|---|
| **GTK4 + libadwaita, Python (PyGObject)** | yes, starts on demand, exits | yes: `Gtk.CssProvider` loads `colors.css` (`@define-color sl_*`) and a small `settings.css` mapping Adwaita named colours (`window_bg_color`, `accent_bg_color`, ...) to `@sl_*`; libadwaita 1.10 supports this | sliders, switches, combo rows, search, sidebar; screen-reader support | `Adw.ExpanderRow` "Show details" per setting | backend is plain Python (no GTK import), UI smoke test headless | **CHOSEN** |
| rofi/menu TUI | yes | rofi-colors.rasi | no sliders, poor for 40+ options | good | easy | **kept as secondary**: the same backend powers `seclegion-set` CLI and a rofi quick menu (Super+M > Settings > quick toggles) |
| Quickshell/QML panel | needs a resident process | custom | good | poor | hard | rejected for 1.x; 2.0 spike (matches full-plan) |
| GTK3 + Python | yes | gtk3 CSS | ok | ok | ok | rejected: libadwaita 1.10 already installed; GTK3 end-of-line |

Why not a Rust/C app: no benefit; Python+GI is already in base (python-gobject, theme engine is Python). Cost: Python start-up ~250 ms, accepted.

### B2. Architecture (one deliverable per layer)

```
desktop/settings/
  seclegion_settings/
    backend/            pure Python, no gi import, unit-tested
      registry.py       Setting dataclass + SETTINGS table (id, page, label, kind, reader, writer, file, privileged, capability)
      readers.py        read current values (parse files / run read-only commands)
      writers.py        user-level writers, each returns WriteResult(files, commands, applied_live)
      capabilities.py   detect: battery threshold, backlight, kbd backlight, ppd, hyprsunset/wlsunset, bluetooth, wifi, lid
      render.py         pure functions that generate config text (hypridle.conf, logind drop-in, input.lua, ...)
      priv.py           client for the root helper (calls pkexec)
      cli.py            `seclegion-set list|get|set|explain <id> [value]` (--json, --dry-run)
    ui/                 GTK4/libadwaita (thin): window.py, pages/*.py, css/settings.css
  helper/seclegion-settings-helper     root, python, allowlist, no shell, no network (ISO only)
  polkit/org.seclegion.settings.policy
  tests/
```
Launchers: `seclegion-settings [--page ID] [--search TEXT]` (launcher with `#!/usr/bin/python3 -I`, same pattern as `tools/seclegion-theme`), `seclegion-set` CLI, `.desktop` entry, Super+M > Settings, waybar right-click on battery/volume/clock opens the matching page.

Rules:
1. Every setting is one registry row. The UI is generated from the registry; the CLI exposes the same rows; a unit test asserts every row has a reader, writer, `file` or `command` description, and a label.
2. `WriteResult` lists exactly what was done; the UI shows it in the "Show details" expander (§B5) and as a toast with Undo (restores the previous value from the saved read).
3. Capability detection hides or greys rows ("Not supported on this hardware: no charge threshold file") — never errors out.
4. **No daemon**: settings are applied once; persistence is in config files. Live-apply uses `hyprctl eval`/`brightnessctl`/`wpctl`/etc.

### B3. Pages and options (every option, backend, file written)

Priv = P means root via helper (ISO/package install only). "Live" = also applied immediately without logout.

**1. Power & Battery**
| Option | Control | Backend (read → write) | File written | Priv |
|---|---|---|---|---|
| Power profile (power-saver / balanced / performance) | 3-way segmented | `powerprofilesctl get|set` (ppd D-Bus, no root) | ppd state `/var/lib/power-profiles-daemon/state.ini` (ppd's own) | no |
| Auto profile on AC/battery | switch + 2 combos | udev-free: `seclegion-power-watch`? NO daemon → use a systemd **user path/udev-less** approach: `~/.config/systemd/user/` unit triggered by upower? Rejected. Instead write a `udev` rule (ISO) `/etc/udev/rules.d/61-seclegion-power.rules` that runs `/usr/lib/seclegion/power-switch AC|BAT` (calls ppd) | rules file | P |
| Battery charge limit (60–100 %, presets 60/80/100) | slider, only if `charge_control_end_threshold` exists (absent on owner's laptop → row hidden with explanation) | read sysfs; write via helper | sysfs + `/etc/systemd/system/seclegion-charge-limit.service`? use `tmpfiles.d` drop-in `/etc/tmpfiles.d/seclegion-charge.conf` (`w /sys/class/power_supply/BAT0/charge_control_end_threshold - - - - 80`) | P |
| Battery status, health %, cycles, time left | read-only | `upower -i` | — | no |
| Low-battery alert thresholds (15 / 7 %) | 2 spinners | user file `~/.config/seclegion/battery.toml` read by the existing battery-alert timer | that file | no |
| Lid close on battery / on AC / docked | 3 combos: suspend, lock only, hibernate (if available), do nothing | helper writes drop-in | `/etc/systemd/logind.conf.d/50-seclegion-lid.conf` (`HandleLidSwitch=`, `HandleLidSwitchExternalPower=`, `HandleLidSwitchDocked=`); applied by `systemctl kill -s HUP systemd-logind` — **never restart logind** (kills the session) | P |
| Power button action | combo: power menu / suspend / poweroff / ignore | helper | `/etc/systemd/logind.conf.d/50-seclegion-power.conf` `HandlePowerKey=` (+ Hyprland XF86PowerOff bind stays our menu) | P |
| Suspend mode (s2idle vs deep) | combo, shown only if `/sys/power/mem_sleep` lists both; owner: `s2idle [deep]` | read sysfs | `/etc/tmpfiles.d/seclegion-mem-sleep.conf` | P |
| Show "Suspend" / "Hibernate" in power menu | switches | user | `~/.config/seclegion/menu.d/power.toml` | no |

**2. Sleep, Lock & Idle** (hypridle)
| Option | Control | File | Priv |
|---|---|---|---|
| Lock screen after N min (1,2,3,5,10,15,30, never) | combo | `~/.config/hypr/hypridle.conf` listener `timeout = N*60`, `on-timeout = loginctl lock-session` | no (but **host: forbidden file**, see §F-D5) |
| Turn screen off after (30 s … never; must be ≥ lock) | combo | listener `on-timeout = hyprctl dispatch dpms off` (Lua mode: `hyprctl eval 'hl.dsp.dpms({action="off"})'` — spike), `on-resume` dpms on | no |
| Suspend after (battery / AC separately; defaults 15 min battery, never AC per D5) | 2 combos | listener `on-timeout = systemctl suspend` guarded by `sh -c '[ "$(cat /sys/class/power_supply/AC*/online)" = 1 ] || systemctl suspend'` | no |
| Lock before sleep | switch | `general { before_sleep_cmd = loginctl lock-session; after_sleep_cmd = hyprctl eval dpms on }` | no |
| Stay awake while playing media / inhibitors | switch | `ignore_dbus_inhibit = false` (honour) | no |
| Stay awake now (Super+Ctrl+I) | switch | `systemd-inhibit` unit `seclegion-stay-awake.service` (user) start/stop | no |
| Lock now / Sleep now | buttons | `loginctl lock-session` / `systemctl suspend` | no |
Hypridle is reloaded with `pkill -USR1`? hypridle has no reload signal: restart the user unit (`systemctl --user restart hypridle`) or on host kill by pid — implemented in `writers.py` with a pid-by-uid helper, never `pkill -f`.

**3. Display**
| Option | Backend | File |
|---|---|---|
| Brightness slider (+ per-source: AC/battery default) | `brightnessctl -d <dev> set N%` (read `-m`) | none (state held by kernel; restored by systemd-backlight) |
| Keyboard backlight (if `*::kbd_backlight`) | `brightnessctl -d '*kbd_backlight' set` | none |
| Night light on/off, temperature 3500–6500 K, schedule (off / sunset-sunrise needs location → manual times) | `hyprsunset` via `hyprctl hyprsunset temperature N` or `wlsunset`; Super+Ctrl+N shares state file | `~/.config/seclegion/nightlight.toml` |
| Scale (1.0/1.2/1.5/2.0/auto), resolution + refresh rate, per monitor | `hyprctl monitors -j` → live `hyprctl eval 'hl.monitor{...}'` with 15-s revert dialog | `~/.config/seclegion/monitors.lua` (ISO user.lua includes it); owner's `monitor.lua` untouched on host |
| Mirror / extend / internal off on lid close with external | buttons | same file |
| Reduced motion (animations off) | switch | `appearance.lua` |
**4. Sound**: output device (default sink) combo, volume slider, mute, balance; input device, mic level, mic mute; per-app volume list; test sound. `wpctl status/set-default/set-volume/set-mute` + `pactl` for names; no files (WirePlumber stores defaults in `~/.local/state/wireplumber`). "Open advanced mixer" → `pavucontrol`.
**5. Network**: Wi-Fi switch (`nmcli radio wifi`), network list + connect (password dialog goes to `nmcli --ask`/`nmcli dev wifi connect ... password` via stdin from the dialog, never argv and never logged), saved networks forget, airplane mode (`rfkill`), Ethernet status, hostname (read; change via `hostnamectl` polkit), DNS preset (automatic / Cloudflare / Quad9 / custom — NM connection `ipv4.dns`), VPN list (NM, `nmcli con up`), "Open full editor" → `nm-connection-editor`. Files: NM profiles under `/etc/NetworkManager/system-connections/` (written by NM itself).
**6. Bluetooth**: power switch (`bluetoothctl power on|off`), paired devices connect/disconnect/forget, scan + pair (agent via `bluetoothctl` pipe in a Gio subprocess), "Advanced" → `blueman-manager`. File: BlueZ storage `/var/lib/bluetooth` (owned by bluez).
**7. Keyboard & Mouse**: layouts list (us, ara; reorder, add), layout switch key (Super+Space / Alt+Shift / Caps), repeat rate and delay, touchpad (tap-to-click, natural scroll, disable while typing, speed, click method), mouse (speed, flat accel, left-handed). Live: `hyprctl eval 'hl.config({input={...}})'`; persisted to `~/.config/seclegion/input.lua` which the ISO's user.lua requires; on the owner's host the file is shown and a one-line include is offered (§F-D5). Cheat-sheet link to `seclegion-keys`.
**8. Appearance**: theme source (SecLegion Dark default / From wallpaper), contrast (normal/high), accent hint (`seclegion-theme apply --accent`), wallpaper picker (thumbnail grid of `~/Pictures/Wallpapers`, `~/.config/wallpapers` — configurable folder; applies with `seclegion-theme apply --wallpaper`), gaps in/out, rounding, border size, blur, transparency (live, `appearance.lua`), fonts (mono / UI / size), cursor size, dark/light (1.3), GTK theme application status (§C7), preview chips of all `sl_*` tokens (read from `colors.json`). Writes via `seclegion-theme` only — the Settings app never writes colour files itself.
**9. Notifications**: Do Not Disturb, popup position (top-right/-left, via swaync `config.json` `positionX/Y`), timeout per urgency, show on lock screen (off by default), sound on/off, history clear, per-app mute list, test buttons (calls `seclegion-notify-test low|normal|critical`). Files: `~/.config/swaync/config.json` (host: the symlinked copy is owned by `seclegion-host`, so the app writes `~/.config/seclegion/swaync-overrides.json` merged at login by `seclegion-notify-merge`; ISO ships merge step in the swaync launcher).
**10. Apps & Defaults**: default browser, terminal, file manager (**fixes Dolphin-vs-Thunar mismatch**, §C8), editor, PDF, image, mail — `xdg-mime default` / `xdg-settings`; autostart apps list (toggle `~/.config/autostart/*.desktop` and the hypr autostart is read-only listed); startup items count.
**11. Date, Language & Region**: timezone (`timedatectl set-timezone` via polkit action `org.freedesktop.timedate1.set-timezone`, built-in), NTP switch (`set-ntp`), 12/24 h clock (waybar format via `~/.config/seclegion/clock.toml`, bar already has toggle script), locale display (read `localectl`), keyboard layout shortcut.
**12. Updates & Snapshots**: pending update count (`checkupdates`), last update date (pacman log), "Update now" (opens kitty running `seclegion-update`), update notifications (opt-in, 1.0.1), snapshot list (snapper read-only: number, date, type, description), "Create snapshot", "Restore" → opens rescue guide (restore needs reboot), keep-N setting (helper edits `/etc/snapper/configs/root` `NUMBER_LIMIT`), mirror status; "Reset <component> to default" (calls `seclegion-refresh-config` after showing the diff).
**13. Storage**: disk list with used/free bars (`statvfs`, `findmnt`), btrfs usage (`btrfs filesystem usage`, needs no root for `df`), snapper space, trash size + "Empty trash" (Gio, confirm dialog), `/` 80 % warning level.
**14. Security**: firewall status and on/off (ufw via helper), SSH server on/off (`systemctl enable --now sshd`, helper, default off), screen-lock requirement note, listening ports (read `ss -tlnp` info), "Authorised-targets-only" reminder text, USB auto-mount toggle (udisks2 policy, 1.x). No passwords handled.
**15. Users & Login** (1.x, read-only first): current user, avatar `~/.face`, change password button launches `passwd` in kitty float (**app never sees password**), autologin status (read), session choice (Hyprland/GNOME from greetd config, read-only).
**16. Troubleshoot** (§A5): restart buttons + "Reset to default", "Copy diagnostics" (redacted: no tokens, no IPs unless ticked).
**17. About**: logo, version, channel, kernel, uptime, CPU/GPU/RAM/disk (via `fastfetch --format json` if present else `/proc`), Hyprland version, repo links, licence (MIT, Omarchy inspiration attribution), "Copy system info".

Search box (Ctrl+F) searches registry labels + keywords; deep links from menu: `seclegion-settings --page power|sleep|display|sound|network|bluetooth|input|appearance|notifications|apps|region|updates|storage|security|about`.

### B4. Privilege handling (never stored passwords)

1. Everything in the table above marked "no" runs as the user. Nothing is run through `sudo`.
2. Root work goes through one helper `/usr/lib/seclegion/settings-helper` invoked as `pkexec /usr/lib/seclegion/settings-helper <action> <args>`. Polkit action file `org.seclegion.settings.policy` defines one action per capability, each with a clear message and `auth_admin_keep` (admin password asked by polkit's own agent, which is the system's agent, not our app):
   - `org.seclegion.settings.logind` "Change what happens when you close the lid or press the power button"
   - `org.seclegion.settings.charge-limit` "Limit how far the battery charges"
   - `org.seclegion.settings.sleep-mode` "Change the sleep mode"
   - `org.seclegion.settings.firewall` "Turn the firewall on or off"
   - `org.seclegion.settings.sshd` "Turn the SSH server on or off"
   - `org.seclegion.settings.snapper` "Change how many snapshots are kept"
   Each uses `org.freedesktop.policykit.exec.path` annotation to bind to the helper path, and `exec.argv1` is the action name so the prompt text matches what runs.
3. The helper: Python with `-I`, **allowlist of actions**, strict value validation (enum or integer range; no free text), writes only to fixed paths (`/etc/systemd/logind.conf.d/50-seclegion-*.conf`, `/etc/tmpfiles.d/seclegion-*.conf`, `/etc/snapper/configs/root` via atomic temp+rename), refuses symlink targets, never runs a shell, takes no environment (`env -i`-style by construction), logs one line to the journal (`logger -t seclegion-settings`) with the action and value, makes a `.bak` of the previous file (kept in `/var/lib/seclegion/settings-backups/`) so Undo works, and prints the exact file text it wrote to stdout for the Details panel.
4. After a logind change the helper sends `SIGHUP` to logind (`systemctl kill -s HUP systemd-logind`), never restarts it; the UI states "Applies now" or "Applies after next boot" explicitly.
5. `--dry-run` shows the file text without privilege (the UI shows it before the prompt, so the polkit prompt is expected).
6. **On the owner's live host this helper is not installed** (protocol forbids `/etc`, `/usr`): privileged rows show "Needs the SecLegion package" and a "Show what would be written" preview. The ISO/package ships the helper. Owner decision D6 offers a user-level alternative.
7. Mutation tests: helper accepting an unlisted action, a path outside the allowlist, a value outside range, or a symlinked target must turn red.

### B5. Expert transparency

Each row is an `Adw.ActionRow`; a chevron expands "Details" showing: setting id, current value, **file or command that is written**, the exact lines (syntax-highlighted via CSS classes), whether it needs privilege, whether it applies live, and buttons: "Copy command", "Open file in editor" (user files), "Reset to default". A global switch "Show details everywhere" (header menu) keeps all expanders open. The CLI `seclegion-set explain power.lid_battery` prints the same.

### B6. Theming and look

- `app.py` loads, in order: libadwaita default (dark, `Adw.ColorScheme.FORCE_DARK`), `$XDG_STATE_HOME/seclegion/theme/current/colors.css` (fallback `/usr/share/seclegion/theme/default/colors.css`), then packaged `settings.css`. The latter maps tokens to libadwaita names: `@define-color window_bg_color @sl_bg; @define-color view_bg_color @sl_surface; @define-color headerbar_bg_color @sl_surface; @define-color card_bg_color @sl_surface2; @define-color accent_bg_color @sl_accent; @define-color accent_fg_color @sl_bg; @define-color accent_color @sl_accent; @define-color destructive_bg_color @sl_crit; @define-color warning_bg_color @sl_warn; @define-color success_bg_color @sl_ok; @define-color window_fg_color @sl_text`, border/outline `@sl_border_active`.
- Cyber look: JetBrainsMono Nerd Font for headings and values, monospace chips for config paths, 1 px accent frame on the focused row, scanline-free (no heavy effects), small "SEC//LEGION" header glyph from the logo PNG, status chips ("LIVE", "REBOOT", "ROOT") coloured with `sl_ok/sl_warn/sl_crit`.
- A `Gio.FileMonitor` on `colors.css` re-loads the CSS provider when the wallpaper theme changes (no daemon; only while the window is open).
- Accessibility: contrast of every token pair used checked by the theme engine's contrast gate; keyboard navigation on all rows; tooltips on icons.

### B7. Mockup description (for the builder and the screenshot gate)

Window 980x680 (min 720x520, collapses the sidebar to a hamburger below 800 px). Left sidebar (Adw.NavigationSplitView): logo + "SecLegion Settings", search entry, 17 page rows with symbolic icons, group labels (SYSTEM: Power, Sleep, Display, Sound, Network, Bluetooth, Input — PERSONAL: Appearance, Notifications, Apps, Region — MAINTENANCE: Updates, Storage, Security, Troubleshoot, About). Content: page title, then `Adw.PreferencesGroup` cards on `sl_surface2` with 1 px `sl_border_inactive` frame. Example Power page: a row of three big profile buttons (Saver / Balanced / Performance) with the active one filled `sl_accent`; battery card (92 %, "Health 94 %, 312 cycles, 6 h 10 min left") with a thin accent bar; "Lid closed (on battery)" combo with a `ROOT` chip; "Battery charge limit" row shows "Not supported on this laptop" in muted text. Each row's chevron reveals a mono block: `file: /etc/systemd/logind.conf.d/50-seclegion-lid.conf  HandleLidSwitch=suspend` with Copy. Bottom toast: "Saved. Applies now. Undo".

### B8. Test strategy

1. **Backend unit tests** (`desktop/settings/tests/`, stdlib `unittest`, run `python3 -m unittest discover`): fake `SL_HOME` + fake sysfs (`SL_SYSFS`) + PATH stubs for `hyprctl`, `brightnessctl`, `wpctl`, `nmcli`, `bluetoothctl`, `powerprofilesctl`, `loginctl` (same pattern as `tests/host/fake-host`). For every registry row: read → write → read round-trip; file text golden-compared; `--dry-run` writes nothing; capability absent → row hidden.
2. Helper tests: allowlist, range, symlink, atomic write, backup/undo, idempotence; polkit policy XML lint (`xmllint`, every action has `message` and `defaults`, every helper action has a policy action: a test cross-checks both lists).
3. Render tests for hypridle.conf: parse back; ordering lock < dpms < suspend enforced; never suspend on AC.
4. **GTK smoke test** (headless): `GDK_BACKEND=broadway` or `xvfb-run` where available, else `pytest.skip` loudly; instantiate every page, assert no exception, every row has a details expander; no network calls (monkeypatched).
5. **Screenshot check**: run `seclegion-settings --page power` under a nested Hyprland/`weston --backend=headless`/the VM, `grim` the window, assert: window size ≥ 720x520, sample pixel at sidebar = `sl_bg`, accent-filled profile button pixel = `sl_accent`, OCR (tesseract) contains "Power", "Lid", "Battery". Golden image is not committed; tolerance by pixel sample.
6. Licence and secret scans: no URL egress at start-up (strace-free check: run with `unshare -n` and assert exit 0), nothing in logs matching `password=`.

## C. Specs

### C1. Lock screen dots (host component `lock`) — quick win #1

Root cause (F5): `input-field` sets `inner_color` (dark) and `outer_color` but no `font_color`; `text_color` is not an `input-field` key in hyprlock 0.9.6, so the dots render in the default dark colour on a dark `inner_color`.

Repo: new `desktop/hypr/hyprlock.conf` (template, SPDX MIT) installed as `~/.local/share/seclegion/host/lock/hyprlock.conf`; `~/.config/hypr/hyprlock.conf` becomes a symlink to it (existing file backed up by `seclegion-host apply lock`; the protocol allows `~/.config/<x>` symlink flips only for the listed dirs, so **the component adds `hypr/hyprlock.conf` to that list** — decision D4, because hyprlock.conf is not under the forbidden "hypridle, monitor, input, keybind" modules).

File content (precise):
```
# SPDX-License-Identifier: MIT
source = ~/.local/state/seclegion/theme/current/hyprlock-colors.conf
# `source` of a missing file is an error: host-apply guarantees current/ exists by
# copying /usr/share/seclegion/theme/default/ (or desktop/theme/default/) if absent.
background { monitor = ; path = ~/.cache/wallpaper_frame.png; blur_size = 5; blur_passes = 1 }
label { ... text = $TIME ... color = $sl_text ... }            # time, date: $sl_text / $sl_muted
input-field {
    monitor =
    size = 320, 55
    outline_thickness = 3
    rounding = 12
    dots_size = 0.28
    dots_spacing = 0.35
    dots_center = true
    dots_rounding = -1
    inner_color = $sl_surface            # keep alpha: rgba(...) has ff alpha; use 0.85 via a derived literal if needed
    outer_color = $sl_accent
    check_color = $sl_warn
    fail_color = $sl_crit
    font_color = $sl_text                # THE FIX: dots + typed text
    capslock_color = $sl_warn
    numlock_color = $sl_warn
    fade_on_empty = false
    placeholder_text = <span foreground="##RRGGBB">Enter password...</span>   # hyprlock placeholder needs a literal, see below
    fail_text = <i>$FAIL ($ATTEMPTS)</i>
    font_family = JetBrainsMono Nerd Font
    position = 0, -10
    halign = center
    valign = center
}
```
Placeholder colour: hyprlock `placeholder_text` cannot take `$var` colours inside Pango markup reliably; use `placeholder_text = Enter password...` (default placeholder colour follows `font_color` with reduced alpha). Contrast rule: `font_color` vs `inner_color` ≥ 7:1 — a unit test in `tests/theme` computes it for the default and for any wallpaper-derived palette using `seclegion_theme.color`; if the theme engine's `sl_text`/`sl_surface` ever fall below 4.5:1 the generator clamps `sl_text`.
Also keep layout labels (time/date) with `color = $sl_text` and `$sl_muted`. Do not add `lock` of notification text.
Host component `lock`: `seclegion-host apply lock` = back up → validate (`hyprlock --version` exists; parse test: run `hyprlock --config <file> --immediate` is **forbidden** (locks screen); validate statically with a Python check of keys + `source` target exists) → symlink flip → no reload needed (read at next lock) → no dead-man needed, but the standard 120 s switch is armed anyway → verify: file resolves, `font_color` line present, colours equal `colors.json` tokens. Owner check: Super+Shift+L, type a character, see light dots, Esc not available — they unlock by password; if broken, `seclegion-host rollback --last` from another TTY or a second SSH session is documented; the lock is **not** invoked by Legion.
Gate wiring: `tests/host/test-apply-rollback.sh` gets a `lock` case in the fake host.

### C2. Workspace tweaks

**C2.1 Clickable workspace numbers (F1/F2).** Root cause: Waybar 0.15.0 dispatches legacy strings that Hyprland 0.56 Lua mode refuses. Plan with a 30-minute spike first (task W-1):
1. Spike S-ws: check whether the packaged waybar has a newer build with Lua-aware dispatch (`pacman -Si waybar`, release notes of waybar > 0.15.0, `waybar-git` in AUR not allowed in `[seclegion]` unless owner agrees). Check if Hyprland exposes a legacy-dispatch toggle (search `hyprctl getoption`/`man hyprland` for "legacy"); the binary has `CDispatcherTranslator`, so a compat flag may exist. If a flag exists, set it in `seclegion-host.lua` (our own file, allowed) and **stop here**: `on-click: activate` and scroll work unchanged.
2. Otherwise (default plan, no waybar patch): replace the built-in module with `custom/ws1 … custom/ws20`, each:
   ```
   "custom/ws3": { "exec": "seclegion-ws 3", "return-type": "json", "interval": "once",
                   "signal": 8, "on-click": "hyprctl dispatch 'hl.dsp.focus({ workspace = \"3\" })'",
                   "on-scroll-up": "hyprctl dispatch 'hl.dsp.focus({ workspace = \"e-1\" })'",
                   "on-scroll-down": "hyprctl dispatch 'hl.dsp.focus({ workspace = \"e+1\" })'" }
   ```
   `seclegion-ws N` (shell/Python, no loop) prints `{"text":"3","class":"active|occupied|empty|urgent"}` or `{"text":"","class":"hidden"}` (module disappears). One tiny helper `seclegion-wsevents` (user unit `seclegion-wsevents.service`, started from the bar's `exec-on-event`? no: a systemd **user** unit, `socat` on `.socket2.sock`, on `workspace>>`, `createworkspace>>`, `destroyworkspace>>`, `openwindow>>`, `closewindow>>`, `movewindow>>`, `urgent>>` runs `pkill -RTMIN+8 -x waybar`), restarted by the host component. Cost: one idle `socat`. The config is generated from `desktop/waybar/config.jsonc.in` by a build step (`tools/gen-waybar-ws N=20`) so 20 modules are not hand-written; generated file is committed so the host-apply diff is reviewable.
   CSS: `#custom-ws1 … ` replaced by class selectors `.custom-ws.active` using the module `class` list: add `"class"` is per-module, so use CSS rules for `#custom-ws1.active, #custom-ws2.active, ...` generated too. Same pill look as the current `#workspaces button` rules (tokens).
3. Third option (decision D1-alt): fix upstream and wait. Not default.
**C2.2 Persistent workspaces 1–5.** `hl.workspace_rule({ workspace = "1", persistent = true })` … for 1–5 in `seclegion-host.lua` (owner can edit the count in `~/.config/seclegion/workspaces.toml`, Settings > Appearance "Always show workspaces 1–N"). Waybar's built-in module reads them (F3); the custom approach reads `persistent` from `hyprctl workspacerules -j`.
**C2.3 More than 10 workspaces.** 
- Bar: show every existing workspace (`all-outputs`, no cap; custom variant shows up to 20, overflow chip `+N` showing count and opening the workspace overview/menu).
- Keys (new file `seclegion-keys.lua`, see §C6/D2; chosen free keys, all pass `seclegion-keys lint`):
  - `Super + period` → next empty workspace: `hl.dsp.focus({ workspace = "empty" })` (Hyprland `workspace empty`; the first empty ID);
  - `Super + Shift + period` → move focused window to a new empty workspace and follow: `hl.dsp.window.move({ workspace = "empty" })` (spike: if `move` does not accept `empty`, fall back to `hyprctl dispatch` Lua helper that computes the lowest free ID from `hyprctl workspaces -j`, a 15-line Lua function in `seclegion-keys.lua`);
  - `Super + Alt + period` → same but silent (follow = false);
  - `Super + comma` is reserved for notifications (Super+, family) — not used;
  - `Super + Ctrl + Left/Right` → previous/next workspace (`e-1/e+1`), `Super + Alt + 1..0` → workspaces 11–20 (`code:10..19`, id = n+10) and `Super + Alt + Shift + 1..0` move window there. (Super+Alt+digit is free, F4.)
  - Arabic layout aliases: the owner binds both `Arabic_*` keysyms in places; digits and period are layout-independent via `code:` bindings, so use keycodes (period = `code:60`), documented in the file header.
- Move-window-to-new-workspace keys also covered by Settings "Keyboard" page listing (read-only).
- Gate uses QMP key injection in the VM and `hyprctl activeworkspace` (host: owner presses the key; Legion tests the Lua with `hyprctl dispatch` against a **nested** Hyprland, never the live session).

### C3. Resize any floating window (owner addition)
Current state (F4/F9): `Super + mouse:273` (right-drag) `window.resize()` exists. Missing: edge-grab, keyboard resize, presets.
1. **Mouse:** keep the existing bind. Add `hl.config({ general = { resize_on_border = true, extend_border_grab_area = 20, hover_icon_on_border = true } })` in `seclegion-host.lua` (our file; options exist in 0.56 `general:` — spike confirms names with `hyprctl getoption general:resize_on_border`). Right-drag works on tiled and floating windows; border-drag works on floating and tiled (changes split). Add `windowrule` nothing.
2. **Keyboard resize submap** (`seclegion-keys.lua`): `Super + R` is taken (rofi) → use **`Super + Alt + R`** (decision D2 lets owner choose). Implementation with Lua `hl.bind` + submap API (Hyprland 0.56 Lua: `hl.define_submap("resize", function() ... end)` — builder reads `wiki.hypr.land` Lua section and confirms name; if the API differs, use `hl.dsp.submap`): in submap `resize`: `left/right/up/down` and `H/J/K/L` → `hl.dsp.window.resize({x=±40,y=0,relative=true})` (Shift = 10 px steps, Ctrl = 200 px), `equal` / `minus` grow/shrink both axes keeping the centre, `C` centre, `F` toggle float (so tiled windows can be floated first), `1/2/3` presets, `Return`/`Escape` exit with `hl.dsp.submap("reset")`. Waybar shows a `custom/submap` chip "RESIZE" (hyprland/submap module exists in waybar: add `"hyprland/submap": {"format":" RESIZE","tooltip":false}` — its click path is not needed). Tiled windows: arrows resize the split (`resizeactive` works on tiled).
3. **Presets:** `Super + Ctrl + 1/2/3` → 50 %, 70 %, 90 % of the monitor, centred, floating the window first if it is not floating. NOTE: Omarchy-style bar-panel binds on `Super+Ctrl+digit` are skipped (§A1), so these keys are free. Implementation: a Lua function in `seclegion-keys.lua` using `hl.get_active_window()` and the monitor size (`hl.get_active_monitor()` — name uncertain, spike) calling `hl.dsp.window.float({action="enable"})`, `hl.dsp.window.resize({x=W,y=H,exact=true})`, `hl.dsp.window.center()`. Fallback if Lua monitor API is missing: shell helper `seclegion-winsize 50|70|90` using `hyprctl monitors -j` + `hyprctl dispatch` Lua strings (this one is a plain script with unit tests).
4. Settings > Keyboard shows the resize keys; cheat sheet lists them.
5. Gate: nested-Hyprland test spawns `kitty`, floats it, runs `seclegion-winsize 70`, asserts `hyprctl clients -j` size = 70 % ±2 px and centred ±2 px.

### C4. File manager free space and look (owner addition)
Finding (F9): xdg default = **Dolphin**, key Super+E opens **Thunar**, owner also has Nautilus and yazi; mismatch is itself a bug (double-click on a folder in a browser opens Dolphin).
1. **Pick one primary: Thunar** (matches the key, lightest, GTK so it follows the GTK theme). Decision D7 (owner). Set `xdg-mime default thunar.desktop inode/directory` via Settings > Apps (user-level, `~/.config/mimeapps.list`) — a **host** change in the user's config (not forbidden; backup first).
2. **Free space display:**
   - Thunar: View > Show Status Bar (`/org/xfce/thunar/misc-status-bar-visible` in xfconf; since no xfconf daemon, Thunar reads `~/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml` — user file, set `last-statusbar-visible=true`) — Thunar's status bar prints "Free space: 32.1 GiB" for the current folder's filesystem natively.
   - Dolphin (kept installed): "Show Space Information" in the status bar (`~/.config/dolphinrc` `[General] ShowSpaceInfo=true`, `[DolphinStatusBar] ShowZoomSlider=...`) — free space progress bar.
   - Nautilus: sidebar shows disk usage natively (Preferences); no change.
   - yazi: plugin `seclegion-space` (Lua, in `~/.config/yazi/plugins/seclegion-space.yazi/main.lua`, written by us, MIT) showing `free / total` of the cwd's filesystem in the status bar (via `df -h --output=avail,size .`), enabled in `~/.config/yazi/init.lua` (`Status:children_add`). Spike confirms the yazi version API.
   - Fallback: a waybar `disk` module (`"disk": {"format": "󰋊 {free}", "path": "/", "interval": 30, "tooltip-format": "{used} used of {total}", "on-click": "thunar"}`) in modules-right; also `warning` state at 85 % via `"states": {"warning": 85, "critical": 95}`; recommended **both** (waybar chip is the always-visible hint, the file manager gives the per-mount value).
3. **SecLegion look:**
   - GTK3 (Thunar, Nautilus-3 apps): generate `~/.config/gtk-3.0/gtk.css` from tokens (`@define-color theme_bg_color @sl_bg;` + the full GTK3 named colours: `theme_fg_color`, `theme_base_color`, `theme_selected_bg_color`, `theme_selected_fg_color`, `borders`, `insensitive_*`, `warning_color`, `error_color`, `success_color`) and `@import` of `colors.css`. This is a real directory (F9), writable.
   - GTK4/libadwaita (Nautilus): `~/.config/gtk-4.0` is a symlink into `~/.themes/Graphite-Mono/gtk-4.0` (forbidden to write). **Safe approach options** (decision D8): (a) *recommended:* replace the symlink by a real dir `~/.config/gtk-4.0/` containing `gtk.css` = `@import "file://.../Graphite-Mono/gtk-4.0/gtk.css"` (keeps Graphite) then the generated `sl-gtk4.css` overrides (libadwaita named colours: `window_bg_color`, `view_bg_color`, `accent_bg_color`, `headerbar_bg_color`, `sidebar_bg_color`); `seclegion-host apply gtk` backs up the old symlink target string in manifest, restores it on rollback; never writes inside `~/.themes`. (b) run theme only for SecLegion apps via `GTK_THEME` env — no effect on others. (c) leave GTK4 alone, theme only GTK3 + Dolphin.
   - Dolphin/Qt: generated KDE colour scheme `~/.local/share/color-schemes/SecLegion.colors` (INI, from tokens) + `kdeglobals` `[General] ColorScheme=SecLegion` (edit one key; backup). Qt apps without KDE session also use `qt6ct` palette (addendum: qt6ct token palette) — same generator.
   - yazi: `~/.config/yazi/theme.toml` is already hand-coloured with the SecLegion hexes (F9) but not generated; render from tokens: `seclegion-theme` gains a `yazi-theme.toml` output (hook: copy to `~/.config/yazi/theme.toml` only when the file carries our `# generated by seclegion-theme` header, so a hand-edited file is never overwritten; first run backs up the original).
   - Icon theme: stays (Tela/Papirus); a "folder accent" variant is 1.3.
   - New theme outputs go through `seclegion_theme/render.py` + `hooks.py` (`gtk3.css`, `gtk4.css`, `kde.colors`, `yazi-theme.toml`, `qt6ct.conf`), each with a golden test in `desktop/theme/tests`, SPDX headers, and added to the "Output contract" table in README.

### C5. The theme contract grows (supporting both C1 and C4)
`render.py` adds files: `gtk3.css`, `gtk4.css`, `kde.colors`, `yazi-theme.toml`, `qt6ct.conf`; `hyprlock-colors.conf` stays as is. Test: every output parses (GTK CSS via `Gtk.CssProvider.load_from_data` when available, TOML via `tomllib`, INI via `configparser`), no `0x`-style colours, contrast gates apply to the pairs used by the new files.

### C6. The keybind conflict (binding rule R7 §3)
**Conflict:** the owner now wants workspace, resize and other keybinds on the live desktop; R7 §3 forbids editing hypridle, monitor, input and **keybind modules** on the host, and permits only `require("seclegion-host")` plus the file `seclegion-host.lua`.
**Proposal (decision D2):** keep the owner's `modules/keybinds.lua` untouched. Add a **new additive file** `~/.config/hypr/seclegion-keys.lua` (installed by `seclegion-host apply keys`, symlink to `~/.local/share/seclegion/host/keys/seclegion-keys.lua`) loaded from the **existing** `seclegion-host.lua` by one guarded line `pcall(require, "seclegion-keys")` (our file, already allowed → *no new line in the owner's `hyprland.lua`*). If the owner prefers explicitness, the alternative is one line `require("seclegion-keys")` in `hyprland.lua` next to the existing one (a second permitted-by-owner exception).
Safety:
1. The file contains only `hl.bind` calls for keys that `seclegion-keys lint` verifies are absent from the owner's `keybinds.lua` and from `hyprctl binds -j` (lint = diff of (mods,key) sets; any collision fails the apply). It never unbinds or rebinds an owner key.
2. `apply keys` is: back up → lint → install → `hyprctl reload` → `hyprctl configerrors` must be empty → arm the 120 s dead-man; if `configerrors` is non-empty the apply rolls back immediately and the binds disappear (a rollback is just removing the file; `hyprctl reload`).
3. Loaded with `pcall`, so a syntax error in our file cannot break the owner's session (error is logged and the owner's keybinds still load); the host verification still reports it.
4. Keybinds take effect on reload; the rollback path works from a TTY.
5. ISO: the same file ships as `seclegion-keys.lua` and is part of the normal keybind module (no pcall difference).
Without owner approval of D2, Legion implements only the **ISO** side; tasks T3/T4/T14 stay host-gated.

### C7. Keybind conflict check (every new key of this plan vs owner `keybinds.lua` and addendum §2.2)

Owner keys read from `~/.config/hypr/modules/keybinds.lua` (Super+: Return, KP_Enter, T, I, E, B, D, R (rofi app menu), Q, C, F, V, W, P, J, Space, G, Tab, bracket L/R, Y, N, L, Escape, BackSpace, S, Z, F10-F12, H, K, arrows, 0-9; Super+Shift+: Return, KP_Enter, F, W, V, L, B, S, A, C, H/J/K, arrows, 0-9; Super+Ctrl+W; Print variants; XF86 keys; mouse 272/273). Addendum keys: S+M, S+/, S+F1, S+, (+Shift/+Ctrl), S+Ctrl+N/E/C/I/P, Alt+Print, S+Ctrl+Print, S+Alt+Print, S+A, S+X. `seclegion-keys-lint` repeats this check mechanically on every apply (T3 G1/G2). **Super+R is NOT used**; resize mode is on Super+Alt+R.

| New key | Action | Owner keybinds.lua | Addendum 2.2 | Verdict |
|---|---|---|---|---|
| Super+period (`code:60`) | next empty workspace | free | free | OK |
| Super+Shift+period | move window to new empty workspace (follow) | free | free | OK |
| Super+Alt+period | same, silent | free | free | OK |
| Super+Alt+1..0 (`code:10-19`) | focus workspace 11-20 | free (only Super, Super+Shift use digits) | free | OK |
| Super+Alt+Shift+1..0 | move window to workspace 11-20 | free | free | OK |
| Super+Ctrl+Left / Right | previous / next workspace | free (Super+arrows, Super+Shift+arrows only) | free | OK |
| Super+Alt+R | enter resize submap | free (Super+R is rofi, untouched) | free | OK |
| (in submap) arrows, H/J/K/L, equal, minus, C, F, 1/2/3, Return, Escape | grow/shrink, centre, float, presets, exit | active only inside the submap, shadows nothing outside it | n/a | OK |
| Super+Ctrl+1 / 2 / 3 | window 50 / 70 / 90 %, centred | free | free | OK |
| Super+Ctrl+Z / Super+Ctrl+Alt+Z | cursor zoom in / reset | free (Super+Z is scratchpad restore, different mods) | free | OK |
| Super+Ctrl+Return | terminal in cwd | free | free | OK |
| Super+Ctrl+Alt+T / Super+Ctrl+Alt+B | show time / battery notification | free | free | OK |
| Super+Ctrl+T / B / D | btop float / bluetooth / Settings display | free (Super+T/B/D without Ctrl are owner's) | free | OK |
| Super+Ctrl+Alt+W | network (nmtui float) | free | free | OK (Super+Ctrl+W is owner's live wallpaper: avoided) |
| Super+Ctrl+Shift+W | wallpaper grid in Settings | free (Super+Shift+W and Super+Ctrl+W exist, this chord differs) | free | OK |
| Super+Ctrl+equal | calculator | free | free | OK |
| Super+Ctrl+Alt+R | reminder | free | free | OK |
| Super+M, Super+/, Super+F1, Super+X, Super+A | menu, cheat sheet, tools, AI picker | free | owned by addendum | OK (not added by this plan) |
| Rejected: Super+R (rofi), Super+C/V/A/X (owner/addendum), Super+Ctrl+W (live wallpaper), Super+Ctrl+digit bar panels (clash with presets) | | taken | | not used |
Arabic layout: all new binds use `code:` keycodes or non-letter keys, so they work in both `us` and `ara` (the owner's letter binds need `Arabic_*` aliases; ours need none, except Super+Alt+R, Super+Ctrl+T/B/D/Z which get `Arabic_*` aliases generated by the lint tool from the addendum alias table).

## D. Polish list (30 items; priority P1 high … P3 low)

| # | Item | Pri | Host/ISO | Notes |
|---|---|---|---|---|
| 1 | Lock-screen dots visible (C1) | P1 | host | |
| 2 | Clickable workspaces (C2.1) | P1 | host | |
| 3 | Next-empty-workspace key (C2.3) | P1 | host (D2) | |
| 4 | Resize keys/presets/edge grab (C3) | P1 | host (D2) | |
| 5 | One file manager (Thunar) + free space + theme (C4) | P1 | host (user config) | |
| 6 | Waybar `disk` chip with warning states | P2 | host | CSS states from tokens |
| 7 | Waybar `hyprland/submap` chip (RESIZE) | P2 | host | |
| 8 | Hypridle: add screen-off (dpms) at 330 s, before/after sleep lock, no suspend on AC (Settings writes it) | P1 | ISO; host needs D5 | F6 |
| 9 | Autostart hygiene: `swaync` is started twice in owner's autostart.lua, `dunst` references gone | P2 | host (one-line edit already allowed by R7 §3? it's the dunst→swaync edit; double swaync is a new finding) | spawn guard `pidof swaync` |
| 10 | Fix `Super+W`/`Super+V` duplicates and Arabic aliases listed in cheat sheet | P3 | ISO | lint output |
| 11 | OSD (volume/brightness) uses `dunstify` in `ae-osd.sh` but dunst is not the owner; swayosd (addendum) | P1 | ISO; host: script edit forbidden → waybar/swaync `notify-send` shim `dunstify` → `notify-send` wrapper in `~/.local/bin/dunstify` (allowed: `~/.local/bin/seclegion-*` only → name must be `seclegion-dunstify`; so rather a PATH-ahead symlink needs owner OK) | D9 |
| 12 | Battery chip: click opens Settings > Power; right-click cycles profile | P2 | host | |
| 13 | Volume chip: right-click opens Settings > Sound | P3 | host | |
| 14 | Clock chip tooltip: week numbers, calendar scroll to change month | P3 | host | waybar `calendar` options |
| 15 | Network chip: right-click opens Settings > Network; show VPN `tun0` state | P2 | host | |
| 16 | Bluetooth chip (hidden when off/no adapter) | P2 | host | `bluetooth` module |
| 17 | Power-profile chip (hidden when ppd absent) | P2 | host/ISO | |
| 18 | Notification bell chip (DND state) | P2 | host | swaync `custom/notification` |
| 19 | CPU/RAM/temperature tooltip on a single "system" chip | P3 | host | |
| 20 | Wallpaper picker integrated into Settings (the yazi picker stays) | P2 | ISO | |
| 21 | Lock-screen: show keyboard layout (`$LAYOUT`) and a caps-lock warning (`capslock_color`) | P2 | host | in C1 file |
| 22 | Lock-screen: user avatar `~/.face` + name label | P3 | host | |
| 23 | Cursor: confirm size 24 across GTK/Hyprland/XCURSOR | P3 | ISO | already a gate |
| 24 | Window rules: float + centre helper windows (pavucontrol, blueman, nm-connection-editor, SecLegion Settings 980x680) | P2 | host (windowrules.lua is the owner's → do via `seclegion-keys.lua` `hl.window_rule`) | D2 |
| 25 | Smooth workspace switch animation consistent (reduced-motion toggle) | P3 | ISO | |
| 26 | Screenshot flow: after capture, notification with "Open folder / Copy / Edit (swappy)" actions | P2 | ISO | swaync actions |
| 27 | Terminal quality: kitty `confirm_os_window_close`, scrollback pager = bat, URL hints | P3 | ISO | |
| 28 | First-run tour toast ("Press Super+/ for shortcuts, Super+M for the menu") once | P2 | ISO | welcome |
| 29 | Greeter / login branding matching tokens | P3 | ISO | greetd regreet CSS |
| 30 | Low-disk warning: notify at 90 % on `/` and 85 % on any mounted data disk, with link to Storage page | P2 | ISO | user timer |
| 31 | Default Dolphin/Thunar mismatch fix (C4) | P1 | host | included in 5 |
| 32 | `seclegion-doctor`: one command listing config errors (`hyprctl configerrors`), duplicate daemons (swaync twice), missing binaries for every bind, failed user units | P2 | host/ISO | read-only |
| 33 | Keyboard layout OSD in the notification style (exists: toggle-layout.sh) restyled via swaync, plus bar language chip click | P3 | host | already works |
| 34 | Boot: hide fsck/log noise with `quiet` + splash (covered by O12) | P2 | ISO | |
| 35 | Fonts: ensure Arabic glyph coverage (Noto Naskh/Kufi) in bar/lock | P2 | ISO | owner uses `ara` layout |

## E. Work breakdown (Legion tasks)

Ordering: T1–T3 are the quick visible host wins. Every host task uses `tools/seclegion-host apply <component>` (backup, dead-man 120 s, rollback); every host task adds a case to `tests/host/test-apply-rollback.sh`. Gates use the form `G<n> outcome — CHECK: command — EXPECT: token`. Repo root is `/mnt/Dev_Lab/SecLegion-OS`.

**T1. Lock screen dots (host component `lock`).**
Files: `desktop/hypr/hyprlock.conf` (new), `tools/seclegion-host` (add component `lock`, add `hypr/hyprlock.conf` to symlink-flip list), `tools/host-apply` (if component table lives there), `tests/host/test-apply-rollback.sh`, `desktop/theme/tests/test_lock_contrast.py`.
Gates:
- G1 font colour comes from the token — CHECK: `grep -E '^\s*font_color\s*=\s*\$sl_text' desktop/hypr/hyprlock.conf` — EXPECT: `font_color`
- G2 no hard-coded dark inner colour — CHECK: `grep -c 'rgba(5, 15, 14' desktop/hypr/hyprlock.conf` — EXPECT: `0`
- G3 check/fail colours use tokens — CHECK: `grep -E 'check_color = \$sl_warn|fail_color = \$sl_crit' desktop/hypr/hyprlock.conf | wc -l` — EXPECT: `2`
- G4 contrast ≥ 7:1 — CHECK: `python3 -m unittest desktop.theme.tests.test_lock_contrast` — EXPECT: `OK`
- G5 apply/rollback on fake host — CHECK: `bash tests/host/test-apply-rollback.sh` — EXPECT: `PASS` (ends with the suite's pass line; builder records the exact token)
- G6 source target exists after apply (fake host) — CHECK: `bash tests/host/test-apply-rollback.sh 2>&1 | grep lock-source-ok` — EXPECT: `lock-source-ok`
- G7 mutation: drop `font_color` line → G1 turns red (reviewer runs it).
Host: YES. Owner check: lock, type, dots visible; `seclegion-host confirm`.

**T2. Clickable workspaces.**
Files: `desktop/waybar/config.jsonc` (generated from `config.jsonc.in`), `desktop/waybar/style.css`, `tools/gen-waybar-ws` (new), `desktop/waybar/seclegion-ws` (new), `desktop/waybar/seclegion-wsevents.service` (user unit), `tools/seclegion-host` (waybar component installs the helper + unit, `daemon-reload`), tests.
First step: spike S-ws (C2.1.1) recorded in `docs/spec/v1/evidence/ws-spike.md` (Legion writes under `evidence/`, allowed). If a legacy-dispatch flag exists, T2 becomes a 3-line change in `seclegion-host.lua`.
Gates:
- G1 root cause reproduced — CHECK: `bash tests/ws/repro.sh` (sends `dispatch workspace` to a nested Hyprland socket, prints reply) — EXPECT: `lua-rejects-legacy`
- G2 generated config has 20 pills — CHECK: `grep -c '"custom/ws' desktop/waybar/config.jsonc` — EXPECT: `20` (declaration lines; builder fixes exact count with the generator)
- G3 click command works in nested Hyprland — CHECK: `bash tests/ws/click.sh 3` (spawns nested Hyprland, runs the `on-click` string, reads `hyprctl activeworkspace -j`) — EXPECT: `active=3`
- G4 hidden when empty — CHECK: `desktop/waybar/seclegion-ws 15` (no workspace 15) — EXPECT: `"class":"hidden"`
- G5 waybar parses config — CHECK: `waybar -c desktop/waybar/config.jsonc -s desktop/waybar/style.css --log-level error --help >/dev/null; python3 -c "import re,json,sys;json.loads(re.sub(r'^\s*//.*$','',open('desktop/waybar/config.jsonc').read(),flags=re.M))" && echo parse-ok` — EXPECT: `parse-ok`
- G6 host apply waybar on fake host and rollback restores sha256 — CHECK: `bash tests/host/test-apply-rollback.sh` — EXPECT: pass line.
- G7 persistent 1–5 in `seclegion-host.lua` — CHECK: `grep -c 'persistent = true' desktop/hypr/seclegion-host.lua` — EXPECT: `5`
Host: YES (waybar component, `seclegion-host.lua`; user unit allowed by R7 §3). Owner check: click pills 1..5, scroll over bar.

**T3. Next empty workspace + >10 workspaces + move-to-new (keys component).**
Files: `desktop/hypr/seclegion-keys.lua` (new), `tools/seclegion-keys-lint` (new, Python), `tools/seclegion-host` (component `keys`), `desktop/hypr/seclegion-host.lua` (guarded `pcall(require,"seclegion-keys")`), tests. **Blocked until owner answers D2**; ISO side may proceed.
Gates:
- G1 lint detects collision with owner keys — CHECK: `python3 tools/seclegion-keys-lint tests/keys/fixtures/owner-keybinds.lua desktop/hypr/seclegion-keys.lua` — EXPECT: `collisions=0`
- G2 mutation: add `SUPER + Tab` to keys file → CHECK: same command with `tests/keys/fixtures/mutant.lua` — EXPECT: `collisions=1`
- G3 empty-workspace dispatch in nested Hyprland — CHECK: `bash tests/keys/empty-ws.sh` — EXPECT: `empty-ws-ok` (focus moved to the lowest empty id > current non-empty)
- G4 move-to-new keeps window — CHECK: `bash tests/keys/move-new.sh` — EXPECT: `move-new-ok`
- G5 `Super+Alt+1..0` focus ids 11–20 — CHECK: `bash tests/keys/ws11-20.sh` — EXPECT: `ws11-20-ok`
- G6 configerrors empty on reload — CHECK: `bash tests/keys/configerrors.sh` — EXPECT: `configerrors-empty`
- G7 apply/rollback on fake host removes file and symlink — CHECK: `bash tests/host/test-apply-rollback.sh` — EXPECT: pass line.
Host: YES (after D2).

**T4. Resize: edge grab, submap, presets.**
Files: `desktop/hypr/seclegion-keys.lua` (append), `desktop/hypr/seclegion-host.lua` (resize_on_border), `desktop/bin/seclegion-winsize` (fallback), `desktop/waybar/config.jsonc` (submap chip), tests.
Gates:
- G1 border options exist and set — CHECK: `hyprctl getoption general:resize_on_border` against nested instance after loading file (`bash tests/keys/border-opt.sh`) — EXPECT: `int: 1`
- G2 existing right-drag bind untouched — CHECK: `grep -c 'mouse:273' ~/.config/hypr/modules/keybinds.lua` — EXPECT: `1`
- G3 preset 70 % centred — CHECK: `bash tests/keys/winsize.sh 70` — EXPECT: `size-ok center-ok`
- G4 submap enter/step/exit — CHECK: `bash tests/keys/resize-submap.sh` — EXPECT: `submap-ok`
- G5 lint collisions — CHECK: lint command as T3 — EXPECT: `collisions=0`
Host: YES (after D2 for keys; `resize_on_border` only touches our file and can ship in T2's apply).

**T5. File manager: single default, free space, SecLegion GTK look.**
Files: `desktop/theme/seclegion_theme/render.py`, `hooks.py` (gtk3.css, gtk4.css, kde.colors, yazi-theme.toml, qt6ct.conf), `desktop/theme/README.md`, `desktop/fm/thunar.xml`, `desktop/fm/dolphinrc.part`, `desktop/fm/yazi/plugins/seclegion-space.yazi/main.lua`, `tools/seclegion-host` (components `gtk`, `fm`), tests.
Gates:
- G1 gtk3 css parses — CHECK: `python3 -m unittest desktop.theme.tests.test_gtk_outputs` — EXPECT: `OK`
- G2 never writes under `~/.themes` — CHECK: `bash tests/host/test-apply-rollback.sh 2>&1 | grep themes-untouched` — EXPECT: `themes-untouched`
- G3 gtk-4.0 symlink restored on rollback — CHECK: same script, case `gtk` — EXPECT: `gtk4-symlink-restored`
- G4 default handler thunar after apply (fake) — CHECK: `grep 'inode/directory=thunar.desktop' $FAKE_HOME/.config/mimeapps.list` in test — EXPECT: `thunar.desktop`
- G5 Thunar statusbar flag — CHECK: `grep -c 'last-statusbar-visible' desktop/fm/thunar.xml` — EXPECT: `1`
- G6 yazi plugin loads (headless `yazi --clear-cache --version` + lua syntax `luac -p`) — CHECK: `luac -p desktop/fm/yazi/plugins/seclegion-space.yazi/main.lua && echo lua-ok` — EXPECT: `lua-ok`
- G7 yazi theme only overwritten with our header — CHECK: `bash tests/theme/yazi-guard.sh` — EXPECT: `yazi-guard-ok`
Host: YES (user files only; gtk-4.0 symlink flip needs D8).

**T6. Settings backend: registry, readers/writers, CLI, capabilities (no GTK).**
Files: `desktop/settings/seclegion_settings/backend/*`, `tools/seclegion-set`, `desktop/settings/tests/*`.
Gates:
- G1 every registry row has reader/writer/description — CHECK: `python3 -m unittest desktop.settings.tests.test_registry` — EXPECT: `OK`
- G2 round trip for all user-level rows against stubs — CHECK: `python3 -m unittest desktop.settings.tests.test_roundtrip` — EXPECT: `OK`
- G3 absent capability hides row — CHECK: `SL_SYSFS=tests/settings/fixtures/sysfs-nobat tools/seclegion-set list --json | grep -c charge_limit` — EXPECT: `0`
- G4 dry-run writes nothing — CHECK: `bash tests/settings/dryrun.sh` — EXPECT: `dryrun-clean`
- G5 hypridle render ordering/AC rule — CHECK: `python3 -m unittest desktop.settings.tests.test_hypridle` — EXPECT: `OK`
- G6 mutation: swap lock/dpms order → red.
Host: ISO-only code; runs read-only on the host.

**T7. Settings privileged helper + polkit policy.**
Files: `desktop/settings/helper/seclegion-settings-helper`, `desktop/settings/polkit/org.seclegion.settings.policy`, tests.
Gates:
- G1 allowlist enforced — CHECK: `python3 -m unittest desktop.settings.tests.test_helper` — EXPECT: `OK`
- G2 policy XML valid and complete — CHECK: `xmllint --noout desktop/settings/polkit/org.seclegion.settings.policy && python3 tests/settings/policy_xcheck.py` — EXPECT: `policy-ok`
- G3 symlink target refused — CHECK: `bash tests/settings/helper-symlink.sh` — EXPECT: `refused`
- G4 logind drop-in text — CHECK: `desktop/settings/helper/seclegion-settings-helper --dry-run logind lid_battery=suspend` — EXPECT: `HandleLidSwitch=suspend`
- G5 no stored credentials — CHECK: `grep -rEi 'password|sudo ' desktop/settings/seclegion_settings | grep -v '^.*#' | wc -l` — EXPECT: `0` (nmcli connect dialog excluded by naming that module `net_secret.py`; reviewer reviews)
Host: NO (ISO/package; host shows preview only).

**T8. Settings GTK4 app shell: sidebar, search, details expanders, theming.**
Files: `desktop/settings/seclegion_settings/ui/*`, `css/settings.css`, `desktop/settings/seclegion-settings.desktop`, `tools/seclegion-settings` launcher.
Gates:
- G1 every page instantiates — CHECK: `xvfb-run -a python3 -m unittest desktop.settings.tests.test_ui_smoke` — EXPECT: `OK`
- G2 every row has details — CHECK: same — EXPECT: `rows-with-details=ALL`
- G3 CSS loads tokens — CHECK: `python3 tests/settings/css_tokens.py` — EXPECT: `sl_bg-mapped`
- G4 no network at start — CHECK: `unshare -rn python3 tools/seclegion-settings --self-test` — EXPECT: `self-test-ok`
- G5 screenshot sample — CHECK: `bash tests/settings/screenshot.sh power` — EXPECT: `sidebar-bg-ok accent-ok ocr-ok`
- G6 `--page` deep links — CHECK: `tools/seclegion-settings --list-pages | wc -l` — EXPECT: `17`
Host: runs as user on the host from the repo (no install needed; owner may run `tools/seclegion-settings`).

**T9. Settings pages batch 1: Power, Sleep/Lock/Idle, Display, Sound.** Files: `pages/{power,sleep,display,sound}.py`, backend rows, tests; gates: per-row stub tests `python3 -m unittest desktop.settings.tests.test_page_power ...` — EXPECT `OK`; `bash tests/settings/lid-undo.sh` — EXPECT `undo-ok`. ISO (helper) + user rows work on host.
**T10. Settings pages batch 2: Network, Bluetooth, Keyboard & Mouse, Date/Language, Notifications, Apps.** Same gate style; `bash tests/settings/nmcli-secret.sh` — EXPECT `no-secret-in-argv-or-log`.
**T11. Settings pages batch 3: Appearance (theme/wallpaper/fonts/look), Updates & Snapshots, Storage, Security, Troubleshoot, About.** Gates include `seclegion-set get appearance.theme_source` — EXPECT `default`, `python3 -m unittest …test_page_storage` — EXPECT `OK`, About copy-diagnostics redaction test — EXPECT `redacted-ok`.
**T12. Menu + bar + cheat-sheet integration.** Files: `desktop/menu/menu.toml` (Settings entry), waybar right-click handlers, `keybinds.toml` entries. Gate: `seclegion-keys --json | python3 -c 'import json,sys;d=json.load(sys.stdin);print(any("settings" in x["cmd"] for x in d))'` — EXPECT `True`. ISO (host: bar right-clicks only, component `waybar`).
**T13. Omarchy-parity quick wins (NEW rows in §A, 1.0.1):** `seclegion-launch`, pop-out, tiled fullscreen, gaps/transparency toggles, time/battery notifications, reminder, calculator, troubleshoot restarts. Files per feature under `desktop/bin/`; gates: one unit test per script (`python3 -m unittest desktop.tests.test_launch` — EXPECT `OK`), key lint `collisions=0`. ISO + keys component (after D2).
**T14. Polish batch 1 (P1/P2 host items 6,7,9,12,15–18,21,24,32).** Files: `desktop/waybar/*`, `desktop/hypr/seclegion-host.lua`/`seclegion-keys.lua`, `tools/seclegion-doctor`. Gates: `tools/seclegion-doctor --json | grep -c '"level":"error"'` — EXPECT `0`; waybar parse (as T2 G5); `seclegion-notify-test normal` matrix — EXPECT `PASS`. Host: YES.
**T15. Polish batch 2 (ISO: items 8, 10, 11, 20, 23, 25–30, 34, 35).** Gates by item; hypridle gate `python3 -m unittest …test_hypridle` — EXPECT `OK`; `fc-list | grep -ci 'naskh\|kufi'` — EXPECT `1` (≥1; use `-ge` in script).
**T16. Docs and provenance.** `docs/spec/v1/inputs/omarchy-features.md` gains a pointer to §A of this plan; `PROVENANCE.md` lines for Omarchy-derived ideas (menu structure, keys); `docs/settings.md` (user doc, generated from the registry). Gate: `python3 tools/licence-similarity` — EXPECT `PASS`.

Dependencies: T1,T2 independent; T3→T4,T13,T14(keys part); T5 independent; T6→T7→(T9,T10,T11)→T12; T8 after T6. Parallelism: T1,T2,T5,T6 can run in parallel worktrees.

## F. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Workspace-click fix: (a) custom per-workspace waybar modules (default plan), (b) wait for/ask for a waybar release with Lua dispatch, (c) a Hyprland compat flag if the spike finds one | (c) if it exists, else (a). Say yes to proceeding with the 30-min spike. |
| D2 | **Keybind conflict with R7 §3.** Allow a new additive `~/.config/hypr/seclegion-keys.lua`, loaded with `pcall(require)` from the already-allowed `seclegion-host.lua`; lint prevents collisions; dead-man + `configerrors` check. Alternative: put the same lines in your `keybinds.lua` by hand. Without approval Legion ships these keys on the ISO only. | Approve the new file + pcall loader. Keys: `Super+.` next empty workspace, `Super+Shift+.` move to new, `Super+Alt+R` resize mode (Super+R stays rofi), `Super+Ctrl+1/2/3` sizes 50/70/90 % (full conflict table in C7). |
| D3 | Settings toolkit: GTK4 + libadwaita in Python, with a CLI and rofi quick menu on the same backend | Yes. Quickshell stays a 2.0 spike. |
| D4 | Allow `seclegion-host` to flip the `~/.config/hypr/hyprlock.conf` symlink (it is not hypridle/monitor/input/keybinds) | Yes. |
| D5 | Hypridle on the host: R7 forbids it, but sleep/suspend settings need it. Option A: Settings writes `~/.config/seclegion/idle.conf` and offers a one-time guarded include; B: owner edits hypridle.conf once by hand (we show the diff); C: ISO only | B (one-time diff you apply yourself), then Settings manages the included file. |
| D6 | Root settings (lid, power button, charge limit, sleep mode) on this live host: R7 forbids `/etc`. Options: wait for package install; or you run `pkexec` helper yourself after reviewing it | Wait for the ISO/package; the host shows previews. Your laptop has no charge-limit file anyway. |
| D7 | One file manager: Thunar (matches Super+E) vs Dolphin (current xdg default) vs Nautilus | Thunar. Keep Dolphin installed. |
| D8 | GTK4 theming: (a) replace the `~/.config/gtk-4.0` symlink by a real dir that `@import`s Graphite-Mono then our tokens (rollback restores the symlink), (b) per-app only, (c) GTK3 + Qt only | (a). Nothing inside `~/.themes` is written. |
| D9 | `ae-osd.sh` uses `dunstify`, which is not running. Provide `seclegion-dunstify` shim and a PATH-ahead alias, or you edit the script | Edit the script by hand once (we give the diff) or allow the shim in `~/.local/bin`. |
| D10 | Omarchy items marked SKIP (timed passwordless sudo, pacman guard, Super+C/V, dock, plugin system, usage meters, weather) | Confirm skip. |
| D11 | Persistent workspaces count (1–5 default) and bar cap (20) | 5 and 20. |
| D12 | Install `power-profiles-daemon` and `hyprsunset` on the host now (pacman is forbidden by R7; you would run it) so Power and Night-light pages work live | Yes, you install: `sudo pacman -S power-profiles-daemon hyprsunset`. |

Unverified / to check by the builder (named so they are not mistaken for facts): Lua submap API names in Hyprland 0.56; whether `window.move({workspace="empty"})` is accepted; `hl.get_active_monitor` size API; `general:resize_on_border` option names; hyprlock `check_color`/`capslock_color` key names in 0.9.6 (verify with `hyprlock --help`/wiki, not by locking); yazi status-bar plugin API version; whether a Hyprland legacy-dispatch compat flag exists; waybar release carrying Lua dispatch.

## G. Owner answers (2026-10-15)
- **D2: approved, on the live host AND in the ISO.** Add `seclegion-keys.lua`, loaded with `pcall(require)` from `seclegion-host.lua`, with lint, the dead-man switch and a `configerrors` check. The same file ships in the ISO.
- **D4: approved.** `seclegion-host` may flip `~/.config/hypr/hyprlock.conf` to the themed lock config.
- **D7: Thunar** is the SecLegion file manager. Dolphin stays installed.
- **D8: approved, option (a).** `~/.config/gtk-4.0` becomes a real dir that `@import`s Graphite-Mono, with SecLegion tokens on top. Rollback restores the symlink. Nothing is written in `~/.themes`.
- **Super+R stays the rofi app menu.** Resize mode is on Super+Alt+R.
- D1, D3, D5, D6, D9–D12: the recommendations are taken as defaults until the owner says otherwise. D12 (installing packages) is the owner's action.
