# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""plan r12 P2: tools/seclegion-doctor reads saved facts and live state, and writes nothing."""

import json
import os
import subprocess
import sys

from tests.unit.conftest import REPO, load_tool

doctor = load_tool("seclegion-doctor")
TOOL = os.path.join(REPO, "tools", "seclegion-doctor")
FIX = os.path.join(REPO, "tests", "unit", "fixtures")


def run_fixture(name, *extra):
    p = subprocess.run(
        [sys.executable, "-B", TOOL, "--json", "--fixture", os.path.join(FIX, name), *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout


def levels(findings):
    return [(f["id"], f["level"]) for f in findings]


def test_doctor_duplicate_swaync_is_one_error():
    rc, out = run_fixture("doctor-dup.json")
    assert rc == 1
    assert out.count('"level":"error"') == 1
    data = json.loads(out)
    assert ("swaync", "error") in levels(data["findings"])
    assert all(lv == "ok" for i, lv in levels(data["findings"]) if i != "swaync")


def test_doctor_clean_facts_are_all_ok():
    facts = {
        "configerrors": "",
        "swaync": 1,
        "binds": [{"cmd": "kitty", "present": True}],
        "failed_units": [],
    }
    assert {f["level"] for f in doctor.analyse(facts)} == {"ok"}


def test_doctor_config_errors_missing_binds_and_failed_units():
    rc, out = run_fixture("doctor-bad.json")
    assert rc == 1
    got = levels(json.loads(out)["findings"])
    assert ("config", "error") in got
    assert ("binds", "warn") in got
    assert ("units", "warn") in got
    assert ("swaync", "ok") in got
    assert "nosuchprog" in out and "waybar.service" in out


def test_doctor_unknown_facts_are_warnings_not_errors():
    assert {f["level"] for f in doctor.analyse({})} == {"warn"}


def test_doctor_bad_fixture_is_exit_2(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text("[1]")
    assert (
        subprocess.run(
            [sys.executable, "-B", TOOL, "--fixture", str(bad)], capture_output=True, check=False
        ).returncode
        == 2
    )
    assert (
        subprocess.run([sys.executable, "-B", TOOL, "--bogus"], capture_output=True, check=False).returncode
        == 2
    )


def test_doctor_bind_commands_resolves_variables_and_literals():
    lua = (
        'local terminal = "kitty"\nlocal menu = "rofi -show drun"\n'
        'hl.bind(m .. " + T", hl.dsp.exec_cmd(terminal))\n'
        'hl.bind(m .. " + Y", hl.dsp.exec_cmd(terminal .. " -e yazi"))\n'
        'hl.bind(m .. " + D", hl.dsp.exec_cmd(menu))\n'
        'hl.bind(m .. " + B", hl.dsp.exec_cmd("brave || firefox"))\n'
        'hl.bind("SUPER + X", hl.dsp.exec_cmd("~/.local/bin/x"), { description = "d" })\n'
    )
    assert doctor.bind_commands(lua) == ["kitty", "rofi -show drun", "brave || firefox", "~/.local/bin/x"]


def test_doctor_command_present_alternatives(monkeypatch):
    monkeypatch.setattr(
        doctor.shutil, "which", lambda w, path=None: "/usr/bin/" + w if w == "firefox" else None
    )
    assert doctor.command_present("brave || firefox") is True
    assert doctor.command_present("brave || chrome") is False
    assert doctor.command_present("$HOME/x") is None


def tree(root):
    out = {}
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            st = os.lstat(p)
            out[p] = (st.st_mode, st.st_size, st.st_mtime_ns)
    return out


def test_doctor_readonly(tmp_path):
    """A live run in a scratch HOME and cwd changes nothing there, and only queries hyprctl / systemctl."""
    home, cwd, shim = tmp_path / "home", tmp_path / "cwd", tmp_path / "shim"
    log = tmp_path / "calls.log"
    for d in (home / ".config/hypr/modules", cwd, shim):
        d.mkdir(parents=True)
    (home / ".config/hypr/modules/keybinds.lua").write_text(
        'hl.bind("A", hl.dsp.exec_cmd("nosuchprog-zz"))\n'
    )
    for name in ("hyprctl", "systemctl"):
        sh = shim / name
        sh.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n')
        sh.chmod(0o755)
    before_home, before_cwd = tree(home), tree(cwd)
    env = {"HOME": str(home), "PATH": f"{shim}:/usr/bin:/bin", "SECRET_TOKEN": "hunter2-do-not-print"}
    p = subprocess.run(
        [sys.executable, "-B", TOOL, "--json"], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    assert p.returncode in (0, 1), p.stderr
    assert tree(home) == before_home and tree(cwd) == before_cwd
    assert "hunter2" not in p.stdout + p.stderr
    calls = log.read_text().splitlines()
    assert "hyprctl configerrors" in calls
    assert all(c == "hyprctl configerrors" or c.startswith("systemctl --user --failed") for c in calls), calls
    assert "nosuchprog-zz" in p.stdout


def test_doctor_readonly_source_has_no_write_or_dispatch():
    src = open(TOOL, encoding="utf-8").read().replace("(a query, never a dispatch/keyword/reload)", "")
    for bad in (
        "dispatch",
        "keyword",
        "reload",
        "sudo",
        "rmtree",
        "os.remove",
        "os.rename",
        ".write(",
        '"w"',
        "'w'",
        '"a"',
        "kill",
    ):
        assert bad not in src, bad
