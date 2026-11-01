# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-desktop ships seclegion-displayd (owner issue 15): the PKGBUILD's package() runs
against the repository as $srcdir into a tmp $pkgdir, without makepkg or root."""

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKGBUILD = ROOT / "pkgs/seclegion-desktop/PKGBUILD"
UNIT = "usr/lib/systemd/user/seclegion-displayd.service"


def test_pkg_ships_displayd(tmp_path):
    pkgdir = tmp_path / "pkg"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["bash", "-euo", "pipefail", "-c",
                        'source "$1"; srcdir="$2" pkgdir="$3"; package', "x",
                        str(PKGBUILD), str(ROOT), str(pkgdir)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    daemon = pkgdir / "usr/share/seclegion/display/seclegion-displayd"
    assert daemon.is_file() and stat.S_IMODE(daemon.stat().st_mode) == 0o755
    unit = (pkgdir / UNIT).read_text()
    assert "ExecStart=/usr/share/seclegion/display/seclegion-displayd\n" in unit
    assert "WantedBy=graphical-session.target" in unit and "PartOf=graphical-session.target" in unit
    wants = pkgdir / "usr/lib/systemd/user/graphical-session.target.wants/seclegion-displayd.service"
    assert os.readlink(wants) == "/" + UNIT
    assert "desktop/display" in (ROOT / "pkgs/seclegion-desktop/source.list").read_text().split()
