# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Issue 14: the display menu binds (XF86Display locked, Super+Shift+P) are shipped, stay off the
owner's keys (Super+P is his pseudo bind, Super+Ctrl+P is the power profile) and are in the cheat
sheet."""
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop/keys-help/python"))

from seclegion_keys import cheatsheet as cs  # noqa: E402

KEYS = ROOT / "desktop/hypr/seclegion-keys.lua"
OWNER = ROOT / "tests/keys/fixtures/owner-keybinds.lua"
LINT = ROOT / "tools/seclegion-keys-lint"
MENU = "seclegion-display-menu"


def menu_binds():
    return [line for line in KEYS.read_text(encoding="utf-8").splitlines()
            if line.startswith("hl.bind(") and f'exec_cmd("{MENU}")' in line]


def test_display_keybind_xf86display_is_locked_and_super_shift_p_runs_the_menu():
    keys = {re.match(r'hl\.bind\("([^"]+)"', b).group(1): b for b in menu_binds()}
    assert set(keys) == {"XF86Display", "SUPER + SHIFT + P"}
    assert "locked = true" in keys["XF86Display"]
    assert (ROOT / "desktop/display" / MENU).stat().st_mode & 0o111


def test_display_keybind_never_takes_super_p_or_super_ctrl_p():
    text = KEYS.read_text(encoding="utf-8")
    assert not re.search(r'hl\.bind\("SUPER \+ P"', text)
    ctrl_p = re.findall(r'hl\.bind\("SUPER \+ CONTROL \+ P", hl\.dsp\.exec_cmd\("([^"]+)"', text)
    assert ctrl_p == ["seclegion-power-profile cycle"]
    assert re.search(r'mainMod \.\. " \+ P"', OWNER.read_text(encoding="utf-8"))   # the owner's pseudo


def test_display_keybind_no_collision_with_the_owner_snapshot():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run([sys.executable, str(LINT), str(OWNER), str(KEYS)], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0 and "collisions=0" in r.stdout, r.stdout + r.stderr


def test_display_keybind_cheatsheet_lists_both_binds():
    binds = [b for b in cs.collect([str(KEYS)], use_runtime=False) if b["command"] == MENU]
    assert {b["keys"] for b in binds} == {"XF86Display", "SUPER + SHIFT + P"}
    assert all(b["description"].startswith("display menu") for b in binds)
