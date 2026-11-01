<!-- SPDX-License-Identifier: MIT -->
# Plan r11: one theme on every surface, a theme manager, auto theme per wallpaper (T11 of plan-r9)

Owner: OSD colour off-theme; theme must reach every surface; manager plus auto theme per wallpaper.

## Surface audit (read-only, 2026-10-16)

| surface | follows tokens now? | evidence / gap |
|---|---|---|
| OSD popup (`seclegion-osd`) | **no** | It is a swaync low-urgency popup; `desktop/swaync/style.css` `.notification`, `.low/.normal/.critical`, progressbar hard-code `#0d1117/#00ffcc/#ff2266`. **This is the complaint.** |
| swaync popups | **no** | same literals; imports `colors.css`, so `sl_notif_*` (in `swaync-colors.css`) go unused |
| swaync control centre | yes | `@sl_*`; live via `swaync-client --reload-css` hook |
| waybar | yes | `style.css.in` uses `@sl_*`; SIGUSR2 hook |
| window border | partial | `seclegion-host.lua` parses `colors.css`, not the contract's `hyprland-colors.lua`; live update is `hook_hyprland` = `hyprctl keyword` (**out of bounds now**) |
| hyprlock | yes | sources `hyprlock-colors.conf`, read at lock time |
| GTK 3/4, KDE | yes, next app start | `gtk` component imports `current/gtk{3,4}.css` |
| Qt | **no** | owner qt6ct: `style=kvantum`, `color_scheme_path=…/colors.conf` (not SecLegion) |
| kitty, rofi, starship, fastfetch | **no** | engine writes the files; no owner config includes them |
| login (regreet) | **no** | regreet not installed on host; ISO only, no generated CSS yet |
| wallpaper | — | owner scripts write `~/.cache/current_wallpaper`, `_type` (`image|gif|video`), `wallpaper_frame.png`; no hook; matugen installed |

## Hard rules for every job

No sudo, no host `/etc`, never edit owner files (`~/.config/hypr/**` beyond host-tool-owned files,
`~/.config/hyprland-dotfiles/**`, kitty/rofi/qt6ct/starship). No live
`hyprctl dispatch|keyword` and no `hyprctl reload` run by a builder: tests use a stub `hyprctl` on PATH that
logs argv. Live border changes reach the session only via `seclegion-host apply border` (dead-man armed).
One branch per job, `make test` green before report.

## J1 Notifications and OSD on tokens (fixes the complaint)

Deliverables: (1) `desktop/swaync/style.css`: add import of `current/swaync-colors.css` (`sl_notif_*`/`sl_osd_*`);
every literal replaced by a token;
a `.notification.low` with an `int:value` hint (the OSD) styled from `sl_osd_*`. (2) If `sl_osd_*` lacks
bar/track tokens, add them in `render.py` and regenerate `desktop/theme/default/` with `export-default`.
(3) Test `desktop/theme/tests/test_swaync_tokens.py`.
Host component: `notifications` (unchanged install; reload already restarts swaync). Live reload afterwards:
existing `hook_swaync`.

- G1 no colour literals left — CHECK: `grep -cE '#[0-9a-fA-F]{3,8}\b' desktop/swaync/style.css` — EXPECT: `0`
- G2 import present — CHECK: `grep -c 'current/swaync-colors.css' desktop/swaync/style.css` — EXPECT: `1`
- G3 every `@sl_*` used is defined — CHECK: `python3 -m unittest desktop.theme.tests.test_swaync_tokens -v 2>&1 | tail -1` — EXPECT: `OK`
- G4 negative: a style.css using an undefined token fails the test — CHECK: run G3 against a fixture copy with `@sl_nope` — EXPECT: `FAILED`
- G5 default export in sync — CHECK: `make test 2>&1 | tail -3` — EXPECT: `OK`

## J2 Window border from the contract, no `keyword`

Deliverables: (1) `desktop/hypr/seclegion-host.lua`: `pcall(dofile, ~/.local/state/seclegion/theme/current/hyprland-colors.lua)`,
fallback `/usr/share/seclegion/theme/default/hyprland-colors.lua`, then the green literal; values used as
given (`rgba(...)`). (2) `hooks.py` `hook_hyprland`: replace the `keyword` batch with `hyprctl reload`, which
re-evaluates `seclegion-host.lua` (it un-caches itself); skipped unless `HYPRLAND_INSTANCE_SIGNATURE` set **and**
`$CFG/hypr/seclegion-host.lua` exists (border component applied). (3) Tests with stub hyprctl.

- G1 no keyword anywhere in hooks — CHECK: `grep -c keyword desktop/theme/seclegion_theme/hooks.py` — EXPECT: `0`
- G2 lua parses — CHECK: `luac -p desktop/hypr/seclegion-host.lua && echo ok` — EXPECT: `ok`
- G3 stub sees reload only — CHECK: `python3 -m unittest desktop.theme.tests.test_engine -k hyprland -v 2>&1 | tail -1` — EXPECT: `OK` (test asserts stub argv == `reload`)
- G4 negative: no border file → hook `skipped`, stub log empty — CHECK: same test, case `no_border` — EXPECT: `skipped`
- G5 host fake-host run — CHECK: `make host-test 2>&1 | tail -2` — EXPECT: `PASS`

## J3 Auto theme on wallpaper change (watcher, no owner edits)

Deliverables: (1) CLI `seclegion-theme auto on|off|status` (state file `$XDG_STATE_HOME/seclegion/theme/auto`)
and `seclegion-theme sync`: reads `~/.cache/current_wallpaper` + `_type`; `gif|video` → `wallpaper_frame.png`;
missing/unreadable/non-image → exit 0 `skipped`; auto off → `skipped`; same sha256 as `current` → `unchanged`;
else `apply --mode auto --wallpaper IMG`. (2) User units `desktop/theme/systemd/seclegion-theme-sync.path`
(`PathChanged=%h/.cache/current_wallpaper`, `PathChanged=%h/.cache/wallpaper_frame.png`, `TriggerLimitIntervalSec=10`)
and `.service` (oneshot, `ExecStartPre=sleep 1` debounce, `ExecStart=… sync`). (3) Host component `theme-auto`:
installs units into `~/.config/systemd/user/`, `enable --now` the path unit; rollback disables and removes.
matugen `--prefer saturation`; on failure the old theme stays.

- G1 off means no apply — CHECK: test `sync` with auto off — EXPECT: `skipped`
- G2 video wallpaper uses the frame — CHECK: unittest `test_sync.FrameFallback` — EXPECT: `OK`
- G3 idempotent — CHECK: run `sync` twice in the fixture HOME — EXPECT: second line `unchanged`
- G4 units valid — CHECK: `systemd-analyze --user verify desktop/theme/systemd/*.path desktop/theme/systemd/*.service; echo rc=$?` — EXPECT: `rc=0`
- G5 negative: rollback leaves no unit — CHECK: fake-host apply then rollback `theme-auto`; `ls $FAKE/.config/systemd/user | grep -c seclegion-theme-sync` — EXPECT: `0`
- G6 negative: owner files untouched — CHECK: `sha256sum` of `~/.config/hyprland-dotfiles/hypr/scripts/*wallpaper*.sh` before/after — EXPECT: identical

## J4 Theme manager (window + quick picker)

Deliverables: (1) CLI `seclegion-theme list --json`: built-ins (`seclegion-dark`, plus 2 inside the hue clamp 150..205,
e.g. `seclegion-teal`, `seclegion-cyan`, as seed accents) and one entry per recent wallpaper (`wallpaper:<sha8>`, from the
kept theme dirs) each with `{id,label,accent,bg,surface,text}`; `apply --theme ID`. (2) Settings Appearance page rows
in `registry.py`: `appearance.theme` (choice from `list`, swatch preview in `rows.py`), `appearance.auto` (toggle → `auto on|off`),
`appearance.reset` (action → `reset`). (3) `tools/seclegion-theme-pick`: rofi picker themed by `rofi-colors.rasi`, calls `apply --theme`.
Host component: `settings` (already ships `seclegion-theme`); picker added to `settings` bins.

- G1 list shape — CHECK: `tools/seclegion-theme list --json | python3 -c 'import json,sys;d=json.load(sys.stdin);print(all("accent" in t for t in d))'` — EXPECT: `True`
- G2 built-ins pass clamps — CHECK: `python3 -m unittest desktop.theme.tests.test_palette -v 2>&1 | tail -1` — EXPECT: `OK`
- G3 rows present — CHECK: `tools/seclegion-set --list appearance | grep -c 'appearance\.\(theme\|auto\|reset\)'` — EXPECT: `3`
- G4 negative: unknown id rejected, current unchanged — CHECK: `tools/seclegion-theme apply --theme nope; echo rc=$?` — EXPECT: `rc=2`
- G5 settings suite — CHECK: `python3 -m unittest discover -s desktop/settings/tests 2>&1 | tail -1` — EXPECT: `OK`

## J5 Login, Qt and the opt-in surfaces

Deliverables: (1) engine output `regreet.css` (contract row added in README) and ISO wiring copying it to
`/etc/greetd/regreet.css` **inside the ISO build only** (`tests/iso`). (2) `gtk` component: verify the qt6ct `SecLegion.conf` link; print the owner opt-in (kvantum stays). (3) `docs/theme-coverage.md`: the audit table plus the include lines the owner may add for kitty/rofi/starship.

- G1 regreet css on tokens — CHECK: unittest `test_regreet_tokens` (every colour is a `colors.json` value) — EXPECT: `OK`
- G2 ISO copies it — CHECK: `bash tests/iso/<new test>` — EXPECT: `PASS`
- G3 negative: nothing written under host `/etc` — CHECK: `git diff --stat main -- tools/seclegion-host | grep -c '/etc'` — EXPECT: `0`
- G4 doc lists every row of the audit — CHECK: `grep -c '^| ' docs/theme-coverage.md` — EXPECT: `>= 14`

## Order and live reload summary

Order: J1 ∥ J2, then J3 ∥ J4, then J5 (max 2 builders).
Live reload: waybar SIGUSR2; swaync `--reload-css`; border via J2 hook (first install: `seclegion-host apply border`);
kitty SIGUSR1 if included; hyprlock next lock; GTK/Qt next app start; regreet next boot. Main session owns the T11 nested-screenshot and golden-palette gates.

## Decisions for the owner

1. `hyprctl reload` on each auto theme change (J2).  2. Built-in theme set limited to the identity hue clamp.  3. kitty/rofi/starship/kvantum stay owner opt-in.
