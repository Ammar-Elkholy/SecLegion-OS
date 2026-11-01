# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-keys cheat sheet: static Lua parse, JSON schema, availability, runtime merge, hyprctl argv."""

import json
import os
import re
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop", "keys-help", "python"))

from seclegion_keys import cheatsheet as cs  # noqa: E402

KEYS_LUA = os.path.join(ROOT, "desktop", "hypr", "seclegion-keys.lua")
FIELDS = {"keys", "dispatcher", "command", "description", "category", "available"}


def test_cheatsheet_static_parse_covers_every_bind_call():
    text = open(KEYS_LUA, encoding="utf-8").read()
    grep = len(re.findall(r"^\s*hl\.bind\(", text, re.M))
    binds = cs.collect([KEYS_LUA], use_runtime=False)
    assert grep > 0 and len(binds) >= grep


def test_cheatsheet_json_schema_fields():
    binds = cs.collect([KEYS_LUA], use_runtime=False)
    for b in binds:
        assert FIELDS <= set(b)
        assert isinstance(b["available"], bool)
        assert "_sig" not in b
    keys = {b["keys"] for b in binds}
    assert "SUPER + F1" in keys and "SUPER + ALT + R" in keys
    assert any(b["category"] == "Resize mode" for b in binds)


def test_cheatsheet_help_bind_is_in_repo_bind_file():
    b = [x for x in cs.collect([KEYS_LUA], use_runtime=False) if x["keys"] == "SUPER + F1"]
    assert len(b) == 1 and b[0]["command"] == "seclegion-keys"


def test_cheatsheet_missing_command_is_unavailable(tmp_path):
    f = tmp_path / "k.lua"
    f.write_text(
        'hl.bind("SUPER + X", hl.dsp.exec_cmd("no-such-cmd-seclegion"), { description = "gone" })\n'
        'hl.bind("SUPER + Y", hl.dsp.exec_cmd("sh -c true"), { description = "here" })\n'
        'hl.bind("SUPER + Z", hl.dsp.window.close(), { description = "builtin" })\n'
    )
    by = {b["keys"]: b for b in cs.collect([str(f)], use_runtime=False)}
    assert by["SUPER + X"]["available"] is False
    assert by["SUPER + Y"]["available"] is True
    assert by["SUPER + Z"]["available"] is True


RUNTIME = [
    {
        "modmask": 64,
        "key": "F1",
        "dispatcher": "exec",
        "arg": "seclegion-keys",
        "description": "dup",
        "submap": "",
    },
    {
        "modmask": 64 | 1,
        "key": "Q",
        "dispatcher": "killactive",
        "arg": "",
        "description": "runtime only",
        "submap": "",
    },
    {
        "modmask": 64,
        "key": "Z",
        "dispatcher": "exec",
        "arg": "no-such-cmd-seclegion",
        "description": "",
        "submap": "",
    },
]


def test_cheatsheet_merge_adds_runtime_only_without_duplicates(tmp_path):
    f = tmp_path / "k.lua"
    f.write_text('hl.bind("SUPER + F1", hl.dsp.exec_cmd("sh"), { description = "seclegion-keys: help" })\n')
    with (
        mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "x"}),
        mock.patch.object(
            cs.shutil, "which", side_effect=lambda c: "/usr/bin/hyprctl" if c == "hyprctl" else None
        ),
        mock.patch.object(cs.subprocess, "run") as run,
    ):
        run.return_value = mock.Mock(stdout=json.dumps(RUNTIME))
        binds = cs.collect([str(f)])
    keys = [b["keys"] for b in binds]
    assert keys.count("SUPER + F1") == 1
    assert "SUPER + SHIFT + Q" in keys and "SUPER + Z" in keys
    assert next(b for b in binds if b["keys"] == "SUPER + Z")["available"] is False
    assert next(b for b in binds if b["keys"] == "SUPER + F1")["source"] == "static"


def test_cheatsheet_static_only_without_instance(tmp_path):
    f = tmp_path / "k.lua"
    f.write_text('hl.bind("SUPER + F1", hl.dsp.window.close(), {})\n')
    env = {k: v for k, v in os.environ.items() if k != "HYPRLAND_INSTANCE_SIGNATURE"}
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(cs.subprocess, "run") as run:
        assert len(cs.collect([str(f)])) == 1
    run.assert_not_called()


def test_cheatsheet_only_ever_calls_hyprctl_binds_json(tmp_path):
    with (
        mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "x"}),
        mock.patch.object(cs.shutil, "which", return_value="/usr/bin/x"),
        mock.patch.object(cs.subprocess, "run") as run,
    ):
        run.return_value = mock.Mock(stdout="[]")
        cs.collect([KEYS_LUA])
        cs.main(["--list", "--file", KEYS_LUA])
    assert run.call_count >= 1
    for call in run.call_args_list:
        assert call.args[0] == ["hyprctl", "binds", "-j"]


def test_cheatsheet_merge_does_not_duplicate_lua_binds_from_a_real_capture():
    """binds -j reports Lua binds with key "" and keycode 0 (S8): they must match their static rows."""
    static = cs.parse_files([os.path.join(ROOT, "desktop", "hypr", "seclegion-keys.lua")])
    with open(os.path.join(ROOT, "tests", "desktop", "fixtures", "s8-nested-binds.json")) as fh:
        runtime = json.load(fh)
    merged = cs.merge(static, runtime)
    blank_dupes = [e for e in merged[len(static):]
                   if e["description"] in {s["description"] for s in static}]
    assert blank_dupes == []
