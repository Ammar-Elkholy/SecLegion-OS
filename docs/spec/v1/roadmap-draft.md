# SecLegion OS Roadmap 1.1 → 2.0 — Sec draft (round 5)

Author: Sec (Opus 5.5). Status: draft, under Legion review. Binding inputs: spec.md (O1–O8), draft-2.md, PRD, inputs/omarchy-features.md.
Verified on host: in repos — sbctl 0.18, mokutil, systemd-ukify 262, tpm2-tools, libfido2, pam-u2f, fprintd, matugen 4.2, limine, snapper, grub-btrfs, distrobox 1.8.2.5, podman 6.1.4, passt, skopeo, cosign, mkdocs-material, plymouth, gtk4-layer-shell, pacman-contrib, metasploit, ghidra, zaproxy, discord, ranger, neovim, arduino-cli, esptool, openocd, platformio-core, binwalk, restic, borg, pika-backup, vorta, fwupd, ufw, firewalld, archlinux-appstream-data, pyalpm, swtpm, hyprlock (fingerprint block). NOT in repos: shim-signed, mpvpaper, limine-snapper-sync, yay, paru, burpsuite, caido, claude-code, antigravity. `sd-encrypt` already includes TPM2/FIDO2 token libs. **distrobox `create` is always `--privileged`, root-in-container, host network/ipc/pid unless unshared, mounts host `/` at `/run/host` (writable where the user can write), `/dev`, `/sys`, `/tmp`, `$HOME`, `/run/user/$UID`** — its README says isolation is not a goal.

## 1. Release train & patch policy
**Versions:** patch `1.0.x` (fixes, security, vendor/digest bumps, hwdetect rules, fix-only migrations; ISO "media refresh" only for boot/installer fixes, offline cache >90 days, or keyring expiring <60 days) · feature `1.x` (new ISO) · major `2.0` (removals, layout/bootloader changes; tested upgrade or documented reinstall). Version in `seclegion-release` (`VERSION_ID`, `/usr/lib/seclegion/release.toml`); `seclegion-version` prints product/packages/migration levels/channel/vendor ages. Arch stays rolling.
**Channels:** dev (DEV key, never on user systems) · testing `[seclegion-testing]` opt-in via `seclegion-channel` · stable `[seclegion]`. Promotion copies the same signed files (sha256 checked). Stable needs ≥7 days in testing, canary green, upgrade gate green, owner laptops updated; security/boot fixes may use 48 h soak. Omarchy's "Arch held one month behind" not adopted in 1.x (needs own snapshot mirror; delays security fixes) — re-evaluated in 2.0.
**`seclegion-update`** (the one recommended path; welcome, waybar, App Center call it): preflight (≥3 GiB `/`, ≥150 MiB ESP, AC or >30% battery, signed `advisory.json` has no hold) → snapper pre snapshot → `pacman -Sy --needed archlinux-keyring seclegion-keyring && pacman -Su` (only place `-Sy` appears) → vendor fetchers re-verify → `seclegion-migrate --system` (user migrations queued) → `.pacnew` report, restart non-critical changed services or report "reboot required" → optional `seclegion-box update --all` (ticked only) → post snapshot + boot verification (`bootctl list`, `ukify inspect` cmdline, `sbctl verify` once SB enrolled); failure → red notification, update not marked complete. Plain `pacman -Syu` still works: `90-seclegion-migrate.hook` runs system migrations; `seclegion-migrate.service` retries at boot if pending.
**`seclegion-migrate`:** `/usr/share/seclegion/migrations/{system,user}/NNNN-slug.{sh,py}`, numbered bands per release (1.0.x 0001–0999, 1.1 1100–1199…), header `id/release/description/touches/snapshot`. Contract enforced by CI + mutation: idempotent (run twice → zero diff), immutable once released (sha256 recorded), no pacman/network/prompts, writes only `touches:` paths (overlay diff), state in `/var/lib/seclegion/migrations/state.jsonl` (in `@`, rolls back with root) and `~/.local/state/seclegion/migrations/` with backups; never edits user-modified files (writes `.seclegion-new` + notifies); system batch wrapped in snapper pre/post, first failure stops batch and notifies with rescue hint; user migrations run in `seclegion-session` before Hyprland starts. `--list --dry-run --verify`.
**Proposal (Q1):** ship `seclegion-update`, `seclegion-migrate` (zero migrations), `seclegion-channel`, `[seclegion-testing]` already in 1.0 (M11/M12); fallback 1.0.1.
**Deprecation:** announce N, warn N, remove N+2 or 2.0. **Rollback:** `seclegion-update --rollback` (rescue to last pre-snapshot); repo is roll-forward only; signed advisory "hold". **Support:** latest stable only; upgrade gate proves N-1→N and N-2→N; ISO supported 6 months; SecLegion security fixes ≤72 h; vendor ≤7 days (O8).
**Gate reuse:** spec §7 evidence model + new classes **UPGRADE** (install N-1/N-2 ISO, update via testing, rerun all gates, `migrate --verify`) and **SOAK** (≥7 days testing). Canary adds lab image digest pulls, vendor SLA, monthly full lab creation. **R-final** per release: diffoscope, release key, signed sums, licence check, HW attestations, UPGRADE + SOAK, mutation suite red.

## 2. Releases (by dependency and risk) — each carries a slot "items deferred from the UX/Omarchy/AI addendum"
### 1.0.x patches (community track)
1.0.1 update plumbing (if not in 1.0) + **opt-in** update notifications (`seclegion-update-notify.timer`, default off; `checkupdates` + signed advisory; no identifiers sent). 1.0.2 hardware-report intake (GitHub issue form, CI validates `hwreport.json` schema + redaction, labels by GPU class; `--submit-guide` opens the form, never uploads) and docs site (mkdocs-material, no analytics — CI grep). Gates: UPGRADE 1.0→1.0.x; zero network connections at boot with notifications off; redaction test mutation-proven.

### 1.1 — Containers & Labs (PRD §8.3–8.5, §9.1, O7)
- **Packages:** `seclegion-containers` (podman, distrobox, passt, netavark, aardvark-dns, crun, skopeo), `seclegion-box` (Python), `seclegion-labs` (recipes `/usr/share/seclegion/boxes/*.toml`, `images.lock.toml`, menus); migration 1101 ensures subuid/subgid.
- **Isolation ladder** (published in `docs/containers.md` and `seclegion-box info`):
  | Class | How | Network | Filesystem | Devices/GPU | Host services | Use |
  |---|---|---|---|---|---|---|
  | Integrated box (default) | distrobox with separate box home + `~/SecLegion/Shared/<n>` | host netns (rootless: no raw sockets/monitor mode, S11a) | host `/` at `/run/host`, writable where you can write | `/dev`, `/dev/dri`, `--nvidia` if detected | session D-Bus, PipeWire, Wayland, X11, keyring/agent sockets | convenience — **equivalent to your user account, not a sandbox** |
  | Sealed box | plain `podman run`: `--network none`/pasta, keep-id userns, only `/work`, no `/run/user`, no-new-privileges; Wayland socket only with `--wayland` | none / private NAT | `/work` | none unless asked | none | untrusted inputs |
  | Disposable VM | `seclegion-vm disposable <template>`: qcow2 overlay on `seclegion-isolated`, deleted at shutdown | isolated | none | explicit USB | none | **malware & exploitation (PRD §8.5)** |
- **`seclegion-box`** `create [--recipe offsec|kali-lab|blackarch-lab|arch|file] [--class integrated|sealed] [--net host|private|none] [--gpu] [--device]`, `enter`, `list [--json]`, `update [--rebase]`, `remove [--keep-home]`, `export` (recipe allowlist only), `info`, `doctor`. Labels `org.seclegion.recipe/digest`; disk preflight (size × 1.5); **never auto-start** (no quadlets, restart, socket, linger — gate).
- **Images:** `images.lock.toml` `ref@sha256` for kali-rolling, blackarch, archlinux (namespaces UNVERIFIED); `tools/image-bump` via skopeo, human approval; cosign where vendors sign (UNVERIFIED); `:latest` fails mutation test.
- **Recipes:** `seclegion-offsec` (Kali base: metasploit-framework, burpsuite, ghidra, caido — Caido in Kali UNVERIFIED → in-box fetcher; Java under XWayland; msfdb without init S11d) · `kali-lab` (`kali-tools-<category>` choices, Full with size warning) · `blackarch-lab` (`blackarch-<group>` or full; BlackArch repo **only inside the box**, SigLevel Required).
- **Menus:** XDG categories; one launcher per category (kitty in lab with `seclegion-tools list --lab … --category …`), GUI apps exported on create only, removed on remove (PRD §18.2).
- **Installer 1.1:** screen 12 checkboxes "Full BlackArch Security Lab" / "Kali Tools Lab" (online) → `/var/lib/seclegion/firstboot/labs.toml` → first-login welcome creates with consent + progress; post-install `seclegion-tools install kali-lab|blackarch-lab`.
- **Host firewall prerequisite (Q2):** ufw deny-in/allow-out; `seclegion-box listen <port> [--for 1h]` adds a timed rule; S11e checks ufw + libvirt + netavark coexistence.
- **Claude Code / Antigravity (O7):** fetchers per O6 (`/opt/<vendor>/<ver>`, pinned sha256, nothing redistributed); self-update off; telemetry off via managed settings / policy (keys UNVERIFIED); Antigravity on Super+I; SLA ≤7 days; logins/keys always user-entered.
- **Screensaver** pre-lock if it slipped from 1.0.
- **Spikes:** S11a rootless networking per tool · S11b GUIs on Hyprland incl. hybrid NVIDIA · S11c image provenance/sizes · S11d msfdb · S11e firewall coexistence.
| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| L1 | base, `seclegion-box`, sealed class, firewall | full lifecycle leaves no residue; no podman/linger units after reboot; integrated box can't write host `/etc`; sealed: no `/run/host`, no `/run/user`, no route with `--net none`, no `/dev/dri` without `--gpu`; LAN scan from second VM shows only allowed ports | — |
| L2 | offsec + heavy tools | **host `pacman -Q` and `pacman-conf` byte-identical before/after**; msfconsole version; Ghidra headless on fixture; Burp/Ghidra/Caido OCR under Hyprland; running digest = lock | 1650/4060: GUIs render on iGPU, NVIDIA not woken without `--gpu` |
| L3 | Kali lab | category install; real apt works inside box; launcher; update/rebase/remove clean; host pacman unchanged | — |
| L4 | BlackArch lab | in-box no TrustAll, SigLevel Required; tampered pkg rejected; host repos unchanged; mutation: BlackArch on host → red | — |
| L5 | installer lab option + first-login creation | QMP/OCR; offline greys option | — |
| L6 | Claude Code / Antigravity fetchers | wrong sha256 rejected; no self-update writes outside `/opt`; zero outbound before login; keybind lint | — |
| L7 | disposable VM | overlay deleted; isolated no route; base hash unchanged | USB passthrough of safe device |
| L8 | Release 1.1 | R-final + UPGRADE + SOAK | owner ISO + lab install on a laptop |
Owner decisions: offsec base [Kali; fallback Arch + fetchers] · firewall [ufw deny-in] · Claude Code/Antigravity on community ISO [installer "AI coding tools (cloud)" checkbox, unticked] · BlackArch full offered [yes, size warning] · Metasploit on host [no, container per PRD §8.5].
Out of scope: rootful boxes, Docker default, VMware.

### 1.2 — Package experience & App Center (PRD §8.6–8.8, §21)
- **Catalog v2** `catalog/tools/*.toml` (schema-validated): name, description, category (Security / BlackArch Lab / Kali Lab / Containers / Virtualization / AI / Development / Gaming / System / Help), location, computed status, launch method, package + source, version, privileges, safety note, docs link, needs internet, needs special hardware, safe test, removal, update policy. Docs generated.
- **`seclegion-install` / `seclegion-tools {search,info,install,remove,launch,terminal,list}`:** catalog → official repos (pyalpm) → `[seclegion]` → lab/box offer; **never AUR implicitly**; never `-Sy` alone; stale DB → "run seclegion-update first".
- **apt-get compatibility:** interactive-shell functions only (`/usr/share/seclegion/shell/apt-compat.{zsh,bash}` + `alias sudo='sudo '` → `seclegion-apt`); **no apt/apt-get binary on PATH** (scripts still see "not Debian"; skipped inside containers so Kali's real apt works). `install` uses curated `catalog/apt-map.toml`, shows mapping, confirms; `update/upgrade` → offers `seclegion-update`; `search/show` → seclegion-tools; unknown → clear message + alternatives, exit 100; every map entry CI-checked against the sync DB.
- **AUR:** `yay` vendored signed in `[seclegion]`, installed only via `seclegion-tools enable aur` after a warning; diff menu on (flags UNVERIFIED); AUR results only with `--aur`, labelled, never in App Center.
- **App Center `seclegion-appcenter`** (GTK4/libadwaita): Featured, Security, Labs, All packages (pyalpm + archlinux-appstream-data), Updates (runs `seclegion-update`), Installed. Root ops only via **`seclegion-pkgd`** (D-Bus `org.seclegion.Packages1`, polkit `org.seclegion.packages.install` auth_admin_keep) accepting only names from official repos or `[seclegion]`. PackageKit/gnome-software rejected.
- **Optional bundles:** Development (git, nodejs, pipx, neovim, ranger), IoT/Embedded (arduino-cli, esptool, openocd, picocom, minicom, platformio-core, binwalk, flashrom, sigrok-cli, pulseview, uucp helper), Discord, Backups (pika-backup, no schedule by default), lab VM recipes with pinned ISO hashes.
- **Community:** `docs/contributing.md` (catalog entries, PKGBUILD review, licence + evidence rules); catalog PRs CI-validated.
| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| P1 | catalog v2 | schema; every safe test in VM; status = `pacman -Q` + `seclegion-box list` | — |
| P2 | install/tools CLI | no `-Sy` without `-u` (grep + strace); stale DB refusal; AUR never without `--aur` (mutation) | — |
| P3 | apt-compat | `command -v apt-get` empty in `sh`; `sudo apt-get install nmap` → confirm → pacman; burpsuite → offsec offer; unknown → exit 100; Kali box apt works; mutation: `/usr/bin/apt-get` → red | — |
| P4 | AUR opt-in | yay absent until enabled; warning shown | — |
| P5 | App Center + pkgd | pkgd rejects non-repo names, option injection, paths (fuzzing); polkit OCR; flows via QMP | — |
| P6 | Release 1.2 | R-final + UPGRADE + SOAK | owner App Center use |
Owner decisions: apt-compat on by default [yes, interactive-only, off switch] · AUR helper [yay, opt-in] · App Center "All packages" [yes, "Arch official"] · backups [pika-backup, optional] · Flatpak [not planned] · AUR in seclegion-update [no].

### 1.3 — Look & feel (PRD §16.2, §17) — post-1.0 because it touches every surface and needs S7
**Prerequisite (Q3):** 1.0 configs already rendered from `tokens.toml` via templates; 1.3 moves rendering to runtime.
- **`seclegion-theme set --wallpaper <img> --mode auto|default|light|custom [--accent] [--contrast normal|high] [--motion full|reduced]`, `preview`, `reset`.** Pipeline: matugen → semantic tokens (bg, surface, text, muted, accent, accent2, borders, 16 ANSI) → **identity clamp** (dark bg L* ≤12; auto keeps accent in teal/cyan-green family, range UNVERIFIED; custom any hue) → **contrast clamp** (text ≥4.5:1 target 7:1; UI/borders ≥3:1; high-contrast ≥7:1 + 3 px borders; OKLCH lightness only) → **protected semantics** (error/warning/success/critical fixed, bg adjusted instead) → glyph+text for every status. Output to `~/.local/state/seclegion/theme/<hash>/` + atomic symlink; applies to Hyprland, waybar, rofi, kitty, swaync, swayosd, hyprlock, screensaver, GTK3/4 (adw-gtk-theme + css), Qt (qt6ct/kvantum), plymouth.
- **Live wallpapers:** animated images via awww (UNVERIFIED); video via mpvpaper vendored **opt-in** (pauses on battery/fullscreen/lock; theme from ffmpeg frame); owner's Super+Ctrl+W active only when installed.
- Light mode (owner's light asset), reduced motion, high contrast, curated wallpaper collection + local files, rotation only if approved, community themes = data only (code stripped, Omarchy pattern).
- **Screensaver variants** Logo / Clock (no notification content) / Wallpaper (pre-blurred) / Off; ≤1 fps; stops at DPMS; never inhibits idle; hyprlock gets matching layouts; if S7 permanently red → variants are hyprlock layouts only.
- Plymouth boot splash (unless the addendum ships it in 1.0).
| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| T1 | theme engine | property tests over ≥500 synthetic wallpapers + owner assets: thresholds met, semantics unchanged, deterministic, idempotent; mutation: clamp off → red | — |
| T2 | surfaces | VM screendump + OCR per surface; sampled colours = tokens | — |
| T3 | accessibility | high-contrast ≥7:1; reduced motion disables animations | — |
| T4 | screensaver variants | S7 suite per mode; CPU <2% avg over 120 s (UNVERIFIED) | both laptops: mode → lock → suspend → resume, no leak |
| T5 | live wallpaper | paused on battery/fullscreen; absent → no keybind | battery drain measured |
| T6 | Release 1.3 | R-final + UPGRADE + SOAK | owner visual sign-off |
Owner decisions: default screensaver [Logo] · identity clamp [strict teal/cyan] · light theme [yes, "preview"] · mpvpaper opt-in [yes] · rotation [off, offered] · plymouth [yes unless in 1.0].

### 1.4 — Boot security & power
- **Secure Boot wizard `seclegion-secureboot`** (opt-in, post-install): sbctl own keys **+ Microsoft keys kept** (flag UNVERIFIED); signs systemd-boot, UKIs, memtest, fwupd EFI; won't say "enable SB" until `sbctl verify` clean; per-vendor Setup Mode docs; mandatory BitLocker recovery-key confirmation if Windows present. Shim/MOK rejected for 1.x. Install ISO stays SB-off (no Microsoft-signed shim).
- **TPM2 LUKS:** `systemd-cryptenroll --tpm2-pcrs=7 --tpm2-with-pin=yes` (PIN default) + mandatory recovery key shown once, never logged; passphrase slot kept.
- **FIDO2** LUKS + pam-u2f (sudo/polkit/hyprlock), opt-in. **Fingerprint** fprintd for sudo/polkit/hyprlock; never greeter first login or LUKS.
- **Hibernation `seclegion-hibernate enable`:** `@swap` nodatacow + `btrfs filesystem mkswapfile --size <RAM>`, zram higher priority, systemd-initrd resume (offset UNVERIFIED), warning if no LUKS, NVIDIA preserve-memory + suspend units, disk preflight.
- **Snapshot recovery from boot menu:** stay on systemd-boot; add **"SecLegion Recovery" UKI** with a TUI listing snapper snapshots of `@`, setting default subvolume, chroot `mkinitcpio -P` (+ sbctl sign). Limine + limine-snapper-sync rejected for 1.x (bootloader migration, AUR-only, ESP size) — re-evaluated in 2.0.
- **fwupd** opt-in (LVFS is a network service).
- Spikes: S14a OVMF custom keys + swtpm · S14b recovery UKI chroot rebuild · S14c btrfs swapfile resume.
| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| B1 | Secure Boot | enroll → verify → boot SB on; unsigned UKI refused; kernel update re-signed; Windows warning OCR | both laptops: SB on, NVIDIA loads, Windows boots (after verified BitLocker key) |
| B2 | TPM2/FIDO2 | swtpm PIN unlock; recovery key unlocks; PCR7 change → passphrase; recovery key never in journal | owner FIDO2 key if available |
| B3 | fingerprint | PAM lint: never in greetd auth; sudo falls back to password | ≥1 laptop with reader |
| B4 | hibernation | VM hibernate/resume incl. LUKS | both laptops incl. NVIDIA |
| B5 | recovery entry | broken kernel update → Recovery → snapshot → boots with matching modules; SB variant | one laptop drill |
| B6 | Release 1.4 | R-final + UPGRADE + SOAK | — |
Owner decisions: SB key model [own + Microsoft via sbctl] · TPM default [PCR7 + PIN] · FIDO2 hardware for testing [owner to say] · hibernation [opt-in] · fwupd [opt-in].

### 2.0 — Community distribution & hardened defaults
Installer opt-ins (queue SB wizard, TPM2+PIN, labs, AUR); multi-maintainer key ceremony, subkey rotation calendar, published reproducible-build attestations; ≥2 independent `[seclegion]` mirrors; evaluate held Arch snapshot mirror for stable; remove everything deprecated through 1.4 (UPGRADE from 1.3 and 1.4); re-evaluate Limine snapshot boot, shim, GNOME fallback, BIOS. Gates: 1.x gates + independent third-party ISO hash reproduction + key-ceremony record. Owner: co-maintainers; held mirror only with hosting.
**Close now (owner confirms):** BIOS/legacy — won't do · in-installer NTFS resize — won't do (O1) · GNOME — not planned.

## PRD coverage (post-1.0 view)
| PRD § | Item | Release |
|---|---|---|
| 1 | Embedded/IoT, Discord | 1.2 bundles |
| 3.3 | Boot splash | 1.3 (or addendum) |
| 4.1 | BIOS optional | won't do |
| 4.3–4.6 | Installer, dual boot | 1.0; labs 1.1; SB/TPM opt-ins 2.0 |
| 5 | General hardware, reports | 1.0 + 1.0.2 |
| 6.1 | GNOME fallback | not planned |
| 6.2–6.5 | Workflow, notifications, OSD | 1.0 + addendum (keyboard backlight keys to confirm in M7) |
| 7.1–7.3 | Browsers, editors, owner apps | 1.0; Claude Code/Antigravity 1.1; Neovim/Ranger 1.2 catalog |
| 8.2 | Tier-1 | 1.0 |
| 8.3–8.5 | BlackArch, Kali, heavy tools, disposable VMs | 1.1 |
| 8.6 / 21 | seclegion-tools catalog | 1.0 → 1.1 → 1.2 |
| 8.7–8.8 | seclegion-install, App Center, yay, apt-get compat | 1.2 |
| 9.1 | Podman/distrobox | 1.1 |
| 9.2–9.3 | KVM + networks | 1.0; disposable VM 1.1; lab VM recipes 1.2 |
| 10 | LUKS / TPM, FIDO2 / hibernation | 1.0 / 1.4 / 1.4 |
| 11 | No automatic network | notifications opt-in 1.0.1; fwupd opt-in 1.4 |
| 16.1–16.3 | Logo screensaver / variants / lock | 1.0 if S7 green else 1.1 / 1.3 / 1.0 |
| 17 | Adaptive theming etc. | 1.3 |
| 18 | Omarchy ease, welcome, shortcut menu | addendum (1.0) |
| 19 | Gaming | 1.0 |
| 20 | AI | addendum (1.0) |
| 21.1 System | updates / backups / snapshots / recovery | 1.0.1 / 1.2 / 1.0 / 1.4 |
| — | Secure Boot, fingerprint, firmware | 1.4 |

## Questions for Legion
Q1 pull update/migrate/testing channel/UPGRADE harness into 1.0? · Q2 host firewall in 1.0 or 1.1 prerequisite? · Q3 1.0 configs template-rendered from `tokens.toml`? · Q4 integrated boxes as one-click launchers vs sealed default for offsec GUIs? · Q5 recovery-UKI vs Limine testability, mutation targets? · Q6 apt-compat as interactive shell functions only — meets PRD §8.8?

## UNVERIFIED
Rootless raw sockets/monitor mode (S11a); Kali/BlackArch image namespaces, signatures, sizes (S11c); Caido in Kali; msfdb without init (S11d); firewall coexistence (S11e); subuid from 1.0 useradd; Claude Code managed-settings keys, vendor hashes; Antigravity telemetry mechanism; yay diff flags; awww animation; mpvpaper licence; accent hue range; screensaver CPU threshold; sbctl Microsoft flag + signing hook; NVIDIA with SB; swapfile resume offset; recovery UKI rebuild (S14b); archive.archlinux.org mirror policy.
