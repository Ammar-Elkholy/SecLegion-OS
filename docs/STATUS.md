<!-- SPDX-License-Identifier: MIT -->
# SecLegion OS: status

Updated 2026-10-31 (ISO #11). Progress 81% (1.0 = 80%). Branch `clean-room-rebuild`, HEAD before this file: `9f30657`.
History before 2026-11-01 was wiped from GitHub on the owner's word; it is kept in
`/mnt/Dev_Lab/iso-artifacts/seclegion-git-history-2026-11-01.bundle`. Commit ids below refer to that bundle.

## Done
- M0 foundation: layout, REUSE, container wrapper, QEMU harness, evidence verifier, TESTING.md.
- Live-host desktop: `seclegion-host` (apply/confirm/rollback, dead-man), waybar, swaync, keys, OSD, idle, gtk/fm, lock.
- Theme engine `seclegion-theme`; Settings GTK4 app (17 pages) + backend `seclegion-set`.
- Signed local `[seclegion]` repo with about 20 packages (`tools/build-pkgs`); ISO profile and GRUB theme.
- Installer: configurator, archinstall flow, seclegion-post, target_check, firstboot, GUI pages.
- CP-A closed on ISO #6 (16/16 gates; ISO sha256 `2e33cd5e…`, `/mnt/Dev_Lab/iso-artifacts/iso6/`).
- I2: a real install boots to regreet with Hyprland only. I3: erase, erase-luks and alongside all install.
- CP-B closed: 6 M4 rows; verify-evidence OK (23 results).
- D2: greeter VM test; skel copied in post.
- U5: fast install in 316 s; a disk under 20 GiB is refused before anything is written.
- Migration work of 2026-10-28 (all merged, `clean-room-rebuild` 30b0ab2; unit suite 1240 passed, lint green):
  - Dev profile (DAILY-DRIVER gap 2): git, openssh client (sshd stays masked), gnupg, base-devel, docker,
    socat; docker.service enabled; user in `docker`.
  - Gap 1: Legion Slim 5 16AHP9 hwdetect fixtures (hybrid, discrete); NVIDIA suspend units + param.
  - Gap 1b: `seclegion-post` applies the hwdetect plan (`installer/installd/hwplan.py`).
  - Installer on the ISO: package `seclegion-installer`; the Install kiosk runs the GTK GUI; root only via
    `pkexec /usr/bin/seclegion-install` and a polkit rule written to /run by the install target only.
  - AQ_DRM_DEVICES uses colon-free udev links `/dev/dri/seclegion-{igpu,dgpu}`.
  - Owner runbook `docs/USB-MIGRATION.md` (Windows prep, firmware, flash, live tests, install, move work).

## In progress (CHECKPOINT 2026-10-30, late night)
- ISO #9 (`/mnt/Dev_Lab/iso-artifacts/iso9/`, sha256 90a5891d…, built from 7f622c1): all 34 VM gates PASS
  (31 first run; M1-theme-repro needed disk space, M2-units-live was a boot-still-starting flake, M6-roles had a
  comma in a `Shell.say` line, fixed in 5560e4c with the `SAY_RE` pin). `verify-evidence --iso` OK (36
  results). ISO #8 records archived to `/mnt/Dev_Lab/iso-artifacts/evidence-archive-2026-10-30/`.
- Owner-reported desktop issues (DAILY-DRIVER gaps 13-18), plan in `docs/plans/desktop-issues.md`. Merged:
  - Lane A (2f08d28, gaps 13/17 part): waybar GPU module shows every GPU (AMD busy %, NVIDIA via
    `nvidia-smi -i <slot>` on AC only; "dGPU off" when runtime-suspended, no query on battery); network speed
    in bits/s (bytes read 8x low against Mbit/s).
  - Lanes B-C2 (621199a, gap 15): `seclegion-displayd` clears ghost monitors (enabled in Hyprland, connector
    `disconnected`): moves their workspaces to a live monitor, disables the ghost, re-enables on re-plug. udev
    and socket2 events only, no polling (a status read can wake the dGPU). Package unit + host `display`
    component. Finding: Hyprland 0.56.2 already migrates workspaces on a clean output removal (nested).
  - Lane D (e4bc310, gap 16): `seclegion-wallpaper` paints the SecLegion background on every output at start
    and on hotplug; theme apply repaints. seclegion-branding pkgrel 2 (generated default.png, MIT),
    seclegion-desktop pkgrel 3 (depends awww).
- Unit suite 1467 passed, lint green. These package changes are not on ISO #9: they need ISO #10.
- Subagent rule slips (reported to the owner): lanes B/B2 each ran one read-only `hyprctl version` against
  the live Hyprland; a lane D test ran one real `awww img` on the live session (fake PNG, rejected). Fixed:
  the test now passes `env=ctx.env` and stubs `os.environ`.
- Pre-existing, outside testpaths: 4 failing tests in `desktop/theme/tests` (2 `test_hyprland_host_lua_*`,
  lua exits 1; 2 `test_sync` Units SPDX).
- Kept worktree `agent-a0385fdb52b3ba760` (its .venv is the project python).

- CHECKPOINT 2026-10-31 (after the weekly reset): merged L3a (77550d6, pkexec backend: polkit action
  `org.seclegion.settings.root-apply`, timezone/ssh/firewall/snapshot_keep still refused), L4 (c998aba,
  `seclegion-display-menu` on XF86Display and SUPER+SHIFT+P, waybar display button; bab1473 links it into
  ~/.local/bin), displayd scale fix (8fd62f5: a re-plugged HDMI keeps the owner's scale), L5b (037acb2,
  `seclegion-sysmon` GTK4 monitor with every GPU; waybar cpu/gpu clicks open it). Unit suite 1503 passed,
  lint green, pushed. Live laptop: `apply waybar`, `apply display`, `apply keys` all confirmed (first waybar
  apply auto-rolled back with no log, cause unknown; the retry was verified and confirmed). Fn+F7 binds load at
  the next Hyprland config reload or login. Slip: an L5b test ran the host nvidia-smi once (dGPU already
  on, AC); fixed.
- Later the same night: merged L3b (7f8efe4, Settings acts through the password prompt and shows no command),
  L6 (9ef985b, `seclegion-wifi` GTK4 panel on the bar's network click; libnm added to the lists in 603de72),
  L3c (9c59eb6, root writers for time zone, SSH server (unmask+enable / disable+mask), firewall, snapshot count),
  c5148ee (firewall row reads ufw.conf ENABLED; installer writes the snapper config 0644). Unit suite 1548
  passed, lint green, pushed. Live: `apply settings` and `apply waybar` confirmed (Wi-Fi panel staged).
  Privileged writes on this laptop need /usr/bin/seclegion-root-apply + the polkit policy (owner, root: install
  the seclegion-settings package). Running: L7 Settings Display layout page.
- CHECKPOINT 2026-10-31 (day): merged L7 (f6439f6, Settings Display: layout row laptop/extend/mirror/external
  through `seclegion-display-menu`, connected-displays row) and VG10 (new VM gate M12-desktop-units on the
  installed base: packages, root helper + polkit action, real timezone apply and a refused path value,
  snapper config 0644, displayd/wallpaper user units, launchers, python imports). Unit suite 1564 passed, lint
  green. ISO #10 (`/mnt/Dev_Lab/iso-artifacts/iso10/`, sha256 a83153b5…, built from 2d34767, before L7) gates:
  25 PASS, 8 FAIL, evidence b8b4b3f; M12-desktop-units PASS (VG10 run at 38f61d4). `verify-evidence --iso` OK
  (34 results; ISO #9 records left the tree).
  - M1-theme-repro: check-space refused (24.2 GiB free at /var/tmp/seclegion-build, needs 25).
  - 7 installed-base gates (M11-rollback, M6-roles/single-session/branding/browsers, M7a-defaults,
    M7a-docker-ufw): a stale cache marker with no `target.qcow2` (left by the VG10 agent, whose delete was
    refused). The owner deleted it; the re-run at 28e4dd0 passed all 7 (12 min with the base rebuild).
  So ISO #10: 33 of 34 gates PASS (`verify-evidence --iso` OK, 41 results); only M1-theme-repro is open.

- CHECKPOINT 2026-10-31 (ISO #11): merged S6 (S6-userlua gate), S7b (961a345, S7-result gate: a word typed
  under hyprlock reaches no client; focus by `hl.dsp.focus`), 48e5e8c (seclegion-dotfiles pkgrel 2 ships
  ~/.config/hypr/hypridle.conf: without it hypridle exited and idle/suspend never locked), Wi-Fi hidden
  networks, harness: a cache marker without its disk is rebuilt. ISO #11 (`/mnt/Dev_Lab/iso-artifacts/iso11/`,
  sha256 7fe0becd…, built from 8b355e2): all 36 VM gates PASS (M2-units-rescue failed once with the start of
  the selftest report missing from serial, passed on re-run). `verify-evidence --iso` OK (37 results). ISO #10
  records archived to `/mnt/Dev_Lab/iso-artifacts/evidence-archive-2026-10-31/`. Unit suite 1622 passed, lint
  green. GitHub release parts: `iso11/release/` (3 parts < 2 GiB, PARTS.SHA256SUMS, JOIN.txt).
- 2026-11-01: GitHub history wiped on the owner's word (one fresh commit 184c340, old history in the bundle).
  All 36 VM gates re-run on ISO #11 at 184c340: PASS (M1-theme-repro needed the install cache deleted for disk
  space, then passed). Published: GitHub release `iso11-2026.10.31` (3 parts) and a public Google Drive link
  (one file, in `docs/NEXT-ON-NEW-OS.md`), both sha256 7fe0becd….

## Next steps (in order)
1. Owner: download (Drive link) or use the local ISO, then flash
   and install per `docs/USB-MIGRATION.md`. The work to continue on the new install is in
   `docs/NEXT-ON-NEW-OS.md`.
2. Remaining CP-C rows: S1-kiosk-ara, M5-gui-ocr, M5-ara.
3. W1 VM half (the key matrix over QMP on the installed base); RL1 G75 repro with an ephemeral key (D-RL1).
4. Follow-ups: snapperd may cache NUMBER_LIMIT (check in a VM); M2-units-rescue serial-report flake (once).
5. Owner checks for the desktop issues: after an HDMI unplug run `hyprctl monitors all` (ghost left?); `wev` on
   Fn+F7; Wi-Fi bits/s against a known transfer; dGPU `runtime_status` reaches `suspended` on battery.
   Licence call: ship the owner's "Seclegion Wallpaper.png" as default.png?
6. Unverified until metal: pkexec + /run polkit rule, GTK under cage as the installer user, p13 reboot
   as that user, env via /etc/environment.d under uwsm, hwdetect picks nvidia-open for the live kernel only
   (linux-lts not handled), udev GPU links on the real Legion.
7. Later: CP-D, CP-G (= 1.0); 1.1: S1, U2-U4, V1, CP-E.

## Decided 2026-10-30 (owner, or agent under owner delegation; see docs/decisions.md)
- D-H1 multilib only with gaming (owner). D-UPD-1 hosted `[seclegion]` on GitHub Releases, interim disabled.
- D-RL1 owner holds the release key offline, no test key in git. D-GRT-1 regreet Session row accepted.
- D-BR-1 branding stays all rights reserved until the owner picks a licence.
- Git remote: `git@github.com:Ammar-Elkholy/SecLegion-OS.git` (old repo wiped on the owner's word; `main` there
  is the stale old local main, `clean-room-rebuild` is current). Standing permission to push.

## Known problems / workarounds
- Install logs are ~640 KB each (pacman progress bars). Trim them if repo size matters.
- The UKI uses Arch's `splash-arch.bmp`. Fold the fix into the Plymouth/branding work.
- The installed system has no core/extra sync DBs until the first `pacman -Sy`.
- Still open: real AI catalog digests; the `OLLAMA_NO_CLOUD`/aichat vars; SNAP_PAC_SKIP is unverified.
- One unit test flaked once under build load. Run the suite with `-rf` to name it.
- The main checkout has no `.venv`. Use the one in worktree `agent-a0385fdb52b3ba760` (keep that worktree).
- `make lint` needs an absolute PATH to that venv's bin.
- `make evidence` in the main checkout needs `--iso` (the build output is under `/var/tmp/seclegion-build/out`).
- Waybar tray can hang on the glycin icon loader. Workaround: `systemctl --user restart waybar`.
- Live host: `notifications`/`border` were applied by the old tool. Re-apply them with `seclegion-host` when convenient.

## Resume commands
```bash
cd /mnt/Dev_Lab/SecLegion-OS
PY=/mnt/Dev_Lab/SecLegion-OS/.claude/worktrees/agent-a0385fdb52b3ba760/.venv/bin/python
tools/build-iso    # ISO #8 from 24044b3; archive to /mnt/Dev_Lab/iso-artifacts/iso8/
SECLEGION_ISO=out/<iso8> $PY -m pytest -q -x -m iso tests/install -k "i2_run or i3 or m11"
tools/seclegion-progress --all
```
Series plan and agent notes:
`~/.config/Claude/side-session-notes/local_518e15f0-cf9a-4f75-b36f-6a5112e79b8a/`.

## Migration-critical (only the old laptop has these)
- Remote `origin` = github.com/Ammar-Elkholy/SecLegion-OS (SSH). Push `clean-room-rebuild` before moving.
- Branches: `clean-room-rebuild` (integration) and `main`. Unmerged: `worktree-agent-a29b75cd54650d532`
  (V2 WIP, superseded by 83a3d55; delete once M11-rollback passes on ISO #8) and the three lane branches
  of 2026-10-30 afternoon. The 33 merged worktrees and branches were removed on 2026-10-28. Regenerate the bundle before copying.
  `.claude/worktrees/` is local only and need not be copied.
- `.venv` exists only in worktree `agent-a0385fdb52b3ba760`. On the new laptop, run `make bootstrap` (creates `./.venv`).
- Build outputs (gitignored, rebuildable):
  - `out/` (repo, evidence; the ISO #6 copy was deleted 2026-10-28, the archive in iso6/ keeps it);
  - `/var/tmp/seclegion-build/{out,pkgcache,pkgbuild,profile,vm}` (about 2.3 G after the 2026-10-28 cleanup);
  - `/var/tmp/seclegion-build.lock`.
- Archived ISOs + evidence (not in git, keep): `/mnt/Dev_Lab/iso-artifacts/`, about 16 G.
  - `iso6/`: the current ISO, sha256 2e33cd5e…; `verify-evidence --iso` needs it.
  - `iso5/`.
  - Two older ISOs.
  - `evidence-archive-2026-10-23/`.
- VMs: only throwaway qemu images under `/var/tmp/seclegion-build/vm` (about 2 MB debug leftovers). No persistent VMs.
- Docker:
  - images `archlinux:latest` (base of the build container, pulled by `tools/docker-build.sh`) and `kalilinux/kali-rolling`
    (not used by the build);
  - two anonymous volumes from 2026-09-02 that predate this project and are not used. No named volumes.
- Secrets and keys: none persistent. The DEV package-signing key is generated per build inside the
  container and destroyed. Only `dev-key.fingerprint` is written to the build output. The RL1 release key does not exist
  yet. Test passwords are fixtures in `tests/` (dummy values).
- Source branding assets outside git: `/mnt/Dev_Lab/SecLegion/` (313 M):
  - `Planning Prompt.md` (the PRD);
  - logos, `Grub Splash.png`, `seclegion-spinner.png`, wallpapers, videos.
- `/var/tmp/seclegion-repo/` is from the old (Calamares) project and is not needed.
- Host packages the build/tests use:
  - docker 29.9, qemu-base + qemu-desktop 11.1, edk2-ovmf 202608 (`/usr/share/edk2/x64/OVMF*.4m.fd`);
  - swtpm, socat, tesseract + tesseract-data-eng, python 3.14, git;
  - KVM access, and the user in the `docker` group.
  - shellcheck, ruff and reuse come from `.venv`.
- Live-host desktop state for this laptop:
  - `~/.local/state/seclegion/host-backups` and `~/.local/share/seclegion/host` (applied components);
  - owner dotfiles `~/.config/hyprland-dotfiles`.
  On the new laptop, re-apply with `tools/seclegion-host apply <component>` instead of copying backups.
- Claude memory: `~/.claude/projects/-mnt-Dev-Lab-SecLegion-OS/memory/`. Copy it to keep the agent preferences.
  The project path must match, or the directory needs renaming.
