# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-hwdetect: print the JSON plan for this machine (or for a fixture root)."""

import argparse
import json
import sys
from pathlib import Path

from . import DEFAULT_HW_DIR, engine


def build_plan(root, hw_dir, extra_rules=()):
    """Facts under `root` evaluated against the rules in `hw_dir` (+ extra rule files/dirs)."""
    hw_dir = Path(hw_dir)
    table = engine.load_nvidia_table(hw_dir / "nvidia-table.toml")
    rules = engine.load_rules(engine.default_rule_paths(hw_dir, extra_rules))
    return engine.evaluate(engine.collect(root, table), rules)


def add_common_args(parser):
    parser.add_argument("--root", default="/", help="sysfs/procfs root; a fixture dir with the same layout")
    parser.add_argument("--hw-dir", default=DEFAULT_HW_DIR, help="dir with rules.d/ and nvidia-table.toml")
    parser.add_argument("--rules", action="append", default=[], metavar="PATH",
                        help="extra rule file or directory (repeatable)")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="seclegion-hwdetect", description=__doc__)
    add_common_args(parser)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.root, args.hw_dir, args.rules)
    except (OSError, engine.RulesError, KeyError) as err:
        print(f"seclegion-hwdetect: {err}", file=sys.stderr)
        return 2
    json.dump(plan, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
