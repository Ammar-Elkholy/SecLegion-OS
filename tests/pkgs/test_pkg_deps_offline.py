# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Every Arch dependency of a seclegion-* package must be in the lists its install path reads.

A package that can reach the target installs offline from the cache, so its dependencies must be in the
offline cache lists (or the base meta). An ISO-only package (in iso/packages/seclegion.list, not in
installer/installd/post-packages.list: seclegion-installer) is installed by mkarchiso into the live system:
its dependencies must be in the ISO lists.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# members of the `base` meta package, which base.list installs
BASE_META = {"bash", "coreutils", "curl", "filesystem", "grep", "pacman", "sed", "systemd"}


def listed(lists=("base", "desktop", "cache")):
    names = set()
    for n in lists:
        for line in (REPO / "iso" / "packages" / f"{n}.list").read_text().splitlines():
            name = line.split("#")[0].strip()
            if name:
                names.add(name)
    return names


def names_in(path):
    return {ln.split("#")[0].strip() for ln in path.read_text().splitlines()} - {""}


def iso_only():
    on_iso = names_in(REPO / "iso" / "packages" / "seclegion.list")
    return on_iso - names_in(REPO / "installer" / "installd" / "post-packages.list")


def test_pkg_deps_of_seclegion_packages_are_in_the_offline_lists():
    cache, iso, only_iso, missing = listed(), listed(("base", "live", "desktop")), iso_only(), {}
    for pkgbuild in sorted((REPO / "pkgs").glob("seclegion-*/PKGBUILD")):
        have = (iso if pkgbuild.parent.name in only_iso else cache) | BASE_META
        m = re.search(r"^depends=\((.*?)\)", pkgbuild.read_text(), re.S | re.M)
        if not m:
            continue
        deps = [re.split(r"[<>=]", d.strip("'\""))[0] for d in m.group(1).split()]
        gone = [d for d in deps if d and not d.startswith("seclegion-") and d not in have]
        if gone:
            missing[pkgbuild.parent.name] = gone
    assert missing == {}


def test_pkg_deps_never_name_a_sibling_seclegion_package():
    """makepkg in the build container resolves depends from core/extra only, so a seclegion-* depend
    fails the package build (pkgs/README.md); siblings are installed together by the package lists."""
    bad = {}
    for pkgbuild in sorted((REPO / "pkgs").glob("seclegion-*/PKGBUILD")):
        m = re.search(r"^depends=\((.*?)\)", pkgbuild.read_text(), re.S | re.M)
        deps = [d.strip("'\"") for d in (m.group(1).split() if m else [])]
        sib = [d for d in deps if d.startswith("seclegion-")]
        if sib:
            bad[pkgbuild.parent.name] = sib
    assert bad == {}
