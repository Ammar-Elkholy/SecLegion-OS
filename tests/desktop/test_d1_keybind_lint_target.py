# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LINT = ROOT / "tools/seclegion-keys-lint"
OURS = ROOT / "desktop/hypr/seclegion-keys.lua"


def lint(tmp_path, owner, ours):
    o, u = tmp_path / "o.lua", tmp_path / "u.lua"
    o.write_text(owner)
    u.write_text(ours)
    return subprocess.run([sys.executable, str(LINT), str(o), str(u)], capture_output=True, text=True)


def test_keybind_lint_target_missing_binary_fails(tmp_path):
    r = lint(tmp_path, "", 'hl.bind("SUPER + F5", hl.dsp.exec_cmd("/nonexistent-bin --x"))\n')
    assert r.returncode == 1 and "missing-binary" in r.stdout


def test_keybind_lint_target_existing_binary_ok(tmp_path):
    r = lint(tmp_path, "", 'hl.bind("SUPER + F5", hl.dsp.exec_cmd("/usr/bin/env x"))\n')
    assert r.returncode == 0, r.stdout


def test_keybind_lint_target_us_and_ara_layouts(tmp_path):
    # parenleft is code:18 on us and code:19 on ara; every spelling must collide with the keycode
    for owner_key in ("SUPER + SHIFT + parenleft", "SUPER + SHIFT + parenright", "SUPER + SHIFT + 9"):
        r = lint(tmp_path, f'hl.bind("{owner_key}", hl.dsp.exec_cmd("x"))\n',
                 'hl.bind("SUPER + SHIFT + code:18", hl.dsp.exec_cmd("y"))\n')
        assert r.returncode == 1 and "collisions=1" in r.stdout, owner_key
    r = lint(tmp_path, 'hl.bind("SUPER + 1", hl.dsp.exec_cmd("x"))\n',
             'hl.bind("SUPER + arabic_1", hl.dsp.exec_cmd("y"))\n')
    assert r.returncode == 1


def test_keybind_lint_target_real_keys_clean(tmp_path):
    r = lint(tmp_path, "", OURS.read_text())
    assert r.returncode == 0, r.stdout
