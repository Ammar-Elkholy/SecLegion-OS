# hw

Data for `seclegion-hwdetect` (package: `pkgs/seclegion-hwdetect/`). Spec A10.

- `rules.d/*.toml`: rules in name order. Schema and match keys are documented in
  `pkgs/seclegion-hwdetect/python/seclegion_hw/engine.py`. A later job adds `hw/gaming.toml`; the loader
  already picks it up (see `EXTRA_RULE_FILES`), as does `--rules FILE_OR_DIR`.
- `nvidia-table.toml`: NVIDIA PCI device IDs by driver branch (Turing+ = `nvidia-open`, older = nouveau).
  `tools/check-nvidia-table <supportedchips.html>` fails on any disagreement with the vendor file;
  `--emit` regenerates the table. The vendor HTML is never committed.
- `rules.d/30-nvidia.toml` hybrid rule: `AQ_DRM_DEVICES` names `/dev/dri/seclegion-igpu` and `-dgpu` (Aquamarine splits the
  variable on `:`, so by-path names cannot be used); the plan's `udev_rules` create those links from the PCI addresses.
- `nvidia-html.sha256`: expected sha256 of the vendor file; `UNPINNED` until the release checkpoint pins it.
- `fixtures/<name>/root/`: sysfs/procfs trees (`--root`) for the M3 cases and the Legion Slim 5 16AHP9
  (hybrid and discrete MUX modes), each with `expected-plan.json`. PCI directories spell `0000:00:02.0` as `0000_00_02.0` (colons are not allowed on
  every filesystem). Serial, UUID, MAC and hostname values in them are decoys for the redaction tests.
  `fixtures/nvidia/` holds the synthetic HTML and table for the parser tests.

Tests: `pytest -q tests/hw`.
