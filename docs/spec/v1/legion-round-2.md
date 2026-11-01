# Round 2 — Legion (Sonnet 5.5) → Sec: critique of Draft 1

Verified on host: `linux-firmware` is a meta over 12 splits (~410 MiB installed); `cage` 0.3.1 depends on wlroots0.20; `/etc/os-release` is an unowned symlink to `/usr/lib/os-release`; `systemd-ukify` ships no pacman hook / kernel-install plugin; hyprland 0.56.2-4, gparted 42.2, sway 1.12, tesseract-data-eng, swtpm in repos; nested KVM on; Python 3.14.8.

## 1. Verdicts
| Section | Verdict | Change / reason |
|---|---|---|
| A1 installer | ACCEPT-WITH-CHANGE | installd validates plan itself: re-derives target disk, refuses root/live-medium disk, requires typed device name, schema check. Passphrases via fd/stdin, never argv/logs; redactor tested. Usernames/hostnames/locales whitelisted before arch-chroot. Build screens incrementally on top of gated M4 backend. |
| A2 GRUB | ACCEPT-WITH-CHANGE | Concede gfxmenu. Gate: theme builds reproducibly (fonts via `grub-mkfont` at build, no blobs); OCR against real gfxmenu render; zero "Arch" strings in grub.cfg. |
| A3 privilege | ACCEPT-WITH-CHANGE | See B1. Mask `getty@tty1` for kiosk (releng ships tty1 drop-in). Gate: sshd not enabled, exact listening-socket list, Rescue only root tty. |
| A4 pacstrap | ACCEPT-WITH-CHANGE | See B2. |
| A5 systemd-boot+UKI | ACCEPT-WITH-CHANGE | Pick one UKI generator — mkinitcpio presets `default_uki` (ukify has no hook). Spike before M4: kernel update regenerates UKI + `.osrel` title. ESP <5 MB → offer own 1 GiB ESP + NVRAM entry instead of refusing; UI says Windows then via firmware menu. |
| A6 btrfs | ACCEPT-WITH-CHANGE | Default-subvolume rollback spike before M4. |
| A7 greetd+regreet | ACCEPT | Gate: `us,ara` toggle, PAM password, exactly one session entry. |
| A8 repo/signing | ACCEPT-WITH-CHANGE | See B3, B4. |
| A9 roles | ACCEPT | |
| A10 hwdetect | ACCEPT-WITH-CHANGE | `supported-gpus.json` UNVERIFIED; nvidia-utils ships `/usr/share/doc/nvidia/html/supportedchips.html`. Fixture ID table is source of truth; build fails if Turing+ boundary disagrees with packaged HTML. Add generic fallback rule (safe-gfx + warning) for unknown devices. |
| A11 gaming | ACCEPT-WITH-CHANGE | 1.0 checkbox. Acceptance: pkgset installs, vulkaninfo lists matching device, steam-devices udev rules exist, `gamemoded -t` passes; rest HW-attested. See B2. |
| A12–A15 | ACCEPT | 1.1 / 1.2 as planned. |
| A16 build | ACCEPT-WITH-CHANGE | Free-space check before build (44 GB on root FS). Archive-pinned offline cache, see B2. |
| C milestones | ACCEPT-WITH-CHANGE | Snapper + UKI spikes into M3/M4. |
| D | ACCEPT-WITH-CHANGE | See §5. |

## 2. Sec's four disagreements
1. **GRUB gfxmenu on ISO — concede.** Condition: ISO bootloader and installed bootloader are separate decisions.
2. **No archinstall lib — concede.** Explicit JSON command plan is more reviewable; loop-device matrix in M4 is the real gate.
3. **Gaming in 1.0 — concede** (owner requirement), with A11 acceptance limits and B2 fixed.
4. **Lock + Logo screensaver in 1.0 — hold narrowly.** hyprlock accepted. `seclegion-screensaver` must be a display-only layer that cannot receive input; hypridle starts hyprlock at the same moment or earlier. Gate: synthetic key press after screensaver reaches no window; killing screensaver leaves lock up. If not green by M7 → screensaver slips to 1.1; 1.0 ships hyprlock alone.

## 3. Answers to Sec's questions
1. **No-resize alongside:** acceptable for 1.0, not good. Needs a first-class guide screen detecting BitLocker, Fast Startup, hibernated NTFS (read signatures only, never mount rw); no-free-space → exact instructions + docs link. Escalate (5.1).
2. **QMP+OCR:** not flaky if timing is removed — each screen announces itself on serial/journal; sendkeys wait on signal; OCR only confirms; `tesseract-data-eng`, fixed font/resolution. Injected probes count only if shipped image hash unchanged and probe is a separate unit on a copy with diff recorded; report labels shipped-image-only vs probe checks.
3. **Snapper spike:** move before M4. Criteria: loop install → snapshot → kernel update → `snapper rollback` → reboot → `@snapshots` mount survives. Fallback: `subvol=@` cmdline + manual rollback script. Decide before M4.
4. **Firmware:** full `linux-firmware` (~410 MiB) for 1.0; "any laptop" beats disk saving.
5. **cage vs sway:** decide by spike; note cage tracks wlroots0.20. If cage can't switch XKB at runtime → sway kiosk for installer, cage for regreet.
6. **Live password:** per-boot random, shown on welcome card, plus "set my own password"; Install-mode user needs none (polkit, B1).

## 4. Blocking defects
- **B1 Polkit rule reopens NOPASSWD in Live mode.** Unauthenticated `execute` for `seclegion-live` lets any process in Try-Live (browser, tools) wipe disks. Fix: rule applies only when `/run/seclegion/mode` = `install`; Live requires `auth_admin`. Gates: Live-boot D-Bus `execute` → not authorized; Install-boot succeeds only for kiosk session; `allow_any`/`allow_inactive` = no.
- **B2 Partial-upgrade hazard.** Archive-dated offline base + current-mirror online gaming/nvidia packages = partial upgrade (PRD §11). Fix: when online, full `pacman -Syu` in target before any online set; offline → online tiers unavailable with clear message (or ship gaming in offline cache, ~2 GB). Gates: `pacman -Qu` empty when online; nvidia `vermagic`/`dkms status` = installed kernel.
- **B3 Python ABI coupling.** Pure-Python seclegion packages in `/usr/lib/python3.14/site-packages` break on Arch Python bump. Fix: private path `/usr/lib/seclegion/…` with pinned launcher, or rolling rebuild policy + **compat canary** (scheduled rebuild + M1–M6 gates against current Arch).
- **B4 Signing flow under-specified; release gate can't fail.** Dev builds use throwaway "DEV" key stamped in `seclegion-release`; M12 compares ISO keyring fingerprint to pinned `release-key.fpr`. Gate: no `SigLevel` weaker than Required for `[seclegion]`, no TrustAll, in ISO and target. Repo hosting URL layout UNVERIFIED (GitHub Releases ≠ pacman mirror) → spike before M3.
- **B5 `/etc/os-release`.** `filesystem` reinstall can restore symlink. Gate: after `pacman -S filesystem`, still SecLegion; grep "arch linux" over /etc, os-release, UKI `.osrel`, issue, motd, fastfetch empty.
- **B6 "Zero failed units" too weak.** Add exact expected-enabled-units list per target + each active.
- **B7 UNVERIFIED → spikes before dependents:** snapper rollback + UKI hook (before M4); cage XKB (before M2 kiosk); Lua require path (before M6/M7); efibootmgr NVRAM label (before M5); repo URL layout (before M3); GRUB Argon2 dropped (GRUB ISO-only); supported-gpus.json → packaged HTML / fixture table.
- **B8 HW-only gates must not be silent.** M12 refuses release notes unless every HW-MANUAL row has hwreport + operator attestation; test removes one attestation → M12 fails.

## 5. Escalate to owner
1. Alongside install without resize (+ guide screen, BitLocker/Fast Startup/hibernation detection) — accept for beginners?
2. Shared Windows ESP <5 MB: refuse-and-explain (Sec) vs own ESP + firmware menu (Legion).
3. Live-mode install asks for the random password (Legion: non-negotiable).
4. Screensaver: in 1.0 only if input-isolation gate green by M7, else 1.1.
5. Rolling-repo maintenance cost: canary job + update policy, or a config-only `[seclegion]` repo.
6. Brave deferred; VS Code = `code` OSS — owner confirms departure from current apps.
