# SecLegion 1.0 Addendum — UX parity, Omarchy features, AI (Sec draft, round 5)

Status: Sec proposal under Legion review. Extends spec.md; O1–O8 and A1–A13 stay binding unless marked **PROPOSAL**. (v) = verified on host.

## 1. Shell architecture — keep A9 multi-daemon
Keep waybar + swaync + swayosd + hyprlock + hypridle + rofi + hyprpolkitagent, **plus** uwsm (v) session manager (every role a systemd user unit on `graphical-session.target`; fixes the waybar ordering bug; probe-able) and a **secrets role** (gnome-keyring unlocked by PAM in greetd). Quickshell (v, LGPL-3.0) = 2.0 evaluation spike.
Why not a single Quickshell shell: owner already runs waybar/hyprlock (exact fidelity); per-role probes vs testing our own QML via our own IPC; Quickshell is pre-1.0 and coupled to Qt private APIs; one QML error kills bar+notifications+OSD; **we would own the lock screen's PAM code — decisive against it for a security OS**; thousands of QML lines for one maintainer.

## 2. Workflow migration matrix (→ docs/current-workflow-migration.md)
Rules: **all binds by keycode** (`code:NN`) so one bind works in us and ara (fixes wrong ا/ء aliases, removes ~40 duplicates; Lua syntax UNVERIFIED → spike S8); `keybinds.toml` lint (xkbcommon both layouts, no duplicate key+mods, every binary exists); `seclegion-ctl <verb>` replaces ae-osd.sh router.

### 2.1 Owner keybinds
| Current | Action | SecLegion | Status | Notes |
|---|---|---|---|---|
| S+Return/KP_Enter/T | kitty | same | KEEP | QMP test both layouts |
| S+Shift+Return/KP_Enter | antigravity | same → VS Code `code` | CHANGE (decided, PRD §7.2) | |
| S+I | antigravity | unbound in 1.0 → antigravity 1.1 | CHANGE (O7) | no binds for missing commands |
| S+E | thunar | same | KEEP | |
| S+B | brave‖firefox | firefox | CHANGE (O6) | Brave via rofi |
| S+D, S+R | rofi toggle | same | KEEP | |
| S+Q, S+C | close | same | KEEP | dead kitty super+c/v maps removed; kitty keeps Ctrl+C/Ctrl+V; Omarchy Super+C/V rejected |
| S+F | fullscreen | same | KEEP | |
| S+V, S+W, S+Shift+F | float+centre | same | KEEP | |
| S+P | pseudo | same | KEEP | |
| S+J | togglesplit + focus down | togglesplit only | FIX | focus down = S+Down; opt-in vim profile in user.lua |
| S+Space | us↔ara + popup | same, popup via swayosd "EN/AR" | KEEP | Omarchy menu moved to S+M |
| S+G, S+Tab/], S+Shift+Tab/[ | groups | same | KEEP | |
| S+Shift+W | wallpaper picker | `seclegion-wallpaper pick` (yazi, awww wipe, hyprlock frame) | FIX | wallust removed; static palette in 1.0 |
| S+Ctrl+W | live wallpaper | gif/webp via awww | FIX (partial) | video (mpvpaper) later |
| S+Y | yazi | same | KEEP | theme `[mgr]` fix |
| S+Shift+V | copyq | same | KEEP | |
| S+N | swaync panel (broken) | same | FIX | one daemon, correct alias |
| S+L/Esc/BackSpace | wlogout | `seclegion-power` (rofi): Lock, Suspend, Logout, Reboot, Shutdown, Firmware | CHANGE (A9) | neon look, confirm on reboot/shutdown |
| S+Shift+L | lock | `pidof hyprlock ‖ hyprlock` | FIX | |
| S+Shift+B | toggle waybar | same | KEEP | |
| Print/S+Shift+S, Shift+Print, S+Print, Ctrl+Print | screenshots | same (grimblast/swappy) | KEEP | Omarchy colour-picker key rejected |
| S+arrows/H/K | focus | same | FIX | J → togglesplit |
| S+Shift+arrows/H/K/J | move | same | KEEP | |
| S+1..0 / S+Shift+1..0 | workspaces | same by keycode | KEEP | |
| S+S, S+Shift+A, S+Z | scratchpad | same | KEEP/FIX | Z alias fixed |
| S+wheel, S+LMB/RMB, 3-finger swipe | ws / move / resize | same | KEEP | swipe HW gate |
| XF86 vol/mute/mic/bright/media | ae-osd.sh | `seclegion-osd` → swayosd, locked, repeat | KEEP | volume ≤100% |
| (new) XF86Pause, KbdBrightness± | — | bound only if hardware detected | NEW (PRD §6.5) | |
| (new) Alt+XF86 vol/bright | — | 1% steps | NEW (Omarchy) | |
| S+F10/F11/F12 | media | same, now locked | FIX | |
| S+Shift+C | clock 12/24h | same | KEEP | |

### 2.2 New keys (free keys only; owner approves set — D3)
S+M `seclegion-menu` · S+/ and S+F1 `seclegion-keys` cheat sheet · S+, / +Shift / +Ctrl close latest / close all / DND · S+Ctrl+N night light · S+Ctrl+E emoji · S+Ctrl+C capture menu · Alt+Print record · S+Ctrl+Print OCR → clipboard (eng+ara) · S+Alt+Print colour picker · S+Ctrl+I stay awake · S+Ctrl+P power profile · S+A SecLegion AI chat · S+X `seclegion-tools`. Waybar logo: left-click rofi, right-click `seclegion-menu`.

### 2.3 Visual & behaviour mapping
| Area | SecLegion 1.0 | Gate |
|---|---|---|
| Notifications (swaync) | top-right, margin 20/50 (CSS, UNVERIFIED), width 380, radius 12, 1 px frame, padding 12/16, JBM Nerd 11, bold summary + body, icon 48, progress 8 px r4; urgency colours low `#0d1117/#00ffcc/#00e5ff`, normal `#0d1117/#e6f1ff/#00ffcc`, critical `#1a0010/#ff4488/#ff2266`; timeouts 2 / 5 / sticky; grouping; S+N panel 400 px (title+clear, DND, MPRIS art, inhibitors), slide-right, token colours. `seclegion-notify-test {low,normal,critical,progress,action}` (PRD §6.4). **Deltas (D4):** left-click = action, middle/right = close; no right-click close-all (S+Shift+,); no 5-popup cap; history uncapped; fixed width | one D-Bus owner and exactly one Notifications service file; layer geometry ±2 px; frame colour per urgency; timeouts ±0.5 s; DND test; S+N opens panel |
| OSD (swayosd) | the *intended* look made real: bottom-centre, 360×80, radius 14, bg `#0a0f1aee`, text `#00ffcc`, frame `#00e5ff`, 6 px bar, ~2 s, JBM 13; volume ±5 ≤100, mute with level, mic, brightness ±5 (exponent kept), media title ≤40 chars (`--custom-message` UNVERIFIED → fallback low notification); SecLegion emblem | own layer namespace; bottom-centre; VM volume via QMP + wpctl; brightness/mic/media HW |
| Bar (waybar 36) | exact modules/order and effective look; battery 30/15 colours; clock + toggle + calendar; nmtui; pavucontrol/scroll/middle-mute; **added when active only:** tray, notification/DND bell, recording dot, stay-awake eye, AI pill | on-click binaries exist; OCR; hidden modules absent when idle |
| Launcher (rofi) | owner look, Figtree 13 shipped, logo present | golden screenshot; `fc-match Figtree` |
| Lock (hyprlock) | owner layout + SecLegion logo, avatar `~/.face`, user name, keyboard-layout label | OCR: name + layout, no notification text; suspend HW |
| Idle (hypridle) | lock 300 s, screen off 330 s, suspend 900 s battery only (D5), before_sleep lock, after_sleep dpms on | fake-clock order; never suspend on AC; inhibitor honoured |
| Terminal (kitty) | owner settings, neon token colours, super+c/v maps removed | config parse; no kitty map shadowed by Hyprland |
| Window rules | kitty **tiles** by default (D2); helper windows class `seclegion-float` float 800×500; other floats kept | `hyprctl clients` |
| Shell / prompt / fastfetch | zsh plugins + zoxide/bat/btop/eza installed; owner aliases + target/vpn/myip; starship HUD rewritten MIT; rotating SecLegion logos | alias/function presence; golden prompt renders |
| Look & feel | gaps/border/rounding/shadow/blur/animations copied verbatim; **ARGB border bug fixed** (`rgba(00ff88ff)`/`rgba(0b1e1ccc)`); reduced-motion toggle | `hyprctl getoption` + pixel sample; token generator rejects ambiguous hex |
| Input / monitor / cursor | us,ara; tap; middle emulation; scale auto from EDID (owner's 1.2 in user.lua); Bibata 24 everywhere | all three cursor values 24 |
| Fonts | JetBrainsMono Nerd, Inter, Roboto Mono, Cantarell, Noto + emoji from repos; Figtree vendored (OFL, check) | every referenced family in `fc-list` |
| GTK / Qt | Graphite-Mono-Dark, Tela-circle-grey, Papirus-Dark fallback; Graphite/Tela/Bibata built from source in `[seclegion]` (D6); Qt via qt6ct token palette, kvantum dropped | gsettings; qt6 app palette |
| Autostart | uwsm units: waybar, swaync, swayosd-server, hypridle, hyprpolkitagent, awww-daemon, copyq, nm-applet, gnome-keyring; dunst/polkit-gnome/wlogout dropped | single-owner + secrets-owner gates |
| Scripts | ae-welcome → `seclegion-welcome`; prompt helpers kept; seclegion-gpu-run kept; cava/glava/quickshell toggles dropped | shellcheck/ruff + unit tests |

## 3. Omarchy adoption (MIT; notice in PROVENANCE.md for reused code)
| Feature | Decision | SecLegion |
|---|---|---|
| Quickshell shell | LATER 2.0 spike | §1 |
| archinstall configurator | REJECT | own installer |
| LUKS on by default | **PROPOSAL P1** | ticked by default for erase installs only (D11) |
| Autologin after LUKS | REJECT 1.0 | opt-in later |
| Plymouth unlock splash | LATER | after S3 green |
| Limine snapshot boot | REJECT | systemd-boot (A5) |
| Snapshot before update | ADOPT | `seclegion-update` one snapper pair per update |
| Factory reset | ADAPT | 1.0 makes `seclegion-baseline` snapshot; UI later |
| Custom kernels | REJECT | linux + linux-lts |
| Menu | ADAPT | `seclegion-menu` (rofi, TOML + user `menu.d`) on S+M |
| System menu | ADAPT | owner's power menu keys |
| Keybinding help | ADAPT | `seclegion-keys` on S+/ from keybinds.toml + live `hyprctl binds` |
| Notification keys, Alt fine OSD steps, stay awake, night light, capture (OCR/record/QR), colour picker, emoji, power profiles, battery alerts (15% / 7% sticky), sshd off, refresh-config, fwupd entry (fetch on click), gaming menu | ADOPT | as §2.2 |
| ufw default deny | ADOPT | deny in / allow out on install (D7), virbr0 DHCP/DNS allowed |
| Lock S+Ctrl+L, Super+C/V clipboard, tte screensaver, timed passwordless sudo, pacman guard, supergfxctl, usage-meter panel | REJECT | owner keys / A3 / PRD §18 full pacman / A10 |
| Hibernation, fingerprint/FIDO2 | LATER | needs own PAM/resume mutation tests |
| Theme system | ADAPT | 1.0 builds the renderer `seclegion-theme apply` (tokens.toml → templates for every app), SecLegion Dark only; picker/install/matugen/high-contrast later |
| TUI installs | ADAPT | btop + lazygit installed; menu later |
| Update + migrations | ADOPT | `seclegion-update`: space check → snapshot → keyrings → `-Syu` → `seclegion-migrate` → vendor fetchers → pacnew/orphan report → UKI check → reboot notice |
| Channels, web apps, dev env (mise), vendor HW scripts, dictation, lifecycle hooks, unattended install, nightly images, coredump→AI | LATER | see §6 |
| Dock, reminders, world clock, plugins, Windows VM, Tailscale/LocalSend | no target | not owner workflow |

## 4. SecLegion AI (1.0, PRD §20)
- **Name (D1):** SecLegion AI — `seclegion-ai`, alias `ai`, GTK app "SecLegion AI Center", package `seclegion-ai`.
- **Runtime:** ollama (v, MIT) + **ollama-vulkan default GPU backend**; ollama-cuda (≈3.2 GB download) offered by consent on NVIDIA Turing+ ≥4 GB VRAM; ollama-rocm by consent on ROCm allowlist only. ollama + vulkan + aichat in offline cache. **Per-user** `seclegion-ai-runtime.service`, **disabled by default**, `127.0.0.1:11434`, models in `~/.local/share/seclegion-ai/models`, stops after 30 min idle; system ollama.service disabled. `*-cloud` model tags refused; egress gate is the real guard.
- **Model manager** (AI Center + CLI `seclegion-ai models list|info|pull|test|use|rm`): curated `catalog.toml` (~10 models; tag, pinned digest, size, RAM/VRAM per quant, CPU-OK, licence + non-OSI label, use); consent dialog (name, size, licence, host, disk); custom tags with warning; `test` reports OK + tokens/s + CPU/GPU placement; plain-language errors (RAM/VRAM numbers, backend missing, disk full, unreachable, incompatible); requirements screen greys out models that won't fit.
- **Chat:** **aichat** (v) on S+A in kitty (sessions, roles, RAG, `-e` shell commands with confirmation). AI Center = models, providers/keys, privacy, defaults, test (no chat window in 1.0; native GTK chat 1.1). Optional "browser chat" = aichat `--serve` on 127.0.0.1, local provider only, dropped if CORS gate fails. open-webui/alpaca/gpt4all not in repos.
- **API providers:** OpenAI, Anthropic, Gemini, OpenAI-compatible. Keys entered masked in AI Center, stored in **Secret Service** (gnome-keyring), passed only via environment to the child aichat process; never in config files. "Test connection" is the only network call, on click. Providers labelled `local-…` / `cloud-…`.
- **Privacy UI:** every surface says **LOCAL: runs on this computer** or **CLOUD: sends your text to <provider>** (text + icon). Default always local. Piping to cloud shows byte count + destination and needs `y` each time; non-TTY refused. No telemetry, no auto-download, no file read unless named. RAG corpus = SecLegion docs + tool catalog only.
- **Coding:** **Continue** VS Code extension installed on click, pointed at the local runtime (cloud key user-managed with warning); `ai cmd "…"` = `aichat -e` with confirmation; VS Code telemetry off in skel. Claude Code + Antigravity stay 1.1 (O7).
- **Security-learning assistant:** aichat role `seclegion-tutor` (explains tools/methodology, restates authorised-targets-only rule) with tool-catalog context; "Ask SecLegion AI" action on each `seclegion-tools` entry; tool output never attached automatically.
- **Docs assistant:** aichat RAG over SecLegion docs, keybindings, catalog; embedding model all-minilm (~46 MB, consent); index rebuilt via migration when docs change. Man pages/user documents later.
- **Integration:** welcome "Set up local AI (optional)" card; menu > AI; seclegion-tools AI category; waybar AI pill ("AI LOCAL"/"AI CLOUD") only while active; S+A; `ai`; VS Code; Firefox.
- **Dictation/image tools:** none in 1.0 (whisper.cpp not in repos; later, owner approval). Live ISO: "Install SecLegion OS to use local AI".

## 5. Milestone changes
Order: M6 → S7 → **S8** (Lua keycode binds + `hyprctl binds -j`) → **S9** (swaync margin, swayosd custom message) → M7 → **M7a** → M8 → M9 → **M9a** → M10 → M11 → M12. spec §6 "1.2: SecLegion AI" moves to 1.0.
| # | Scope | Automated gate | HW gate |
|---|---|---|---|
| M6+ | uwsm, secrets role, **welcome (§18.1)** | one owner each: Notifications/polkit/secrets; one Notifications service file; all role units active; welcome once, reachable from menu, every button resolves | — |
| M7+ | full §2 matrix | QMP every bind **in us and ara**; keybind lint; notification geometry/colour/timeouts/DND; OSD bottom-centre separate namespace; border probe; fonts; cursor ×3; lock OCR; idle order, no suspend on AC | both laptops: every XF86/F-key, brightness, mic LED, kbd backlight, OSD look, swipe, lock after suspend, **owner side-by-side visual sign-off vs current machine** |
| **M7a** | menu, **cheat sheet (§18.2)**, capture, night light, emoji, power profiles, battery, stay-awake, reduced motion, `seclegion-update` + migrations + refresh-config, fwupd entry, ufw/sshd defaults, baseline snapshot | every live bind in `seclegion-keys --json` with command + availability, none missing; reachable from shortcut/launcher/welcome/bar; OCR fixture eng+ara; recording playable; update: one snapshot pair, migration once, rerun no-op, failing migration aborts with snapshot intact, missing UKI aborts; ufw deny-in; sshd inactive; baseline exists | battery alert; power profile switch |
| **M9a** | SecLegion AI | runtime disabled, no :11434 listener, no models by default; **egress:** zero non-loopback packets from AI processes during local use; consented pull only from allowlisted hosts; tiny local fixture model loads in 4/8 GB VMs, oversized → RAM error; **keys:** canary key reaches stub, found nowhere on disk/logs/journal, not in config, masked in UI, not in serve env; non-TTY cloud pipe refused; `-cloud` tag refused; pull without consent refused; catalog lint; CORS gate; hwdetect → backend fixtures | 1650: vulkan + cuda load ~3B on GPU; 4060: ~8B; ≥1 AMD/Intel community report; Continue completes code locally |
| M10+ | ufw interplay | nested NAT + DNS/DHCP with ufw; isolated no route | — |
| M12+ | release notes list AI catalog licences + "no models in ISO" | licence check covers catalog, themes, fonts | — |
Mutation additions: AI runtime enabled by default · `api_key` in aichat config · second Notifications service file · keybind with missing binary · ARGB border token · `-cloud` tag allowed.

## 6. Deferred (for the roadmap)
1.1: Claude Code + Antigravity (O7) · native GTK chat · RAG over man pages/user docs · hibernation · fingerprint/FIDO2 · plymouth unlock · mise dev envs + TUI menu · vendor HW rules · nightly ISO/qcow2 · screensaver if S7 slips.
1.2: theme picker/install/matugen/high-contrast/lifecycle hooks · factory reset UI · update channels · web apps, XCompose · dictation (whisper.cpp), AI agent mode with approval UI, coredump→AI (user-initiated) · opt-in autologin after LUKS, unattended install · video wallpapers.
2.0 spike: Quickshell. No target: Limine snapshot boot, dock/reminders/world clock/plugins, Windows VM, keyboard RGB, image generation.

## 7. Owner decisions (new)
| # | Decision | Default |
|---|---|---|
| D1 | AI name | SecLegion AI |
| D2 | kitty always floating? | tile; float helper windows only |
| D3 | new key set §2.2 | approve |
| D4 | swaync deltas from dunst | accept |
| D5 | idle | lock 300 s, screen off 330 s, suspend 900 s on battery only |
| D6 | vendor Graphite/Tela/Bibata (built from source) vs repo alternatives | vendor |
| D7 | ufw deny inbound on install | yes |
| D8 | AI GPU | vulkan automatic; CUDA/ROCm by consent |
| D9 | coding assistant | Continue, on click, local model |
| D10 | dictation in 1.0 | no |
| D11 | LUKS ticked by default for erase installs | yes |
| D12 | community links on welcome | project GitHub + hardware-report guide |
| D13 | S+X tools, S+A AI | approve |

## 8. Questions for Legion
S8 keycode binds fallback (keysym + generated alias table)? · per-user ollama unit vs system service (GPU ACLs, multi-user port) · cut order if 1.0 slips: browser chat → Continue → docs RAG → QR/recorder → battery/power profiles (model manager, keys, privacy not cuttable) · egress gate host-based vs process+window-based · swaync/swayosd gaps: accept deltas or own a small GTK4 OSD helper?

UNVERIFIED: swaync margin CSS; swayosd custom message; ollama cloud-disable + digest verification; aichat key env names + serve CORS; Continue status; Figtree/Graphite/Tela/Bibata licences; wtype in repos; snap-pac skip variable.
