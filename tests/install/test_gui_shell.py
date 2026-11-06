# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer window shell: theme CSS from the tokens (pure) and the sidebar/breakpoint under Broadway."""

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))
from theme import load_css  # noqa: E402

TOKENS = os.path.join(ROOT, "desktop", "theme", "tokens.toml")


def test_gui_shell_css_comes_from_the_tokens():
    css = load_css(TOKENS)
    assert "@define-color accent_bg_color #00FF88;" in css
    assert "@define-color window_bg_color #050F0E;" in css
    assert "@define-color accent_fg_color #050F0E;" in css
    for cls in (".step-done", ".step-current", ".step-todo"):
        assert cls in css


def _free_display():
    run = os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")
    for n in range(60, 90):
        if not os.path.exists(os.path.join(run, f"broadway{n}.socket")):
            return n
    return 60


def test_gui_shell_sidebar_and_breakpoint_under_broadway(tmp_path):
    broadwayd = shutil.which("gtk4-broadwayd")
    py = "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi; gi.require_version('Gtk','4.0');"
                       "gi.require_version('Adw','1')"], capture_output=True).returncode:
        pytest.skip("gi GTK4/libadwaita not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display()
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}")
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "gui_shell_probe.py")], env=env,
                           capture_output=True, text=True, timeout=90)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    wide, narrow = got["wide"], got["narrow"]
    assert not wide["collapsed"] and wide["sidebar_visible"]
    assert wide["rows"] == wide["visible"] and wide["title"]
    assert wide["row0"] == ["step-current"] and not wide["step_visible"]
    assert wide["after_next"] == [["step-done"], ["step-current"]]
    # kiosk: no close button (closing would end cage), and no Back on the first page
    assert wide["window_buttons"] is False
    assert wide["back_sensitive"] is False and wide["back_after_next"] is True
    assert narrow["collapsed"] and narrow["step_visible"]
    assert narrow["step"] == f"Step 2 of {narrow['n']}"
    # header: one menu button (Reboot / Power off / About), no standalone About button
    menu = got["menu"]
    assert menu["items"] == ["Reboot", "Power off", "About"]
    assert menu["actions"] == ["win.reboot", "win.poweroff", "win.about"]
    assert menu["tooltip"] == "Menu" and menu["icon"] == "open-menu-symbolic"
    assert menu["have"] == [True, True, True] and menu["labelled_buttons"] == []
    # no green Next on the progress and finished pages; Back is also gone on the finished page
    foot = got["footer"]
    assert foot["progress"]["next"] is False and foot["finished"]["next"] is False
    assert foot["finished"]["back"] is False and foot["welcome"]["next"] is True
    # a disk with no partitions: the replace-a-partition group is hidden (or absent)
    assert got["disk_empty"] and not any(got["disk_empty"])


def test_power_argv_for_reboot_and_poweroff():
    from pages.p13_finished import POWEROFF_ARGV, REBOOT_ARGV, power
    calls = []

    def runner(argv, check):
        calls.append((argv, check))

    power("reboot", runner)
    power("poweroff", runner)
    assert calls == [(["systemctl", "reboot"], False), (["systemctl", "poweroff"], False)]
    assert REBOOT_ARGV == ["systemctl", "reboot"] and POWEROFF_ARGV == ["systemctl", "poweroff"]


def test_power_rejects_an_unknown_action():
    from pages.p13_finished import power
    for bad in ("halt", "", None, "reboot; id"):
        with pytest.raises(ValueError):
            power(bad, runner=lambda *a, **k: pytest.fail("must not run"))
