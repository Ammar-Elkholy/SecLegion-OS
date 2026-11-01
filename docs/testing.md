# Testing

Implements [spec.md section 7 and M0](spec/v1/spec.md). Generated results are in [TESTING.md](../TESTING.md) - never edit it by hand.

## Commands

| Command | What it does |
|---|---|
| `make bootstrap` | create `.venv` with pytest, ruff, reuse, shellcheck (pip; no root needed) |
| `make test` | pytest unit tests (`tests/unit`) |
| `make lint` | shellcheck, ruff, `reuse lint`, and the container-start check. A missing linter prints `WARNING: lint SKIPPED <tool>`; it never passes silently |
| `make iso` | `tools/build-iso`: build the ISO in a privileged container, output to `out/` |
| `make vm` | boot `out/*.iso` in QEMU/OVMF via `tests/iso`, write `evidence/M0-boot/<iso-sha256>/` |
| `make evidence` | regenerate TESTING.md and run `tools/verify-evidence` |

## Evidence

Each test writes `evidence/<test-id>/<iso-sha256>/result.json` (schema in `tools/lib/evidence.py`:
commit, ISO sha256, class, env, command, expected, actual, exit code, artifact sha256s). Only
`result.json` is tracked; artifacts (serial log, screendump) stay local and are re-hashed by
`tools/verify-evidence` (`--rows-only` for a fresh clone without artifacts). `PASS` requires exit
code 0 and at least one artifact; a test that did not run is recorded `NOT RUN`.

## Harness (`tests/lib`)

QEMU + OVMF as the invoking user, fresh copy of OVMF_VARS per run, QMP over an inherited
socketpair (send-key, screendump), serial over an inherited socketpair with event-driven
`wait_for(pattern)` (no sleeps), optional tesseract OCR (`SKIPPED: tesseract missing` if absent).
If OVMF is not installed the harness raises `OvmfNotFound`; it never assumes a path.

## Build container rules (docker group is root-equivalent)

Only `tools/docker-build.sh` may start a container: image pinned by digest, repository mounted
read-only, workdir under `/var/tmp` on ext4 (NTFS/fuseblk refused), no `$HOME`, `/` or `/etc` mounts,
output chowned to the user. `tools/check-container-start` (part of `make lint`) fails otherwise.
The wrapper's modes are `iso`, `theme` (only the GRUB theme and `out/grub-theme.sha256`, no ISO) and
`check`; the mode is a fixed word passed to `tools/container-build.sh`, never a caller-supplied flag.
