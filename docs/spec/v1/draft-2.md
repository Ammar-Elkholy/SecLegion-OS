# SecLegion OS Implementation Plan — Draft 2 (Sec + Legion)

Status: Draft 2 (Sec round 3). Replaces Draft 1. Pending Legion round-4 sign-off and owner approval. Nothing is implemented before owner approval (PRD §13).
**Owner decisions of 2026-10-14 (§H below) override this draft where they conflict.**

## Round 3 response — Sec → Legion (summary)
New host facts: polkit 127 reads `/run/polkit-1/rules.d` (runtime reload UNVERIFIED); `/etc/mkinitcpio.d/linux.preset` is unowned, created from `hook.preset` only if missing; missing `/etc/kernel/cmdline` → mkinitcpio embeds `/proc/cmdline` (ISO cmdline inside chroot!); mkinitcpio UKI `.osrel` from `/etc/os-release`; `/etc/os-release` symlink comes from systemd `etc.conf` tmpfiles `L` (earliest filename wins); `/etc/issue` = `\S{PRETTY_NAME}`; `nvidia-open-lts` in extra; nvidia-utils 315 MiB; ext-session-lock-v1 draws only lock surfaces while locked.
- B1 ACCEPTED-MODIFIED: grant rule written to `/run/polkit-1/rules.d/` only by a unit in `seclegion-install.target`, matching kiosk user `seclegion-installer`; installd re-checks mode. *(Superseded by owner decision H3.)*
- B2 ACCEPTED-MODIFIED: online → `pacman -Syu` in target first; offline → online tiers greyed; nvidia-open/-lts/utils in offline cache (~325 MiB); gaming online-only; Live pacman pinned to archive date.
- B3 ACCEPTED: Python in `/usr/lib/seclegion/python`, `python3 -I` launchers, official deps only; weekly canary.
- B4 ACCEPTED: DEV key, `SECLEGION_CHANNEL=dev`, "DEV BUILD" mark; M12 fingerprint + SigLevel gate; S2 hosting.
- B5 ACCEPTED-MODIFIED: `seclegion-release` ships `/usr/lib/seclegion/os-release` + `/usr/lib/tmpfiles.d/00-seclegion-os-release.conf` (`L+`) + pacman hook; `/usr/lib/os-release` stays Arch's (technical attribution); grep gate over resolved os-release, UKI `.osrel`, `/etc/issue`, motd, fastfetch, loader entries.
- B6, B7, B8 ACCEPTED. **B9 (new):** `bootctl install` on host loop devices writes host NVRAM → installd refuses unless booted from SecLegion media; M4 runs in VMs.
- Screensaver: a display-only layer over hyprlock is impossible (only lock surfaces drawn while locked). → Logo drawn by hyprlock's own layout (secure); optional pre-lock overlay grabs input, exits on first input, documented as visual only; default no gap; slips to 1.1 if S7 red by M7.

## Context
Previous attempt (git 3864099): docs overclaimed (6 of 15 installer screens; PASS by inspection), NOPASSWD sudo + empty passwords, archiso initramfs leaked into installed systems (LUKS unbootable), unsigned repo, Install == Live. Owner wants a clean-room auditable Arch-based distro, general laptop/desktop hardware support, Omarchy-style gaming-ready.
**1.0 outcome:** signed UEFI ISO; branded GRUB menu with genuinely different Install/Live/Rescue states; custom guided installer (erase / alongside-free-space / manual; btrfs; optional LUKS2); data-driven hardware layer; owner's Hyprland workflow; Tier-1 tools; KVM networks; snapshots + rescue; gaming option. TESTING.md generated from evidence. 1.0 is the first auditable release, not PRD §15 "complete".

## A. Architecture decisions
**A1 Installer.** Python GTK4/libadwaita UI (user `seclegion-installer`) → JSON plan → D-Bus `org.seclegion.Installer1` → root `seclegion-installd` (`sgdisk`, `cryptsetup`, `mkfs.btrfs`, `pacstrap -K`, `arch-chroot`, `bootctl`). installd validates independently: schema; target disk re-derived by by-id + serial; refuses disk holding `/`, boot medium, mounted partitions; typed device name; username/hostname/locale/timezone allowlists before arch-chroot; passphrases only via fd (redactor unit-tested); refuses unless booted from SecLegion media (B9). Review screen shows exact command list. Disk modes: (1) erase selected disk; (2) alongside into unallocated space only, never resize; guide screen reads signatures (BitLocker, Fast Startup, hibernated NTFS) and explains shrinking from Windows; (3) manual partition assignment + GParted button (U10).

**A2 ISO boot.** GRUB gfxmenu (`uefi.grub`), UEFI-only, no syslinux; theme built from owner assets at build time (`grub-mkfont`, no binaries in git). Entries: Install (default, 10 s), Try Live, Rescue, Memory Test, UEFI Settings, Safe Graphics ▸ Install/Live; each sets `seclegion.mode=` + its own `systemd.unit=` target; greetd and kiosk each wanted only by their own target. Dev builds show "DEV BUILD". ISO bootloader and installed bootloader are separate decisions.

**A3 Privilege.** *(See H3 — owner decision replaces the password model.)* root locked `!*`; no openssh on ISO; releng autologin drop-in deleted; `getty@tty1` masked in install target; polkit actions `org.seclegion.installer.probe` / `.execute` with `allow_any`/`allow_inactive` = no; Rescue root shell on tty1 only from Rescue entry; kiosk compositor (cage or sway) chosen by S1.

**A4 Target population.** Two-phase pacstrap from manifest using signed archive-pinned offline cache: (1) base without kernels; (2) installd writes allowlisted files (fstab, crypttab, hostname, locale, vconsole, users, `/etc/kernel/cmdline`, `/etc/mkinitcpio.d/*.preset`); (3) kernels + rest. Online: switch target pacman.conf to mirrors, `pacman -Syu` first, then online sets. Offline: online sets disabled with reason. Offline cache: base, desktop, full linux-firmware, nvidia-open/-lts/utils. ISO-only packages never in target. Live pacman pinned to archive date.

**A5 Installed boot.** systemd-boot + UKIs from mkinitcpio `default_uki`/`fallback_uki` → `/boot/EFI/Linux/seclegion-<kernel>[-fallback].efi`. Hooks `base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck`; LUKS2 argon2id. Erase: 1 GiB ESP at `/boot`. Alongside: Windows ESP at `/efi` gets only the systemd-boot binary (≥5 MB free) + new 1 GiB XBOOTLDR at `/boot`; <5 MB → own SecLegion ESP (see H2). Nothing else ever written to Windows ESP (incl. `EFI/BOOT/BOOTX64.EFI`). NVRAM label per S5. Pacman hook warns if any preset lacks `_uki`.

**A6 Btrfs.** `compress=zstd:1,noatime`; `@ @home @snapshots @var_log @pkg @libvirt(+C)`; root via default subvolume (S4; fallback `subvol=@` + manual rollback script); snapper + snap-pac, 5 daily / 2 weekly; no snapshot boot entries; `seclegion-rescue rollback` restores snapshot, reinstalls kernel, regenerates UKIs; zram min(RAM/2, 8G); no disk swap unless hibernation.

**A7 Greeter.** greetd + regreet in kiosk compositor; us/ara toggle; PAM password; exactly one session entry.

**A8 Repos & signing.** core, extra, multilib (if gaming), `[seclegion]` `SigLevel = Required DatabaseRequired` via `seclegion-keyring`. Packages: keyring, release, base, branding, desktop, hwdetect, tools, welcome, rescue, dotfiles; ISO-only live, installer, installd; vendored PKGBUILDs via `makechrootpkg` (ffuf, responder, grimblast; + Brave, VS Code per H6). Python in `/usr/lib/seclegion/python`. Keys: release = owner offline primary + token subkey; dev = throwaway DEV key. Hosting by S2. os-release per B5. Dotfiles `/usr/share/seclegion/hypr/*.lua` + skel loader + `user.lua` (S6); `seclegion-dotfiles reset|diff`.

**A9 One program per role** (`desktop/roles.toml`): notifications swaync; OSD swayosd; polkit hyprpolkitagent; portals hyprland+gtk; bar waybar; launcher rofi; wallpaper awww; idle hypridle; lock hyprlock; screenshots grimblast+swappy; power menu rofi `seclegion-power`. Static palette from `tokens.toml`; GNOME dropped. Lock = hyprlock with SecLegion Logo layout (secure state). Optional pre-lock `seclegion-screensaver` only if S7 green.

**A10 `seclegion-hwdetect`.** TOML rules on PCI class/vendor/device, boot_vga, virt, CPU, DMI. NVIDIA eligibility from fixture table; build fails if it disagrees with `/usr/share/doc/nvidia/html/supportedchips.html`; Turing+ → nvidia-open (or -lts), no DKMS; older → nouveau + vulkan-nouveau + message. Unknown GPU → generic mesa + warning + safe-gfx entry. Hybrid → nvidia-prime + switcheroo-control, `AQ_DRM_DEVICES` iGPU first. Always: full linux-firmware, sof-firmware, alsa-ucm-conf, both microcodes. VM guest agents, tap-to-click, HiDPI from EDID. `seclegion-hwreport` redacted JSON, never auto-uploads.

**A11 Gaming** (installer checkbox, online): multilib, steam, steam-devices, gamescope, gamemode(+lib32), mangohud(+lib32), vulkan-icd-loader(+lib32), lib32 Vulkan per GPU, wine-staging, winetricks, lutris, gpu-screen-recorder; gamemode group.

**A12–A15** unchanged: containers/labs 1.1; KVM networks 1.0; apt-compat 1.1; AI 1.2.

**A16 Build host.** `/var/tmp/seclegion-build` on ext4; refuse fuseblk/ntfs and <25 GiB free (42 GB today); archive date pinned; `SOURCE_DATE_EPOCH` from commit; `packages.lock`; diffoscope; CI lint/unit; VM matrix local; weekly canary vs current Arch.

## B. Repository layout
```
iso/{profile,grub-theme} pkgs/<name>/PKGBUILD installer/{ui,installd,schema} hw/{rules.d,fixtures,nvidia-table.toml}
desktop/{roles.toml,keybinds.toml,tokens.toml,hypr,waybar,rofi,...} catalog/ branding/{source,exports,SHA256SUMS}
tools/{build,check-space,gen-testing-md,verify-evidence,canary} tests/{lib,unit,iso,install,desktop,expected-units/*.txt,matrix.toml,mutation}
evidence/<test-id>/<iso-sha256>/  docs/ (PRD §12 set)  README.md PROJECT_STATUS.md TODO.md TESTING.md(generated) ENGINEERING_LOG.md
```

## C. Milestones
Rule: nothing starts until the previous gate is green with evidence. Spikes timeboxed, end with a decision in `docs/decisions.md` + fallback.
VM matrix: GPU std/virtio/virtio-gl/qxl/safe-gfx; disk virtio-blk/NVMe/AHCI; 4/8 GB; OVMF SB off. Console oracle: `seclegion-selftest.service` JSON lines on serial; harness waits on signals, OCR confirms. Evidence classes: AUTO, PROBE (diff recorded), HW-MANUAL.

| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| M0 | Tree, PRD §12 files, Makefile, space/fuseblk guard, QEMU+OVMF+QMP+serial+OCR harness, evidence generator, CI lint | harness boots stock releng ISO, captures serial+screendump; generator rejects hand-edited PASS (mutation); shellcheck/ruff/pytest green | — |
| S1 | Kiosk XKB: cage vs sway runtime us↔ara; regreet same | OCR shows Arabic glyph after toggle | — |
| M1 | Branded GRUB ISO, 6 entries | default highlighted; autoboot ≥10 s; distinct selftest mode per entry; memtest/fwsetup; zero "arch" in grub.cfg + rendered menu; theme rebuild byte-identical | owner USB boot |
| M2 | Install/Live/Rescue targets, users, polkit, kiosk placeholder, minimal Live Hyprland, Rescue TUI | static security set (per H3); expected units per target exact + active; listening sockets exact; killed UI → error screen with log path | — |
| S2 | Repo hosting (GitHub Releases vs static host; redirects, real `.db`, `:`/`+` mangling) | pacman `-Sy` + install from host in VM | — |
| M3 | Signed repo pipeline (DEV key), seclegion-* pkgs, hwdetect, os-release mechanism, Python private path, canary | clean-chroot builds; tampered pkg/DB rejected; SigLevel gate; hwdetect fixtures (Intel, AMD, AMD+1650, Intel+4060, Pascal→nouveau, unknown→generic, VM, LTS→nvidia-open-lts); NVIDIA table = HTML; `pacman -S filesystem systemd` keeps SecLegion os-release (U8); canary green once | — |
| S3 | UKI: presets before kernel; kernel update regenerates both; `.osrel`/`.cmdline` correct | `ukify inspect`: `.cmdline` = `/etc/kernel/cmdline`, no `archiso`/`seclegion.mode`; `.osrel` SecLegion | — |
| S4 | Btrfs default-subvolume rollback | install → snapshot → kernel update → rollback → reboot → `@snapshots` mounted, boots | — |
| M4 | installd on probe-injected ISO copy in VM | erase, erase+LUKS, alongside (fake Windows ESP hash unchanged), small ESP → own ESP, manual; `pacman -Qkk` clean outside allowlist; no live leftovers; `lsinitcpio` sd-encrypt no archiso; journald persistent; LUKS sendkey + wrong pass rejected; refuses on bare metal; online `pacman -Qu` empty; offline greys tiers; validator fuzzing; passphrase never in logs | — |
| S5 | NVRAM label + own-ESP boot order | `efibootmgr -v` label; fresh-VARS boot | partly HW |
| M5 | GUI installer, 15 screens, incremental | QMP keys + OCR every screen across matrix, no sleeps; dual-boot hashes unchanged; XBOOTLDR; both entries in `bootctl list`; guide screen detects fixture BitLocker/Fast Startup/hibernation; disk-full → error screen | owner real dual boot after verified backup |
| S6 | Hyprland Lua require + `user.lua` | override applies; `hyprctl` reload | — |
| M6 | Installed desktop, roles, greeter, branding, welcome | one Notifications owner, one polkit agent; no alternative-role packages; keybinds lint; OCR greeter/wallpaper/fastfetch; branding grep clean | — |
| S7 | Screensaver input/lock interplay (timeboxed to M7) | overlay: synthetic input reaches zero clients; killing overlay still locks on time; no idle inhibitor; suspend not blocked | — |
| M7 | Owner workflow: keybinds + Arabic aliases, OSD, hyprlock Logo, idle | keybind lint; notification OCR; idle timers in order; lock OCR shows no notification content | both laptops: XF86 keys, brightness, OSD, lock after suspend/resume |
| M8 | HW layer on target, NVIDIA, gaming | vulkaninfo (virgl/lavapipe); steam-devices udev, `gamemoded -t`, `pacman -Qu` empty; NVIDIA pkg matches kernel; hwreport schema | 1650 & 4060: nvidia-smi, `prime-run vkcube`, Proton game, controller, audio, gpu-screen-recorder; ≥1 Intel-only + ≥1 AMD-only community report before "general hardware" claim |
| M9 | Tier-1 tools + `seclegion-tools` | safe test command per catalog entry; docs generated | — |
| M10 | KVM default + isolated | nested guest NAT+DNS; isolated no route; virt-manager OCR | USB passthrough |
| M11 | Rescue + rollback drills | snap-pac pre/post; rollback after kernel update boots; UKIs regenerated | — |
| M12 | Release | diffoscope; keyring fpr = `release-key.fpr`, no DEV key; signed SHA256SUMS; notes only if every HW-MANUAL attested (mutation); canary green | owner flashes USB, target confirmed |

## E. Risks
Overclaiming; dual-boot data loss; host damage in dev (B9); partial upgrades; kernel/UKI mismatch; UKI picking up ISO cmdline; Arch branding leaks; Python/Lua API churn; owner maintenance capacity; repo hosting quirks; key loss; untested hardware; screensaver mistaken for security; ISO size (3–4 GB UNVERIFIED) vs 42 GB host; distrobox mistaken for sandbox (1.1). Mitigations as in A/C/G.

## F. Release roadmap
- **1.0 = M0–M12.**
- **1.1:** podman + distrobox `seclegion-box`, digest-pinned BlackArch/Kali labs, heavy tools in containers, apt-get shim, Antigravity (if approved), pre-lock screensaver if it slipped.
- **1.2:** matugen adaptive theming + WCAG clamp, screensaver variants, App Center, SecLegion AI.
- **No target:** Secure Boot, BIOS, in-installer NTFS resize, snapshot boot entries, GNOME, live wallpapers.

## G. Verification strategy
`evidence/<test-id>/<iso-sha256>/result.json` (test_id, milestone, class, commit, iso_sha256, probe_diff_sha256, env, command, expected, actual, exit_code, started/ended, artifacts[{path,sha256}], harness_version). `tools/gen-testing-md` generates TESTING.md; CI diffs (hand edits fail); `verify-evidence` re-hashes. Weekly canary runs M1–M6 gates against current Arch. HW-MANUAL rows need redacted `hwreport.json`, step log, signed `attestation.toml`; M12 refuses otherwise (mutation test). Mutation suite re-introduces: NOPASSWD on target, empty shadow on target, archiso hook in target, Install==Live, `:latest` image, SigLevel Optional, missing `/etc/kernel/cmdline`, Arch os-release symlink.

## UNVERIFIED
U1 cage XKB (S1); U2 GitHub Releases as pacman repo (S2); U3 preset-before-kernel UKI + fallback size (S3); U4 snapper default-subvol rollback (S4); U5 NVRAM label / second ESP (S5); U6 Lua require (S6); U7 overlay input swallowing (S7); U8 tmpfiles duplicate path; U9 polkit `/run` reload; U10 GParted under kiosk; U11 hyprlock logo+clock; U12 supportedchips.html parse; U13 ISO size.

## H. Owner decisions (2026-10-14) — override the draft
- **H1 Dual boot:** install alongside only into free space; the user shrinks Windows from Windows themselves (like Omarchy/Kali). Guide screen stays.
- **H2 Small Windows ESP:** owner delegated → pick the most stable option that cannot damage Windows. **Decision:** if the Windows ESP has <5 MB free (or any doubt), create a separate 1 GiB SecLegion ESP with its own NVRAM entry; never write to, resize or move anything Windows owns. Windows then reached via the firmware boot menu (explained on screen).
- **H3 Passwords on the USB:** no password to install or to try the system. Live user autologins without password; `sudo` in Try-Live is passwordless **on the USB only** (Ubuntu/Kali Live norm); installer needs no password in Install or Live mode. The only password is the one set for the new user in the setup's User Account screen. Replaces the per-boot random password and Legion's B1 "Live asks password" fix. Accepted risk (owner informed): a malicious site opened in Try-Live could in theory reach the disks. Gates kept/added: mutation tests prove no NOPASSWD / no empty password / no autologin / no live user ever reaches the installed system; installd validation and typed-disk-name confirmation remain.
- **H4 Screensaver:** if S7 isn't green by M7, 1.0 ships the branded hyprlock lock screen only; the logo screensaver arrives in an update.
- **H5 Repo upkeep:** owner accepts maintaining the signed `[seclegion]` repo (Python packages + canary). The kartik317 GitHub dotfiles the owner's desktop is based on are broken and have **no LICENSE** (not redistributable) → all SecLegion configs are rewritten from scratch under the project's MIT licence, using only the owner's own preferences (keybinds, colours, layout) as requirements.
- **H6 Apps:** VS Code = **Microsoft build** (owner's current `visual-studio-code-bin`), packaged in the signed `[seclegion]` repo from Microsoft's official download with pinned checksum (Microsoft licence). **Brave** packaged the same way from Brave's official release, preinstalled in 1.0. Firefox stays default (Super+B).
