# Plan r15 — working smarter within Claude Pro limits

Status: proposal (2026-10-18). Result of the Sec (plan) vs Legion (counter) debate. Scope cuts and the tier choice are the owner's.

## Budget model (agreed)
- The **weekly cap** is the binding limit; the 5-hour window is secondary. Opus draws it down several times faster than Sonnet.
- Plan **3 plan-hours per window** (4 is upside). SecLegion stops at **70% weekly** usage so other projects keep ≥30%.
- Calibrate: `/usage` at start and end of each window for the first 3 jobs, then re-tune the numbers below.

## Rules
1. Fresh main session per work block; it reads only the tail of `docs/STATUS.md`. Main context target ≤ 60k.
2. Jobs sized to ≤ 70k tokens, commit per sub-item, briefs written as files (spec + gates) so a new session re-reads a file, not a conversation.
3. Builders run their own gates and report one line per gate (≤ 500 tokens total). The main session re-runs the gates and reads the diff; it remains the only reviewer (owner rule), with small diffs reviewed in one pass.
4. Opus = briefs, review, install-engine design, escalation after 2 failed iterations. Sonnet = all code.
5. ISO + VM gates run from a script (`tools/checkpoint-run`, exit code + JSON summary); no agent watches a passing run. A failing run gets one Sonnet agent with the log. Unattended/night runs are opt-in and use keep-awake.
6. Installed-base qcow2 + overlays only for the install-engine dev loop.
7. Dropped: window anchoring, Haiku log readers, fat (150k) builders.

## Tier timings (realistic, with rework)
| Tier | Contents | Agent hours | Normal (4 days/wk, 2 windows/day) | Low-token (1 window/day, 1 agent) |
|---|---|---|---|---|
| 1.0-core | install engine (I1, I-devloop, I2a, I2b, I3, I4), text installer, desktop, greetd+regreet login (O9b), updates (W3), release (RL1), security tools (S8/9) | ~60 h + ~10 h runs | **~3–4 weeks** | ~7–8 weeks |
| 1.0-full | + W1/W2/W4, TUI (U3), H1, rest of L1, polished greeter (D2) | +~28 h | +~2 weeks | +~4 weeks |
| 1.1 | GUI installer, AI system, D3/D4, V1, gaming extras | +~37 h | +~2.5 weeks | +~5 weeks |

Sec estimated core at 2 weeks assuming every window is perfect; Legion's 4 weeks assumes ~16 useful h/week. Planned figure: 3–4 weeks.

## Weekly template
- Mon, Tue, Thu, Fri — SecLegion. Window A: brief → builder(s). Window B: review, merge, queue checkpoint run.
- Wed, Sat — other projects (SecLegion at most reads a run's JSON).
- Sun — off / buffer.

## Risks
1. Install-engine debugging blowup (+10 h): dev loop first; 2 failed iterations → Opus spike; 6 h buffer.
2. Usage limit mid-job: commit per sub-item, STATUS checkpoint at 75% of a window.
3. Machine contention (RAM, Brave, disk ≥ 20 GB free).
4. Main-session context bloat: rule 1.
5. Laptop sleep during runs: keep-awake, resume-safe script.

## Owner decisions (2026-10-18)
- **archinstall engine, Omarchy-style** (D-R14-2). Checkpoint B becomes:
  - I1 configurator (4 h): text wizard, ~5 questions, Enter accepts defaults; writes archinstall `user_configuration.json` + credentials (tmpfs, 0600); validates it; G20-G22 refusals and no-secret-in-logs stay.
  - I-devloop (2 h): unchanged.
  - I2 archinstall run + `seclegion-post` (5 h): offline pacstrap from the embedded signed cache; post step adds `[seclegion]`, packages, greetd + regreet, ufw, sshd masked, first-boot unit. Replaces I2a + I2b (10 h).
  - I3 VM matrix (4 h): erase, erase+LUKS, alongside (Windows partitions byte-identical), offline zero-network.
  - I4 target-clean + mutation (4 h): unchanged, plus "no archinstall credential file or secret log in target".
  - U1 text UI folds into I1; U1 keeps only first-boot setup (2 h).
- **Series**: exactly 1 agent at a time, normal pace. VM/ISO runs are scripts, not agents, so they run beside the agent.
- **Progress meter**: `tools/seclegion-progress` reads `docs/progress.toml`. 1.0 = 80%, perfected (1.1) = 100%. Update the item's status in the same commit that merges it.

## Timeline (series, ~3 plan-h/window, 2 windows/day, 4 SecLegion days/week ≈ 24 plan-h/week)
| Milestone | Remaining agent h (+25%) | Weeks | Meter |
|---|---|---|---|
| Checkpoint A closed | ~1 | this week | ~29% |
| Checkpoint B (installs like Omarchy) | ~22 | +1 | ~45% |
| Checkpoint C (installed Hyprland + login) | ~22 | +1 | ~60% |
| Checkpoint D (workflow, updates) | ~24 | +1 | ~72% |
| **1.0 release** | ~16 | +1 | **80%** |
| 1.1 perfected (GUI installer, AI, gaming, VMs) | ~48 | +2 | **100%** |
1.0 ≈ 4–4.5 weeks, 100% ≈ 6–7 weeks.
