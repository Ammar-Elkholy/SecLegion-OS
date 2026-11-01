# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G45b: one session only (owner decision O9b). Hyprland through uwsm, no other desktop or display manager."""

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import post  # noqa: E402

FORBIDDEN = re.compile(r"^(gnome-session|gdm|gnome-shell|sddm|lightdm|plasma[\w-]*)$")
LISTS = glob.glob(os.path.join(REPO, "iso", "packages", "*.list")) + [
    os.path.join(REPO, "iso", "profile", "packages.x86_64"),
    os.path.join(REPO, "installer", "installd", "post-packages.list"),
]


def _names(text):
    out = []
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append(re.split(r"[<>=\s]", line)[0])
    return out


def _bad(names):
    return [n for n in names if FORBIDDEN.match(n)]


def _pkgbuild_depends(text):
    out = []
    for m in re.finditer(r"^\s*(?:depends|optdepends)=\(([^)]*)\)", text, re.M):
        out += [re.split(r"[<>=:]", t.strip("'\""))[0] for t in m.group(1).split()]
    return out


def test_single_session_package_lists_clean():
    assert len(LISTS) >= 5
    for path in LISTS:
        assert not _bad(_names(open(path, encoding="utf-8").read())), path


def test_single_session_pkgbuild_depends_clean():
    paths = glob.glob(os.path.join(REPO, "pkgs", "seclegion-*", "PKGBUILD"))
    assert paths
    for path in paths:
        assert not _bad(_pkgbuild_depends(open(path, encoding="utf-8").read())), path


def test_single_session_detector_catches_gdm():
    assert _bad(_names("hyprland\ngdm  # x\n")) == ["gdm"]
    assert _bad(_pkgbuild_depends("depends=('bash' 'sddm')")) == ["sddm"]


def test_single_session_only_hyprland_via_uwsm():
    assert re.findall(r"^Exec=(.*)$", post.SESSION_FILE, re.M) == ["uwsm start -- hyprland.desktop"]
    src = open(os.path.join(REPO, "installer", "installd", "post.py"), encoding="utf-8").read()
    writes = re.findall(r'self\.write\("(etc/greetd/sessions/[^"]+)"', src)
    assert writes == ["etc/greetd/sessions/hyprland.desktop"]


def test_single_session_greeter_points_at_single_file_dir():
    assert "SESSION_DIRS=/etc/greetd/sessions" in post.GREETER_CMD
    assert not re.search(r"SESSION_DIRS=\S*(wayland-sessions|:)", post.GREETER_CMD)


def test_single_session_no_package_ships_a_wayland_session():
    for root in ("pkgs", "iso", "installer", "desktop"):
        for dirpath, _dirs, files in os.walk(os.path.join(REPO, root)):
            if "wayland-sessions" in dirpath or "xsessions" in dirpath:
                assert not files, dirpath
    for path in glob.glob(os.path.join(REPO, "pkgs", "*", "PKGBUILD")):
        assert not re.search(r"wayland-sessions|xsessions", open(path, encoding="utf-8").read()), path
