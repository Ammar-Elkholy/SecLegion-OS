# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Every package a hwdetect rule can add must be in the offline cache: the install has no network."""

from conftest import HW, REPO
from seclegion_hw import engine

LISTS = REPO / "iso" / "packages"
# Virtual names a rule uses that a cached package provides (checked with `pacman -Si mesa`:
# Provides libva-mesa-driver). `pacman -S libva-mesa-driver` installs mesa.
PROVIDED_BY = {"libva-mesa-driver": "mesa"}


def names(path):
    out = set()
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.add(line)
    return out


def rule_packages():
    rules = engine.load_rules(engine.default_rule_paths(HW))
    return {p for rule in rules for p in rule.get("add", {}).get("packages", [])}


def test_rule_packages_are_all_in_the_offline_cache_lists():
    have = names(LISTS / "base.list") | names(LISTS / "desktop.list") | names(LISTS / "cache.list")
    want = {PROVIDED_BY.get(p, p) for p in rule_packages()}
    assert want, "no rule adds a package: the rules did not load"
    missing = sorted(want - have)
    assert not missing, f"rule packages missing from the offline cache lists: {missing}"


def test_rule_packages_are_official_ones_only():
    assert not [p for p in rule_packages() if p.startswith("seclegion-")]
