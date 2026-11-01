# seclegion-hwdetect

Reads sysfs (or a fixture tree via `--root`) and applies the TOML rules in `hw/` to print a JSON plan:
`packages`, `kernel_params`, `services`, `udev_rules`, `env`, `settings`, `warnings`, `messages`, `boot_entries`, plus the
detected `facts`. Python (stdlib only) installs to `/usr/lib/seclegion/python`; the launchers in `bin/` run it with
`python3 -I`.

- `seclegion-hwdetect [--root R] [--hw-dir D] [--rules FILE_OR_DIR]...` prints the plan.
- `seclegion-barcheck [-o FILE [--force]]` runs the non-interactive daily-driver bar checks (B1-B13,
  docs/DAILY-DRIVER.md) read-only and prints `PASS|FAIL|SKIP <row> <check> — <detail>`; exit 0 only without a FAIL.
- `seclegion-hwreport [--root R] [-o FILE [--force]]` prints or writes a redacted JSON report (no serials,
  MACs, UUIDs, hostnames or user names) for community GitHub reports. It contains no network code and
  never uploads anything.

Build: `makepkg` from this directory inside the repository (it reads `../../hw`); `check()` compares the
NVIDIA table with `/usr/share/doc/nvidia/html/supportedchips.html` from `nvidia-utils`.
