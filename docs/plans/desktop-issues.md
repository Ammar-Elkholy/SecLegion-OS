<!-- SPDX-License-Identifier: MIT -->
# Desktop issues plan (DAILY-DRIVER gaps 13-18)

Final plan after 3 plan/attack rounds (2026-10-30). Lanes A, B-C2 and D are merged; the rest are queued in `docs/STATUS.md`.

Changes from attack (each point checked against the code)

- **1, accepted.** The Lua build takes Lua expressions through dispatch: `render.py:28` uses `hyprctl dispatch 'hl.dsp.dpms({action="off"})'`. Nothing in `desktop/` or `tools/` uses `keyword` or `moveworkspacetomonitor`, and `hooks.py:16` marks runtime hyprctl as UNVERIFIED. Changes:
  - displayd drops the `keyword monitor` fallback completely. The owner's `modules/monitor.lua` is a catch-all (`output=""`, preferred, auto, 1.2), so eDP-1 is never disabled by config. Only L4's "External only" can disable it, so L4 owns the restore.
  - The command that moves a workspace is no longer assumed. The L1a-i spike finds the working form on the nested instance and prints it. The daemon takes it from one constant that the spike fills in.
- **2, accepted in part.** `WAYLAND_DISPLAY=wayland-1` is set in agent shells, so `nested.sh:21` passes. Still unproven: whether a second output can be created and removed in the nested instance. The spike now tests exactly that: `hyprctl output create headless`, falling back to `wayland`, then `output remove`. If it fails, item 15 ships on unit tests alone, a VM gate for the next ISO is written in the same lane, and L1a-i is reported "logic done, behaviour unproven", not "done".
- **3, accepted in part.** I read the owner's files, read-only. There are no workspace-to-monitor rules: `windowrules.lua` and `animations.lua` hold only commented examples, and `keybinds.lua:127-131` holds plain focus and move binds. So the attack's suspected cause does not exist. Accepted: reproduce before building. The nested repro is now gate G1 of L1a-i and runs before any daemon code. It also prints each workspace's `monitor` field, so we can tell a Hyprland problem from a waybar one. `seclegion-wsevents` ignores `monitorremoved`, so stale pills alone could be the symptom.
- **4, accepted.** `pytest.ini` testpaths leave out theme, ws, settings, host, keys, idle, osd and `desktop/settings/tests`. `tests/keys` holds only `test_lint.py`. The keymatrix, cheatsheet and d1 tests are in `tests/desktop`.
  - L4 G2 now points at `tests/desktop`.
  - `tests/display` is the only new directory, and L1a-i adds it to testpaths.
  - Gates outside testpaths name their path explicitly.
  - Every gate now lists exact test function names, and EXPECT requires each one to show PASSED in `-v` output. A lower bound alone no longer counts.
- **5, accepted.** The `PKEXEC_UID`/`SL_ETC` hardening is dropped: pkexec scrubs the environment, so that check could never fail. Its gate is replaced by `policy_exec_path`, which asserts that the policy's exec.path annotation equals `/usr/bin/seclegion-root-apply` and that the PKGBUILD installs the file there. `seclegion-polkit-agent.service` exists. The next-ISO VM gate checks that it is active before the pkexec write.
- **6, accepted, and confirmed worse than stated.** The owner's `keybinds.lua:56` binds `SUPER + P` to pseudo, and `seclegion-keys.lua:89` binds `SUPER + CONTROL + P` to power-profile. SUPER+P is dropped. The binds are now `XF86Display`, `XF86Project` (locked), and `SUPER + SHIFT + P`, which is free in both trees. If `wev` shows Fn+F7 sends SUPER+P, rebinding pseudo is the owner's decision. The new binds are added to the owner-collision check in `test_d1_keybind_lint_target.py`.
- **7, accepted.** Rule: L1b lands before L4, and L4 rebases on the merged L1b before it starts.
- **8, accepted.** Waybar has no hardcoded `interface`, so it follows the default route; `network_interface` asserts that stays true. A STATUS item asks the owner to compare the reading against a known transfer.
- **9, accepted.** Added test `card_order_independent`, which swaps card0 and card1 in the fixture.
- **10, accepted.** L1a is split into L1a-i (spike, repro, daemon, nested test) and L1a-ii (unit, package, host component). This session runs L5a, L2 and L1a-i in parallel. That is 3 small lanes under the owner's near-reset rule. The owner should know that item 18 waits until after the reset (Owner items).
- **11, accepted.**
  - L1b paints every current output when displayd starts, which covers the first login even if the owner's autostart runs early.
  - The menu gets a `flock` single-instance guard.
  - `no_commands_shown` is a grep of all row and toast text against command patterns.

## Issues

**15 (P0) Workspaces stay on an unplugged output**
- **Cause (to be confirmed by repro):**
  - `seclegion-host.lua:51-56` makes workspaces 1-5 persistent, with no monitor handler.
  - `seclegion-wsevents` ignores `monitorremoved`.
  - The owner's files have no workspace-to-monitor rules.
- **Design:** `desktop/display/seclegion-displayd`, a stateless Python daemon on socket2.
  - On `monitorremoved` or `monitorremovedv2` it reads `monitors -j` and `workspaces -j`.
  - Every workspace whose monitor is gone moves to the focused enabled monitor, or else the first enabled one. The move uses the dispatch form the spike proved.
  - If no output is enabled, it logs and does nothing.
  - Hooks for tests: `SL_HYPRCTL`, `SL_SOCKET2`. hyprctl gets the signature from the daemon's own environment.

**16 Stock wallpaper on the new output**
- **Cause:**
  - The owner's `autostart.lua:25,31` runs `awww-daemon` and `restore-wallpaper.sh` once at login, so nothing repaints a new output.
  - On an installed system nothing starts awww.
  - The branding package ships no background.
- **Design:**
  - The displayd hook runs on `monitoradded` and once at start: `awww img --outputs <out> <img> --transition-type none`, up to 10 tries 0.3 s apart.
  - Image order:
    1. `~/.cache/current_wallpaper`, unless `current_wallpaper_type` is `video`
    2. the theme's `current/wallpaper`
    3. `/usr/share/backgrounds/seclegion/default.png`, committed (no Pillow)
  - `seclegion-theme apply` calls the same helper.
  - `seclegion-wallpaper.service` is package-only, with `ExecCondition=!awww query`, so it never starts a second daemon on the live host.
  - The skel config sets `force_default_wallpaper=0`.

**14 Display menu**
- **Cause:** nothing is bound to the Display key anywhere.
- **Design:**
  - `seclegion-display-menu` in rofi, behind a `flock` guard.
  - Modes: Laptop only, Extend, Mirror, External only.
  - A pure renderer turns the chosen mode into hyprctl argv. The monitor-apply form comes from the L4 spike, with no file written.
  - External only arms a revert: if no external output is enabled, eDP-1 comes back.
  - Binds: XF86Display, XF86Project, SUPER+SHIFT+P. Plus a waybar button.

**17 Wi-Fi**
- **Now:** `config.jsonc.in:117-118` changes to `{bandwidthUpBits}`/`{bandwidthDownBits}` in the wifi and ethernet formats. No `interface` key. Regenerate the config.
- **Later:** L6.

**13 GPU**
- **Now:** `seclegion-gpu` loops over `card*/device/vendor`.
  - AMD `0x1002` reads `gpu_busy_percent`.
  - NVIDIA `0x10de`:
    - `runtime_status=suspended`: shows "dGPU off" and starts no child process.
    - `active` with `nvidia-smi` present: one query, about 50 ms every 5 s, only while the dGPU is already awake.
    - `nvidia-smi` missing: the NVIDIA entry is hidden.
  - The tooltip lists every GPU.
- **Later:** L5b, the sysmon app.

**18 Settings full control**
- **Privileged writes:** `registry.write` runs `pkexec /usr/bin/seclegion-root-apply <id> <value>` off the UI thread. `rootapply.py` is reused unchanged.
- **pkexec errors:** exit 126 and 127 leave the value unchanged and show separate toasts.
- **Policy:** `org.seclegion.settings.root-apply`, `auth_admin_keep`, with an exec.path annotation.
- **UI:** shows no command text anywhere.

## Lanes

Rules for every lane:
- Sonnet 5.5, one worktree per lane, branch off `clean-room-rebuild`.
- `PY=/mnt/Dev_Lab/SecLegion-OS/.claude/worktrees/agent-a0385fdb52b3ba760/.venv/bin/python`
- Before each commit: `$PY -m pytest -q -rf` exits 0, and `PATH=<venv>/bin:$PATH make lint` exits 0 (lines ≤ 110). Package lanes also run `make lint-pkgs`.
- pytest exit 5 counts as FAIL. A gate passes only when every test it names shows PASSED in `-v` output.
- Never send hyprctl to the live signature. Nested scripts unset `HYPRLAND_INSTANCE_SIGNATURE` and pin the nested one.
- No sudo, no pacman, no `/etc`, no owner files (reading the owner's hypr tree is allowed). Stop processes by pid only.
- Report: commits, one line per gate, decisions to review, what remains.

---

**L5a: GPU probe (item 13). Runs now.**
- **Goal:** the waybar GPU module shows every GPU on the Legion Slim 5 (AMD 780M, plus RTX 4060 when awake) without waking the dGPU.
- **Files:** `desktop/waybar/seclegion-gpu`, `tests/desktop/test_waybar_modules.py`, fixtures under `tests/desktop/fixtures/drm/`.
- **Constraints:**
  - The existing 4 `SL_GPU_FILE` tests (`:148-167`) migrate to a new `SL_DRM_ROOT` fixture hook. Do not delete them.
  - Run no child process when the dGPU is suspended or `nvidia-smi` is absent.
  - Output stays waybar JSON with classes `ok`, `warn` and `hidden`.
- **Deliverables:**
  1. The vendor loop.
  2. The tooltip listing every GPU.
  3. Tests: the 4 migrated ones plus `test_gpu_amd_only`, `test_gpu_nvidia_suspended_no_smi_call` (the stub `nvidia-smi` writes a marker file, and the test asserts it is absent), `test_gpu_nvidia_active`, `test_gpu_nvidia_no_smi`, `test_gpu_card_order_independent`.
- **Gate G1:** CHECK `$PY -m pytest -q -v tests/desktop -k gpu`. EXPECT exit 0, with all 9 named tests PASSED.

---

**L2: Wi-Fi speed units (item 17, speed half). Runs now.**
- **Goal:** the bar's speed readout uses bits per second, comparable to Mbit/s link and speed-test figures.
- **Files:** `desktop/waybar/config.jsonc.in` (network block only), the generated `desktop/waybar/config.jsonc`, `tests/desktop/test_waybar_modules.py`.
- **Constraints:**
  - Leave `interval` at 5. Add no `interface` key.
  - Regenerate the config only with `tools/gen-waybar-ws`.
- **Deliverables:**
  1. Bits placeholders in `format-wifi` and `format-ethernet`.
  2. `test_network_bits` parses the rendered JSON and asserts Bits, with no Bytes, in both formats.
  3. `test_network_interface` asserts there is no hardcoded interface.
  4. A line in the report for the STATUS owner check: compare against a known transfer.
- **Gates:**
  - G1: CHECK `$PY -m pytest -q -v tests/desktop -k "network_bits or network_interface"`. EXPECT exit 0, both PASSED.
  - G2: CHECK `tools/gen-waybar-ws && git diff --exit-code desktop/waybar/config.jsonc`. EXPECT exit 0.

---

**L1a-i: hotplug repro and displayd logic (item 15). Runs now.**
- **Goal:** prove the bug in nested Hyprland, then fix it with a stateless daemon that moves workspaces off a removed output.
- **Files:** `tests/display/{spike-output.sh,hotplug.sh,test_displayd.py}`, `desktop/display/seclegion-displayd`, `pytest.ini` (add `tests/display` to testpaths).
- **Constraints:**
  - Reuse `tests/ws/nested.sh`.
  - hyprctl calls go only to the nested signature. The daemon reads the signature from its own environment.
  - The daemon has no `keyword` path and does nothing when no output is enabled.
  - Find the move dispatch form in the spike; do not assume the classic `moveworkspacetomonitor` works. The Lua build takes `hyprctl dispatch '<hl.dsp... expr>'`, as in `render.py:28`. Keep it in one constant.
- **Deliverables, in order:**
  1. The spike: a second output is created (headless, else wayland), workspace 7 is moved to it with the found form, then the output is removed. It prints `SPIKE ok <create-form> <move-form>` or `SPIKE no-output`.
  2. `hotplug.sh`: create the output, put workspace 7 on it, remove it, then print each workspace's `monitor` from `workspaces -j` and the verdict.
  3. The daemon.
  4. Unit tests with a fake socket2 and a recording hyprctl:
     - `test_removed_moves_to_focused`
     - `test_removed_none_focused_uses_first`
     - `test_all_off_does_nothing`
     - `test_ignores_present_monitor`
     - `test_v2_event_parsed`
- **Gates:**
  - G0: CHECK `bash tests/display/spike-output.sh`. EXPECT `SPIKE ok` or `SPIKE no-output`.
    - On `no-output`: skip G1 and G3, and write the VM gate `tests/install` `-k displayd_hotplug` (marked `iso`, collected with no errors). Report "logic only".
  - G1, repro (before the daemon exists): CHECK `SL_NO_DAEMON=1 bash tests/display/hotplug.sh`. EXPECT `FAIL ws7-on-removed`.
    - On PASS: stop. Report that Hyprland already migrates workspaces, and include the monitor fields. The cause is then on the waybar side (wsevents), and the next lane is re-planned.
  - G2: CHECK `$PY -m pytest -q -v tests/display -k displayd`. EXPECT exit 0, all 5 named tests PASSED.
  - G3: CHECK `bash tests/display/hotplug.sh`. EXPECT `PASS ws7-on-remaining`, exit 0.

---

**L1a-ii: displayd delivery (item 15). Runs after L1a-i merges, this session if budget allows.**
- **Goal:** ship the daemon on installs and on the live host.
- **Files:**
  - `desktop/units/seclegion-displayd.service` (reaches the package through the `PKGBUILD:52-58` glob)
  - `pkgs/seclegion-desktop/{PKGBUILD,source.list}`: add `display` to the `_tree` loop and the chmod
  - `tools/seclegion-host`: a new `display` component, built like `idle` and staged through `.sl-units`
  - `tests/expected-units/{install,live}.txt`, `tests/pkgs`, `tests/tools`
- **Constraints:**
  - The unit is a graphical-session user unit.
  - Do not add `display` to the list of components applied by default without the 120 s dead-man path. Follow how `idle` does it.
  - No sibling package depends.
- **Deliverables:** the unit file, the package wiring, the host component, `test_pkg_ships_displayd`, `test_host_stages_displayd`.
- **Gate G1:** CHECK `$PY -m pytest -q -v tests/pkgs tests/tools -k displayd`. EXPECT exit 0, both PASSED. Also `make lint-pkgs` exits 0.

---

**L1b: wallpaper on every output (item 16). Deferred; runs before L4.**
- **Goal:** the SecLegion or owner wallpaper shows on every output, at login and on hotplug.
- **Files:** the displayd awww hook, `desktop/units/seclegion-wallpaper.service`, `desktop/theme/seclegion_theme/`, `pkgs/seclegion-branding/*` (committed `default.png`), the skel `hyprland.lua` (`force_default_wallpaper=0`), `tests/expected-units`, `tests/display`, `tests/theme`.
- **Constraints:**
  - Start no second awww daemon on the live host: `ExecCondition=!awww query`, and the unit is package-only.
  - No Pillow.
  - If awww is absent, exit quietly.
- **Deliverables:**
  1. Paint every output when the daemon starts, and on `monitoradded`.
  2. The image order from issue 16.
  3. Up to 10 retries.
  4. Theme apply calls the helper.
- **Gates:**
  - G1: CHECK `$PY -m pytest -q -v tests/display -k wallpaper`. EXPECT PASSED for `test_wallpaper_order`, `test_wallpaper_per_output_argv`, `test_wallpaper_retries`, `test_wallpaper_video_skipped`, `test_wallpaper_awww_absent`, `test_wallpaper_on_start_all_outputs`.
  - G2: CHECK `$PY -m pytest -q -v tests/theme -k awww_on_apply`. EXPECT 1 PASSED. `tests/theme` is outside testpaths, so the path is named here.

---

**L3a: privileged settings backend (item 18). After the reset.**
- **Goal:** privileged settings write through pkexec instead of being refused.
- **Files:** `desktop/settings/seclegion_settings/backend/registry.py` (`:1181-1182`), new `org.seclegion.settings.policy`, `pkgs/seclegion-settings/{PKGBUILD,source.list}` (`polkit` in depends, policy in `package()`), `desktop/settings/tests/{test_backend,test_rootapply}.py`.
- **Constraints:**
  - `rootapply.py` stays unchanged. Its CLI is `[--dry-run] <id> <value>`, checked against ALLOWED and re-coerced.
  - `SL_PKEXEC` overrides the pkexec path in tests only.
  - Exit 126 and 127 map to separate error types, and the stored value is left untouched.
- **Gate G1:** CHECK `$PY -m pytest -q -v desktop/settings/tests -k "pkexec_argv or pkexec_126 or pkexec_127 or policy_exec_path or hostile_id"`. EXPECT exit 0, all 5 PASSED. Also `make lint-pkgs` exits 0.

---

**L3b: settings UI with no commands (item 18). After L3a.**
- **Goal:** the Settings app gives full control and never shows a command for the user to run.
- **Files:** `ui/rows.py` (`:70,209-211,463,527-532`), the `ui/offthread.py` callers, `test_pages_s{1,2,3}.py`, `test_ui_smoke.py`.
- **Constraints:**
  - Privileged writes run off the UI thread.
  - theme-auto calls `seclegion-theme auto` directly.
  - `test_no_commands_shown` greps all row and toast text for command patterns: `sudo`, `pkexec`, `seclegion-`, `systemctl`, backticks, `$ `.
- **Gates:**
  - G1: CHECK `$PY -m pytest -q -v desktop/settings/tests -k "no_commands_shown or write_offthread"`. EXPECT both PASSED.
  - G2: CHECK `$PY -m pytest -q desktop/settings/tests`. EXPECT exit 0.

---

**L4: display menu (item 14). After L1b and L2, rebased on both.**
- **Goal:** one reliable menu for Laptop only, Extend, Mirror and External only.
- **Files:** `desktop/display/seclegion-display-menu`, `desktop/hypr/seclegion-keys.lua`, keymatrix and cheatsheet data, `config.jsonc.in` (button), `tests/display`, `tests/desktop`.
- **Constraints:**
  - Binds: XF86Display, XF86Project (locked), SUPER+SHIFT+P. Never SUPER+P (owner pseudo) or SUPER+CONTROL+P (power profile).
  - `flock` single-instance guard.
  - Apply at runtime with no file written, using the form found by a G0 spike on the nested instance.
  - External only keeps a way back to eDP-1.
- **Gates:**
  - G0: CHECK `bash tests/display/spike-monitor-apply.sh`. EXPECT `SPIKE ok <form>`. On failure: stop and report.
  - G1: CHECK `$PY -m pytest -q -v tests/display -k render_mode`. EXPECT PASSED for `laptop`, `extend`, `mirror`, `external`, `external_restore`.
  - G2: CHECK `$PY -m pytest -q -v tests/desktop -k "keymatrix or cheatsheet or keybind_lint"`. EXPECT exit 0, and the new binds pass the owner-collision check.
  - G3, if the L1a-i spike was ok: CHECK `bash tests/display/modes.sh`. EXPECT `PASS modes`.

**Later lanes**
- L5b: GTK4 sysmon app.
- L6: `seclegion-wifi` module, libnm panel, and `libnm` in depends. After L3b and L2.
- L7: Settings Displays page using the L4 renderer.

**Shared files (serial order)**
- `config.jsonc.in`: L2, L4, L5b, L6.
- `desktop/display/`, `pkgs/seclegion-desktop`, `tools/seclegion-host`: L1a-i, L1a-ii, L1b, L4.
- Settings files: L3a, L3b, L6, L7.
- L5a, L2 and L1a-i share no files. L1a-i only creates new files plus `pytest.ini`.

## Order

- **Now, 3 lanes in parallel:** L5a, L2, L1a-i. Merge L5a and L2 first, since they are small and certain.
- **Then, if budget remains:** L1a-ii, then L1b.
- **At each merge:** checkpoint `docs/STATUS.md` and `docs/progress.toml`. Record:
  - the deferred hyprlock and swayosd second-output checks
  - the owner check of Wi-Fi speed against a known transfer
  - that item 18 waits until after the reset
- **After the reset:** L3a, L3b, then L4, then L5b and L6, then L7.
- **Next ISO (after L1a-ii, L1b, L3a, L4):** VM gates for:
  - `seclegion-displayd` and `seclegion-wallpaper` active
  - `seclegion-polkit-agent` active, and a pkexec write as the test user
  - `displayd_hotplug`, if the L1a-i spike printed `no-output`
- **Owner items:**
  - Run `wev` on Fn+F7. If it sends SUPER+P, decide whether to rebind pseudo in `keybinds.lua:56`.
  - Confirm Sonnet builders, since the task text says Opus.
  - Re-test item 15 on the Legion after L1a-ii merges and `seclegion-host apply display` runs.
  - Re-check Wi-Fi speed after L2.