# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOADER = ROOT / "pkgs/seclegion-dotfiles/skel/.config/hypr/hyprland.lua"
LUA = shutil.which("luajit") or shutil.which("lua")

STUB = """
order = {}
hl = { on = function() end, exec_cmd = function() end,
       bind = function(k) order[#order+1] = k end,
       dsp = { exec_cmd = function() end } }
package.preload["seclegion-host"] = function() order[#order+1] = "host" end
dofile(arg[1])
print(table.concat(order, ","))
"""


def test_user_lua_static_order():
    src = LOADER.read_text()
    assert src.rindex("user.lua") > src.rindex("hl.bind(")
    assert "pcall(dofile, user)" in src
    assert 'exec_cmd("waybar")' not in src


@pytest.mark.skipif(not LUA, reason="no lua interpreter")
def test_user_lua_loaded_last_and_overrides(tmp_path):
    (tmp_path / ".config/hypr").mkdir(parents=True)
    (tmp_path / "stub.lua").write_text(STUB)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin"}

    def run():
        return subprocess.run(
            [LUA, str(tmp_path / "stub.lua"), str(LOADER)], env=env, capture_output=True, text=True
        )

    r = run()
    assert r.returncode == 0 and r.stdout.strip().endswith("SUPER + L")  # missing user.lua is fine
    (tmp_path / ".config/hypr/user.lua").write_text('order[#order+1] = "user"')
    assert run().stdout.strip().split(",")[-1] == "user"
    (tmp_path / ".config/hypr/user.lua").write_text("error('boom')")
    r = run()
    assert r.returncode == 0 and "user.lua failed" in r.stdout


def test_user_lua_units_present():
    for u in ("waybar", "swaync", "swayosd", "hypridle", "polkit-agent"):
        assert (ROOT / f"desktop/units/seclegion-{u}.service").is_file()
