# SecLegion OS: parts, requirements, status (2026-10-17)

Estimates are agent-hours of builder work (one Sonnet builder, Opus planning, main-session review),
from this project's measured pace (25-60 min per job, 3-6 jobs per milestone). They are rough. Two
builders run at once, so wall-clock is about half the agent-hours, plus pauses for usage limits and
the owner's hands-on tests.

## A. Live host (owner's laptop): desktop layer

| Part | Requirement | Status |
|---|---|---|
| Host tool `seclegion-host` | apply/confirm/rollback, backups, 120 s dead-man, baseline-0 | DONE (live) |
| Keys | SecLegion binds via `seclegion-keys.lua`, lint (us+ara), no collisions | DONE (live, 60 binds) |
| Workspaces | empty-ws, move-new, 11-20, clickable waybar pills | DONE (live) |
| Resize | Super+Alt+R mode, edge grab, presets Super+Ctrl+1/2/3 | DONE (live) |
| Window rules | helper windows float and centre | DONE (live) |
| Top bar (waybar) | single Wi-Fi icon, techy network module, stats (CPU/temp/RAM/GPU/disk/load), Bluetooth, power profile, DND bell, right-click to Settings, under 1 % CPU | DONE (live, 0.7 % CPU) |
| Notifications / OSD | swaync on theme tokens, one replacing popup per key | DONE (live) |
| Lock / idle / lid | lock component, autolock choice (default / 15 / 30 / 60 / never), lid ignore | DONE (live) |
| Theme engine | default + matugen auto, GTK3/4, Qt, KDE, yazi, border, swaync, waybar | DONE (live) |
| Theme manager | Settings rows, picker on Super+Shift+T, auto theme per wallpaper | DONE (live; auto stays off until `seclegion-theme auto on`) |
| File manager | Thunar default, status bars, Dolphin, yazi plugin | DONE (live) |
| Settings app | 17 pages with real rows; root rows preview-only plus `seclegion-root-apply` | DONE (live) |
| Doctor | read-only `seclegion-doctor` | DONE (live) |

Desktop leftovers, about 8-10 h:
- waybar clock does not read `clock.toml`
- the Hyprland "launched without start-hyprland" boot message is not reproduced (needs the owner's journal line)
- the Settings window still writes on the UI thread
- the baseline-0 live-host gap
- the lint / REUSE cleanup of older files

## B. 1.0 ISO milestones (spec.md + addendum)

| Milestone | Requirement (short) | Status | Remaining h |
|---|---|---|---|
| M0 | Tree, Makefile, guards, QEMU/OCR harness, evidence, CI | DONE | 0 |
| M1 | Branded GRUB ISO with 6 entries, memtest/fwsetup, zero "arch", reproducible theme | DONE (VM-verified, evidence; owner USB boot pending) | 0 |
| M2 | Targets, users, privilege, kiosk placeholder, Live, Rescue, pinned repos, offline cache | IN PROGRESS: code merged; VM gates still failing (offline cache sync, sshd mask) | 3-5 |
| M3 | Signed repo (DEV key), `seclegion-*` packages, fetchers, hwdetect, os-release, canary | NOT STARTED | 8-10 |
| M4 | installd: erase, erase+LUKS, alongside Windows, manual; no NOPASSWD on target | NOT STARTED (planned r13 J3a) | 10-14 |
| M5 | Installer UI (text first, then 15-screen GUI), fast install under 15 min, `seclegion-postinstall` | NOT STARTED (planned r13 J3b/J3c) | 15-20 |
| M6 / M6+ | Installed desktop: roles, greeter (regreet css done), branding, welcome, uwsm, VS Code/Brave; ship the host components above as packages | PARTLY (host pieces exist, not yet on the ISO) | 8-10 |
| M7 / M7+ | Owner workflow on the ISO: full key matrix tested in us and ara, OSD, lock, idle | PARTLY (works on host; ISO-side QMP tests remain) | 6-8 |
| M7a | Omarchy-style utilities: menu, cheat sheet, capture, night light, emoji, power profiles, battery, stay-awake, reduced motion, `seclegion-update` + migrations, firewall, baseline snapshot | PARTLY (power profile, battery, autolock, theme picker done) | 10-12 |
| M8 | Hardware layer: NVIDIA (1650, 4060), prime-run, gaming (Steam, gamemode) | NOT STARTED; needs both laptops | 8-10 + owner tests |
| M9 | Tier-1 security tools + `seclegion-tools` catalog, safe test per entry | NOT STARTED | 10-15 |
| M9a | SecLegion AI: ollama (Vulkan), pick a model from a curated ~10, off by default, no egress | NOT STARTED (owner moved it to 1.0.1; can move it back) | 10-12 |
| M10 / M10+ | KVM networks (NAT, isolated), ufw interplay | NOT STARTED | 4-6 |
| M11 | Rescue + snapshot rollback drills | NOT STARTED | 5-6 |
| M12 / M12+ | Release: diffoscope, release key, signed SHA256SUMS, licence check, notes | NOT STARTED; owner key and attestations | 6-8 |

**1.0 remaining: about 105-135 agent-hours (about 55-70 wall-clock hours with 2 builders), plus the desktop leftovers and the owner's hardware tests.**

## C. After 1.0 (roadmap, not estimated)

- **1.0.1:** update channels, testing repo, opt-in update notices, upgrade harness.
- **1.0.2:** hardware-report intake, docs site.
- **1.1 Containers & Labs:** `seclegion-box`, Kali / BlackArch labs.
- **1.2 Package experience:** App Center, `seclegion-install`.
- **1.3 Look & feel:** light theme, high contrast. Much of this is already done on the host.
- **1.4 Boot security:** Secure Boot wizard, TPM2, FIDO2, hibernation.
- **2.0 Community:** multi-maintainer keys, mirrors, attestations.

## D. Owner-only actions

- Boot the ISO from USB, and do the real install after a backup, naming the exact device.
- Test hardware on both laptops (M8).
- Create the release signing key, which never goes in git or the ISO.
- Send the boot-message journal line: `journalctl -b -g 'without|start-hyprland'`.
- `sudo rm -rf` any root-owned build leftovers the agents report.
