# SecLegion OS

Arch-based security distro for one owner: "like Omarchy, but personalized". Hyprland is the only
session. Installs with archinstall (like Omarchy). Version 1.0 = 80% on the progress meter, perfected = 100%
(`tools/seclegion-progress [--all]`, data in `docs/progress.toml`). Current state and next steps:
`docs/STATUS.md`.

## Architecture
- `pkgs/` — PKGBUILDs for the `seclegion-*` packages (release, base, keyring, branding, dotfiles,
  desktop, theme, settings, rescue, firstboot, hwdetect, ai, gaming, virt, fetchers…). Built and
  signed into a local `[seclegion]` repo by `tools/build-pkgs`. The repo sits below core/extra in
  pacman.conf, so it cannot shadow official packages. Packages do not depend on sibling seclegion
  packages, because makepkg resolves only the Arch repos.
- `iso/` — archiso profile (`iso/profile`), package lists (`iso/packages`, `iso/packages.d`), and the GRUB theme.
  `tools/build-iso` runs build-pkgs, then mkarchiso, inside a container.
- `installer/installd/`:
  - `configurator.py` turns the choices into archinstall JSON. It refuses an erase target under 20 GiB.
  - `seclegion-install` swaps in the offline conf and runs `archinstall --silent --offline`, then `seclegion-post`.
  - `post.py` installs the packages, copies skel (`cp -a -n`), and runs `seclegion-host --system`.
    It also sets up greetd + regreet and ufw, masks the sshd units, strips nullok, enables firstboot and scrubs creds.
  - `target_check.py` validates an installed root.
  - `installer/ui` holds the GUI; `installer/schema` holds the schemas.
- Installed system: systemd-boot with a UKI, btrfs subvolumes `@ @home @log @pkg @.snapshots`, optional LUKS,
  and an alongside (dual-boot) mode.
- `desktop/` — Hyprland/waybar/swaync/theme components. `tools/seclegion-host` applies them to a
  live home: backup, apply, confirm within 120 s or the dead-man rolls back. `--system` mode is for
  installs.
- `tools/seclegion-theme` (theme engine), `tools/seclegion-settings` (GTK4 Settings app),
  `tools/seclegion-set` (settings CLI).
- `tests/` — pytest. Unit tests run by default. VM tests are marked `iso` and use QEMU/OVMF through
  `tests/lib` (`devloop.py`, `bootgate.py`, QemuVM with `keep_vars`/`reuse_vars`; serial
  `send()` for the LUKS prompt; the QMP typer cannot type `%`).
- `tools/lib/evidence.py` + `tools/verify-evidence` + `tools/gen-testing-md` → `TESTING.md`.
  Serial patterns are ordered, and the test secrets are forbidden patterns.

## Commands
```bash
# python with pytest/ruff (main checkout has no .venv yet; reuse this one)
PY=/mnt/Dev_Lab/SecLegion-OS/.claude/worktrees/agent-a0385fdb52b3ba760/.venv/bin/python
$PY -m pytest -q -rf                       # unit suite
SECLEGION_ISO=out/<iso> $PY -m pytest -q -x -m iso tests/install -k <name>   # VM gates
PATH=/mnt/Dev_Lab/SecLegion-OS/.claude/worktrees/agent-a0385fdb52b3ba760/.venv/bin:$PATH make lint  # absolute PATH only
make lint-pkgs
tools/build-iso                            # one build dir at a time: /var/tmp/seclegion-build
make evidence                              # or tools/verify-evidence --iso <iso>
tools/seclegion-progress --all
```
Finished ISOs are archived to `/mnt/Dev_Lab/iso-artifacts/isoN/`. Package changes need a new ISO
before the VM gates can see them.

## Working mode (owner rules)
- Autonomous: don't ask the owner, work toward perfecting the OS. Nothing is cut from scope without the owner.
- Opus main session plans and reviews. Sonnet 5.5 subagents implement in worktrees. No reviewer subagents:
  the main session reviews every branch and re-runs every gate itself before merging.
- One agent at a time (series) by default; at most 2 lanes.
- Branch `clean-room-rebuild` is the integration branch; `main` is the default branch.
- Checkpoint `docs/STATUS.md` and `docs/progress.toml` at every merge and before rate limits.
- Record evidence PASSes on a clean committed tree only. Lint must be green before every commit (lines ≤ 110).

## Hard rules
- No sudo in agent shells (no_new_privs). Root actions belong to the owner.
- Containers start only via `tools/docker-build.sh`. `tools/check-container-start` must stay green.
- Stop builds only with `docker stop --time 600`. A shorter stop leaves root-owned files behind.
- Never write a physical disk or USB. Use qemu image files under `/var/tmp/seclegion-build/vm`
  only. A real device needs the owner's approval of the exact target.
- No third-party repos or keys, and no telemetry. Vendor binaries are fetched on first boot, never shipped.
- No keys or secrets in git, the ISO, logs or evidence. The DEV signing key is generated per build
  inside the container and never leaves it.
- Live host changes only go through `seclegion-host`, which keeps a backup and runs the 120 s dead-man.
- Never send hyprctl dispatch/keyword/reload to the live Hyprland. Use nested instances or VM guests.
- Never edit owner files: `~/.config/hyprland-dotfiles`, `hypridle.conf`, `~/.ssh`, `~/.gnupg`,
  `~/.themes`, `~/.icons`, wallpapers. Never touch the owner's keyring or Secret Service.
- Never reboot, log out, edit `/etc`, touch the display manager, or run pacman. The only exceptions are the
  read-only `pacman -Si` and `pacman -Q`.
- No `pkill`/`killall` by pattern. Stop processes by pid. Delete only what you created, by exact path.
- Never walk `.claude/worktrees/` from another checkout. The sandbox kills such a process (exit 137).
- Never use git stash. To set work aside, write a patch file in the scratchpad.
