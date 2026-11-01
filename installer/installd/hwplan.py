# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""hwdetect's plan for this machine, checked, for seclegion-post to apply to the target.

The plan comes from `seclegion-hwdetect` run inside the target (arch-chroot sees the same /sys and
/proc as the live system, and the rules are the ones of the package that gets installed). It is tool
output, but its values end up in a kernel command line, unit names and an environment file, so each
one is checked against a narrow pattern; one bad value rejects the whole plan.

Applied by post.py: packages, kernel_params, services, udev_rules, env. Logged only: warnings,
messages. Not used (no consumer exists yet): boot_entries, settings.
"""

import json
import re
import subprocess

TOOL = "seclegion-hwdetect"
TIMEOUT = 60  # seconds

PACKAGE = re.compile(r"[a-z0-9@._+-]+")
KERNEL_PARAM = re.compile(r"[A-Za-z0-9_.,:=/@+-]+")
UNIT = re.compile(r"[A-Za-z0-9@._:-]+\.(service|socket|timer|path|target)")
UDEV_GPU_RULE = re.compile(
    r'KERNEL=="card\*", KERNELS=="[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", SUBSYSTEM=="drm", '
    r'SUBSYSTEMS=="pci", SYMLINK\+="dri/seclegion-(igpu|dgpu)"'
)
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENV_VALUE = re.compile(r"[A-Za-z0-9_.,:=/@+\\-]*")  # environment.d(5): no spaces, quotes or $

EMPTY = {
    "packages": [], "kernel_params": [], "services": [], "udev_rules": [], "env": {},
    "warnings": [], "messages": [],
}


def _strings(plan, key, pattern):
    items = plan.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"plan {key!r} is not a list")
    for item in items:
        if not isinstance(item, str) or not pattern.fullmatch(item):
            raise ValueError(f"plan {key!r} has a bad entry: {item!r}")
    return list(dict.fromkeys(items))


def clean(plan):
    """The parts of the plan post applies, validated; ValueError when any value is unsafe."""
    if not isinstance(plan, dict):
        raise ValueError("plan is not an object")
    env = plan.get("env", {})
    if not isinstance(env, dict):
        raise ValueError("plan 'env' is not an object")
    for key, value in env.items():
        if not ENV_KEY.fullmatch(str(key)) or not isinstance(value, str) or not ENV_VALUE.fullmatch(value):
            raise ValueError(f"plan 'env' has a bad entry: {key!r}")
    return {
        "packages": _strings(plan, "packages", PACKAGE),
        "kernel_params": _strings(plan, "kernel_params", KERNEL_PARAM),
        "services": _strings(plan, "services", UNIT),
        "udev_rules": _strings(plan, "udev_rules", UDEV_GPU_RULE),
        "env": dict(sorted(env.items())),
        "warnings": [str(x) for x in plan.get("warnings", [])],
        "messages": [str(x) for x in plan.get("messages", [])],
    }


def fetch(root):
    """Run seclegion-hwdetect inside ROOT and return its plan, raw (post cleans it). Raises on failure."""
    r = subprocess.run(
        ["arch-chroot", root, TOOL], capture_output=True, text=True, check=True, timeout=TIMEOUT
    )
    return json.loads(r.stdout)
