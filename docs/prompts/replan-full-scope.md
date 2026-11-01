You are Opus 5.5, the planner and reviewer for SecLegion OS (repo /mnt/Dev_Lab/SecLegion-OS, branch clean-room-rebuild). Read docs/ROADMAP-STATUS.md, docs/STATUS.md, docs/spec/v1/spec.md, addendum-draft.md, full-plan.md, plan-r13.md and docs/decisions.md first.

GOAL: Re-plan the REMAINING 1.0 work as fast as possible WITHOUT cutting scope. Every milestone stays in 1.0: M2-M12, M6+, M7+, M7a, M9a (SecLegion AI, moved back into 1.0), M10+ and M12+, plus the desktop leftovers. Nothing is deferred.

HOW TO PLAN: plan through a delegated debate.
1. Spawn one Sonnet 5.5 subagent (model "sonnet") as "Legion", the implementer's voice. You are "Sec". Use SendMessage for at most 3 rounds:
   - You propose.
   - Legion attacks it for feasibility, hidden work, test cost and file conflicts.
   - You revise.
   Record the final positions and open disagreements in docs/spec/v1/plan-r14-debate.md.
2. Decide the installer first. The owner wants Omarchy-level install speed and simplicity. Compare:
   - (a) our own installd plus a text UI, then the GUI;
   - (b) archinstall driven by a SecLegion config, the way Omarchy does it, plus our own branded front end and `seclegion-postinstall`;
   - (c) a hybrid.
   The owner still wants every installer feature in the spec:
   - erase, erase+LUKS, alongside Windows, manual;
   - a branded experience;
   - a working desktop in under 15 minutes with few prompts;
   - no NOPASSWD and no autologin on the target.
   Pick the option that delivers all of that fastest, and document it in docs/decisions.md as a reversal of "own installer" if you change it.
3. Write docs/spec/v1/plan-r14.md. It contains:
   - every remaining job, each with at most 3 deliverables;
   - an owner-files list per job, and which jobs can run in parallel on disjoint files (at most 2 builders at once);
   - gates in the form `G<n> outcome — CHECK: cmd — EXPECT: token`, including negative gates;
   - an hour estimate per job and a critical path.

BUDGET RULES (the owner cannot upgrade the plan):
- Opus plans and reviews. Sonnet 5.5 builds (pass model "sonnet" on every builder). At most 2 subagents at once.
- Keep the plan good enough that nothing gets built twice. Spend planning tokens where mistakes are expensive: installer, privilege, signing, disks.
- Testing rhythm changes:
  - no full ISO rebuild and VM boot per small job;
  - builders run unit, static and nested tests per job;
  - the ISO is rebuilt and all VM gates run once per CHECKPOINT;
  - a checkpoint is a group of 3-5 jobs or one milestone, and the plan names each one;
  - privilege, signing and disk-writing gates are never skipped at a checkpoint;
  - define which evidence rows each checkpoint produces for tools/verify-evidence.
- Each builder handoff is under 120k context: one job, quoted rules, no "read the whole spec".

HARD SAFETY RULES (unchanged):
- No sudo for agents.
- Containers only via tools/docker-build.sh.
- Never write a physical disk or USB: qemu image files only, and exact-target owner approval for any real device.
- No third-party repos or keys, and no telemetry.
- No keys or secrets in git, the ISO or logs.
- Host changes only via seclegion-host, with backup and the 120 s dead-man.
- Never send hyprctl dispatch/keyword/reload to the live Hyprland; use a nested instance only.
- Never edit the owner's files: ~/.config/hyprland-dotfiles, hypridle.conf, ~/.ssh, ~/.gnupg, ~/.themes, ~/.icons, wallpapers.
- No pkill by pattern.
- Disk space: NVMe root has about 38 GB free, and each ISO build needs 25 GB. Use one build dir at a time, copy finished ISOs to /mnt/Dev_Lab/iso-artifacts/, and delete build dirs after each checkpoint. The NTFS disks cannot hold build trees.

CURRENT STATE TO RESUME:
- M2 code is merged, but its VM gates still fail on two things:
  - the offline cache `pacman -Sy` returns rc 1 in the live VM;
  - sshd must be masked (decision M2-openssh).
- The last builder died at the usage limit mid-build. /var/tmp/seclegion-build-j2d holds a reusable pkgcache. Its worktree is .claude/worktrees/agent-a880d726f25d1ada4; check it for uncommitted work.

OUTPUT:
- Commit plan-r14.md, plan-r14-debate.md and the decision entry.
- Report to the owner in plain words, under 300 words:
  - the installer choice and why;
  - the checkpoint list;
  - total hours and the critical path;
  - what the owner must do, and when.
- Then start the first checkpoint's jobs with 2 Sonnet builders, without asking further questions.
