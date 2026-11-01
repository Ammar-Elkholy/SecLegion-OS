# Plan r14: all remaining 1.0 work, full scope (v4: round 3 fixes, Hyprland-only O9b)

Date 2026-10-17. Sec (Opus 5.5) plans and reviews. Builders are Sonnet 5.5, **at most 2 at once, one per lane** (owner 2026-10-17: "get back the parallel agents but only 2"; goal is less wall-clock time).
Scope:
- milestones M2 close, M3, M4, M5, M6/M6+/M6g, M7/M7+, M7a, M8, M9, M9a, M10/M10+, M11, M12/M12+;
- spikes S1-S9;
- owner decisions O9-O12;
- the desktop leftovers.

Nothing is deferred. Debate record: [plan-r14-debate.md](plan-r14-debate.md).

## 0. Rules quoted in every handoff
- **R0 Two lanes.** At most 2 subagents at once: one in lane A (system, installer, ISO) and one in lane B (desktop, features). A lane's next job starts after its previous job is reviewed and merged by the main session. Only one ISO build (docker) and one VM run at a time: every `tools/docker-build.sh` call (ISO, `pkgs`, theme), every package build, every VM run and every installed-base qcow2 build takes `flock /var/tmp/seclegion-build.lock` (`tools/lib/locks.sh`); the other lane runs unit/nested tests meanwhile.
- **R0a Merge order.** Both lanes merge into `clean-room-rebuild` only through the main session. A lane rebases on that branch before each handoff, and never starts a job whose input is unmerged.
- **R1 Containers.** No sudo. Containers start only via `tools/docker-build.sh`, and `tools/check-container-start` stays green.
- **R2 No real disks.** Never write a physical disk or USB. VM disks are image files in the build dir, and the harness refuses `/dev/*`.
- **R3 Trust and secrets.**
  - No third-party repos or keys, and no telemetry.
  - No secrets in git, the ISO, logs or evidence. Passwords reach installd only as yescrypt hashes or through an fd.
  - The DEV signing key is generated in the container per build and never leaves it.
  - The only exception is `tests/keys/repro-dev.gpg`, a key labelled TEST-ONLY that the reproducibility gate uses and nothing ships.
- **R4 Host.** Host changes go only through `seclegion-host`. Never send hyprctl dispatch/keyword/reload to the live session; use a nested instance. Never edit owner files.
- **R5 Space.**
  - One build dir at a time, `/var/tmp/seclegion-build`.
  - First action of the plan: delete stale `/var/tmp/seclegion-build*` dirs.
  - Run `tools/check-space` before every build; it refuses below 35 GiB (25 GB build + VM images + an ~8 GB cached installed-base qcow2).
  - Copy the finished ISO to `/mnt/Dev_Lab/iso-artifacts/` and delete the build dir after each checkpoint.
  - One VM at a time, at most 8 GB RAM. The host has 14 GiB.
- **R6 Testing rhythm.**
  - Per job: unit, static and nested or container tests only. **No ISO rebuild between jobs**: installer jobs use the I-devloop (boot the last checkpoint ISO, run installd from a mounted second image).
  - One ISO build plus all VM gates per checkpoint (§3).
  - Privilege, signing and disk-writing gates are never skipped at a checkpoint.
- **R7 Handoff size.** One job per handoff, under 120k context, quoting only that job's section and these rules. The main session updates `docs/STATUS.md` after every job. Merge target: `clean-room-rebuild`.
- **R9 Rework cap.** At most 2 failed rebuilds per checkpoint, then stop and re-plan (Sec). Estimates carry a 25% contingency.
- **R10 Slip policy.** Nothing is cut without the owner. If time runs short these are built last (addendum §8): browser chat, Continue, docs RAG, QR/recorder, battery/power profiles.
- **R8 File owners.**
  - Each file has one owning job (listed per job).
  - Package lists: a job adds `iso/packages.d/<job>.x86_64` fragments, which the build concatenates. Nobody else edits `packages.x86_64`.
  - `tests/lib/qemu.py` API freeze: `disks=`, `boot=`, `mem=` and `credentials=` are added in I-devloop and only extended afterwards.
  - ufw and sshd defaults are owned by installd's post step. W3 only tests them.
  - Named cross-lane exceptions: lane B owns `installer/ui/` (U1-U4) and `tests/install/{test_gui_*,fixtures/ntfs}` (U3); lane A keeps `installer/installd`, `installer/schema` and `tests/install/test_{plan,m4,m5}*`. W1 (lane A) owns only `tests/desktop/test_m7_*.py` and starts after D1, D2 and S8/9 are merged.

## 1. Installer decision (D-R14-1)
Option (a) is chosen: our own installd, with a text UI first and the GTK GUI second. That keeps the existing decision A1, which is now made faster.
**Why not (b) or (c), archinstall.** The post step we need anyway already owns most of the work:
- the kernel cmdline;
- mkinitcpio presets with sd-encrypt;
- crypttab;
- the ESP label;
- snapper, ufw and first boot.

What archinstall would add is pacstrap, genfstab, locale, hostname, useradd and `bootctl install`, about 300 lines. In exchange it brings real risks:
- `pre_mounted_config` carries no disk encryption, so it would not write crypttab or `rd.luks` for a LUKS mapper we made;
- its UKI path derives root from its own disk model;
- `--offline` may still touch time sync and mirrors;
- it leaves config logs in the target.

Under (b), archinstall's own partitioner would touch disks beside Windows, and we cannot pin its refusals.

**Omarchy-level speed comes from three things, not from archinstall.**
- The archive-pinned offline cache: no downloads.
- Five prompts, with Enter accepting every default.
- One post-install command (`seclegion-postinstall`).

The target is an installed login prompt in under 900 s. The GUI reuses the same plan JSON and installd.
The addendum §3 "archinstall configurator: REJECT" stands, with this comparison recorded in decisions.md.

## 2. Jobs in run order
Each job lists its owned files, at most 3 deliverables, its gates and an estimate.

### Checkpoint A: M2 close + M3 signed repo (S2)
- **J0 M2 gates.** Owns iso/profile/airootfs selftest and sshd, tests/iso/test_m2_*.py, evidence/M2-*. 6 h. This is the open builder's worktree `agent-a880d726f25d1ada4`.
  - G1 all M2 VM tests pass with OCR — CHECK: `SL_REQUIRE_OCR=1 pytest -q tests/iso -k m2` — EXPECT: `passed`, 0 failed
  - G2 negative: a planted enabled sshd fails — CHECK: `pytest -q tests/iso -k planted_sshd` — EXPECT: `passed`
  - G3 — CHECK: `tools/verify-evidence --iso out/*.iso` — EXPECT: `OK`
- **R0 spike: clean-chroot package builds in the container.** Owns `tools/docker-build.sh` (`pkgs` mode) and `docs/spec/v1/r0-spike.md`. 2 h.
  - G4 a hello PKGBUILD builds in the container with `makechrootpkg` or `makepkg` in a fresh root — CHECK: `tools/docker-build.sh pkgs pkgs/hello` — EXPECT: `pkg-ok`
  - G5 `check-container-start` still OK — EXPECT: `OK`
- **R1 repo and signing.** Owns `tools/build-pkgs`, `pkgs/seclegion-keyring/`, the `[seclegion]` section of `iso/profile/pacman.conf`, and `tests/unit/test_repo.py`. 5 h.
  1. A per-build DEV key is generated in the container, and packages and DB are signed with it.
  2. The keyring package is built and installed in the ISO.
  3. The `[seclegion]` file repo lives in the offline cache with `SigLevel = Required DatabaseRequired`.
  - G6 a tampered package is rejected — CHECK: `pytest -q tests/unit/test_repo.py -k tampered_pkg` — EXPECT: `passed`
  - G7 a tampered DB is rejected — CHECK: `-k tampered_db` — EXPECT: `passed`
  - G8 negative: `Optional` anywhere fails — CHECK: `-k siglevel_required` — EXPECT: `passed`
  - G9 no secret key in out/, the pkgs or git — CHECK: `-k no_secret_key` — EXPECT: `passed`
- **R2 system packages.** Owns `pkgs/seclegion-{release,base,rescue}/`. 4 h.
  1. os-release override: tmpfiles `L+` plus a pacman hook.
  2. Base defaults: zram, sudo with password, a hook that warns when a preset has no UKI.
  3. Rescue CLI skeleton.
  - G10 os-release survives a `filesystem` reinstall (container chroot) — CHECK: `pytest -q tests/pkgs -k osrelease` — EXPECT: `passed`
  - G11 negative: a planted Arch os-release symlink fails — CHECK: `-k planted_arch_osrelease` — EXPECT: `passed`
- **R3a desktop packages.** Owns `pkgs/seclegion-{desktop,dotfiles,theme,settings,branding}/`, `tools/seclegion-host` (`--system` mode) and `iso/packages.d/desktop.x86_64`. 5 h.
  1. Every host component ships under `/usr/share/seclegion`, with a skel loader. This replaces R13-1.
  2. `seclegion-host --system` applies those components to a new user.
  - G12 after install in a fresh root, apply works against a fake HOME — CHECK: `pytest -q tests/pkgs -k desktop_apply` — EXPECT: `passed`
  - G13 namcap prints no line outside `pkgs/namcap-allow.txt`, and pkgs/ is REUSE compliant — CHECK: `make lint-pkgs` — EXPECT: `0 errors`
- **R3b theme packages (D6) and Figtree.** Owns `pkgs/seclegion-themes-{graphite,tela,bibata}/` and the Figtree package. Sources are upstream release tarballs fetched at build time with a pinned sha256, recorded in third-party.md; no binaries in git. 4 h.
  - G13b a wrong source sha256 fails the build — CHECK: `-k theme_src_sha` — EXPECT: `passed`
  - G13c licence files (OFL/GPL) are installed — CHECK: `-k theme_licences` — EXPECT: `passed`
- **R4 hwdetect.** Owns `pkgs/seclegion-hwdetect/`, `hw/`, `tests/hw/`. 5 h.
  - G14 rules cover all 8 fixtures — CHECK: `pytest -q tests/hw` — EXPECT: `passed`
  - G15 the table equals the vendor HTML snapshot, whose sha256 is pinned in git — CHECK: `-k supportedchips` — EXPECT: `passed`
  - G16 negative: an edited table row fails — CHECK: `-k planted_table` — EXPECT: `passed`
- **R5 fetchers, canary and hosting (S2).** Owns `pkgs/seclegion-{vscode,brave}-fetch/`, `tools/{vendor-bump,canary}`, `docs/third-party.md`, and `systemd/seclegion-canary.timer` (owner host, documented). 4 h.
  - G17 a wrong sha256 is rejected — CHECK: `pytest -q tests/pkgs -k fetch_bad_sha` — EXPECT: `passed`
  - G18 third-party.md is complete — CHECK: `-k third_party_complete` — EXPECT: `passed`
  - G19 S2: a VM installs from a repo served on the host — CHECK: `pytest -q tests/iso -k s2_host_repo` — EXPECT: `passed`
- **Checkpoint A** runs the ISO build and the VM gates G1-G3, G6, G7, G10 and G19. Evidence rows: `M2-*`, `M3-repo-signed`, `M3-tampered`, `M3-osrelease`, `M3-hwdetect`, `M3-fetch`, `S2-host-repo`.

### Checkpoint B: M4 install engine (S3, S4, S5). Disk-writing, so the highest review cost.
- **I1 plan and guards.** Owns `installer/schema/plan-v1.json`, `installer/installd/{validate,disk}.py` and `tests/install/test_plan.py`. 6 h.
  1. Schema and validator.
  2. Disk layer for four modes:
     - erase;
     - erase+LUKS (argon2id, ticked by default for erase, D11);
     - alongside: the free gap only, plus its own ESP;
     - manual.
  3. A `--dry-run` command list.
  - G20 the golden command lists for the 4 modes — CHECK: `pytest -q tests/install/test_plan.py` — EXPECT: `passed`
  - G21 negative: one red case per refusal — CHECK: `-k refuse` — EXPECT: `passed`. The refusals are:
    - not booted in install mode;
    - the disk holding `/`;
    - the boot medium;
    - a mounted disk;
    - an MBR disk;
    - a small gap;
    - a non-contiguous gap;
    - a wrong confirm name;
    - bare metal or a non-QEMU disk in a DEV build.
  - G22 the passphrase is never in output or logs — CHECK: `-k secret_never_logged` — EXPECT: `passed`
- **I-devloop.** Owns `tests/lib/devloop.py` and the `tests/lib/qemu.py` freeze (`disks=`, `boot=disk`, `mem=`, a second read-only image carrying `installer/`). 2 h. Boots the checkpoint-A ISO in install mode and runs installd from the mounted image, so I2a, I2b and I3 iterate without an ISO rebuild.
  - G25b the devloop runs `seclegion-installd --dry-run` inside the VM — CHECK: `pytest -q tests/install -k devloop_smoke` — EXPECT: `passed`
- **I2a population.** Owns `installer/installd/populate.py`, `installer/installd/seclegion-installd` and the peer-cred socket unit. 5 h.
  1. Two-phase `pacstrap -K` from the manifest against the signed offline cache, A4.
  2. fstab, crypttab, `/etc/kernel/cmdline`, mkinitcpio presets with the A5 hooks, locale, hostname, vconsole us+ara, and the user from a yescrypt hash.
- **I2b boot and post.** Owns `installer/installd/post.py`. 5 h.
  1. `bootctl`, UKIs, the NVRAM label "SecLegion OS".
  2. snapper with snap-pac, ufw deny-in, sshd masked.
  3. The `[seclegion]` packages and the first-boot unit.
  - (I2a and I2b gates, run in the devloop VM:)
  - G23 a container dry run writes exactly the allowlisted files — CHECK: `pytest -q tests/install -k post_allowlist` — EXPECT: `passed`
  - G24 negative: `/mnt/var/log` and the target hold no password material — CHECK: `-k no_secret_in_target` — EXPECT: `passed`
  - G25 the harness refuses `/dev` — CHECK: `pytest -q tests/unit -k refuses_dev` — EXPECT: `passed`
- **I3 VM install matrix.** Owns `tests/install/test_m4_*.py`. 5 h.
  - G26 erase, erase+LUKS (unlocked over serial), alongside and manual. For alongside, the Windows-like fixture partitions must stay byte-identical by sha256 — CHECK: `pytest -q tests/install -k m4` — EXPECT: `passed`
  - G27 online `pacman -Qu` is empty (host-repo network), and the offline install makes zero network attempts with `-nic none`. A package missing from the cache fails fast with a clear message — CHECK: `-k online_qu or offline_strict` — EXPECT: `passed`
  - G28 S3: `.cmdline` equals `/etc/kernel/cmdline` with no archiso. S4: a rollback boots. S5: `efibootmgr -v` shows the label — CHECK: `-k s3 or s4 or s5` — EXPECT: `passed`
- **I4 target-clean and mutation suite.** Owns `tests/mutation/install/*` and `tests/install/test_target_clean.py`. 4 h.
  - G29 the target has:
    - no live user, NOPASSWD, autologin or `nullok`;
    - no archiso hook, and no ISO-only packages;
    - a clean `pacman -Qkk`.
    
    CHECK: `-k target_clean` — EXPECT: `passed`
  - G30 each of at least 14 mutants is caught, and any green mutant fails the gate. The mutants: NOPASSWD on target, an empty shadow hash, `nullok`, the `seclegion-live` package in the target, live sudoers, autologin, the live user, a live polkit rule, an archiso hook, a missing `/etc/kernel/cmdline`, an Arch os-release symlink, SigLevel Optional, a skipped disk refusal, a wrong confirm name accepted — CHECK: `pytest -q tests/mutation -k install` — EXPECT: `14 passed` or more, 0 failed
- **Checkpoint B** runs the ISO build and G26-G30 in the VM. Evidence rows: `M4-erase`, `M4-luks`, `M4-alongside`, `M4-manual`, `M4-online`, `M4-offline`, `M4-target-clean`, `M4-mutation`, `S3-uki`, `S4-rollback`, `S5-nvram`.

### Checkpoint C1 (text install + installed desktop: S1, U1, D1, D2, U5-text) and C2 (GUI installer, welcome, S7: U2, U3, U4, D3, D4, U5-gui)
M5, M6/M6+/M6g, S1, S6, S7, O9, O10, O12. Lane A: S1, U1, U5. Lane B: D1, D2, then U2, U3, U4, D3, D4.
- **S1 spike: kiosk compositor with us↔ara.** It compares cage and sway. Owns `iso/profile/airootfs` kiosk units and `docs/spec/v1/s1-spike.md`. 2 h.
  - G31 OCR finds an Arabic glyph after the layout toggle — CHECK: `pytest -q tests/iso -k s1` — EXPECT: `passed`
- **U1 text setup and first boot.** Owns `installer/ui/seclegion-setup`, `tools/seclegion-postinstall` and the `seclegion-firstboot` unit. 4 h.
  - G32 at most 5 prompts, and Enter accepts the defaults (pty against `--dry-run`) — CHECK: `pytest -q tests/install/test_setup_pty.py` — EXPECT: `passed`
  - G33 the postinstall is idempotent — CHECK: `-k idempotent` — EXPECT: `passed`
- **U2 GUI pages 1-5.** The pages are welcome, language and keyboard, disk mode, alongside guide and manual. Owns `installer/ui/gtk/pages/{1..5}*`. 5 h.
  - G34 each page renders under broadway and emits its plan fragment — CHECK: `-k gui_pages_a` — EXPECT: `passed`
- **U3 NTFS fixtures and the guide.** Owns `tests/install/fixtures/ntfs/*` and the guide detector. 3 h.
  - G35 BitLocker, Fast Startup and a hibernated NTFS are each detected, plus a clean control — CHECK: `-k ntfs_guide` — EXPECT: `passed`
- **U4 GUI pages 6-15.** The pages are encryption, user, review (exact command list plus typed disk name), progress, error with log path, hardware report, gaming and online tiers, finished, and kiosk error. It also adds the Plymouth `seclegion-bits` splash (O12) and the O10 boot-to-setup default. Owns `installer/ui/gtk/pages/{6..15}*` and `pkgs/seclegion-plymouth/`. 6 h.
  - G36 the same broadway harness — CHECK: `-k gui_pages_b` — EXPECT: `passed`
  - G37 a killed UI shows the error screen and the log path — CHECK: `-k kiosk_error` — EXPECT: `passed`
- **D1 roles, uwsm and user.lua (S6, M6+).** Owns `desktop/roles.toml` and the uwsm units in `pkgs/seclegion-desktop`. 4 h.
  - G38 one owner each for notifications, polkit and secrets, and one Notifications service file — CHECK: `-k single_owner` — EXPECT: `passed`
  - G39 the user.lua override applies (nested) — CHECK: `-k user_lua` — EXPECT: `passed`
  - G40 negative: keybind lint covers both layouts, and a bind to a missing binary fails — CHECK: `-k keybind_lint_target` — EXPECT: `passed`
- **D2 greeter, branding and browsers.** Owns the greetd/regreet target config, the fetch-on-first-online-boot hook, and `iso/packages.d/browsers.x86_64`. 4 h.
  - G41 the greeter shows a password prompt for the user and no session selector; exactly one session file exists (Hyprland, O9b) and a correct password starts Hyprland, a wrong one does not; us/ara toggle checked by OCR — CHECK: `-k greeter` — EXPECT: `passed`
  - G42 branding grep returns 0 (vendor `/opt` excluded) — CHECK: `-k branding_target` — EXPECT: `passed`
  - G43 Firefox is the `xdg-settings` default; VS Code and Brave are Wayland-native with the sandbox on — CHECK: `-k browsers` — EXPECT: `passed`
- **D3 welcome app (M6+, §18.1).** Owns `desktop/welcome/`. 3 h.
  - G44 it shows once, can be reached from the menu, and every button resolves — CHECK: `-k welcome` — EXPECT: `passed`
- **D4 S7 screensaver.** Owns `tests/desktop/test_s7.py`. 2 h. (GNOME session dropped by O9b; G45 removed.)
  - G45b no GNOME session, gdm or gnome-shell on the ISO or target, and `/usr/share/wayland-sessions/` holds only the Hyprland entry — CHECK: `-k single_session` — EXPECT: `passed`
  - G46 S7 passes only with one of two outcomes; a run with neither fails:
    - synthetic input reaches no client while the lock still fires;
    - `docs/decisions.md` gains an O4 entry with the measured failure.
    
    CHECK: `-k s7_result` — EXPECT: `passed`
- **U5 fast-install end to end.** Owns `tests/install/test_m5_*.py`. 3 h.
  - G47 from QEMU launch to the installed greeter in under 900 s (KVM, `-nic none`, text path). "Greeter" means the selftest serial marker `greetd active` AND OCR of the regreet prompt — CHECK: `-k fast` — EXPECT: `passed`, `elapsed_s` < 900
  - G48 GUI path: OCR on every screen in us and ara — CHECK: `-k gui_ocr` — EXPECT: `passed`
  - G49 a full disk shows the error screen — CHECK: `-k disk_full` — EXPECT: `passed`
- **Checkpoint C1** runs the ISO build, G31, G38-G43 and G47 in the VM, re-runs G26 and G29-G30, and builds the cached installed-base qcow2 (the backing file for the D, E and F gates). **Checkpoint C2** runs the ISO build, G44-G46 and G48-G49, and re-runs G29-G30.
  - Evidence rows: `S1-kiosk-ara`, `M5-fast`, `M5-gui-ocr`, `M5-ara`, `M5-diskfull`, `M6-roles`, `M6-greeter`, `M6-branding`, `M6-browsers`, `M6-single-session`, `S6-userlua`, `S7-result`.
  - Owner, HW-MANUAL `M5-hw-install`: boot from USB, then do a real install after a backup.

### Checkpoint D: M7/M7+ owner workflow + M7a utilities (S8, S9)
- **S8/S9 spike.** S8 covers Lua keycode binds versus `hyprctl binds -j`. S9 covers the swaync margin and the swayosd custom message. Owns `docs/spec/v1/s8-s9.md` and `tests/desktop/test_s8_s9.py`. 2 h.
  - G50 both have a pass test or a decision entry — CHECK: `-k s8 or s9` — EXPECT: `passed`
- **W1 key matrix and M7+ probes.** Owns `tests/desktop/test_m7_*.py`. 5 h.
  - G51 every bind is sent over QMP, in both us and ara — CHECK: `-k keymatrix` — EXPECT: `passed`
  - G52 notification probes: geometry, colour, timeouts, DND, the OSD namespace, the border ARGB value, `fc-list` fonts and the cursor ×3 — CHECK: `-k m7plus` — EXPECT: `passed`
  - G53 the lock shows no notification content (OCR); the idle order holds; there is no suspend on AC — CHECK: `-k lock_privacy or idle_order` — EXPECT: `passed`
- **W2 menu, cheat sheet and capture.** Owns `desktop/{menu,keys-help,capture}/`. 5 h.
  - G54 `seclegion-keys --json` lists every live bind with its command and availability — CHECK: `-k cheatsheet` — EXPECT: `passed`
  - G55 OCR capture works on eng and ara fixtures; the QR decoder and the recording output are playable — CHECK: `-k capture` — EXPECT: `passed`
- **W3 update, migrations and refresh-config.** Owns `pkgs/seclegion-update/` (migrations live in `pkgs/seclegion-update/migrate/`). 5 h.
  - G56 one snapshot pair per update, each migration runs once, a rerun is a no-op — CHECK: `-k update` — EXPECT: `passed`
  - G57 negative: a failing migration aborts with the snapshot intact; a missing UKI aborts — CHECK: `-k update_abort` — EXPECT: `passed`
  - G58 tests the post-step defaults: ufw deny-in, sshd inactive, and a `seclegion-baseline` snapshot present — CHECK: `-k m7a_defaults` — EXPECT: `passed`
- **W4 remaining utilities.** Night light, emoji, stay-awake, reduced motion, the fwupd entry, battery alerts at 15% and a sticky one at 7%, and the power-profile switch. Owns `desktop/utils/`. 4 h.
  - G59 each one can be reached from its shortcut, the launcher, welcome or the bar — CHECK: `-k reachable` — EXPECT: `passed`
- **Checkpoint D** runs G51-G59 in the VM. Evidence rows: `S8`, `S9`, `M7-keys-us`, `M7-keys-ara`, `M7plus-probes`, `M7-lock`, `M7a-update`, `M7a-defaults`, `M7a-utilities`. Owner HW on both laptops:
  - XF86 and F-keys;
  - mic LED and keyboard backlight;
  - lock after suspend;
  - a side-by-side visual sign-off.

### Checkpoint E: M8 hardware + M9 tools + M9a AI
- **H1 NVIDIA and gaming.** Lane B (after R4). Adds only `hw/gaming.toml` (the manifest installd reads), `iso/packages.d/gaming.x86_64` and `pkgs/seclegion-gaming/`. installd and R4's hwdetect code are not touched. 4 h.
  - G60 hwdetect maps the 1650 and 4060 fixtures to nvidia-open(-lts), and Pascal to nouveau, with a message — CHECK: `-k nvidia_pkgs` — EXPECT: `passed`
  - G61 in the VM, `gamemoded -t` and steam-devices udev pass, and `vulkaninfo` reports the expected ICD name. That check is only a smoke test; the real gate is HW — CHECK: `-k m8_vm` — EXPECT: `passed`
  - G61b "NVIDIA matches kernel": nvidia-open(-lts) in the cache is built for the linux(-lts) in the same cache — CHECK: `-k nvidia_kernel_pair` — EXPECT: `passed`
- **T1 tools catalog batch 1 and the `seclegion-tools` CLI.** Owns `catalog/{recon,web,network}*.toml` and `tools/seclegion-tools`. 5 h.
  - G62 every entry has a safe test against localhost targets only — CHECK: `pytest -q tests/tools -k batch1` — EXPECT: `passed`
  - G63 negative: an entry without a safe test fails lint — CHECK: `-k catalog_lint` — EXPECT: `passed`
- **T2 batch 2 and docs.** Covers passwords, wireless, forensics and reversing, plus `docs/security-tools.md`. 4 h.
  - G64 — CHECK: `-k batch2` — EXPECT: `passed`
  - G65 the generated docs equal the committed docs — CHECK: `-k tools_docs` — EXPECT: `passed`
- **A1 AI runtime, catalog and CLI.** Owns `ai/{runtime,cli}/` and `ai/catalog.toml`. 5 h.
  - G66 disabled by default, no `:11434` listener, no models — CHECK: `-k ai_default_off` — EXPECT: `passed`
  - G67 a pull without consent is refused; a `-cloud` tag is refused; the catalog lint checks digest, licence and size — CHECK: `-k ai_refusals or ai_catalog` — EXPECT: `passed`
- **A2 AI Center with keys in Secret Service.** Owns `ai/center/`. 5 h.
  - G68 the canary key reaches the stub provider and is absent from disk, logs, journal, config and the serve environment; the UI masks it — CHECK: `-k ai_keys` — EXPECT: `passed`
- **A3 aichat integration.** Covers S+A, the tutor and docs-RAG roles, a confirmation for each cloud pipe, refusal of non-TTY pipes, Continue on click, and the waybar AI pill. Owns `ai/aichat/` and the `desktop/waybar` AI module. 4 h.
  - G69 a non-TTY cloud pipe is refused; the CORS gate (browser chat is dropped if it fails) — CHECK: `-k ai_pipe or ai_cors` — EXPECT: `passed`
- **Checkpoint E** runs the ISO build and G61 and G66-G69 in the VM. It adds G70, an egress gate: a counted packet capture on the VM NIC during local use of a tiny fixture model must show zero non-loopback packets. An oversized model must give a RAM error. The VM has 4 GB first, then 8 GB — CHECK: `-k ai_egress` — EXPECT: `passed`.
  - Evidence rows: `M8-vm`, `M9-catalog`, `M9a-off`, `M9a-egress`, `M9a-keys`, `M9a-fixture-model`.
  - Owner HW:
    - the 1650 laptop: nvidia-smi, prime-run, a Proton game, and an AI model of about 3B;
    - the 4060 laptop: an AI model of about 8B.

### Checkpoint F: M10/M10+ virtualisation + M11 rescue (run together with checkpoint E's VM run)
- **V1 libvirt networks.** `default` NAT and `seclegion-isolated`, ufw interplay, and virt-manager. Owns `pkgs/seclegion-virt/`. 4 h.
  - G71 nested NAT with DNS and DHCP while ufw is on; the isolated network has no route; virt-manager starts — CHECK: `-k m10` — EXPECT: `passed`
- **V2 rescue and rollback drills.** Owns `pkgs/seclegion-rescue` (it extends R2). 4 h.
  - G72 a snap-pac pair per transaction, `seclegion-rescue rollback`, and the system boots afterwards — CHECK: `-k m11` — EXPECT: `passed`
- **Checkpoint F** runs G71-G72 in the VM. Evidence rows: `M10-nat`, `M10-isolated`, `M11-rollback`.

### Checkpoint G: M12/M12+ release + desktop leftovers
- **L1 desktop leftovers.** Owns `desktop/waybar` (clock.toml), `desktop/settings` (writes off the UI thread), `tools/host-lib.sh` (the baseline-0 gap) and lint fixes on old files. 6 h.
  - G73 `make lint` — EXPECT: `0 errors`
  - G74 a Settings write does not block the main loop — CHECK: `-k ui_thread` — EXPECT: `passed`
- **RL1 release tooling.** Owns `tools/release`, `tools/licence-check` and `tests/keys/repro-dev.gpg`. 6 h.
  - G75 reproducibility: two builds with the TEST-ONLY key, run in series (the first ISO moves to Dev_Lab before the second is built), give a diffoscope that is identical — CHECK: `-k repro` — EXPECT: `passed`
  - G76 the licence check covers packages, themes, fonts and the AI catalog licences; the notes list vendor versions and their ages, and say "no models in ISO" — CHECK: `-k licences or notes` — EXPECT: `passed`
  - G77 negative: the notes are refused while any HW-MANUAL row is neither attested nor marked `not-attested-by-design` with a required note that the notes print verbatim (community Intel-only/AMD-only reports, USB passthrough), and a release build is refused if it contains the DEV key fingerprint — CHECK: `-k notes_refuse or release_key` — EXPECT: `passed`
- **Checkpoint G** is the release candidate: every VM gate of A-F is re-run on one ISO. Evidence rows: `M12-repro`, `M12-licences`, `M12-notes`. The owner signs SHA256SUMS with the release key.

## 3. Lanes, checkpoints, estimate, critical path
Lane A owns iso/, installer/, the system pkgs and tests/install; lane B owns desktop/, catalog/, ai/, hw/ and the desktop and feature pkgs. A lane may start a later checkpoint's job early when it touches only its own files.

| CP | Lane A jobs (h) | Lane B jobs (h) | CP run h |
|---|---|---|---|
| A | R0 2, R1 5, J0 6, R2 4 | R4 5 first (no repo needed), then R3a 5, R3b 4, R5 4 once R1 is merged | 2 |
| B | I1 6, I-devloop 2, I2a 5, I2b 5, I3 5, I4 4 | S8/9 2, W2 5, W4 4, T1 5, T2 4 (early, unit/nested only; their VM gates G54-G59 run at D, G62-G65 at E, with their ISO fragments) | 3 |
| C1 | S1 2, U1 4, V2 4 (needs I2b), U5-text 1.5 (after D1, D2 merge) | D1 4, D2 4 | 3 |
| C2 | W3 5, U5-gui 1.5 (after U4 merges) | U2 5, U3 3, U4 6, D3 3, D4 2 | 3 |
| D | W1 5, V1 4 | H1 4, A1 5, A2 5 | 2.5 |
| E | — (runs the E+F VM matrix) | A3 4 | 3 |
| F | — (merged into E's run) | — | 0 |
| G | RL1 6 | L1 6 | 4 |

Lane A ≈ 87 h, lane B ≈ 98 h (after the round 3 moves: H1 to lane B, V1 to lane A) of jobs, plus ≈ 20 h of checkpoint runs (which pause the other lane's VM use only). The two lanes run in parallel, so wall clock ≈ 98 + 20 ≈ 118 h, or ≈ 147 h with the 25% contingency. In series the same work would take ≈ 237 h. Total agent work ≈ 205 h (≈ 256 h with contingency).
Critical path: lane A R0 → R1 (gates lane B's package jobs), then lane B (D1 → D2 gates C1, U2-U4 gate C2, A1-A3 gate E). Lane A fills its waits with V2, W3 and V1.
Biggest speed levers:
- the I-devloop, so installer iterations need no ISO rebuild;
- one cached installed-base qcow2 per checkpoint, so later gates skip reinstalls;
- checkpoint F folded into E;
- lane B pulling unit-tested work (W2, W4, T1, T2, S8/9) forward into checkpoint B.

The riskiest jobs get the most review and run earliest: R1 (signing) and I1-I4 (disks and privilege).

## 4. Owner actions and when
- **Now:** nothing.
- **End of checkpoint C:** USB boot, then a real install after a backup, naming the exact device.
- **D and E:** hardware tests on both laptops; USB passthrough (M10); ask for one Intel-only and one AMD-only community hardware report, or mark them `not-attested-by-design`.
- **Before G:** pick the repo hosting (GitHub Releases is proposed), then create the release key offline.
- **Any time:**
  - send `journalctl -b -g 'without|start-hyprland'`;
  - `sudo rm -rf` the root-owned leftovers the builders report.
