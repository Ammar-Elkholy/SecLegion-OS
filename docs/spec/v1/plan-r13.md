# Plan r13: ISO track, M1 to M3 (Sec, for Sonnet builders)

The ISO is still the M0 stock releng profile. Mapping: M1 here is spec M1. M2 is spec M2 plus the package set. M3 is an express slice of spec M4/M5 (erase only, text UI).

## Rules for every job
- Builds go only through `tools/build-iso` → `tools/docker-build.sh`. `make lint` (`check-container-start`) stays green.
- VMs use only image files under `/var/tmp/seclegion-build/vm/`, made with `qemu-img`. The harness refuses `/dev/*`. Never touch a physical disk or USB stick.
- Official core/extra only, archive-pinned. No new keys, no telemetry, no geo-IP. Passwords go on stdin only, never into logs, serial or evidence. No sudo.
- Each VM test writes `result.json` with `serial_patterns`. Every milestone closes with `tools/verify-evidence --iso out/<iso>`, EXPECT `verify-evidence: OK`.

## M1: branded GRUB menu (spec A2)
**J1a profile and menu.** Files: `iso/profile/profiledef.sh`, `iso/profile/grub/{grub,loopback}.cfg`, `syslinux/` and `efiboot/` (both removed), `tests/iso/test_m1_static.py`.
1. In `profiledef.sh`: `iso_name=seclegion`, label `SECLEGION_YYYYMM`, `bootmodes=('uefi.grub')`, a DEV BUILD marker.
2. Six entries, Install the default, 10 s timeout: Install · Try Live · Rescue · Memory Test · UEFI Firmware Settings · Safe Graphics ▸ Install/Live. Each sets `seclegion.mode=<m> systemd.unit=seclegion-<m>.target`. Keep the serial terminal. Load the theme only if `themes/seclegion/theme.txt` exists.
- G1 six entries, Install is the default, timeout ≥ 10 — CHECK: `python3 -m pytest -q tests/iso/test_m1_static.py` — EXPECT: `passed`
- G2 negative: no Arch branding, no BIOS mode — CHECK: `grep -rniE 'arch ?linux|syslinux' iso/profile/grub iso/profile/profiledef.sh | grep -c .` — EXPECT: `0`

**J1b theme built at build time.** Files: `iso/grub-theme/{theme.txt.in,build-theme.sh}`, `tools/container-build.sh`, and a `theme` mode in `tools/docker-build.sh` (same hard-coded flags).
1. `grub-mkfont` (`ttf-jetbrains-mono`) and the background from `Grub Splash.png` go into `/work/profile/grub/themes/seclegion/`. Nothing generated is committed.
2. The build writes `out/grub-theme.sha256`.
3. Colours come from `desktop/tokens.toml`.
- G3 the theme is reproducible — CHECK: two `tools/docker-build.sh theme` runs with the same `SOURCE_DATE_EPOCH`, then `cmp` the two sha files — EXPECT: exit 0
- G4 negative: no binaries in git — CHECK: `git ls-files iso/grub-theme | grep -cE '\.(pf2|png)$'` — EXPECT: `0`
- G5 the wrapper is still the only container entry point — CHECK: `python3 tools/check-container-start` — EXPECT: exit 0

**J1c VM gate** (after J1a and J1b). Files: stub `seclegion-{install,live,rescue}.target` plus a oneshot that echoes `SECLEGION-MODE=<m>` to ttyS0, `tests/iso/test_m1_menu.py`, `tools/check-branding`.
- G6 the default boots without input after ≥ 10 s and prints `SECLEGION-MODE=install` — CHECK: `python3 -m pytest -q tests/iso/test_m1_menu.py -k default` — EXPECT: `passed`
- G7 each entry gives its own mode (chosen with QMP keys) — CHECK: `-k modes` — EXPECT: `passed`
- G8 Memory Test shows `Memtest86+`; Firmware Settings OCR finds `Device Manager` — CHECK: `-k memtest_fwsetup` — EXPECT: `passed`
- G9 negative: the boot shows no "arch" (serial and OCR) — CHECK: `tools/check-branding out/<iso>` — EXPECT: `branding-ok`. A planted string must make it print `branding-FAIL`.

Evidence: `M1-menu`, `M1-modes`, `M1-memtest`, `M1-fwsetup`, `M1-branding`, `M1-theme-repro` (AUTO); `M1-usb` (HW-MANUAL, owner).

## M2: packages, profile, privilege (spec A3, A8, A13)
**J2a packages.** Files: `iso/packages/{base,live,desktop,cache}.list`, `iso/profile/pacman.conf`, `tools/container-build.sh`.
1. Write the lists from `desktop/roles.toml`. Include grub, memtest86+-efi, cage, greetd, regreet, hyprland, firefox, archlinux-keyring. No openssh.
2. `pacman.conf` points at `archive.archlinux.org/repos/<date>` for core/extra only, `SigLevel = Required DatabaseOptional`. The build writes `out/packages.lock`.
3. An offline cache in `/opt/seclegion/cache` (`pacman -Syw`, `repo-add`) that keeps the Arch `.sig` files. The build also copies `desktop/` and the needed `tools/seclegion-*` to `/usr/share/seclegion/`.
- G10 every package resolves — CHECK: the build log — EXPECT: `packages-lock-ok`
- G11 negative: no foreign repo, no Optional/Never SigLevel for packages, no openssh — CHECK: `python3 -m pytest -q tests/iso/test_m2_static.py -k repos` — EXPECT: `passed` (planted `[foo]` turns it red)
- G12 size — CHECK: `stat -c%s out/*.iso` — EXPECT: ≤ 4.5 GB (report the actual size)

**J2b privilege and targets** (`iso/profile/airootfs/` only).
1. Users:
   - `seclegion-live`: password `!`, NOPASSWD in sudoers, greetd `initial_session`. All wanted only by `seclegion-live.target`.
   - `seclegion-installer`: nologin, no sudo.
   - root: `!*`.
   - Remove the releng autologin, `.automated_script.sh`, `.zlogin` and the sshd drop-in.
2. Targets:
   - install: a cage kiosk with a placeholder that shows an error screen with the log path if killed;
   - rescue: a root shell on tty1;
   - live: no lock, hypridle does DPMS only.
- G13 negative: no empty hash, no `nullok`, NOPASSWD only in the live sudoers file — CHECK: `-k privilege` — EXPECT: `passed`

**J2c VM gate** (after J2a and J2b). Files: `seclegion-selftest` with its unit (JSON on ttyS0, no hashes), `tests/expected-units/{install,live,rescue}.txt`, `tests/iso/test_m2_targets.py`.
- G14 each mode runs exactly its expected units and sockets — CHECK: `python3 -m pytest -q tests/iso/test_m2_targets.py` — EXPECT: `passed`
- G15 negative: install mode has no live user and no autologin, and `sudo -n true` fails — CHECK: `-k install_isolation` — EXPECT: `passed`
- G16 negative: a killed kiosk shows the error screen — CHECK: `-k kiosk_killed` — EXPECT: `passed`

Evidence: `M2-units-{install,live,rescue}`, `M2-privilege`, `M2-kiosk-error`, `M2-lock`.

## M3: Omarchy-fast install and first boot
The jobs share this contract:
- Socket: `/run/seclegion-installd.sock`, peer check with SO_PEERCRED, only uid `seclegion-installer`.
- Plan: `installer/schema/plan-v1.json` with `disk_by_id, confirm_name, user, hostname, tz, kb, luks`. Passwords go in separate stdin frames.

**J3a installd.** Files: `installer/installd/seclegion-installd`, `installer/schema/plan-v1.json`, `tests/install/test_plan.py` (lsblk fixtures).
1. Turn the plan into commands: `sgdisk` (1 GiB ESP plus root) → optional LUKS2 argon2id → btrfs with the A6 subvolumes → two-phase `pacstrap -K` from the cache → allowlisted files plus `/usr/share/seclegion` → UKI presets (A5 hooks) → `bootctl` → `chpasswd` on stdin. `--dry-run` prints the list.
2. Refusals:
   - `/proc/cmdline` lacks `seclegion.mode=install`;
   - the disk holding `/`, the boot medium, a mounted disk, MBR;
   - a wrong `confirm_name`;
   - in DEV builds, a by-id that is not `virtio-*` or `*QEMU*`.
- G17 golden command list for an erase plan — CHECK: `python3 -m pytest -q tests/install/test_plan.py` — EXPECT: `passed`
- G18 negative: refuses on the host — CHECK: `installer/installd/seclegion-installd --dry-run tests/install/fixtures/erase.json; echo $?` — EXPECT: `refused: not install mode` and `2`. Each other refusal has a red case.
- G19 negative: the password is never in the output — CHECK: `-k secret_never_logged` — EXPECT: `passed`

**J3b setup UI and first boot.** Files: `installer/ui/seclegion-setup`, `tools/seclegion-postinstall` with the `seclegion-firstboot.service` user unit (runs once, stamp file), `tests/install/test_setup_pty.py`.
1. Five prompts: disk · keyboard us+ara · timezone (a list, default UTC) · user and password · encrypt (unticked). Then a review screen showing the command list and asking for the disk name. Enter accepts every default.
2. `seclegion-postinstall`, the one command: `seclegion-host apply` for every component, then `seclegion-doctor`. Idempotent.
- G20 the pty flow against `--dry-run` takes at most 5 prompts — CHECK: `python3 -m pytest -q tests/install/test_setup_pty.py` — EXPECT: `passed`
- G21 a second postinstall run is a no-op (fake HOME) — CHECK: `-k idempotent` — EXPECT: `passed`

**J3c end-to-end** (after J3a and J3b). Files: `tests/lib/qemu.py` (`disks=`, `boot=disk`, refuses `/dev`), `tests/install/test_m3_fast.py`, `tests/expected-units/installed.txt`.
- G22 from ISO start to the installed greeter in under 15 min (KVM, `net=none`) — CHECK: `python3 -m pytest -q tests/install/test_m3_fast.py -k fast` — EXPECT: `passed`, `elapsed_s` < 900
- G23 first login runs postinstall and `seclegion-doctor` is OK — CHECK: `-k firstboot` — EXPECT: `passed`
- G24 negative: the target has no live user, NOPASSWD, autologin or archiso hook; `/etc/kernel/cmdline` exists; `pacman -Qkk` is clean — CHECK: `-k target_clean` — EXPECT: `passed`
- G25 negative: the harness refuses a device path — CHECK: `python3 -m pytest -q tests/unit/test_ocr_ovmf_qemu.py -k refuses_dev` — EXPECT: `passed`

Evidence: `M3-fast`, `M3-firstboot`, `M3-target-clean`, `M3-luks` (AUTO); `M3-hw-install` (HW-MANUAL, owner).

## Waves (at most 2 builders; the main session reviews and reruns every gate)
J1a ∥ J1b → J1c → J2a ∥ J2b → J2c → J3a ∥ J3b → J3c. The jobs in each parallel pair touch disjoint files, as listed above; `container-build.sh` belongs to J1b, then to J2a.

## Decisions to review (easy to reverse)
- R13-1: the components ship as files under `/usr/share/seclegion` until the `[seclegion]` repo (O5) exists.
- R13-2: a peer-credential socket instead of D-Bus (A1).
- R13-3: a text UI first; the GTK installer reuses installd.
- R13-4: the cache trusts the Arch packager signatures; its local DB is unsigned.

## Owner actions
1. Approve the wrapper's new `theme` mode.
2. Pick the branding licence (M0-3): these images go into a public ISO.
3. Pick the archive pin date.
4. Confirm room on `/var/tmp` (25 GiB or more) for the builds and VM disks.
5. Flash the USB yourself, naming the exact target device. Install on real hardware only after a verified backup.
6. Install `swtpm`, `tesseract`, `tesseract-data-eng`, and `qemu-img` if it is missing.
