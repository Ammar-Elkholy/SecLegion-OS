# Plan r10: T10 OSD, T12 Waybar v2, T13 no surprise lock

Builders: Sonnet, at most 2 at once. The main session reviews every branch. Host rules for every job: no sudo, no edits under `/etc`, never edit `~/.config/hypr/hypridle.conf` or `ae-osd.sh` or any other owner file. Shims go in `~/.local/bin` as symlinks into `~/.local/share/seclegion/host/<comp>/`. Every live change goes through `seclegion-host apply <comp>`, which takes a backup, arms the 120 s dead-man, and waits for `confirm`. Hyprland tests run only in a nested instance. Each new component adds entries to `COMPONENTS`, `comp_paths`, `comp_source`, `stage`, `install_comp`, `reload_comp` and `verify_comp` in `tools/seclegion-host`. `extend_baseline` covers new paths. Tests go in `tests/host/test-apply-rollback.sh` (fake-host).

## Fact found while planning (affects T10 and T12)
The Hyprland process (and hypridle) runs with `PATH=/usr/local/bin:/usr/bin` (read from `/proc/<pid>/environ`), so a `~/.local/bin` shim is invisible to binds and autostart. Fix: the SecLegion-owned `desktop/hypr/seclegion-host.lua` (border component) sets `PATH` to `$HOME/.local/bin:<old>` through the Lua env API. That path then reaches every exec. Job T10-1 checks this first in the nested instance. If the env setting does not survive a reload or does not reach exec children, stop. The owner action is then one line, `ln -s ~/.local/bin/dunstify /usr/local/bin/dunstify` (root), and only that job changes.

## T10 One OSD notification
Interfaces:
- `desktop/osd/dunstify` (bash): rewrites `string:x-dunst-stack-tag:X` to `string:x-canonical-private-synchronous:X`, leaves the other arguments as they are, then runs `exec /usr/bin/dunstify "$@"` by absolute path, so it never calls itself.
- `desktop/osd/seclegion-osd <kind> <value> [label]`: our own keys. It uses the tag `seclegion-osd`, a 2000 ms timeout and low urgency, and passes `int:value`.
- Host component `osd`. Paths: `.local/share/seclegion/host/osd`, `.local/bin/dunstify`, `.local/bin/seclegion-osd`. `install_comp` symlinks both into `~/.local/bin`. `link_or_absent` must refuse a real file already at `~/.local/bin/dunstify`. Reload: nothing.
- Top-right placement and the 2 s timeout come from swaync `config.json` (`positionX: right`, `positionY: top`); this is a `notifications` component edit.

Jobs:
1. PATH line in `seclegion-host.lua`, nested probe script `tests/osd/path-probe.sh`, and the fake-host test for it.
2. `desktop/osd/dunstify`, `desktop/osd/seclegion-osd`, unit test `tests/osd/test_shim.sh` (a fake `/usr/bin/dunstify` set by `SL_DUNSTIFY_REAL` that records its argv).
3. The `osd` component in `seclegion-host`, the swaync position keys, and the fake-host apply/rollback test.

Gates:
- G1 the shim rewrites the tag — CHECK: `tests/osd/test_shim.sh` — EXPECT: `synchronous-tag-ok`
- G2 five presses in a row keep one id — CHECK: nested swaync, `ae-osd.sh vol-up` ×5 with `dunstify -p` probing — EXPECT: `replace-id-stable`
- G3 the shim runs from a Hyprland bind — CHECK: `tests/osd/path-probe.sh` (nested `hyprctl dispatch exec` then read `/proc/<pid>/environ`) — EXPECT: `localbin-first`
- G4 (negative) no recursion and no clobbering — CHECK: a fake host with a real file at `~/.local/bin/dunstify`, `apply osd` — EXPECT: `refusing to replace it`
- G5 (negative) rollback leaves nothing behind — CHECK: `rollback --last; test -e ~/.local/bin/dunstify` — EXPECT: `absent`

## T12 Waybar v2
Duplicate Wi-Fi icon: `nm-applet --indicator` registers a tray item (it also triggers the glycin hang). Use a shim, `desktop/waybar/nm-applet`, that runs `exec /usr/bin/nm-applet` with `--indicator` removed. This keeps the NetworkManager secret agent, so Wi-Fi password prompts still appear, and drops the tray icon, because without `--indicator` the applet only offers the XEmbed icon, which Wayland bars do not show. The builder confirms with `nm-applet --help` first. The `waybar` component installs the shim in `~/.local/bin`, stops the running nm-applet by pid, and starts it again through the shim. Rollback restarts `/usr/bin/nm-applet --indicator`. This change depends on the T10-1 PATH line taking effect at the next login.

Network module (`config.jsonc.in`):
- `interval: 3`; format `󰖩 {essid} {signalStrength}% ⇡{bandwidthUpBytes} ⇣{bandwidthDownBytes}`.
- Tooltip: `{ifname} {ipaddr}/{cidr} gw {gwaddr} {frequency}GHz`.
- `on-click`: `seclegion-settings --page network`. `on-click-right`: `nmcli radio wifi` toggle.
- Separate `custom/sl-vpn` (exec-on-event with `signal`, no interval polling) for the VPN lock state, from `nmcli -t c show --active` type `vpn|wireguard`.

Statistics group `group/sl-stats` (drawer, expands on hover):
- `cpu` (interval 5), `temperature` (k10temp hwmon via `hwmon-path-abs` + `input-filename`), `memory` (5), `disk` (30).
- `custom/sl-gpu` reads `/sys/class/drm/card1/device/gpu_busy_percent` with `interval: 5` and `cat` only. It is hidden if the file is missing.
- `custom/sl-sec` (interval 30): number of listening TCP ports from `/proc/net/tcp{,6}` (state `0A`) and the firewall state, if `nft list` can read it without root; otherwise the firewall part is left out.
- `battery` gains `{power}` W; `custom/sl-uptime` (interval 60).
- Helpers are short-lived scripts in `desktop/waybar/` that `stage` moves to `host/bin`. No resident process. Style uses tokens only, in `style.css.in` chips.

Jobs:
1. Measure the CPU baseline (`tools/host-measure`, waybar plus children over 60 s), add the `nm-applet` shim and its install/rollback in `seclegion-host`, and the fake-host test.
2. Network module, `custom/sl-vpn`, `custom/sl-sec` (plus helpers and the "quiet when missing" test `tests/desktop/test_waybar_modules.py`).
3. Stats group, gpu/uptime helpers, CSS chips and the nested screenshot.

Gates:
- G1 one Wi-Fi icon — CHECK: `busctl --user get-property org.kde.StatusNotifierWatcher /StatusNotifierWatcher org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems` — EXPECT: no `nm-applet` (string `sni-nm-absent`)
- G2 the password agent is kept — CHECK: `pgrep -a nm-applet` — EXPECT: a running `/usr/bin/nm-applet` with no `--indicator`
- G3 idle CPU stays low — CHECK: `tools/host-measure waybar 60` — EXPECT: `cpu<1.0%`
- G4 (negative) missing hardware is quiet — CHECK: `test_waybar_modules.py` with a fake sysfs that has no gpu or hwmon — EXPECT: `empty-output-ok`, exit 0, nothing on stderr
- G5 the config is valid and the bar renders — CHECK: nested waybar + `grim` — EXPECT: `waybar-active` and no `[error]` in the journal
- G6 (negative) rollback brings the tray icon back — CHECK: `rollback --last` then G1 — EXPECT: `nm-applet` present

## T13 No surprise lock
Checked (read-only): hypridle 0.1.8 honours three kinds of idle inhibit: `general:ignore_dbus_inhibit`, `general:ignore_systemd_inhibit` and `general:ignore_wayland_inhibit`. All three default to false, so all three inhibits work by default. It has `-c <path>` and supports `source=`. The owner's conf has no `source=` line, so an include needs an owner edit. Instead:
- Never lock: `seclegion-idle-inhibit.service` (user) runs `systemd-inhibit --what=idle --who=SecLegion --why=autolock-off --mode=block sleep infinity`. This is the same pattern as the lid inhibitor and needs no root for an active session. The owner's hypridle sees `BlockInhibited` contain `idle` and skips its 300 s lock.
- A longer delay (15/30/60 min): run the inhibitor plus `seclegion-idle.service`, which runs `hypridle -c ~/.local/share/seclegion/host/idle/hypridle.conf`. That config sets `ignore_systemd_inhibit = true` (so our inhibitor does not block our own instance), `ignore_dbus_inhibit = true` (the owner's instance holds the ScreenSaver name), `ignore_wayland_inhibit = false` (video still keeps the screen on), and one listener (`timeout = N`, `on-timeout = loginctl lock-session`). Known gap: a D-Bus-only inhibit from a browser is honoured only by the owner's instance, which is already inhibited. This is acceptable; record it in the report.
- `default`: both units stopped, so the owner's 300 s rule applies again.
- An exact match of the owner's own file is never needed. If the owner prefers it later, the one-line action is to append `source = ~/.local/share/seclegion/host/idle/override.conf` to `~/.config/hypr/hypridle.conf`.

Interfaces: `desktop/idle/seclegion-autolock {status|set default|15m|30m|60m|never}` (state in `~/.config/seclegion/autolock`). It writes the conf from a template, then starts or stops the units. Host component `idle`, with paths `host/idle`, both units under `.config/systemd/user/`, and `.local/bin/seclegion-autolock`. Settings row `power.autolock` (choices `default,15m,30m,60m,never`) in `registry.py`; its reader and writer call the CLI. No pkexec.

Jobs:
1. `seclegion-autolock`, the two units and the conf template.
2. The `idle` component in `seclegion-host` (rollback stops both units and removes them) and the fake-host test.
3. The `power.autolock` Settings row with reader, writer and `test_backend.py` cases.

Gates:
- G1 never means inhibited — CHECK: `seclegion-autolock set never; systemd-inhibit --list --what=idle` — EXPECT: `SecLegion`
- G2 the lock delay is honoured — CHECK: nested Hyprland, a test conf with a 5 s timeout writing a marker, inhibitor on, wait 12 s — EXPECT: `marker-absent`. Then the inhibitor off and our instance at 8 s — EXPECT: `marker-present`
- G3 the owner file is untouched — CHECK: `sha256sum ~/.config/hypr/hypridle.conf` before and after apply, set and rollback — EXPECT: `hypridle-unchanged`
- G4 (negative) a bad value is refused — CHECK: `seclegion-autolock set 5s` — EXPECT: exit 2, `not one of`
- G5 (negative) rollback restores default — CHECK: `rollback --last; systemctl --user is-active seclegion-idle-inhibit` — EXPECT: `inactive`, and `seclegion-autolock status` prints `default`

Order: T10-1 first (T12-1 depends on its PATH line), then T13 and T10-2/3 in parallel, then T12.
