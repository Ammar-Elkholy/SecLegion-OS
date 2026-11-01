# SecLegion OS

An Arch-based security distribution: a Hyprland desktop with a curated tool set, a
safe-by-default installer (erase, alongside in free space, or manual), btrfs snapshots,
and KVM labs. It is built for two audiences at once: experienced Linux/DevOps/security
professionals (nothing hides or blocks full control) and beginner students (defaults are
safe and self-explanatory).

**Status: pre-alpha, milestone M0 (project foundation). There is no SecLegion ISO yet.**
The only ISO the tree can build today is the stock Arch `releng` profile used as a
placeholder for the build/boot harness. Read [PROJECT_STATUS.md](PROJECT_STATUS.md) for what
is actually done, and [TESTING.md](TESTING.md) for generated evidence. Nothing is claimed
that is not backed by an `evidence/` record.

## How this project works

- Plan: [docs/spec/v1/spec.md](docs/spec/v1/spec.md) (binding), [full-plan.md](docs/spec/v1/full-plan.md),
  [owner directives](docs/spec/v1/owner-directives-r7.md). Decisions index: [docs/decisions.md](docs/decisions.md).
- Strict milestones M0-M12; nothing starts until the previous gate is green with evidence.
- Test results are generated (`tools/gen-testing-md`) and verified (`tools/verify-evidence`);
  a hand-edited PASS fails the check.

## Developing

```
make bootstrap   # create .venv with pytest, ruff, reuse, shellcheck (no root)
make lint        # shellcheck, ruff, reuse, container-start check
make test        # unit tests
make iso         # build the placeholder ISO in a pinned privileged container -> out/
make vm          # boot out/*.iso in QEMU/OVMF, record evidence
make evidence    # regenerate + verify TESTING.md
```

The ISO build needs the `docker` group, 25 GiB free on a Linux filesystem under
`/var/tmp` (never NTFS), and QEMU with edk2-ovmf for the boot test. See [docs/testing.md](docs/testing.md).

## Licence

MIT, see [LICENSE](LICENSE). Per-file licences are tracked with REUSE ([docs/PROVENANCE.md](docs/PROVENANCE.md)).
The owner's branding images are not yet licensed for redistribution.
