# SecLegion OS — Final Implementation Plan (spec v1)

Version: v1-final · Date: 2026-10-14 · Authors: Sec (Opus 5.5, architect) + Legion (Sonnet 5.5, QA/release), consolidated by the orchestrator.
Status: **Legion SIGN-OFF-WITH-AMENDMENTS (all amendments applied below). Awaiting owner approval to start M0.**
Traceability: [debate.md](debate.md) · [sec-draft-1.md](sec-draft-1.md) · [legion-round-2.md](legion-round-2.md) · [draft-2.md](draft-2.md) (full gate details; this file wins on conflict).

## 1. Context
The previous attempt (git `3864099`) overclaimed (6/15 installer screens, PASS by inspection, cited nonexistent tests), shipped NOPASSWD sudo and empty passwords on the ISO and installed system, leaked archiso initramfs hooks into the target (LUKS unbootable), used an unsigned repo, and made "Install" and "Live" identical. This plan rebuilds SecLegion OS clean-room on branch `clean-room-rebuild` so those failure classes are structurally impossible and every milestone is proven by generated evidence before the next layer starts. 1.0 is the first auditable release; PRD §15 "complete" is the 1.x roadmap.

## 2. Owner decisions (binding)
| # | Decision |
|---|---|
| O1 | Dual boot installs **only into free space**; the user shrinks Windows from Windows (Omarchy/Kali style). Guide screen explains it. |
| O2 | Alongside installs **always create a separate 1 GiB SecLegion ESP** — nothing Windows owns is ever written, resized or moved. Windows is chosen from the firmware boot menu (explained on screen). |
| O3 | **No password to install or to try** from the USB: live user autologin + passwordless sudo on the USB only; installer needs no password. The only password is the new user's, set in setup. Risk accepted: a malicious site in Try-Live could reach the disks. |
| O4 | Screensaver ships only if proven (spike S7) by M7; otherwise 1.0 = branded hyprlock lock screen, screensaver in an update. |
| O5 | Owner maintains the signed `[seclegion]` repo (Python packages + weekly canary). kartik317 dotfiles have **no licence** → all configs rewritten under MIT from the owner's stated preferences. |
| O6 | **VS Code = Microsoft build, Brave preinstalled**, Firefox default (Super+B). ISO is **shared with the community** → neither binary is redistributed: thin `[seclegion]` fetcher packages download the vendor file during install (or first online boot) and verify a pinned sha256. |
| O7 | Claude Code + Antigravity IDE in **1.1** (same fetcher policy). Thunar + Yazi in 1.0. |
| O8 | Vendor update SLA: **Brave and VS Code ≤ 7 days** behind vendor, enforced by the weekly canary. |

## 3. Architecture
**A1 Installer.** Python GTK4/libadwaita UI (user `seclegion-installer`, no shell, no sudo) builds a JSON install plan → D-Bus `org.seclegion.Installer1` → root `seclegion-installd` running plain `sgdisk`, `cryptsetup`, `mkfs.btrfs`, `pacstrap -K`, `arch-chroot`, `bootctl`. Review screen shows the exact command list (PRD §11). installd validates independently: schema; disk re-derived by by-id + serial; refuses the disk holding `/`, the boot medium, mounted partitions, MBR disks, non-contiguous/too-small free space; typed device name; allowlisted username/hostname/locale/timezone; passphrases only via fd, redactor unit-tested; refuses unless booted from SecLegion media (host-damage guard only, not a security boundary). Disk modes: erase selected disk · alongside into free space (guide screen detects BitLocker/Fast Startup/hibernated NTFS by signature and warns that disabling Secure Boot can trigger a BitLocker recovery prompt) · manual partition assignment (+GParted, U10). 15 PRD screens built incrementally on the gated backend.

**A2 ISO boot.** GRUB gfxmenu (`uefi.grub`), UEFI only, theme built at build time from owner assets (`grub-mkfont`, no binaries in git). Entries: **Install SecLegion OS** (default, 10 s) · Try SecLegion Live · Rescue/Recovery · Memory Test · UEFI Firmware Settings · Safe Graphics ▸ Install/Live. Each sets `seclegion.mode=` and its own `systemd.unit=` target; greetd/kiosk units are wanted only by their own target, so Install ≠ Live by construction. Dev builds show "DEV BUILD".

**A3 Privilege (per O3).** ISO-only package `seclegion-live` owns: live user `seclegion-live` (locked password `!`, never empty; no `nullok` anywhere), autologin (greetd `initial_session` wanted only by `seclegion-live.target`), NOPASSWD sudoers, polkit grant for installd. Install kiosk user `seclegion-installer` has no shell/sudo; installd authorizes it via a rule written into `/run/polkit-1/rules.d/` only by the install target. root locked `!*`; no openssh on ISO; Rescue root shell on tty1 only from the Rescue entry. Live has no lock screen (hypridle = DPMS only). Live welcome card states "Live session = full admin, no sign-in". **Target:** root locked, created user in wheel, sudo requires password, no autologin.

**A4 Target population.** Never copy the squashfs. Two-phase `pacstrap` from a manifest via the signed, archive-pinned offline cache: base without kernels → installd writes allowlisted files (fstab, crypttab, hostname, locale, vconsole, users, `/etc/kernel/cmdline`, `/etc/mkinitcpio.d/*.preset`) → kernels + rest. Online: target pacman.conf → mirrors, `pacman -Syu` first, then online tiers (gaming, VS Code/Brave fetch). Offline: online tiers greyed with reason; VS Code/Brave fetched on first online boot via welcome. Offline cache: base, desktop, full linux-firmware, nvidia-open/-lts/utils. Live pacman pinned to the archive date.

**A5 Installed boot.** systemd-boot + UKIs from mkinitcpio `default_uki`/`fallback_uki`; hooks `base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck`; optional LUKS2 argon2id (unticked by default). Every install creates its own 1 GiB SecLegion ESP at `/boot` (O2); NVRAM label "SecLegion OS" (S5). Pacman hook warns if a preset lacks `_uki`.

**A6 Btrfs.** `compress=zstd:1,noatime`; subvolumes `@ @home @snapshots @var_log @pkg @libvirt(+C)`; root via default subvolume (S4; fallback `subvol=@` + manual rollback); snapper + snap-pac (5 daily / 2 weekly); rollback via `seclegion-rescue rollback` (restore, reinstall kernel, regenerate UKIs); zram min(RAM/2, 8G). Snapshots ≠ backups (documented).

**A7 Greeter.** greetd + regreet in the kiosk compositor (cage or sway, S1); us/ara toggle; PAM; exactly one session.

**A8 Repos & signing.** core, extra, multilib (if gaming), `[seclegion]` (`SigLevel = Required DatabaseRequired`, `seclegion-keyring`). Packages: keyring, release, base, branding, desktop, dotfiles, hwdetect, tools, welcome, rescue; ISO-only live, installer, installd; vendored clean-chroot builds ffuf, responder, grimblast; fetchers `seclegion-vscode-fetch`, `seclegion-brave-fetch` (versioned vendor URL + pinned sha256 cross-checked by `tools/vendor-bump` against vendor-published hashes/signatures, U14). Licences in `/usr/share/licenses/<pkg>/`; licence check per M12 (U15). Python in `/usr/lib/seclegion/python` with `python3 -I` launchers. Keys: owner offline primary + token subkey (release); throwaway DEV key (dev builds). Hosting decided by S2. os-release: `seclegion-release` tmpfiles `L+` override + pacman hook (`/usr/lib/os-release` stays Arch's as technical attribution). `docs/third-party.md` records source, version, trust model, update owner and removal for every non-official package (PRD §7.1, §8.2).

**A9 Desktop — one program per role** (`desktop/roles.toml`): swaync · swayosd · hyprpolkitagent · portals hyprland+gtk · waybar · rofi · awww · hypridle · hyprlock (SecLegion Logo layout = secure state) · grimblast+swappy · rofi `seclegion-power` · kitty · zsh+starship · Thunar + Yazi · copyq. Static palette from `tokens.toml` (owner tokens: bg `#050F0E`, surface `#0B1E1C`, accent `#00FF88`, cyan `#00F0FF`, text `#E0FFF4`). GNOME, GDM, dunst dropped. Dotfiles in `/usr/share/seclegion/hypr/*.lua` + skel loader + `user.lua` override (S6); every file SPDX-MIT, `reuse lint` in CI, `docs/PROVENANCE.md`; bundled fonts OFL only. Keybinds: owner's table preserved; Super+B Firefox; Super+Shift+Return VS Code; Antigravity on Super+I (1.1); Brave via rofi only; Super+J togglesplit; Arabic aliases bound by keycode, lint covers both layouts. Optional pre-lock screensaver only if S7 green (O4).

**A10 Hardware (`seclegion-hwdetect`, general support).** TOML rules on PCI class/vendor/device, boot_vga, virt, CPU, DMI → packages, kernel params, env, warnings. NVIDIA: fixture table (build fails if it disagrees with `/usr/share/doc/nvidia/html/supportedchips.html`); Turing+ → nvidia-open(-lts), no DKMS; older → nouveau + vulkan-nouveau with a message; unknown GPU → generic mesa + warning + safe-graphics entry; hybrid → nvidia-prime + switcheroo-control, iGPU first. Always: full linux-firmware, sof-firmware, alsa-ucm-conf, both microcodes; VM guest agents; tap-to-click; HiDPI from EDID. Hardware report on Review/Finished; `seclegion-hwreport` redacted JSON for community GitHub reports, never auto-uploaded.

**A11 Gaming (Omarchy-style, installer checkbox, online).** multilib, steam, steam-devices, gamescope, gamemode(+lib32), mangohud(+lib32), vulkan-icd-loader(+lib32), lib32 Vulkan per GPU, wine-staging, winetricks, lutris, gpu-screen-recorder; user in gamemode group.

**A12 KVM (1.0).** libvirt `default` 192.168.122.0/24 autostart + `seclegion-isolated` (no forward); VM template defaults to isolated; bridging documented, never automatic.

**A13 Build host.** Workdir `/var/tmp/seclegion-build` on ext4; refuse fuseblk/ntfs and <25 GiB free; archive date pinned; `SOURCE_DATE_EPOCH` from commit; `packages.lock`; diffoscope; CI lint/unit; VM matrix local (nested KVM confirmed); weekly canary vs current Arch (M1–M6 gates + vendor SLA).

## 4. Repository layout
```
iso/{profile,grub-theme}  pkgs/<name>/PKGBUILD  installer/{ui,installd,schema}  hw/{rules.d,fixtures,nvidia-table.toml}
desktop/{roles.toml,keybinds.toml,tokens.toml,hypr,waybar,rofi,...}  catalog/  branding/{source,exports,SHA256SUMS}
tools/{build,check-space,gen-testing-md,verify-evidence,vendor-bump,canary}
tests/{lib,unit,iso,install,desktop,expected-units,matrix.toml,mutation}  evidence/<test-id>/<iso-sha256>/
docs/ (PRD §12 set + third-party.md + PROVENANCE.md)  README.md PROJECT_STATUS.md TODO.md TESTING.md(generated) ENGINEERING_LOG.md
```

## 5. Milestones (strict; nothing starts until the previous gate is green with evidence)
VM matrix: GPU std/virtio/virtio-gl/qxl/safe-gfx · disk virtio-blk/NVMe/AHCI · 4/8 GB · OVMF, Secure Boot off. Oracle: `seclegion-selftest.service` JSON on serial; harness waits on signals, OCR (tesseract) only confirms. Evidence classes AUTO / PROBE / HW-MANUAL.

| # | Scope | Automated gate (summary — full lists in draft-2.md §C + amendments) | HW gate |
|---|---|---|---|
| M0 | Tree, PRD §12 files, Makefile, guards, QEMU/OVMF/QMP/serial/OCR harness, evidence generator, CI (shellcheck, ruff, pytest, reuse) | stock releng ISO boots in harness with serial + screendump evidence; hand-edited PASS rejected (mutation) | — |
| S1 | Kiosk compositor runtime us↔ara (cage vs sway) | Arabic glyph OCR after toggle | — |
| M1 | Branded GRUB ISO, 6 entries | default highlighted; ≥10 s autoboot; distinct mode per entry; memtest/fwsetup; zero "arch" strings; reproducible theme | owner USB boot |
| M2 | Targets, users, polkit, kiosk placeholder, minimal Live, Rescue | `seclegion-live` owns all live privileges; no empty hash; kiosk user no sudo; no openssh; exact units + sockets per target; Live hypridle has no lock; killed UI → error screen + log path | — |
| S2 | Repo hosting | pacman install from host in VM | — |
| M3 | Signed repo (DEV key), seclegion-*, fetchers, hwdetect, os-release, canary | tampered pkg/DB rejected; SigLevel gate; hwdetect fixtures (Intel, AMD, AMD+1650, Intel+4060, Pascal, unknown, VM, LTS); NVIDIA table = HTML; os-release survives `filesystem` reinstall; fetcher rejects wrong sha256; `docs/third-party.md` complete | — |
| S3 / S4 | UKI cmdline/osrel; btrfs default-subvol rollback | `.cmdline` = `/etc/kernel/cmdline`, no archiso; rollback boots | — |
| M4 | installd in VM (probe ISO copy) | erase, erase+LUKS, alongside (pre-existing partitions byte-identical, own ESP), manual; target ∩ ISO-only pkgs = ∅; no NOPASSWD/autologin/live user/`nullok`; `pacman -Qkk` clean; sd-encrypt, no archiso; LUKS unlock; online `-Qu` empty; refusals (MBR, small space, bare metal); passphrase never logged; **mutation suite all red** | — |
| S5 | NVRAM label / own ESP boot order | `efibootmgr -v` | partly HW |
| M5 | GUI installer, 15 screens | QMP + OCR every screen, no sleeps; dual-boot fixture unchanged; guide screen detects fixtures; disk-full → error | owner real dual boot after verified backup |
| S6 | Lua `user.lua` override | override applies | — |
| M6 | Installed desktop, roles, greeter, branding, welcome, VS Code/Brave | one notification owner, one polkit agent; keybind lint (both layouts); branding grep (excl. vendor `/opt` payloads); VS Code/Brave Wayland-native, sandbox on; Firefox default (`xdg-settings`) | — |
| S7 | Screensaver input isolation (timeboxed to M7) | synthetic input reaches no client; lock still fires; no inhibitor | — |
| M7 | Owner workflow: keybinds, OSD, hyprlock Logo, idle | idle order; lock shows no notification content | both laptops: XF86 keys, brightness, OSD, lock after suspend (installed system) |
| M8 | Hardware layer, NVIDIA, gaming | vulkaninfo; steam-devices; `gamemoded -t`; NVIDIA matches kernel | 1650 & 4060: nvidia-smi, prime-run, Proton game, controller, audio, recording; ≥1 Intel-only + ≥1 AMD-only community report before claiming general hardware |
| M9 | Tier-1 tools + `seclegion-tools` | safe test per catalog entry; docs generated | — |
| M10 | KVM networks | nested NAT+DNS; isolated no route; virt-manager | USB passthrough |
| M11 | Rescue + rollback drills | snap-pac pairs; rollback boots | — |
| M12 | Release | diffoscope; release key fpr, no DEV key; signed SHA256SUMS; vendor versions/ages + licence check in notes; notes refused unless every HW-MANUAL attested | owner flashes USB (target confirmed) |

Mutation suite (must turn gates red): NOPASSWD/empty shadow/`nullok` on target · `seclegion-live` package, live sudoers, autologin, live user or live polkit rule in target · archiso hook in target · Install==Live · install-mode sudo · `:latest` image · SigLevel Optional · missing `/etc/kernel/cmdline` · Arch os-release symlink · hand-edited PASS · missing HW attestation · wrong vendor sha256.

## 6. Release roadmap
- **1.0 (M0–M12):** ISO + GRUB, installer (erase / alongside / manual, LUKS), hardware layer, gaming option, owner desktop + workflow, Thunar/Yazi, VS Code + Brave (fetched), hyprlock Logo lock (+screensaver if S7 green), Tier-1 tools, `seclegion-tools`, KVM networks, snapshots, rescue.
- **1.1:** podman + distrobox `seclegion-box`, digest-pinned BlackArch/Kali labs, heavy tools in containers (Metasploit, Ghidra, Burp, Caido), apt-get compatibility shim, Claude Code + Antigravity, screensaver if it slipped.
- **1.2:** adaptive matugen theming with contrast clamp, screensaver variants, App Center GUI, SecLegion AI (ollama, consent-only models).
- **No target yet:** Secure Boot, BIOS/legacy, in-installer NTFS resize, snapshot boot entries, GNOME, live wallpapers.

## 7. Verification strategy
Every test writes `evidence/<test-id>/<iso-sha256>/result.json` (commit, ISO sha256, class, env, command, expected, actual, exit code, artifact hashes). `tools/gen-testing-md` generates TESTING.md; CI regenerates and diffs (hand edits fail); `verify-evidence` re-hashes. HW-MANUAL rows need redacted `hwreport.json`, step log and a signed `attestation.toml`. Weekly canary builds against current Arch and checks vendor SLA (O8). A red canary is reported in PROJECT_STATUS.md and blocks release and archive-pin moves.

## 8. Risks (top)
Overclaiming · dual-boot data loss · host NVRAM damage during dev (VM-only installs) · partial upgrades · UKI picking up ISO cmdline · Arch branding leaks · Python/Hyprland Lua churn · vendor staleness + redistribution licence · repo hosting quirks · signing key loss · untested hardware · Try-Live passwordless root (accepted, O3) · screensaver mistaken for security · ISO size (UNVERIFIED) vs 42 GB host · distrobox mistaken for a sandbox (1.1).

## 9. Remaining UNVERIFIED (resolved by spikes/gates)
U1 cage XKB (S1) · U2 GitHub Releases as pacman repo (S2) · U3 UKI preset flow (S3) · U4 snapper rollback (S4) · U5 NVRAM label (S5) · U6 Lua require (S6) · U7 overlay input (S7) · U8 tmpfiles duplicate · U9 polkit `/run` reload · U10 GParted in kiosk · U11 hyprlock logo+clock · U12 supportedchips.html parse · U13 ISO size · U14 vendor hash/signature sources · U15 vendor licence terms · U16 chrome-sandbox perms in VM.

## 10. First execution steps after owner approval (M0)
1. Confirm branch `clean-room-rebuild`, empty tree; start ENGINEERING_LOG.md.
2. Create PRD §12 state files: README.md, PROJECT_STATUS.md, TODO.md, TESTING.md (generated stub), ENGINEERING_LOG.md, and docs/{architecture, decisions, previous-project-audit, installation, recovery, keybindings, current-workflow-migration, package-policy, testing, release-process, security-tools, containers, virtualization, branding, third-party, PROVENANCE}.md.
3. Layout skeleton, `.gitignore`, Makefile (`lint test iso vm evidence`), `tools/check-space`, `tools/gen-testing-md`, result.json schema.
4. Harness in `tests/lib` (QEMU/OVMF fresh VARS, QMP, serial JSON, OCR). Host test packages to install **with owner approval**: swtpm, tesseract, tesseract-data-eng, expect.
5. M0 gate run; evidence recorded; status report to owner.
6. Hand off M1/S1 builds to builder agents in isolated worktrees, reviewed by a fresh reviewer.
