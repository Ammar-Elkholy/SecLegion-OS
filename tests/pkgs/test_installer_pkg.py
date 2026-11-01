# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The seclegion-installer package: the installer (installd + GTK GUI) ships on the ISO.

No container or makepkg: tools/pkg-source packs the tracked files exactly as the build does, the PKGBUILD's
package() runs in bash against that tree, and the installed layout is then exercised with an isolated
interpreter, the way the launchers run it.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.pkgs.test_packages import PKGS, REPO, clean_env, source_list, tracked, words

PKG = PKGS / "seclegion-installer"
LIB = "usr/lib/seclegion/installer"
SKIPPED = ("README.md", ".license")  # documentation and REUSE sidecars are not shipped


def runtime_files():
    """Every tracked installer file the package must ship: installd and the GUI, minus documentation."""
    files = tracked("installer/installd") + tracked("installer/ui")
    return [f for f in files if not f.endswith(SKIPPED) and "__pycache__" not in f]


@pytest.fixture(scope="module")
def pkgdir(tmp_path_factory):
    """package() of the PKGBUILD run on the tarball tools/pkg-source makes (the tarball is removed again)."""
    base = tmp_path_factory.mktemp("installer-pkg")
    srcdir, out = base / "src", base / "pkg"
    srcdir.mkdir()
    out.mkdir()
    tarball = PKG / "seclegion-src.tar.zst"
    try:
        r = subprocess.run([str(REPO / "tools" / "pkg-source"), "pkgs/seclegion-installer"],
                           capture_output=True, text=True, env=clean_env(SOURCE_DATE_EPOCH="1700000000"))
        assert r.returncode == 0, r.stderr
        subprocess.run(["tar", "--zstd", "-xf", str(tarball), "-C", str(srcdir)], check=True)
    finally:
        tarball.unlink(missing_ok=True)
    script = 'set -e; source "$1"; srcdir=$2; pkgdir=$3; package'
    r = subprocess.run(["bash", "-c", script, "x", str(PKG / "PKGBUILD"), str(srcdir), str(out)],
                       capture_output=True, text=True, env=clean_env())
    assert r.returncode == 0, r.stderr
    return out


def test_installer_pkg_is_a_package_with_a_source_list_and_only_arch_depends():
    text = (PKG / "PKGBUILD").read_text()
    assert re.search(r"^pkgname=seclegion-installer$", text, re.M)
    assert {"python", "python-gobject", "gtk4", "archinstall", "polkit"} <= set(words(text, "depends"))
    assert not [d for d in words(text, "depends") if d.startswith("seclegion")]  # pkgs/README.md
    listed = source_list(PKG)
    assert {"installer/installd", "installer/ui", "LICENSE"} <= set(listed)
    assert words(text, "source") == ["seclegion-src.tar.zst"]


def test_installer_pkg_ships_every_runtime_file(pkgdir):
    shipped = {p.relative_to(pkgdir / LIB).as_posix() for p in (pkgdir / LIB).rglob("*") if p.is_file()}
    want = {f.removeprefix("installer/") for f in runtime_files()}
    assert want, "no tracked installer files found"
    assert want <= shipped, f"not shipped: {sorted(want - shipped)}"
    assert shipped <= want, f"shipped but not tracked installer files: {sorted(shipped - want)}"
    for must in ("installd/seclegion-install", "installd/seclegion-post", "installd/post-packages.list",
                 "installd/configurator.py", "installd/post.py", "installd/gaming.py", "installd/virt.py",
                 "installd/release.py", "installd/facts.py", "installd/target_check.py",
                 "installd/winguide.py", "ui/seclegion-installer-gui", "ui/gtk/app.py", "ui/gtk/model.py",
                 "ui/gtk/pages/p9_progress.py", "ui/gtk/pages/p14_kiosk_error.py"):
        assert must in shipped, must


def test_installer_pkg_launchers_are_real_files_running_the_packaged_code(pkgdir):
    for name, target in (("seclegion-install", f"/{LIB}/installd/seclegion-install"),
                         ("seclegion-installer-gui", f"/{LIB}/ui/seclegion-installer-gui")):
        launcher = pkgdir / "usr" / "bin" / name
        assert launcher.is_file() and not launcher.is_symlink(), name  # pkexec and polkit name the path
        assert os.access(launcher, os.X_OK)
        assert launcher.read_text() == f'#!/bin/sh\nexec /usr/bin/python3 -I {target} "$@"\n'
        assert os.access(pkgdir / target.lstrip("/"), os.X_OK), target
    assert (pkgdir / "usr/share/licenses/seclegion-installer/LICENSE").is_file()


@pytest.mark.parametrize("tool", ["seclegion-install", "seclegion-post", "seclegion-configure"])
def test_installer_pkg_installd_runs_from_the_installed_layout(pkgdir, tool):
    """Every module installd imports is in the package: --help runs with -I from another directory."""
    script = pkgdir / LIB / "installd" / tool
    r = subprocess.run(["python3", "-I", str(script), "--help"], cwd="/", capture_output=True, text=True,
                       env=clean_env())
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout


def test_installer_pkg_gui_modules_import_from_the_installed_layout(pkgdir):
    """The GUI's sys.path set-up (ui/gtk, ui/../installd) finds the model and every page without GTK."""
    ui = pkgdir / LIB / "ui"
    probe = (
        "import os, sys\n"
        "src = open(sys.argv[1]).read().split('\\n\\n\\ndef main')[0]\n"
        "exec(compile(src, sys.argv[1], 'exec'), {'__file__': sys.argv[1]})\n"
        "import model, pages\n"
        "from pages import p9_progress, p14_kiosk_error\n"
        "print(p9_progress.KIOSK_INSTALLER)\n"
    )
    r = subprocess.run(["python3", "-I", "-c", probe, str(ui / "seclegion-installer-gui")], cwd="/",
                       capture_output=True, text=True, env=clean_env())
    assert r.returncode == 0, r.stderr
    assert "/usr/bin/seclegion-install" in r.stdout


def test_installer_pkg_is_on_the_iso_and_not_installed_on_the_target():
    iso = (REPO / "iso" / "packages" / "seclegion.list").read_text()
    assert re.search(r"^seclegion-installer$", iso, re.M)
    post = (REPO / "installer" / "installd" / "post-packages.list").read_text()
    assert "seclegion-installer" not in post
    assert Path(REPO / "iso/profile/packages.x86_64").read_text().count("seclegion-installer\n") == 1
