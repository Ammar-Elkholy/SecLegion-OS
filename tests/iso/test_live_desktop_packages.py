# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The live ISO installs the packages that provide the SecLegion desktop (no VM).

seclegion-live-session copies /etc/skel into the live home and starts Hyprland; without these packages
in the live root there is no skel hyprland.lua and no /usr/share/seclegion/hypr, i.e. stock Hyprland.
mkarchiso copies airootfs before pacstrap, so a path owned by both makes pacman fail ("exists in
filesystem").
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AIROOTFS = REPO / "iso" / "profile" / "airootfs"
LIVE_DESKTOP = ("seclegion-dotfiles", "seclegion-desktop", "seclegion-theme", "seclegion-branding")


def listed(path):
    return {ln.split("#")[0].strip() for ln in path.read_text().splitlines()} - {""}


def test_live_iso_installs_the_desktop_packages():
    assert set(LIVE_DESKTOP) <= listed(REPO / "iso" / "packages" / "seclegion.list")
    assert set(LIVE_DESKTOP) <= set((REPO / "iso/profile/packages.x86_64").read_text().split())


def _install_dests(pkgbuild):
    """Destination paths under $pkgdir named in package() (install targets and _tree prefixes)."""
    text = pkgbuild.read_text()
    text = text[text.index("package()"):].replace("\\\n", " ")
    dests = set()
    for m in re.finditer(r'"\$pkgdir/([^"]+)"', text):
        dests.add("/" + m.group(1).replace("$pkgname", pkgbuild.parent.name))
    for m in re.finditer(r"_tree\s+\S+\s+(\S+)", text):
        dests.add("/" + m.group(1).replace("$share", "usr/share/seclegion").strip('"'))
    return dests


def test_desktop_packages_own_no_path_of_the_airootfs():
    files = (p for p in AIROOTFS.rglob("*") if p.is_file() or p.is_symlink())
    airootfs = {"/" + str(p.relative_to(AIROOTFS)) for p in files}
    assert airootfs
    clashes = {}
    for name in LIVE_DESKTOP:
        dests = _install_dests(REPO / "pkgs" / name / "PKGBUILD")
        assert dests, f"{name}: no install destinations parsed"
        hit = sorted(a for a in airootfs for d in dests if a == d or a.startswith(d.rstrip("/") + "/"))
        if hit:
            clashes[name] = hit
    assert clashes == {}
