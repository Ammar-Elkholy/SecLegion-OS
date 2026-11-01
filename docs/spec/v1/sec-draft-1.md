# SecLegion OS — Implementation Plan, Draft 1 (Sec, Opus 5.5)

Status: DRAFT 1 — under review by Legion (Round 2). Not owner-approved.

Verified on host: mkarchiso supports `uefi.grub` and `uefi.systemd-boot`; in official repos: cage, greetd, greetd-regreet, systemd-ukify, sbctl, matugen, awww, swayosd, swaync, hyprpolkitagent, hyprlock, hypridle, hyprshot, gtk4-layer-shell, qemu-guest-agent, diffoscope, steam-devices, gamescope, lib32-vulkan-*, lib32-nvidia-utils, vulkan-nouveau, linux-firmware-{intel,realtek,mediatek,atheros,broadcom}, sof-firmware, {amd,intel}-ucode. NOT in repos: calamares, ckbcomp, wlogout, grimblast, mpvpaper, ffuf, responder, open-webui, aurutils. archinstall 4.5 depends on python-pyparted. `filesystem` owns `/usr/lib/os-release`; nothing owns `/etc/os-release`. distrobox-create mounts `/run/host`, has `--unshare-*` options. Nested KVM on (`kvm_amd nested=1`). GRUB 2.16 Argon2 for LUKS2: UNVERIFIED.

## A. Architecture decisions

**A1. Installer — custom GTK4/libadwaita frontend + own root backend `seclegion-installd`.**
Rejected: Calamares (C++/Qt rebuild churn, ckbcomp AUR, ~4 custom C++ modules needed anyway, GUI path not headless-testable); archinstall lib (API churn, no NTFS resize, hides commands).
Chosen: unprivileged Python GTK4 wizard (all 15 PRD screens) builds a declarative **install plan (JSON)**; Review screen shows the exact plan and commands (PRD §11). Plan sent over D-Bus to `seclegion-installd`, which executes with `sgdisk`, `cryptsetup`, `mkfs.btrfs`, `btrfs subvolume`, `pacstrap -K`, `arch-chroot`, `bootctl` (~1.5k auditable lines).
Disk modes: (1) erase explicitly selected disk; (2) alongside — **only into unallocated space**, user shrinks Windows from Windows; never resize NTFS/BitLocker; Windows ESP only gets our bootloader binary; (3) manual — assign existing partitions to mount points (+ "Open GParted", availability UNVERIFIED).
Cost: no in-installer resize → owner decision D2.

**A2. ISO bootloader — GRUB (`uefi.grub`), UEFI only.** gfxmenu theme (dark bg, logo, fonts, teal highlight), `fwsetup`, chainload memtest86+-efi. Drop `bios.syslinux` until tested.

| Entry | cmdline | Result |
|---|---|---|
| Install SecLegion OS (default, timeout=10) | `seclegion.mode=install systemd.unit=seclegion-install.target` | kiosk compositor, installer only |
| Try SecLegion Live | `seclegion.mode=live systemd.unit=seclegion-live.target` | greetd autologin → Hyprland live desktop |
| Rescue / Recovery | `systemd.unit=seclegion-rescue.target` | `seclegion-rescue` TUI on tty1 |
| Memory Test | chainloader memtest.efi | memtest86+ |
| UEFI Firmware Settings | `fwsetup` | firmware |
| Advanced Safe Graphics ▸ Install/Live | `+ seclegion.safegfx=1 module_blacklist=nvidia,nouveau,amdgpu,radeon,i915,xe` | simpledrm/efifb, `WLR_RENDERER=pixman` |

`greetd.service` and kiosk unit are WantedBy their own target only → Install and Live cannot coincide.

**A3. Live privilege model.** User `seclegion-live`; root locked `!*`. Install: `seclegion-installer-kiosk.service` (User=seclegion-live, PAMName=login, TTYPath=/dev/tty1) runs compositor+UI unprivileged. `seclegion-installd.service` root, D-Bus activated `org.seclegion.Installer1`, policy `/usr/share/dbus-1/system.d/org.seclegion.Installer1.conf`. Polkit actions `org.seclegion.installer.probe` (allow_active=yes) and `org.seclegion.installer.execute` (auth_admin). ISO-only package `seclegion-live` ships `/etc/polkit-1/rules.d/49-seclegion-live.rules` → YES only for `execute`, subject seclegion-live, local+active. Live mode: wheel + per-boot random password (`seclegion-live-password.service`, shown on welcome card, `/run/seclegion/live-password` 0600). Rescue = root tty1 only when chosen. Spike: cage runtime XKB switching UNVERIFIED → fallback sway kiosk.

**A4. Target populated only by `pacstrap -K` from manifest** using signed offline cache on ISO (`/var/lib/seclegion/offline-repo`), then allowlisted writes (fstab, crypttab, hostname, locale, vconsole, users/shadow, `/etc/kernel/cmdline`, loader entries). Never copy squashfs; ISO-only packages never in target manifest.

**A5. Installed boot — systemd-boot + UKIs (systemd-ukify)**, hooks `base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck`, LUKS2 argon2id. Erase layout: ESP 1 GiB at /boot + optional LUKS2→btrfs. Alongside: existing ESP at /efi gets only systemd-bootx64.efi (~150 KB; refuse if <5 MB free) + new 1 GiB **XBOOTLDR** at /boot for UKIs. Windows auto-detected on same ESP; other-disk Windows via firmware menu (documented). NVRAM label via `efibootmgr --label` if bootctl can't (UNVERIFIED).

**A6. Btrfs** `compress=zstd:1,noatime`; subvols `@ @home @snapshots(/.snapshots) @var_log @pkg @libvirt(+C)`; root via btrfs default subvolume (no subvol= in cmdline) for `snapper rollback` (spike). snapper + snap-pac; timeline 5 daily / 2 weekly; no snapshot boot entries in 1.0; rollback via `seclegion-rescue rollback` (reinstalls snapshot's kernel + `mkinitcpio -P`). zram `min(ram/2,8G)` zstd; no disk swap unless hibernation.

**A7. Display manager — greetd + regreet (in cage)**, GTK4 CSS branding. Owner uses GDM → D3.

**A8. Repos & signing.** Official core/extra (+multilib if gaming approved) + one `[seclegion]` repo `SigLevel = Required DatabaseRequired` via `seclegion-keyring`. Contents: `seclegion-{keyring,release,base,branding,desktop,hwdetect,tools,welcome,rescue,labs}` + ISO-only `seclegion-{live,installer,installd}` + owner-approved vendored PKGBUILDs in `pkgs/` (ffuf, responder, grimblast) built with `makechrootpkg`. No ABI-coupled compiled Qt/GTK packages. Owner holds key (offline primary, token subkey). Release: ISO + SHA256SUMS + .sig. Dotfiles: `/usr/share/seclegion/hypr/*.lua`; `/etc/skel/.config/hypr/hyprland.lua` loads SecLegion modules then `user.lua` (Lua require path UNVERIFIED, M6 spike); `seclegion-dotfiles reset|diff`.

**A9. One program per role (`desktop/roles.toml`).** Notifications swaync; OSD swayosd (ae-osd style); polkit hyprpolkitagent; portals hyprland+gtk; bar waybar; launcher rofi 2.0; wallpaper awww; idle/lock hypridle/hyprlock; screenshots grimblast+swappy; power menu rofi `seclegion-power` (wlogout AUR). Static palette from `tokens.toml` in 1.0; matugen + WCAG clamp in 1.2. Screensaver 1.0: `seclegion-screensaver` (GTK4 + gtk4-layer-shell) Logo mode via hypridle before hyprlock; doesn't block suspend. GNOME dropped.

**A10. `seclegion-hwdetect`** — Python lib+CLI; rules `/usr/share/seclegion/hw/rules.d/*.toml` match PCI class/vendor/device, boot_vga, systemd-detect-virt, CPU vendor/DMI → packages, kernel params, env, warnings. NVIDIA: open-kernel eligibility from `supported-gpus.json` (path UNVERIFIED; fallback fixture-tested ID table); Turing+ → nvidia-open (+lib32 if gaming); Maxwell/Pascal/Volta → nouveau + vulkan-nouveau with explicit message. Hybrid → nvidia-prime + switcheroo-control, `AQ_DRM_DEVICES` iGPU first. Firmware: full `linux-firmware` + sof-firmware + alsa-ucm-conf + both ucodes. VMs: guest agents by virt type. Touchpad tap-to-click; HiDPI scale from EDID. Safe-graphics sd-boot entry. Hardware report on Review/Finished. `seclegion-hwreport` redacted JSON for community GitHub issue template; never auto-uploads.

**A11. Gaming first-class installer option** — multilib, steam, steam-devices, gamescope, gamemode(+lib32), mangohud(+lib32), vulkan-icd-loader(+lib32), lib32 Vulkan per A10, wine-staging, winetricks, lutris; gamemode group. Needs multilib approval (D5).

**A12. Containers/labs (1.1)** — rootless podman + distrobox via `seclegion-box` (`--unshare-devsys --unshare-ipc`, home `~/.local/share/seclegion/boxes/<name>`); `/run/host` mount documented, never claimed as isolation; images pinned by digest in `/usr/share/seclegion/labs/images.toml`; Metasploit/Burp/Ghidra/Caido in containers.

**A13. KVM** — libvirt `default` 192.168.122.0/24 autostart + `seclegion-isolated` 10.66.0.0/24 no forward; VM template defaults to isolated.

**A14. apt-get compat (1.1)** — `seclegion-apt-compat` `/usr/bin/apt-get`, curated `apt-map.toml`, shows pacman command, confirms, exit 100 on unknown. One catalog `catalog/*.toml` generates menu, `docs/security-tools.md`, smoke tests.

**A15. AI (1.2)** — ollama `-cuda`/`-rocm` per A10, disabled, 127.0.0.1; `seclegion-ai models` consent-only downloads.

**A16. Build host** — workdir `/var/tmp/seclegion-build` (ext4); refuse fuseblk/ntfs. Pin Arch Linux Archive date; `SOURCE_DATE_EPOCH` from commit; `build/lock/packages.lock`; diffoscope. CI: GitHub lint/unit (shellcheck, ruff, pytest, namcap); VM matrix local/self-hosted.

## B. Repository layout
```
iso/ pkgs/ installer/{ui,installd} hw/{rules.d,fixtures} desktop/ catalog/ branding/{source,exports}
tools/ tests/{lib,unit,iso,install,desktop,matrix.toml} evidence/ docs/
README.md PROJECT_STATUS.md TODO.md TESTING.md(generated) ENGINEERING_LOG.md
```

## C. Milestones (strict; no start until previous gate green with evidence)
Matrix: GPU `-vga std`, `virtio-vga`, `virtio-vga-gl`, `qxl-vga`, safe-gfx; disk virtio-blk, NVMe, AHCI; RAM 4/8 GB; OVMF SB off.
Console oracle: `seclegion-selftest.service` (ConditionPathExists=/dev/ttyS0) emits one JSON line on serial, no input; deeper checks offline (unsquashfs / qemu-nbd) or probes injected into the test copy of the disk only.

| M | Scope | Automated gate | HW gate |
|---|---|---|---|
| M0 | Tree, docs, Makefile, fuseblk guard, QEMU/OVMF/QMP/serial/OCR harness, evidence generator | harness boots stock releng ISO & captures serial+screenshot; generator rejects hand-edited PASS; lint green | — |
| M1 | Branded GRUB ISO, 6 entries | OCR default entry highlighted; autoboot ≥10 s; distinct selftest mode per entry; memtest/fwsetup OCR; no "arch linux" in boot files/os-release | owner USB boot |
| M2 | Live user + security baseline; install kiosk placeholder; minimal Live Hyprland; Rescue TUI | no NOPASSWD, no empty shadow, root `!*`, polkit rule exactly one action; 0 failed units across matrix; killed UI → error screen w/ log path | — |
| M3 | Signed repo pipeline + hwdetect | clean-chroot builds; tampered pkg rejected; DB sig verified; fixtures Intel, AMD, AMD+NVIDIA(1650), Intel+NVIDIA(4060), Pascal→nouveau, VM | — |
| M4 | installd headless | loop devices: erase, erase+LUKS, alongside (fake Windows), manual; leak check; boots to selftest ok; LUKS sendkey; wrong pass rejected | — |
| M5 | GUI installer 15 screens | QMP sendkey + OCR per screen across matrix; dual-boot fixture hashes unchanged, XBOOTLDR created, both entries in `bootctl list`; disk-full injection | owner real dual-boot after verified backup |
| M6 | Installed desktop, roles, greeter, branding, welcome | one `org.freedesktop.Notifications` owner; one polkit agent; no alternatives installed; keybinds.toml lint; OCR greeter/wallpaper/fastfetch | — |
| M7 | Owner workflow migration (keybinds, Arabic, OSD, idle/lock/screensaver) | keybind lint, OCR notification, idle timer | both laptops: XF86 keys, brightness, OSD, lock after suspend |
| M8 | HW layer on target, NVIDIA, gaming | vulkaninfo on virgl/lavapipe, `gamemoded -t`, steam present, hwreport | 1650 & 4060: nvidia-smi, prime-run vkcube, Proton game, controller; ≥1 Intel-only + ≥1 AMD-only community report before claiming general HW |
| M9 | Tier-1 tools + seclegion-tools CLI | per-catalog safe test command | — |
| M10 | KVM networks | nested guest NAT+DNS; isolated no route; virt-manager OCR | USB passthrough |
| M11 | Rescue & rollback drills | snap-pac pre/post; rollback after kernel update boots | — |
| M12 | Release | reproducibility diff; signed SHA256SUMS; generated notes | owner flashes USB (target confirmed) |

Releases: 1.0 = M0–M12; 1.1 = containers, labs, heavy tools, apt-compat; 1.2 = adaptive theming, screensaver variants, App Center, AI; later = Secure Boot, BIOS.

## D. Owner decision batches (PROPOSED DEFAULT)
- **D1 (blocks M0–M1):** signing key generation [owner, offline primary + token subkey]; `[seclegion]` repo on installed systems [yes]; release host [GitHub Releases]; UEFI-only [yes]; boot art [Grub Splash.png]; ISO name [`seclegion-YYYY.MM.DD-x86_64.iso`, label `SECLEGION_YYYYMM`]; licence [MIT]; evidence screenshots in git [hashes only].
- **D2 (installer):** custom installer [yes]; no resize, alongside into free space only [yes]; systemd-boot no snapshot entries [yes]; LUKS2 argon2id unticked default [yes]; subvol/snapper [A6]; offline base install [yes]; live per-boot random password [yes]; installer UI languages [English + Arabic]; Arabic keyboard [`ara`]; kernel [`linux`, LTS optional].
- **D3 (desktop conflicts):** Super+B [Firefox; Brave on Super+Shift+B]; Super+Shift+Return [VS Code; Antigravity on Super+I]; notifications [swaync, remove dunst]; OSD [swayosd]; polkit [hyprpolkitagent]; DM [greetd+regreet]; GTK theme [Graphite-Mono recoloured]; cursor [Bibata-Modern-Ice 24]; Super+J [togglesplit]; Super+L focus-right [no]; power menu [rofi]; live wallpapers/mpvpaper [defer]; idle [screensaver 240s, lock 300s, DPMS 600s, suspend-on-battery 900s]; screensaver default [Logo]; kartik317 dotfiles [check licence; rewrite + credit]; GNOME [drop].
- **D4 (packages):** AUR [build ffuf/responder/grimblast ourselves; yay optional]; Brave [defer until trust model documented]; VS Code [`code` OSS]; Antigravity/Claude Code/claude-desktop [optional catalog entries via vendor installer]; Metasploit/Ghidra [containers]; firewall [ufw]; Docker [optional, off]; apt-get shim [1.1].
- **D5 (gaming/AI/community):** multilib [yes]; Steam/Lutris [installer option, unticked]; gaming packages [online]; AI name ["SecLegion AI"]; curated model list; community links [none until provided]; 1.0/1.1/1.2 split [yes].

## E. Top risks
1. Overclaiming → generated TESTING.md, CI diff, HW-MANUAL needs hwreport + operator log.
2. Dual-boot data loss → no resize, append-only Windows ESP, serial shown, typed disk name, checksum fixture, real HW only after verified backup.
3. Kernel/module mismatch after rollback → rescue reinstalls kernel + regenerates UKI.
4. Arch branding leaks → `seclegion-release` writes `/etc/os-release` via pacman hook; grep gates; sd-boot title from UKI `.osrel`.
5. Hyprland Lua API churn → archive pin + config smoke test.
6. New partitioning code → small scope, loop-device tests, command preview.
7. ISO size / 44 GB host ext4 → offline base only, workdir cleanup, space check.
8. Key loss/compromise → offline primary, revocation cert, documented procedure.
9. Distrobox mistaken for sandbox → documented.
10. Untested hardware → data-driven layer, safe-gfx entry, community reports.

## F. Answers to Legion
1. Privilege boundary per A3; M2 static gate + same checks on target. Agree.
2. pacstrap from manifest; offline gate: `pacman --root /mnt -Qkk` clean outside allowlist; unowned files in /etc,/usr ⊆ allowlist; `lsinitcpio` UKI has sd-encrypt, no archiso; no seclegion-live user/rule/pkg; no autologin; journald not volatile.
3. systemd-boot + UKIs; argon2id native; 100 MB ESP → binary only + XBOOTLDR, refuse <5 MB; no snapshot entries in 1.0. Agree.
4. Per A8; build ffuf/responder/grimblast; VS Code = `code`; Brave/Antigravity/Claude Code off ISO pending approval; owner maintains; `tools/check-updates`.
5. selftest JSON on serial + offline mounts + probes injected into test disk copy only; nested KVM confirmed.
6. Strict order per C, plus M0 for harness.
7. roles.toml drives manifest lint + runtime D-Bus/pgrep probes; evidence `result.json` (commit, ISO sha256, command, exit, artifact hashes) → `gen-testing-md` → CI diff.
8. Per C; owner told PRD §15 "complete" = 1.x roadmap, 1.0 = first auditable release.

**Disagreements with Legion:** GRUB gfxmenu on ISO (text systemd-boot fails §4.1 branding); no archinstall lib (hides commands §11 wants shown); gaming stays in 1.0 (owner requirement); lock + Logo screensaver stay in 1.0 (daily driver).

## G. Open questions for Legion
1. Alongside-into-free-space only (no resize) — acceptable beginner UX?
2. Is QMP sendkey + OCR GUI testing too flaky; do injected probes on the test disk copy count as "testing what we ship"?
3. Move snapper default-subvolume rollback spike to M4?
4. Full `linux-firmware` vs detected split packages?
5. cage vs sway kiosk for runtime Arabic layout switching?
6. Per-boot random Live password vs well-known (kali/kali style)?
