<!-- SPDX-License-Identifier: MIT -->
# Plan R12 (Sec): resize, the last 8 Settings pages, J5 login and Qt, Omarchy-parity polish (2026-10-16)

Sonnet builders, max 2 at once; the main session reviews and re-runs gates. Rules: no sudo, no `/etc` or `/usr` writes, no live
`hyprctl dispatch/keyword/reload/eval` (tests use `nested_hyprctl` from `tests/ws/nested.sh`), never edit owner files (`~/.config/hypr/modules/*`).

## Facts the jobs rely on (Hyprland 0.56 Lua, from STATUS and the committed files)
- Known: `hl.bind`, `hl.dsp.focus`, `hl.dsp.window.move`, `hl.dsp.exec_cmd`, `hl.config`, `hl.workspace_rule`, `hl.env`; dispatch takes
  Lua strings; each reload is a new Lua state; `binds -j` shows `code:N` binds as key `""`.
- **Unverified** (K1 checks first, nested only, notes findings in `tests/keys/resize-submap.sh`): submap API name, `hl.dsp.window.resize`
  args, monitor size getter, `resize_on_border`/`extend_border_grab_area` names.
- Pages with no `registry_page` in `ui/pages.py`: bluetooth, input, region, updates, storage, security, users, troubleshoot.

## A. K1: resize mode (plan r8 C3, T4). Host component `keys`, plus `border` for the edge grab
Files: `desktop/hypr/seclegion-keys.lua`, `desktop/hypr/seclegion-host.lua`, `desktop/hypr/seclegion-winsize` (only if the Lua
monitor API is missing), `tools/seclegion-keys-lint`, `tests/keys/*`, and the waybar `hyprland/submap` chip (`desktop/waybar/config.jsonc{,.in}`, `style.css{,.in}`).
1. Edge grab: `general` `resize_on_border=true, extend_border_grab_area=20, hover_icon_on_border=true` in `seclegion-host.lua`.
2. Super+Alt+R `resize` submap: arrows/HJKL 40 px (Shift 10, Ctrl 200), `equal`/`minus` both axes, `C` centre, `F` float, Return/Escape
   reset; lint scopes submap binds (no exit 2); waybar `hyprland/submap` chip.
3. Super+Ctrl+1/2/3 (`code:10..12`): float if tiled, 50/70/90 % of the monitor, centred.
- G1 edge grab is set — CHECK: `bash tests/keys/border-opt.sh` (nested) — EXPECT: `border-ok`
- G2 submap enter, step and exit — CHECK: `bash tests/keys/resize-submap.sh` — EXPECT: `submap-ok`
- G3 the 70 % preset is centred — CHECK: `bash tests/keys/winsize.sh 70` — EXPECT: `size-ok center-ok`
- G4 no collision with the owner's keys — CHECK: `tools/seclegion-keys-lint ~/.config/hypr/modules/keybinds.lua desktop/hypr/seclegion-keys.lua` — EXPECT: `collisions=0`
- G5 negative: Super+R (rofi) is left alone, and a submap bind that collides inside its own scope is caught — CHECK: `grep -c '"SUPER + R"' desktop/hypr/seclegion-keys.lua; python3 -m pytest -q tests/keys/test_lint.py` — EXPECT: `0` and `passed` (with a new red case `test_submap_dup`)
- G6 negative: no live hyprctl in the tests — CHECK: `grep -hn 'hyprctl' tests/keys/border-opt.sh tests/keys/resize-submap.sh tests/keys/winsize.sh | grep -vc nested_hyprctl` — EXPECT: `0`

## B. Settings: the 8 empty pages. Host component `settings`
Files: `desktop/settings/seclegion_settings/backend/{registry,readers,writers,capabilities}.py`, `ui/pages.py`, `desktop/settings/tests/`;
shared, so **S1→S2→S3 run in sequence**. User rows write only `~/`; root rows are `privileged=True` saying "Needs root: preview only"
(as `power.lid_*`). Tests use `stubs.py`/`stub_tool.py` and a temp HOME, never the real tools.

**S1: bluetooth, storage, updates**
1. Bluetooth: power toggle (`bluetoothctl`), paired list (info), "Advanced" → `blueman-manager`; hidden with a reason if no adapter.
2. Storage: per-mount usage (info), trash size + "Empty trash" (`gio trash --empty`, confirm), low-disk level 70-95 % (`~/.config/seclegion/storage.toml`).
3. Updates: pending count (`checkupdates`), last update (pacman.log), "Update now" (terminal); snapshot keep-N privileged.

**S2: input, region, troubleshoot** (after K1, because it touches `seclegion-host.lua`)
1. Input: repeat rate/delay, touchpad tap, natural scroll, dwt → `~/.config/seclegion/input.lua`, `pcall(dofile)` from `seclegion-host.lua`;
   applies at next reload (the app never reloads).
2. Region: 12/24 h clock (`clock.toml`), locale (info), timezone (privileged).
3. Troubleshoot: `systemctl --user restart` waybar/swaync/hypridle; "Copy diagnostics" redacted.

**S3: security, users**
1. Security: ports (`ss -tln`), sshd enabled (info); firewall/SSH toggles privileged.
2. Users: name, `~/.face` (info), "Change password" = `passwd` in a terminal (app never sees it), autologin read-only.

Gates (each job runs the ones that apply to its pages; S3 runs all of them):
- G1 backend tests pass — CHECK: `python3 -m pytest -q desktop/settings/tests` — EXPECT: `passed` (and no `failed`)
- G2 every page has rows — CHECK: `PYTHONPATH=desktop/settings python3 -c "from seclegion_settings.ui import pages as p; print(sum(1 for x in p.PAGES if not p.settings_for(x)))"` — EXPECT: `0` (S1 `5`, S2 `2`)
- G3 negative: a user row never writes outside `~` — CHECK: `PYTHONPATH=desktop/settings python3 -c "from seclegion_settings.backend import registry as r; print(sum(1 for s in r.SETTINGS if not s.privileged and s.file.startswith('/')))"` — EXPECT: `0`
- G4 negative: every root row says so — CHECK: the same one-liner counting `s.privileged and 'Needs root' not in s.description` — EXPECT: `0`
- G5 the CLI explains a new row — CHECK: `tools/seclegion-set explain storage.low_disk` (S2: `input.repeat_rate`, S3: `security.ports`) — EXPECT: `~/.config/seclegion/`
- G6 UI smoke — CHECK: `python3 -m pytest -q desktop/settings/tests/test_ui_smoke.py` — EXPECT: `passed`

## C. L1: J5 login and Qt (plan r11 J5). Host component `gtk`; regreet goes to the ISO only
Files: `desktop/theme/*` (the `regreet.css` output and its README contract row), `tests/iso/*`, `docs/theme-coverage.md`,
and the `gtk` preflight in `tools/seclegion-host` (it only prints).
1. An engine output `regreet.css` built from tokens. The ISO build copies it to `/etc/greetd/regreet.css` inside the image.
2. `gtk` checks that the qt6ct `SecLegion.conf` link resolves and prints the owner's opt-in line (kvantum stays).
3. `docs/theme-coverage.md`: the audit table and the include lines for kitty, rofi and starship.
- G1 tokens only — CHECK: `python3 -m pytest -q tests/theme -k regreet_tokens` — EXPECT: `passed`
- G2 the ISO copies it — CHECK: `python3 -m pytest -q tests/iso -k regreet -p no:cacheprovider` — EXPECT: `passed`
- G3 negative: nothing under host `/etc` — CHECK: `git diff --stat clean-room-rebuild -- tools/seclegion-host | grep -c '/etc'` — EXPECT: `0`
- G4 negative: a broken qt6ct link is reported — CHECK: `make host-test` (new case `gtk-qt6ct-dangling`) — EXPECT: `PASS`
- G5 the audit is complete — CHECK: `grep -c '^| ' docs/theme-coverage.md` — EXPECT: `>= 14`

## D. Omarchy-parity polish: the top 5 not yet done (plan r8 D)
Done already: disk chip, lock caps colour, OSD. Picked: #16 Bluetooth chip, #17 power-profile chip, #18 DND bell (+#12/#15 deep links),
#24 float/centre helper windows, #32 `seclegion-doctor`.

**P1: waybar chips** (component `waybar`, after K1 because of the same waybar files)
1. A `bluetooth` chip, hidden when the adapter is off or missing.
2. A power-profile chip (hidden when there is no ppd), plus a `custom/notification` bell that shows the swaync DND state.
3. Right-click on battery, network and pulseaudio opens `seclegion-settings --page power|network|sound`.
- G1 modules parse and are wired — CHECK: `python3 -m pytest -q tests/desktop/test_waybar_modules.py` — EXPECT: `passed`
- G2 the chip colours come from tokens — CHECK: `python3 -m pytest -q tests/desktop -k css_tokens` — EXPECT: `passed`
- G3 negative: no chip calls a live dispatch — CHECK: `grep -c 'keyword\|reload' desktop/waybar/config.jsonc` — EXPECT: `0`
- G4 deep links resolve — CHECK: `PYTHONPATH=desktop/settings python3 -c "from seclegion_settings.ui import pages as p; print(all(p.resolve(i) for i in ('power','network','sound')))"` — EXPECT: `True`

**P2: window rules and doctor** (components `border` and `settings`; after K1 and S2, which also touch `seclegion-host.lua`)
1. Float + centre pavucontrol, blueman-manager, nm-connection-editor, Settings 980x680.
2. `tools/seclegion-doctor --json` (read-only): config errors, duplicate swaync, missing bind binaries, failed user units; tests read saved JSON.
- G1 rules load in the nested compositor — CHECK: `bash tests/keys/winrules.sh` — EXPECT: `rules-ok`
- G2 doctor unit tests — CHECK: `python3 -m pytest -q tests/unit -k doctor` — EXPECT: `passed`
- G3 negative: a duplicate swaync fixture is flagged — CHECK: `tools/seclegion-doctor --json --fixture tests/unit/fixtures/doctor-dup.json | grep -c '"level":"error"'` — EXPECT: `1`
- G4 negative: doctor writes nothing — CHECK: `python3 -m pytest -q tests/unit -k doctor_readonly` — EXPECT: `passed`

## Order and parallelism (max 2 at once)
| Wave | Jobs | Why they do not clash |
|---|---|---|
| 1 | K1 ∥ S1 | K1 touches hypr, lint and waybar files; S1 touches only `desktop/settings` |
| 2 | S2 ∥ L1 | S2 touches settings and `seclegion-host.lua`; L1 touches theme, iso, docs and `tools/seclegion-host` |
| 3 | P1 ∥ S3 | P1 touches waybar files; S3 touches settings |
| 4 | P2 | `seclegion-host.lua` (shared with S2) and `tools/` |

Live apply (main session, after review): `border` then `keys`, then `waybar`, `settings`, `gtk`, each confirmed under the dead-man switch.
