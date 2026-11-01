# TODO

## Now (M0 close-out)
- Owner/Sec review of the M0 branch `legion/m0-foundation`.
- Install host test packages if wanted: tesseract, tesseract-data-eng (OCR is optional and skipped when absent); swtpm and expect are not needed yet.

## Next
- S1: kiosk compositor runtime us/ara toggle (cage vs sway).
- M1: branded GRUB ISO with six entries, replacing the placeholder `iso/profile`.
- Pin an archive date and `SOURCE_DATE_EPOCH` from the commit for reproducible builds (A13).
- Hash-pin the dev tools in `requirements-dev.txt`.
- CI workflow running lint, unit tests and `verify-evidence --rows-only` (hosting not chosen, see S2).

## Deferred
- Everything in M2 onward, and 1.1/1.2 items (spec section 6).
- diffoscope reproducibility check (needs two builds; M12 gate).

## Requires owner approval
- Branding licence for the owner PNG assets (currently all rights reserved in REUSE).
- Host package installs (any `pacman` action; agents have no root).
- Repo hosting choice (spike S2) and signing key plan (spec A8).
- Any change to the owner's running system (live-host-first rule, backup and rollback required).
