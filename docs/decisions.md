# Decisions

Index of binding decisions. Full text: [spec.md sections 2-3](spec/v1/spec.md),
[full-plan.md](spec/v1/full-plan.md) (O9-O12), [owner-directives-r7.md](spec/v1/owner-directives-r7.md).
Add a new decision here with a date; never rewrite an old one - supersede it.

## Owner decisions

- **O1** Dual boot installs only into free space; the user shrinks Windows from Windows.
- **O2** Alongside installs always create a separate 1 GiB SecLegion ESP; nothing Windows owns is written.
- **O3** No password to install or try from the USB (live autologin + passwordless sudo on the USB only); the only password is the new user's.
- **O4** Screensaver ships only if spike S7 proves it by M7; otherwise 1.0 has the branded hyprlock screen.
- **O5** Owner maintains the signed `[seclegion]` repo; kartik317 dotfiles have no licence, so all configs are rewritten under MIT.
- **O6** VS Code (Microsoft build) and Brave are preinstalled via thin fetcher packages with a pinned sha256; binaries are never redistributed. Firefox is default.
- **O7** Claude Code and Antigravity IDE arrive in 1.1; Thunar + Yazi in 1.0.
- **O8** Brave and VS Code must be at most 7 days behind the vendor, enforced by the weekly canary.
- **O9** ~~GNOME second session~~ — superseded by O9b (2026-10-17).
- **O9b** (owner, 2026-10-17) Hyprland is the only session. No GNOME, no session selector. After install the machine boots to the login page (greetd + regreet), the user types their password, and Hyprland starts. M6g and its gates are dropped.
- **O10** The USB boots to the SecLegion setup (installer kiosk), never straight into a desktop; "Try Live" is a non-default entry.
- **O11** Super+/ cheat sheet and Super+M menu stay; Super+A opens an AI picker listing only installed/configured entries.
- **O12** Plymouth boot splash `seclegion-bits` in 1.0, frames pre-rendered at build time; also used for the LUKS prompt.

## Owner directives, round 7 (2026-10-14)

Plan approved; two audiences (experts and beginners) first-class; dynamic wallpaper theming in 1.0 with no resident theming daemon; polished bar with SecLegion logo top-left; live-host-first rule (dynamic changes on the owner's running system first with backup and one-command rollback, anything needing reboot/bootloader/initramfs/display manager only in ISO/VM); no root for agents; ISO builds in a privileged container.

## Architecture decisions

- **A1** Installer: GTK4/libadwaita UI builds a JSON plan; root `seclegion-installd` runs plain sgdisk/cryptsetup/mkfs/pacstrap and re-validates everything.
- **A2** ISO boot: GRUB gfxmenu, UEFI only, six entries each with its own `seclegion.mode` and systemd target, so Install is not Live by construction.
- **A3** Privilege: ISO-only `seclegion-live` owns all live privileges; installer user has no shell or sudo; target has root locked, sudo with password, no autologin.
- **A4** Target population: never copy the squashfs; two-phase `pacstrap` from a manifest via a signed offline cache.
- **A5** Installed boot: systemd-boot + UKIs from mkinitcpio, optional LUKS2, own 1 GiB ESP per install.
- **A6** Btrfs layout with subvolumes, zstd, snapper + snap-pac, rollback via `seclegion-rescue`; snapshots are not backups.
- **A7** Greeter: greetd + regreet in a kiosk compositor, us/ara toggle.
- **A8** Repos and signing: core/extra/multilib + signed `[seclegion]`; every non-official package recorded in third-party.md.
- **A9** Desktop: one program per role (`desktop/roles.toml`), static palette from `tokens.toml`, MIT-licensed rewritten dotfiles, REUSE-clean.
- **A10** Hardware: `seclegion-hwdetect` TOML rules; NVIDIA fixture table checked against the vendor HTML; redacted hardware report, never auto-uploaded.
- **A11** Gaming: Omarchy-style installer checkbox (multilib, steam, gamescope, gamemode, mangohud, wine-staging, lutris).
- **A12** KVM: libvirt `default` NAT plus `seclegion-isolated`; VM template defaults to isolated.
- **A13** Build host: workdir `/var/tmp/seclegion-build` on ext4, refuse fuseblk/ntfs and under 25 GiB free, pinned archive date, reproducibility checks.

## Decisions made while building M0 (need review)

See ENGINEERING_LOG.md entry 2026-10-14 for rationale.

- **M0-1** Container starts go through one wrapper, `tools/docker-build.sh` (image by digest, repo read-only, hard-coded mounts); `make lint` fails if any other file starts a container (Sec R7 rule).
- **M0-2** `check-space` also refuses vfat/exfat/msdos (no permissions or symlinks), beyond the spec's fuseblk/ntfs.
- **M0-3** Owner PNG assets at the repository root are marked all-rights-reserved in REUSE until the owner picks a branding licence.
- **M0-4** Dev tools (pytest, ruff, reuse, shellcheck) are installed into a gitignored `.venv` with pip (`make bootstrap`) because system packages need root.
- **M0-5** The build container keeps `--privileged`, an accepted risk. Why: `mkarchiso` needs loop devices and mounts (squashfs and ESP image assembly), and a full ISO build is the only way to verify a narrower set, which has not been done. Candidate narrower flags, all **UNVERIFIED**: `--cap-add SYS_ADMIN` with a seccomp/AppArmor profile; `--device /dev/loop-control` plus the loop devices instead of full device access. Inside the container `pacman -Syu` is **unpinned**: the image is pinned by digest but the packages it installs are whatever the mirrors serve that day, so the build is neither reproducible nor protected from a bad upstream package. Follow-up (proposed, not done): pin a dated Arch Linux Archive mirror in the container's `mirrorlist` and bump it together with the image digest (A13). Mitigations in place: the repo is mounted read-only, mounts and flags are hard-coded in `tools/docker-build.sh`, every bind source must be canonical (no symlink component) and owned by the invoking user, and `make lint` fails if anything else starts a container. Residual: the symlink and ownership check and the `docker run` are separate steps, so a process running as the same uid can swap a checked path for a symlink in between (same-uid TOCTOU); a same-uid attacker already owns the repo and the build directory, so this is accepted and not closed.
- **M0-6** `tools/check-container-start` is deny-by-default. Outside the wrapper it flags (1) any container-engine word (`docker`, `podman`, `nerdctl`, `buildah`, `ctr`, `runc`, `crun`, `youki`, `systemd-nspawn`, `lxc-start`, the compose tools, a path basename, a quoted list item, the default of a `${X:-docker}` / `${X:=podman}` expansion) and (2) any engine-named variable (`$DOCKER`, `${ENGINE}`, `${DOCKER:-docker}`, Make's `$(DOCKER)` and `$$DOCKER`) in command position, in both cases unless a read-only verb (`pull`, `image inspect`, `images`, `ps`, `version`, `info`) follows, past global flags. A verb is allowlisted only when every flag before it is a known no-argument flag or a known argument flag whose value is skipped (`--context x`, `-H h`, and the compose flags `-f -p --profile --env-file --project-directory`); any other flag denies, because it may swallow the verb as its value. Command position is the start of a line or of a command after `; & | ( ) { ! `` ` `` (so `$(` too), a shell keyword or a Make recipe prefix (`@ + -`), past wrappers (`sudo`/`doas` with flags and `-u USER`, `env` with `-u X` and assignments, `exec`, `eval`, `command`, `nohup`, `time`, `timeout N`, `nice -n N`, `setsid`, `xargs`, `sh -c "..."`/`bash -c '...'`, `su`, `runuser`, `stdbuf`, `ionice`, `chrt`); wrappers also include `run0`, `systemd-run`, `pkexec`, `nsenter`, `unshare`, `flock`, `watch`, `strace` and `taskset`. Backstop for wrappers command position cannot see (`sudo -u "$U"`, `timeout "$T"`, a user's `retry 3`, a Make `CMD = $(DOCKER) run`): an engine-named variable anywhere, followed by whitespace or a quote and then an unknown flag or a starting verb (`run create start restart exec compose up unpause kube play pod service plugin build buildx container stack swarm context cp commit load import machine system volume network`), is flagged too, except on a line that starts with `#`, `echo`, `printf`, `log`, `warn` or `die`. Any other engine-named variable (an argument, a path such as `"$XDG_RUNTIME_DIR"/bus`, a string, starship's `$docker_context`) is not a start. It also always flags (3) the Python SDK (`import docker`, `from_env`, `APIClient`, `*Client`, `aiodocker`, `containers.run/create/start/exec*`, `container*.start(`), `http+unix:` URLs, engine sockets (also URL-encoded), assignments to `DOCKER_HOST` / `CONTAINER_HOST` (not `${DOCKER_HOST:-}` reads or `"$DOCKER_HOST"` uses), HTTP paths on the engine API ports `:2375/` and `:2376/`, and engine symlinks. It joins backslash continuations and multi-line argument lists. It skips only the top-level directories `.git`, `.venv`, `build/`, `out/` (the last two hold the ISO), `.pytest_cache`, `.ruff_cache` and `.claude` (tool caches and agent worktrees hold test ids, not code), plus the `.git` pointer file of a worktree; a top-level FILE with any other skipped name is scanned, and nested `build/` and `evidence/` are scanned. Compiled `.pyc` files are not read, and Markdown is scanned inside code fences only, so prose may name the tools (this replaces the old `docs/spec/` skip). It is a tripwire, not a sandbox: a command assembled at run time evades it, which review has to catch.
- **M0-7** `tools/docker-build.sh` has a `check` mode that validates the layout and starts nothing; `SECLEGION_TEST_ROOT` (moves the `/var/tmp` root, drops the 25 GiB floor) is refused in any other mode, so the unit tests can exercise the symlink and ownership refusals without a container.
- **M0-8** Evidence verification (`tools/verify-evidence`) is a consistency check, not proof that a run happened. It checks that the commit is a real ancestor of HEAD, that the timestamp is not in the future and not before the commit's committer date, that the ISO hash matches (a PASS with no `out/SHA256SUMS` and no `--iso` fails unless `--rows-only`), that `serial_patterns` equal the canonical patterns registered for the test in `tools/lib/evidence.py`, that the stored `serial.log` satisfies them, and that every artifact re-hashes. A fabricated but self-consistent `serial.log` on a real commit cannot be detected without signing; this is an accepted residual. An `SL_BOOT_LOGIN_RE` run records non-canonical patterns and so can never verify as PASS.

## M2-openssh (2026-10-16, main session, reversible)
gvfs → gcr-4 → openssh pulls the openssh package onto the ISO. Spec A3 ("no openssh") is read as "no SSH server": the package may be present as a dependency, but sshd.service is masked, no host keys exist, nothing listens on :22. `check_repos` asserts those three instead of package absence. Dropping gvfs (Thunar trash/mounts) was rejected. Owner may overrule.

## D-R14-1 Installer: own installd (2026-10-17, Sec/Legion debate, reversible)
Option (a) is kept: our own installd, text UI first, then a GTK GUI on the same plan JSON. This does **not** reverse A1 ("own installer").
- (b) archinstall alone: rejected. Its partitioner would touch disks beside Windows with refusals we cannot pin.
- (c) hybrid, our partitioning and LUKS plus archinstall `pre_mounted_config`: rejected. It writes no crypttab or `rd.luks` for a mapper we made, its UKI path derives root from its own disk model, `--offline` may still touch time sync and mirrors, and it leaves config logs in the target. It would save only about 300 lines (pacstrap, genfstab, locale, hostname, useradd, bootctl), and our post step already owns the rest.
- Omarchy-level speed comes from the archive-pinned offline cache, five prompts with Enter accepting each default, and one post-install command. Target: an installed login prompt in under 900 s (G47).

## D6a Theme packages as built (2026-10-18, R3b, reversible)
- GTK: `seclegion-themes-graphite` builds upstream Graphite (tag 2026-08-23) `--color dark`, grey accent → `Graphite-Dark`. Upstream has no "Mono" variant; the owner's `Graphite-Mono` in ~/.themes is a third-party repack. The token CSS overrides colours anyway.
- Icons: Arch `extra` `tela-circle-icon-theme-grey` (no vendored package); Papirus-Dark fallback. Dark variant presence unverified.
- Cursor: `seclegion-themes-bibata` v2.0.7 uses upstream's prebuilt release assets (Modern-Classic, Modern-Ice), pinned by sha256, because `python-clickgen` is not in Arch. Not built from source: an accepted deviation from D6. The owner uses Bibata-Modern-Ice; default size 24.
- Font: `seclegion-fonts-figtree` v2.0.3 (OFL). D1 sets these names (gtk-theme, icon-theme, cursor-theme) for new users.

## D-R14-2 Installer: archinstall engine, Omarchy-style (2026-10-18, owner; supersedes D-R14-1)
Owner: "lets use archinstall i want to be like omarchy". SecLegion is Omarchy personalised for the owner.
- Like omarchy-iso: our own text configurator asks ~5 questions (Enter accepts each default), writes archinstall's `user_configuration.json` + credentials file (tmpfs, 0600, deleted after), and runs archinstall pinned to the version in the ISO (4.5-1 at time of writing). Then `seclegion-post` runs in the target chroot: `[seclegion]` repo + keyring, packages, greetd + regreet (O9b, Hyprland only), ufw deny-in, sshd masked, first-boot unit.
- Offline: archinstall's pacstrap uses the ISO's pacman.conf, which points at the embedded signed cache (`file:///opt/seclegion/cache`).
- Default path is erase / erase+LUKS (btrfs, systemd-boot). Alongside Windows only uses free space; our configurator validates the generated JSON before archinstall runs (the G21 refusals stay), and the G26 VM test pins Windows partitions byte-identical by sha256.
- D-R14-1's risks are now owned by tests, not by avoiding archinstall: G24/G29 check the target holds no credential material or archinstall logs with secrets; G27 checks the offline install makes zero network attempts.
- The GUI installer (1.1) drives the same configurator JSON.

## O4 S7 screensaver spike result (2026-10-23, D4, reversible)
S7 not proven: the spike needs synthetic input injected into a nested Hyprland to show it reaches no client while the lock still fires, and the host has no injector (`wtype`, `ydotool`, `wlrctl` all absent from PATH; `tests/keys/lib.sh` already records that keys cannot be injected into the nested compositor), and no layer-shell client library is installed (`gtk4-layer-shell` absent), so no idle visual could be built or measured; 1.0 ships the branded hyprlock screen (`desktop/hypr/hyprlock.conf`). A future spike with an input injector reopens it, and `tests/desktop/test_s7.py` then accepts an `s7-*.json` PASS fixture.

## D-H1 Steam and [multilib] (2026-10-30, DECIDED by owner)
Arch's official [multilib] is enabled in the installed `/etc/pacman.conf` only when the user chose gaming in the installer (hints `gaming: true`); never otherwise. Steam and steam-devices come from it.
The install is offline and the cache has no multilib packages, so Steam installs on the first online boot: `seclegion-steam.service` (shipped by `seclegion-gaming`, enabled by `seclegion-post` with a `steam-pending` marker) runs `pacman -Syu --needed --noconfirm steam` (a full upgrade: Arch does not support partial upgrades), logs failure, retries on the next boot and never blocks boot.
`seclegion-install-steam` does the same by hand (Omarchy's `omarchy-install-steam`).

## D-UPD-1 Updates for [seclegion] (2026-10-30, agent under owner delegation, reversible)
Target: a hosted, signed `[seclegion]` repository published as GitHub Release assets of `https://github.com/Ammar-Elkholy/SecLegion-OS` (Omarchy also hosts its own package repo), signed with the RL1 release key the owner holds offline. Neither the repository nor the key exists yet.
Interim: the installed `/etc/pacman.conf` keeps `[seclegion]` fully commented out (SigLevel `Required DatabaseRequired` kept, future Server `https://github.com/Ammar-Elkholy/SecLegion-OS/releases/download/repo` commented), because the `file://` cache exists only on the live ISO. `pacman -Syu` then works against core/extra only. `seclegion-keyring` stays installed, so enabling the repo later is one uncomment.
`seclegion-*` packages update by installing a newer ISO until the hosted repository exists. The install itself still pulls them from the offline cache (active section until the last step of `seclegion-post`).

## D-RL1 Release signing key (2026-10-30, agent under owner delegation, reversible)
The owner generates and holds the RL1 release key offline (Omarchy: one maintainer signs its own repo). It is never in git, the ISO, CI, logs or evidence, and no TEST-ONLY release key is committed: the G75 repro test generates an ephemeral key inside its run and discards it. Build-time packages stay signed by the per-build DEV key, which never leaves the container. Generating RL1 and publishing its public half in `seclegion-keyring` is an owner action, before the hosted repository (D-UPD-1) goes live.

## D-GRT-1 Regreet Session row (2026-10-30, agent under owner delegation, reversible)
Accepted as is: regreet always shows a Session row, which lists only Hyprland (O9b; no other session files are installed). Hiding it would need a patched regreet, a package we would then maintain against upstream for a cosmetic gain. Revisit if regreet gains an option to hide the row.

## D-BR-1 Branding licence (2026-10-30, agent under owner delegation)
The owner's PNG assets stay all rights reserved (M0-3). Publishing them under an open licence cannot be undone, so only the owner picks one. Code, configs and docs stay MIT (A9, REUSE-clean).

## D-BR-2 Branding on installed files (2026-10-30, agent under owner delegation, reversible)
The screen rule (`BRAND_RE`: "Arch Linux" and the word "arch") stays for everything the user sees (M1-branding, serial and OCR). On the files of installed `seclegion-*` packages the word "arch" is technical, not branding: PKGBUILD `arch=('x86_64')`, `ID_LIKE=arch` in os-release (attribution), `arch-chroot`, the `arch-core`/`arch-extra` package sources, comments that cite Arch packages. So the target gate `M6-branding` greps those files for the product name only (`NAME_RE`, "Arch Linux" in any spelling) and must find none.

## D-DKR-1 Docker under ufw (2026-10-30, agent under owner delegation, reversible)
Docker's published ports (`-p 8080:80`) are DNATed and pass through FORWARD, so ufw's INPUT policy never sees them and the port would be reachable from the LAN. Omarchy fixes this with the AUR `ufw-docker` script; we may not use AUR or third-party code (it is GPL-3.0, ours is MIT), so `seclegion-post` appends its own block to `/etc/ufw/after.rules` and `after6.rules` (`with_docker_user` in `installer/installd/post.py`).
The block fills Docker's `DOCKER-USER` chain: established traffic and traffic from container bridges (`docker0`, `br-+`) return, everything else jumps to ufw's `ufw-user-forward` and new connections that ufw did not allow are dropped. A port is opened with `sudo ufw route allow proto tcp to any port <port>`; localhost access does not pass FORWARD and is unaffected. VM gate: `M7a-docker-ufw`. The block also declares `ufw-user-forward`: ufw-init restores before, after, then user rules, so a jump to a chain only `user.rules` declares fails the after.rules restore and ufw.service with it (seen on ISO #8); `user.rules` refills the chain right after.
