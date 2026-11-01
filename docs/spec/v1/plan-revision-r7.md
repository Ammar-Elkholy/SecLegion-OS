# Plan revision R7 (Sec, Opus 5.5) — 2026-10-14

Amends `full-plan.md` for `owner-directives-r7.md`. Status: **binding**, except where §6 says an owner decision is pending.

## 1. Amendments to full-plan.md

**Three tracks replace "nothing starts until the previous gate is green":**
- **I (ISO):** M0→M12, strictly in order.
- **T (theme engine):** userland only. Gated by pytest and property tests.
- **H (live host):** dynamic surfaces only.

Tracks T and H may start before M0 is green. They reach the ISO only through M6+/M7+.

**Theming moves into 1.0 (§2, §3).** `seclegion-theme` has two modes:
- `default`: static tokens, no matugen. This is the shipped default.
- `auto`: matugen from the wallpaper.

Both modes go through the same tokens, the identity, contrast and protected-colour clamps, the templates and the reload hooks.

| Release | Surfaces and features |
|---|---|
| 1.0, never cut | Hyprland, waybar, rofi, kitty, swaync, swayosd, hyprlock, starship, fastfetch |
| 1.0, may slip to 1.0.x | GTK3/4 (adw-gtk3 CSS overlay) and Qt (qt6ct). This is cut-order position 2.5. |
| 1.3 | Light theme, high contrast, theme picker and install, video wallpapers, community themes |

**Roadmap gates.** T1–T3 become gates **M7t** (engine) and **M7s** (surfaces). The golden screenshots use `default` mode plus 3 fixed test wallpapers.

**New spikes:**
- **S-theme** must pass before T1 is gated. It checks the matugen 4.2 JSON flags, Hyprland 0.56 Lua colour syntax and reload-on-error, waybar `@import` plus SIGUSR2, kitty SIGUSR1, `swaync -rs`, swayosd style reload, and starship (generate the whole `starship.toml` and set `STARSHIP_CONFIG`).
- **S-host** records the idle PSS/CPU baseline on the host before any change.

**New O13 audience rule.** Every default is safe and explained for beginners. No SecLegion tool wraps, hides or replaces pacman, `~/.config`, the terminal or the Hyprland config. User overrides always win.

**A13 (build).** The build runs as `docker run --privileged` from a pinned `archlinux` image digest, and only through `tools/docker-build.sh`:
- The repo is mounted read-only.
- The workdir is a Docker volume or `/var/tmp/seclegion-build`. A guard refuses NTFS paths.
- Output files are chowned back to the user.

QEMU runs as the user, with a per-run copy of the OVMF vars, user-mode networking and swtpm as the user.

**M2–M7.** Every host deliverable states its ISO path. The host result is the owner's preview. **ISO VM acceptance is the gate.**

## 2. Top risks and fixes
1. **The docker group is root-equivalent.**
   - Containers start only through the wrapper and `make` targets.
   - The reviewer greps every diff for `docker run`, `-v /` and `--privileged`.
   - Mounting `$HOME`, `/` or `/etc` is forbidden.
2. **1.0 scope is too large.** Proposal: move M9a AI and M6g GNOME to 1.0.1, and keep greetd+regreet instead of GDM (*owner decision*).
3. **Mutation tests.** Required only on security and integrity gates: signing, SigLevel, key leak, egress, forged PASS, the contrast clamp, generated-code injection.
4. **Generated config is executable (Lua, rasi, CSS, toml).**
   - Accept only colour tokens matching `^[0-9a-f]{6}([0-9a-f]{2})?$` and fixed numbers.
   - Add an injection mutation test.
   - Load the generated file through `pcall`, falling back to the package defaults.
5. **A broken Hyprland reload could strand the owner.** Syntax-check before reloading, and add a 120 s dead-man rollback (`systemd-run --user`).
6. **Writing into the wrong place.**
   - `~/.config/gtk-4.0` points into `~/.themes`.
   - Configs pointing at the repo on NTFS break when it is unmounted.

   Fix: copy to `~/.local/share/seclegion/host/` on ext4 and flip only the `~/.config` symlink. GTK on the host is deferred.
7. **The theme pipeline has no concurrency rules.**
   - Take a `flock`, render into a hash directory, and swap atomically.
   - Hooks run in parallel with a 2 s timeout each.
   - The whole run takes ≤1.5 s and leaves nothing resident.
   - kitty reloads by SIGUSR1 only, never remote control.
8. **Beginners have no recovery story.** Add:
   - `seclegion-doctor` (read-only);
   - `seclegion-theme reset`, reachable from a TTY and the menu;
   - a welcome-screen page on what to do when the desktop breaks;
   - a plain-language cheat sheet.
9. **The host and ISO session models differ (no uwsm on the host).** "Works on host" is never a gate. The ISO VM must show exactly one Notifications owner and one service file.
10. **Licence contamination and secrets in evidence.**
    - Rewrite, don't copy.
    - CI runs `tools/licence-similarity`.
    - Evidence is redacted and gitignored.
    - Backups are mode 0700, cover only the allowed list, and are never committed.

## 3. Live-host-first protocol (binding for Tracks H and T)

**Source of truth.** Changes flow repo → `make host-install COMPONENT=x` → host. Nothing is edited on the host and copied back.

**Allowed, with a backup taken first:**
- `~/.config/{waybar,swaync,swayosd,rofi,kitty,starship.toml,fastfetch}`, by flipping the symlink only.
- Hyprland: one added line, `require("seclegion-host")`, plus the new file `~/.config/hypr/seclegion-host.lua`.
- Autostart: one edited line in `modules/autostart.lua` (dunst→swaync).
- `~/.local/{share,state}/seclegion/` and `~/.local/bin/seclegion-*`.
- User units, followed by `daemon-reload`.

**Forbidden:**
- `/etc`, `/usr`, `/boot`, `/var` (except the build dir); pacman; system units; the display manager; mkinitcpio.
- hypridle, monitor, input and keybind modules.
- `~/.ssh`, `~/.gnupg`, keyrings and browser profiles; `~/.zshrc` until the owner says OK.
- `~/.themes`, `~/.icons` and the wallpaper library.
- **Any git operation in `~/.config/hyprland-dotfiles`.**
- Stopping the compositor, pkill/killall patterns, locking the screen.

**Backups** go in `~/.local/state/seclegion/host-backups/<UTC>-<component>/` (mode 0700). Each holds:
- `manifest.json`: paths, symlink targets, sha256, daemon pids and command lines, hyprctl option values, the Notifications owner;
- `files.tar`;
- `dotfiles.patch`, for information only;
- `rollback.sh`.

A **baseline-0** backup is taken before the first change.

**Commands:**
- `seclegion-host apply <component>`: back up → validate → install → reload one component → arm the 120 s dead-man switch → verify.
- `seclegion-host confirm`: disarm the dead-man switch.
- `seclegion-host rollback [--last|<id>|baseline-0]`: works from a TTY. It is tested (apply → rollback → sha256 compare) before the first real change.

**Verification on the host:**
- `hyprctl configerrors` is empty.
- There is exactly one Notifications owner.
- The `seclegion-notify-test` matrix passes.
- A grim screenshot pixel-sample matches `colors.json`.
- The idle delta is within budget against S-host.
- The owner says yes, recorded in `evidence/host/<id>.md`.

**Licence hygiene.**
- Record facts from the kartik317 files, then write the implementation from that table with no kartik file open.
- Owner-authored assets need an attestation and an SPDX header.
- `tools/licence-similarity` fails above the threshold the reviewer sets on the first run (about 20%).

## 4. Review checklist (every deliverable)
1. **Gate and evidence.** The gate ran green and the evidence was generated by the tool. Zero-test runs are rejected.
2. **Tests.** Each fix has a test that fails without it. Security gates have a mutation test. No test was weakened. Lint is clean.
3. **Scope.** Matches the milestone row.
4. **Licence.** SPDX on every file, the similarity check passes, and `docs/third-party.md` is updated.
5. **Security.**
   - No `docker run` outside the wrapper.
   - No eval, `sh -c` built from strings, or `pkill -f`.
   - No kitty remote control and no listening sockets.
   - Generated config contains validated tokens only.
   - No secrets in logs or evidence.
   - Writes are atomic.
6. **Host safety.** Backup taken, rollback tested, dead-man switch armed, component on the allowed list, no session restart, ISO path stated.
7. **Lightweight**, measured against S-host:
   - Idle PSS +≤5% and CPU ≤1% average over 60 s.
   - No new resident process.
   - Custom modules are event-driven or poll every 5 s or more.
   - The theme run takes ≤1.5 s.
8. **Two audiences.** Beginners get a safe default, a plain-language error and a discoverable entry point. Experts get printed paths, overrides that win, and nothing hidden.
9. **Theme contract.** File names match the contract. Text contrast is ≥4.5:1 and UI ≥3:1. Protected colours are unchanged. Missing state falls back to the package defaults.
10. **Docs.** README or man page updated; migration deltas recorded.

## 5. Updated 1.0 build order
- **Stage 0:** M0 (ISO track); T0 (S-theme spike, schema, clamps, property tests, contract, injection test); H0 (`seclegion-host` backup, rollback, confirm, dead-man switch, baseline-0, S-host).
- **Stage 1:**
  - H1 border fix, H2 swaync, H3 waybar with the logo, T1 reload hooks and host wiring.
  - In parallel: M1 and spikes S2–S5.
- **Stage 2:**
  - Remaining surfaces on the host: rofi, kitty, swayosd, hyprlock, starship, fastfetch. Then GTK/Qt, which is cuttable. Then the wallpaper picker wiring, then the owner's sign-off.
  - In parallel: M2, M3, S-uwsm, the licence spike, S8 and S9.
- **Stage 3:** M4/M5 installer, then M6/M6+ porting the host work into packages with VM gates and golden screenshots, then M7/M7+/M7t/M7s.
- **Stage 4:** M7a, M8, M10. M9a and M6g only if they stay in 1.0.
- **Stage 5:** M11, M12.

Estimate: about 60–70 builder runs, or about 50 if AI and GNOME move to 1.0.1 (UNVERIFIED).

**UNVERIFIED:**
- the S-theme reload mechanisms;
- Hyprland Lua behaviour on error;
- matugen flags;
- OVMF on the host;
- swayosd style reload;
- the similarity threshold;
- the idle budgets;
- run counts.

## 6. Pending owner decisions
- R7-D1: move SecLegion AI (M9a) and the GNOME session (M6g) to 1.0.1, and drop the GDM swap in favour of greetd+regreet.
- R7-D2: approve the dead-man switch, the one-line hooks and the symlink-flip method on the host.
- R7-D3: attest that you authored `ae-osd.sh`, the SecLegion logos and your local dotfile edits.
- R7-D4: run `sudo pacman -S --needed matugen swayosd`.

## 7. Owner answers (2026-10-14)
- R7-D1: **Accepted.** The owner prioritises quality over speed. SecLegion AI (M9a) and the GNOME session (M6g) move to **1.0.1**. The login screen stays greetd+regreet, with no GDM swap.
- R7-D2: covered by the owner's "full permissions" approval for dynamic changes on the host, under §3.
- R7-D3: **Attested.** The owner authored `ae-osd.sh`, the SecLegion logos and the local dotfile edits. They may be imported under MIT with SPDX headers.
- R7-D4: **Done.** The owner installed matugen and swayosd.
