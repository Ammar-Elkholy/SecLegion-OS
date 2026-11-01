# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-hwreport: a redacted hardware report for community GitHub issues.

Contains: PCI IDs and classes, CPU vendor/model, an allowlist of DMI strings, kernel flavour,
display geometry, and the plan. Never contains serials, UUIDs, MAC addresses, hostnames, user names.
There is no network code in this program: the user reads the output and posts it themselves.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from . import detect, engine, system

REPORT_SCHEMA = 1
NOTICE = "Redacted by seclegion-hwreport. It is never uploaded; review it, then attach it to your report."
MAC_RE = re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.IGNORECASE)
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
HOME_RE = re.compile(r"/(?:home|run/user)/[^/\s\"']+")
REDACTED = "[redacted]"


def sensitive_values(root):
    """Exact strings that identify this machine or its owner (read only to be scrubbed out)."""
    root = Path(root)
    found = set()
    for rel in (
        "sys/class/dmi/id/product_serial",
        "sys/class/dmi/id/product_uuid",
        "sys/class/dmi/id/board_serial",
        "sys/class/dmi/id/chassis_serial",
        "sys/class/dmi/id/chassis_asset_tag",
        "proc/sys/kernel/hostname",
        "etc/hostname",
        "etc/machine-id",
    ):
        found.add(system.read_text(root / rel))
    net = root / "sys/class/net"
    for entry in sorted(net.iterdir()) if net.is_dir() else []:
        found.add(system.read_text(entry / "address"))
    return {v for v in found if len(v) >= 4}


def scrub(value, secrets):
    """Recursively replace known secrets and anything shaped like a MAC, UUID or home path."""
    if isinstance(value, dict):
        return {scrub(k, secrets): scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, REDACTED)
        value = MAC_RE.sub(REDACTED, value)
        value = UUID_RE.sub(REDACTED, value)
        return HOME_RE.sub(lambda m: m.group(0).rsplit("/", 1)[0] + "/[user]", value)
    return value


def build_report(root, hw_dir, extra_rules=()):
    plan = detect.build_plan(root, hw_dir, extra_rules)
    facts = engine.collect(root, engine.load_nvidia_table(Path(hw_dir) / "nvidia-table.toml"))
    report = {
        "schema": REPORT_SCHEMA,
        "notice": NOTICE,
        "dmi": facts["dmi"],
        "cpu": {"vendor": facts["cpu"]["vendor"], "model": facts["cpu"]["model"]},
        "kernel_release": facts["kernel_release"],
        "pci": [
            {k: d[k] for k in ("pci_id", "class", "subsystem_vendor", "subsystem_device", "boot_vga")}
            for d in facts["pci"]
        ],
        "plan": plan,
    }
    return scrub(report, sensitive_values(root))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="seclegion-hwreport", description=__doc__)
    detect.add_common_args(parser)
    parser.add_argument("-o", "--output", metavar="FILE", help="write here instead of stdout")
    parser.add_argument("--force", action="store_true", help="overwrite FILE if it exists")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.root, args.hw_dir, args.rules)
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            with open(args.output, "w" if args.force else "x") as handle:
                handle.write(text)
        else:
            sys.stdout.write(text)
    except (OSError, engine.RulesError, KeyError) as err:
        print(f"seclegion-hwreport: {err}", file=sys.stderr)
        return 2
    return 0
