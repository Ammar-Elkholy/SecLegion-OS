# Previous project audit

Summary of [spec.md section 1](spec/v1/spec.md): the previous attempt (commit `3864099`) overclaimed
and was set aside; SecLegion OS is rebuilt clean-room on `clean-room-rebuild`. This restates the
spec's findings (claim versus code); it is not a fresh audit of that commit.

| Claimed / reported | Actual (per spec section 1) | Structural fix in this rebuild |
|---|---|---|
| Installer delivered | 6 of 15 installer screens existed | M4/M5 gate every screen with QMP + OCR evidence |
| Tests PASS | PASS by inspection; cited tests that do not exist | Evidence generated from `result.json`; hand-edited PASS fails `tools/verify-evidence` (M0) |
| (not claimed) | NOPASSWD sudo and empty passwords on the ISO and the installed system | `seclegion-live` owns live privileges; target checked for NOPASSWD, `nullok`, empty hash (M2, M4) |
| Installed system with LUKS | archiso initramfs hooks leaked into the target; LUKS unbootable | Target hook set fixed in A5; gate: no archiso in target (M4) |
| Package repo | Unsigned | `SigLevel = Required DatabaseRequired` gate (M3) |
| "Install" and "Live" modes | Identical | Separate boot entries and systemd targets; Install==Live is a mutation test |

Rule carried forward: nothing is reported done without generated evidence (spec section 7).
