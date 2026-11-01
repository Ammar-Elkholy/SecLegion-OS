# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-install-steam (D-H1) with a fake pacman. Names: test_install_steam_*."""

import os
import subprocess
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "pkgs" / "seclegion-gaming"


def run(tmp_path, conf, pacman_rc):
    (tmp_path / "pacman").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/calls\nexit {pacman_rc}\n')
    os.chmod(tmp_path / "pacman", 0o755)
    (tmp_path / "pacman.conf").write_text(conf)
    (tmp_path / "pending").write_text("steam\n")
    env = {
        **os.environ,
        "SECLEGION_PACMAN": str(tmp_path / "pacman"),
        "SECLEGION_PACMAN_CONF": str(tmp_path / "pacman.conf"),
        "SECLEGION_STEAM_PENDING": str(tmp_path / "pending"),
    }
    r = subprocess.run([str(PKG / "seclegion-install-steam")], env=env, capture_output=True, text=True)
    calls = (tmp_path / "calls").read_text() if (tmp_path / "calls").exists() else ""
    return r, calls, (tmp_path / "pending").exists()


def test_install_steam_success_clears_the_marker(tmp_path):
    r, calls, pending = run(tmp_path, "[multilib]\nInclude = /x\n", 0)
    assert r.returncode == 0 and calls.strip() == "-Syu --needed --noconfirm steam" and not pending


def test_install_steam_offline_keeps_marker_and_never_fails(tmp_path):
    r, _, pending = run(tmp_path, "[multilib]\nInclude = /x\n", 1)
    assert r.returncode == 0 and pending and "retry" in r.stderr


def test_install_steam_without_multilib_does_nothing(tmp_path):
    r, calls, pending = run(tmp_path, "#[multilib]\n#Include = /x\n", 0)
    assert r.returncode == 0 and calls == "" and pending


def test_install_steam_unit_is_conditional_and_ships():
    unit = (PKG / "seclegion-steam.service").read_text()
    assert "ConditionPathExists=/var/lib/seclegion/steam-pending" in unit
    assert "network-online.target" in unit
    assert "seclegion-install-steam" in (PKG / "PKGBUILD").read_text()
