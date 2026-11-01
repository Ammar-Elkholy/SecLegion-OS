# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""A new user's hypridle has a config that locks on logind's Lock signal (found by the S7 VM lane:
without ~/.config/hypr/hypridle.conf, seclegion-hypridle.service exits 1 and idle never locks)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKEL = ROOT / "pkgs/seclegion-dotfiles/skel/.config/hypr/hypridle.conf"
PKGBUILD = ROOT / "pkgs/seclegion-dotfiles/PKGBUILD"
UNIT = ROOT / "desktop/units/seclegion-hypridle.service"
AUTOLOCK = ROOT / "desktop/idle/hypridle.conf.in"


def test_skel_hypridle_runs_hyprlock_on_lock():
    text = SKEL.read_text()
    assert re.search(r"^\s*lock_cmd\s*=\s*pidof hyprlock \|\| hyprlock\s*$", text, re.M)
    assert re.search(r"^\s*before_sleep_cmd\s*=\s*loginctl lock-session\s*$", text, re.M)


def test_dotfiles_package_installs_it_into_skel():
    assert ("$startdir/skel/.config/hypr/hypridle.conf\" \"$pkgdir/etc/skel/.config/hypr/hypridle.conf\""
            in PKGBUILD.read_text())


def test_the_unit_reads_the_user_config_and_the_autolock_timer_sends_lock_session():
    assert re.search(r"^ExecStart=/usr/bin/hypridle$", UNIT.read_text(), re.M)  # ~/.config/hypr/hypridle.conf
    assert "on-timeout = loginctl lock-session" in AUTOLOCK.read_text()
