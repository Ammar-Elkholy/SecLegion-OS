# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Opt-in gaming package list: hwdetect's plan + the user's "gaming" answer -> extra packages.

Reads hw/gaming.toml (shipped at /usr/share/seclegion/hw/gaming.toml). Nothing here installs;
post.py appends the returned list to its package install only when hints carry gaming: true.
D-H1: the same opt-in also enables Arch's [multilib] in the installed pacman.conf; the [multilib]
packages (Steam) are not in the offline cache and install on the first online boot (multilib_packages).
"""

import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATHS = ("/usr/share/seclegion/hw/gaming.toml", os.path.join(HERE, "..", "..", "hw", "gaming.toml"))
NVIDIA_MODULES = ("nvidia-open", "nvidia-open-lts")


def load_manifest(path=None):
    for p in [path] if path else MANIFEST_PATHS:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    raise FileNotFoundError("gaming.toml not found")


def gaming_packages(gaming, manifest=None):
    """Extra packages for the opt-in gaming set; [] unless gaming is exactly True."""
    if gaming is not True:
        return []
    m = manifest or load_manifest()
    out = []
    for p in [*m["packages"]["official"], *m["packages"]["seclegion"]]:
        if p not in out:
            out.append(p)
    return out


def multilib_packages(gaming, manifest=None):
    """Packages that come from [multilib] on the first online boot; [] unless gaming is exactly True."""
    if gaming is not True:
        return []
    return list((manifest or load_manifest())["multilib"]["packages"])


def nvidia_view(plan):
    """What hwdetect's plan chose for NVIDIA: {"modules": [...], "message": str or None}."""
    msgs = plan.get("messages") or []
    return {
        "modules": [p for p in plan.get("packages", []) if p in NVIDIA_MODULES],
        "message": msgs[0] if msgs else None,
    }
