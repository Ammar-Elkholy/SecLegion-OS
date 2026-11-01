# Plan r14 debate record (Sec on Opus 5.5 vs Legion on Sonnet 5.5, 3 rounds)
Date: 2026-10-17. Result: plan-r14.md v4. Legion: AGREE after round 3 items 1, 3 and 4 were applied.

## Final positions
- Installer: option (a), own installd (D-R14-1). Legion accepted it in round 2.
- Execution: two lanes, at most 2 Sonnet builders at once. The owner first asked for series, then reversed that to lower wall-clock time.
- Testing: an ISO rebuild and the VM gates run once per checkpoint. Installer jobs iterate through I-devloop. Privilege, signing and disk gates are never skipped.
- Owner change after the debate (O9b): Hyprland is the only session. GNOME and M6g are dropped, and the greeter has no session selector.

## Round 1 (Legion on v0)
Legion found the series/parallel plan underspecified, file ownership shared between jobs, gates G18-G27 weak, scope missing (M7a, M9a, M10+, M12+, desktop leftovers), and no decision path for S7. Sec answered in v1 with single-owner files, the G18-G27 rewrite, the added scope, and an S7 decision entry.

## Round 2 (Legion on v1)
| Objection | Resolution in v2 |
|---|---|
| pacstrap cannot run in the container, so every installer fix costs an ISO rebuild | I-devloop: boot the checkpoint ISO once and mount `installer/` into the VM; R6 says no ISO rebuild between jobs |
| Checkpoint C too large (10 jobs, 39 h) | split into C1 (text install plus installed desktop) and C2 (GUI); cached installed-base qcow2 per checkpoint |
| 25 GiB space floor too low | R5: 35 GiB, stale build dirs deleted first, one VM of at most 8 GB |
| Gates that cannot pass or cannot fail (G13, G30, G61, G77, G47) | namcap allowlist; G30 lists 14 mutants; G61b nvidia/kernel pair; G77 `not-attested-by-design`; G47 clock defined |
| R3 and I2 overloaded | split into R3a/R3b and I2a/I2b; 25% contingency; rework cap of 2 |

## Round 3 (Legion on the v2 two-lane split)
| Objection | Resolution in v3 |
|---|---|
| R3a, R3b and R5 need R0 and R1 from lane A | lane A runs R0 → R1 first; lane B starts with R4 |
| The lock covered only ISO builds | R0: every docker-build, package build, VM run and base qcow2 takes the flock |
| `installer/ui`, `fixtures/ntfs`, `hw/` and `desktop/migrate` had owners in both lanes | R8 names the cross-lane exceptions; H1 moved to lane B (adds only `hw/gaming.toml`); migrations moved under `pkgs/seclegion-update/` |
| Lane A idles at C1/C2; the early lane B VM gates had no checkpoint | V2 and W3 fill lane A's waits, V1 moved to lane A at D; G54-G59 run at D and G62-G65 at E |
| Merge policy | R0a: only the main session merges, lanes rebase before each handoff, and no job starts on unmerged input |

## Open disagreements
None.
