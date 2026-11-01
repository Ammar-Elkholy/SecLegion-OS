# SecLegion OS — Full System Plan (1.0 → 2.0)

Version: v1-full · 2026-10-14 · Sec (Opus 5.5) + Legion (Sonnet 5.5), consolidated by the orchestrator.
Status: **Legion round 6 — spec.md SIGN-OFF; addendum and roadmap SIGN-OFF-WITH-AMENDMENTS (applied below).** Awaiting owner decisions (§6) and approval to start M0.

## How the documents fit
| Document | Role | Precedence |
|---|---|---|
| [spec.md](spec.md) | 1.0 core: installer, boot, privilege, repos, hardware, gaming, tests, owner decisions O1–O8 | binding; its §6 roadmap is replaced by §3 below |
| [addendum-draft.md](addendum-draft.md) | 1.0 UX parity matrix, Omarchy adoption, SecLegion AI, milestones M6+/M7+/M7a/M9a | binding once amended by §2 and §4 below |
| [roadmap-draft.md](roadmap-draft.md) | release train, update/migration policy, 1.1 → 2.0 plans, PRD coverage table | binding once amended by §2 and §4 below |
| this file | reconciliation + amendments + open decisions | wins on conflict |
| [debate.md](debate.md) | full Sec ↔ Legion history | record |

## 1. One-paragraph summary
1.0 is a signed UEFI ISO with a branded boot menu, a custom guided installer (whole disk / free space next to Windows / manual; btrfs + optional LUKS2), data-driven hardware support, Omarchy-style gaming, the owner's Hyprland workflow reproduced key-for-key (bugs fixed), Omarchy's best utilities on free keys, **SecLegion AI** (local-first, consent-only), Tier-1 tools, KVM labs networking, firewall, snapshots, rescue and a safe update command. Every later release (1.1 labs → 1.2 package experience → 1.3 look & feel → 1.4 boot security → 2.0 community) is fully planned and delivered as signed package updates with numbered migrations, snapshots and upgrade-tested gates.

## 2. Reconciliation (single placement for every conflict)
| Topic | Decision |
|---|---|
| `seclegion-update` | **1.0 (M7a)**, one design owned by roadmap §1: preflight (space on `/` and ESP, power, advisory hold) → snapper pre → keyrings → `-Syu` (only `-Sy` site) → `seclegion-migrate` → vendor fetchers → pacnew/orphan report → boot verify (UKI present, cmdline correct, old-kernel UKI cleanup) → reboot notice. `--rollback` (rescue wrapper) in 1.0. |
| `seclegion-migrate` | **1.0** engine with zero migrations + idempotence/immutability/`touches:` mutation tests; M7a proves a half-failed migration leaves the pre-snapshot **restorable** (rollback actually run). |
| Packaging | update/migrate/refresh-config/`seclegion-ctl` ship inside `seclegion-base` (no new 1.0 packages). |
| Channels + `[seclegion-testing]` | **1.0.1** (needs S2 hosting + soak). Testing and stable both signed by owner key; DEV key never signs testing. DBs re-signed per repo on promotion. |
| Update notifications | **1.0.1**, opt-in, default off (PRD §11). |
| UPGRADE gate harness | **1.0.1** (needs a released N-1 ISO). 1.0 proves install → update → migrate no-op. |
| Theme renderer | **1.0**: `seclegion-theme apply` renders every surface from `tokens.toml` (SecLegion Dark only). |
| Adaptive theming, picker, theme install, high contrast, light | **1.3**. |
| Screensaver | O4/S7: 1.0 if S7 green by M7, else 1.1; variants **1.3**. |
| Plymouth splash | **1.3**. |
| Video live wallpapers (mpvpaper, opt-in) | **1.3**. |
| Hibernation, fingerprint, FIDO2, TPM2, Secure Boot | **1.4**. |
| Factory reset | baseline snapshot **1.0**; reset UI **1.2**. |
| Firewall (ufw deny-in) | **1.0 (M7a)** with an explicit libvirt virbr0 NAT/DNS/DHCP rule; M10 gate; 1.1 S11e becomes a regression check. |
| LUKS default | stays **unticked** (spec A5) unless owner decides otherwise (§6 #7). |
| Claude Code, Antigravity, native GTK chat | **1.1**. |
| Coredump → AI (user-initiated) | **1.2**. |
| Continue VS Code extension | **1.0.x** (third-party marketplace fetch; licence/telemetry check first). |
| Hardware-report intake, docs site | **1.0.2**. |
| Neovim, ranger, IoT/dev bundles | **1.2**. |
| BIOS/legacy, in-installer NTFS resize | **won't do** (owner confirmed). GNOME → see O9. |
| Plymouth splash | **1.0** (owner O12) — replaces the 1.3 placement above. |

## 3. Release map
| Release | Contents |
|---|---|
| **1.0** | spec.md M0–M12 + addendum: workflow parity (M7+), Omarchy utilities + update/migrate + firewall + baseline snapshot (M7a), SecLegion AI (M9a), welcome + cheat sheet. After M7, M7a / M9a / M10 run in parallel worktrees; none starts before S8, S9, S-uwsm green. |
| **1.0.1** | channels + testing repo, update notifications (opt-in), UPGRADE harness, any 1.0 cut items |
| **1.0.2** | hardware-report intake, docs site |
| **1.0.x** | Continue extension; cut-order items if 1.0 slips |
| **1.1** Containers & Labs | podman/distrobox `seclegion-box`, isolation ladder (integrated / sealed / disposable VM), Kali + BlackArch labs, heavy tools in containers, installer lab checkboxes, Claude Code + Antigravity, native GTK AI chat, AI RAG over man pages/user docs, mise dev envs, nightly ISO/qcow2, screensaver if it slipped |
| **1.2** Package experience | catalog v2, `seclegion-install`, apt-get compatibility (interactive), yay opt-in, App Center + `seclegion-pkgd`, bundles (dev, IoT/embedded, Discord, backups), factory reset UI, web apps, XCompose, dictation (whisper.cpp, owner approval), AI agent mode with approval UI, coredump → AI, opt-in autologin after LUKS, unattended install, contributor guide |
| **1.3** Look & feel | adaptive matugen theming with identity + contrast clamps, protected semantic colours, high contrast, reduced motion, light theme, theme picker/install (code stripped), screensaver variants, plymouth, video wallpapers |
| **1.4** Boot security & power | Secure Boot wizard (own + Microsoft keys), TPM2 + PIN, FIDO2, fingerprint, hibernation, recovery UKI with snapshot picker, fwupd opt-in |
| **2.0** Community | installer opt-ins (SB, TPM, labs, AUR), multi-maintainer keys, ≥2 mirrors, reproducible-build attestations, held-mirror evaluation, Quickshell + Limine re-evaluation, deprecation removals |

## 4. Legion round-6 amendments (binding)
**Blocking fixes**
- **AI keys:** the key-leak scan covers home, `/var/log`, journal, core dumps, `/tmp`, swap; run after a forced provider error; mutation that logs the key must turn red. Locked keyring must never fall back to plaintext (mutation). **Live ISO hides the API-key UI entirely.**
- **AI egress:** process/cgroup-based (nftables counters per AI unit), with a **positive control** (deliberate outbound packet from the same cgroup must be seen) and a mutation (stray `curl` in runtime start → red). Consented pulls separately checked against an allowlist.
- **Model pulls:** digest recorded in `catalog.toml` verified after download; mismatch refused (mutation); trust model in `docs/third-party.md`; spike **S10** (ollama digest + cloud-disable) before M9a.
- **Unverified numbers** (screensaver CPU, accent hue range): gates become "threshold recorded by spike, then enforced".
**Major fixes**
- New spikes before M6+/M7+: **S-uwsm** (greetd → uwsm session, target ordering, Lua config) and a **licence spike** (Figtree, Graphite, Tela, Bibata; Papirus-Dark/Adwaita fallback).
- M7+ owner visual sign-off gets an automated floor: golden screenshots with per-surface pixel-diff tolerance.
- gnome-keyring: unlocked after normal login; locked-and-prompting on any other path.
- `aichat -e`: non-TTY refused; mutation disabling confirmation → red.
- ufw rule set documented; gate that `pacman -Syu`, DNS, DHCP, browsing, libvirt NAT work with ufw active.
- Per-user ollama: GPU works without group edits; stopping unit leaves no :11434 listener.
- `tools/vendor-bump` automated; canary opens an issue when SLA is breached.
- apt-compat docs state scripts won't see it (owner confirms against PRD §8.8).
- Keycode binds: if S8 fails, keysym + generated alias table; M7+ waits for S8.
- swaync/swayosd gaps: accept documented deltas; media-title fallback = low-urgency notification; no own OSD helper in 1.0.
**1.0 cut order if it slips:** (1) browser chat, Continue, docs RAG → 1.0.x · (2) QR, recorder, OCR, colour picker, emoji → 1.0.x · (3) battery alerts, power profiles, night light, reduced motion → 1.0.x · (4) refresh-config, fwupd entry → 1.0.1 · (5) screensaver, CUDA/ROCm consent paths → 1.1 · (6) security tutor + "Ask AI" → 1.1. **Never cut:** model manager, key storage, privacy labels, egress gate, ufw default, update-with-snapshot, baseline snapshot, A1–A5. If those can't hold, AI as a whole moves to 1.0.1.

## 5. Spike order before/inside 1.0
S1 kiosk XKB · S2 repo hosting · S3 UKI · S4 snapper rollback · S5 NVRAM · S6 Lua user override · **S-uwsm** · **licence spike** · S7 screensaver · **S8** keycode binds · **S9** swaync margin / swayosd message · **S10** ollama digest + cloud-disable.

## 6. Open owner decisions (ordered by what they block)
| # | Decision | Blocks | Proposed default |
|---|---|---|---|
| 1 | New key set (S+M menu, S+/ cheat sheet, S+, notifications, S+Ctrl+N/E/C/I/P, Alt+Print, S+Ctrl+Print, S+Alt+Print, S+A AI, S+X tools) | M7+ | approve |
| 2 | kitty tiles (helpers float) vs always floating | M7+ | tile |
| 3 | swaync differences from dunst (left-click = action, no right-click close-all, no 5-popup cap) | M7+ | accept |
| 4 | Idle: lock 300 s, screen off 330 s, suspend 900 s on battery only | M7+ | approve |
| 5 | Themes/icons/cursor: build Graphite/Tela/Bibata from source vs repo alternatives | M6+ | build if licences pass, else Papirus/Adwaita |
| 6 | Firewall deny inbound by default | M7a | yes |
| 7 | LUKS encryption ticked by default for whole-disk installs | M4/M5 | no (unticked) |
| 8 | AI name | M9a | SecLegion AI |
| 9 | AI GPU: Vulkan automatic; CUDA/ROCm downloads by consent | M9a | approve |
| 10 | Coding assistant Continue (local model) | 1.0.x | approve |
| 11 | Dictation in 1.0 | M9a | no (1.2) |
| 12 | Community links on welcome screen | M6+ | project GitHub + hardware-report guide |
| 13 | Curated AI model shortlist (~10) | M9a | owner picks from shortlist |
| 14 | Offsec lab base image | 1.1 | Kali, Arch fallback |
| 15 | Claude Code/Antigravity installer checkbox (unticked) | 1.1 | yes |
| 16 | Offer "Full BlackArch" with size warning | 1.1 | yes |
| 17 | apt-get compatibility on by default, interactive only | 1.2 | yes, with off switch |
| 18 | yay AUR helper opt-in | 1.2 | yes |
| 19 | Default screensaver / teal clamp / light theme / mpvpaper / rotation / plymouth | 1.3 | Logo / strict / preview / opt-in / off / yes |
| 20 | Secure Boot keys / TPM PIN / FIDO2 hardware / hibernation / fwupd | 1.4 | own+Microsoft / PCR7+PIN / owner says / opt-in / opt-in |
| 21 | Co-maintainers, held Arch mirror | 2.0 | only with hosting |
| 22 | Won't do: BIOS, in-installer Windows resize, GNOME | — | confirm |

## 7. Owner decisions recorded 2026-10-14 (round 6 answers) — binding
- **Confirmed defaults:** §6 #1–#4 (new keys, idle, swaync deltas), kitty **tiles** (#2), LUKS **unticked** (#7), ufw deny-in (#6), AI name **SecLegion AI** + Vulkan default / CUDA-ROCm by consent (#8–#9), themes built from source if licences pass (#5), welcome links GitHub + hardware guide (#12), won't-do BIOS and in-installer Windows resize.
- **O9 GNOME session (reverses "GNOME dropped"):** Hyprland stays the default; GNOME is a second session chosen at the login screen via a **session icon in the bottom-right corner**. Each session runs only its own roles (GNOME: gnome-shell notifications, polkit agent, portals; Hyprland: A9 roles) — per-session role table and one-daemon-per-role gates for **both** sessions. Login screen: GDM's session gear sits bottom-right and handles GNOME's lock/user switching natively, so **PROPOSAL: switch the display manager from greetd+regreet to a SecLegion-branded GDM** when GNOME ships (spike S-gnome compares GDM vs regreet session picker + GNOME lock under greetd). Placement: **1.0**, installer option "GNOME session" ticked by default, plus milestone **M6g** (session isolation: no Hyprland role starts in GNOME and vice versa; both sessions listed; Hyprland default; portals per session via `XDG_CURRENT_DESKTOP`). Owner may move it to 1.1 if 1.0 slips (cut-order position 5).
- **O10 USB boots to setup:** the USB never boots straight into a Hyprland or GNOME desktop; the default entry boots the SecLegion setup (installer kiosk), like Omarchy/Kali. "Try SecLegion Live" remains a non-default menu entry (PRD §4.1).
- **O11 Shortcut and AI pickers (Omarchy-style):** Super+/ cheat sheet and Super+M menu stay; **Super+A opens an AI picker** (rofi list, like Omarchy's agent picker) to choose: SecLegion AI local chat, configured cloud providers, VS Code assistant, and from 1.1 Claude Code / Antigravity. Only installed/configured entries appear.
- **O12 Boot splash in 1.0:** custom Plymouth theme `seclegion-bits` — on power-on, binary bits fall and slide in from the side with a glitch effect and assemble into the SecLegion logo (Omarchy idea, own style). Frames pre-rendered at build time from the owner's logo by a script in `branding/` (no binaries in git); also used for the LUKS passphrase prompt. Requires the `plymouth` mkinitcpio hook → added to spike **S3** (UKI) and gates: splash shown on boot in VM (screendump OCR/pixel check), LUKS prompt works through the splash, safe-graphics entry disables it, boot time regression ≤ 1 s (threshold recorded by spike). Same theme optionally on the ISO boot.
