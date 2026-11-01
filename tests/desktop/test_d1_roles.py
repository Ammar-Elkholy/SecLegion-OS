# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop"))
import roles_check as rc  # noqa: E402


def test_single_owner_real():
    assert rc.check(rc.load(), rc.package_lists()) == []


def test_single_owner_mako_fails():
    errs = rc.check(rc.load(), rc.package_lists() | {"mako"})
    assert any("more than one provider" in e for e in errs)


def test_single_owner_missing_package_and_binary():
    roles = rc.load()
    assert any("not in the package lists" in e for e in rc.check(roles, set()))
    errs = rc.check(roles, rc.package_lists(), files_of=lambda p: ["/usr/bin/other"])
    assert any("is not shipped by" in e for e in errs)


def test_single_owner_installed_binaries():
    def ql(pkg):
        r = subprocess.run(["pacman", "-Ql", pkg], capture_output=True, text=True)
        return [ln.split()[1] for ln in r.stdout.splitlines()] if r.returncode == 0 else None
    assert rc.check(rc.load(), rc.package_lists(), files_of=ql) == []


def test_single_owner_session_is_uwsm_one_file():
    src = (ROOT / "installer/installd/post.py").read_text()
    assert src.count("Exec=") == 1 and "Exec=uwsm start -- hyprland.desktop" in src
