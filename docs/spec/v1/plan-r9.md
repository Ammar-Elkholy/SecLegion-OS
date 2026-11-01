<!-- SPDX-License-Identifier: MIT -->
# Plan R9: owner feedback after the first live use (2026-10-15 night)

Owner messages, quoted. Each item gets a task, a gate, and a host apply with backup and rollback.

## Done live
- Lid ignore: system settings only previewed, so the lid suspended. A user-level lid inhibitor (`seclegion-lid-inhibit`) is held now. T9 makes the Settings row real and ships `seclegion-root-apply` for the root rows.
- Keys: `border` and `keys` components applied and confirmed (25 binds).

## T10 One notification for the function keys
"the notifications of the function keys are being sent again every time it changes, it supposed to be just one notification on the top right."
- Cause: `ae-osd.sh` calls `dunstify` with `x-dunst-stack-tag`. swaync ignores that hint, so each press stacks. swaync does advertise `x-canonical-private-synchronous` (verified with `GetCapabilities`).
- Fix without editing the owner's script: a `dunstify` shim (rewrites `x-dunst-stack-tag:X` to `x-canonical-private-synchronous:X`, then execs `/usr/bin/dunstify`), installed by a host component ahead of `/usr/bin` in PATH (`~/.local/bin` is first), plus `seclegion-osd` for our own keys. One OSD popup, replaced in place, 2 s timeout, top right.
- Gate: fake `/usr/bin/dunstify` records args; a press sequence yields the same synchronous tag every time; real swaync nested test (replace id stays the same) if feasible.

## T11 Theme everywhere, theme manager, automatic per wallpaper
"theme color affects everything: the login, the waybar, the notification, the windows outline; make a theme manager like the wallpaper manager, automatic: get a fitting theme for each wallpaper, the best colors for the theme in it."
- Coverage audit (one table in `docs/`): every surface, whether it follows the tokens now (waybar, swaync, rofi, kitty, hyprlock, swayosd, starship, fastfetch, window border/outline, GTK3/4, Qt, yazi; login greeter on the ISO via regreet CSS).
- Window outline: the `border` component must source the theme's `hypr-colors.lua`/token file and reload on theme change (no hard-coded green).
- Theme manager: a window and a quick picker. Entries are the built-in SecLegion themes plus one generated palette per wallpaper (matugen, `--prefer saturation`), each with a live colour preview; Apply, Auto toggle, Reset. Auto mode: wallpaper change triggers `seclegion-theme apply --wallpaper` (hook into the owner's wallpaper manager script via the theme engine, no edits to owner files; use a watcher on the wallpaper state if the manager has no hook).
- Gate: golden palettes for 3 fixed wallpapers; contrast clamps hold; nested screenshot shows the border and bar in the new accent.

## T12 Waybar v2: network, statistics, more techy than Omarchy
"the waybar has some problems like the 2 wifis, and being not very SecLegion personalized about the network settings and techy enough, and no statistics. Omarchy is good, I want SecLegion better."
- Two wifi icons: the `network` module and the `nm-applet` tray icon both show. Keep one (our module) and hide the tray one (tray `hide`/filter, no autostart edit).
- Network module: SSID, signal bars, IP, up/down speed, VPN state, interface; tooltip with gateway, DNS, link speed; click opens a SecLegion network panel (Settings Network page), right-click toggles Wi-Fi.
- Statistics group (compact, expands on hover or click): CPU % and temperature, RAM, GPU (amdgpu), disk, net speed, load, battery watts, uptime. Event-driven or at most every 2-5 s; no resident process beyond waybar; total CPU under 1 %.
- Style: tokens only, mono glyphs, security-flavoured chips (VPN lock, listening ports count, firewall state if readable).
- Gate: idle CPU measured before and after; the bar renders with no duplicate icons in a nested screenshot; modules degrade quietly when hardware is missing.

## T13 — no surprise lock (owner 2026-10-15 night: "laptop logs out and still asks for passwd")
Cause (read-only check): owner's `hypridle.conf` runs `loginctl lock-session` after 300 s idle, so hyprlock asks for the password. Not a logout (uptime unbroken). Fix without editing owner files: Settings row `power.autolock` (user-level idle inhibitor service, like the lid one) plus a longer-timeout option in a SecLegion-owned hypridle include; owner's hypridle.conf stays untouched unless the owner approves. Planned by an Opus planner, built by Sonnet.
