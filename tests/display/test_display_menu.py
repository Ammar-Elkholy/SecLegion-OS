# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""desktop/display/seclegion-display-menu (owner issue 14): the pure renderer, and the menu against
a stub hyprctl and a stub rofi. Nothing reaches a real Hyprland: SL_HYPRCTL points at the stub."""

import fcntl
import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

MENU = Path(__file__).resolve().parents[2] / "desktop/display/seclegion-display-menu"
_loader = SourceFileLoader("seclegion_display_menu", str(MENU))
dm = module_from_spec(spec_from_loader(_loader.name, _loader))
_loader.exec_module(dm)


def mon(name, mid, disabled=False, mirror="none", scale=1.2):
    return {"id": mid, "name": name, "width": 2560, "height": 1600, "refreshRate": 165.0,
            "scale": scale, "disabled": disabled, "mirrorOf": mirror}


EDP, HDMI = mon("eDP-1", 0), mon("HDMI-A-1", 1, scale=1.0)
ON = 'hl.monitor({{ output = "{}", disabled = false, mirror = "", mode = "2560x1600@165.00", scale = {} }})'
ON_EDP, ON_HDMI = ON.format("eDP-1", "1.2"), ON.format("HDMI-A-1", "1")
WS = [{"id": 1, "monitor": "eDP-1"}, {"id": 4, "monitor": "HDMI-A-1"}, {"id": 2, "monitor": "HDMI-A-1"},
      {"id": -98, "monitor": "HDMI-A-1"}]


def move(ws, m):
    return ["dispatch", f'hl.dsp.workspace.move({{ workspace = "{ws}", monitor = "{m}" }})']


def focus(m):
    return ["dispatch", f'hl.dsp.focus({{ monitor = "{m}" }})']


def off(m):
    return ["eval", f'hl.monitor({{ output = "{m}", disabled = true }})']


def test_render_mode_laptop_moves_workspaces_home_before_disabling_the_external():
    assert dm.render("laptop", [EDP, HDMI], WS) == [
        ["eval", ON_EDP], move(2, "eDP-1"), move(4, "eDP-1"), off("HDMI-A-1"), focus("eDP-1")]


def test_render_mode_extend_enables_both_and_stops_mirroring():
    mirrored = dict(HDMI, mirrorOf="0")
    assert dm.render("extend", [EDP, mirrored], WS) == [["eval", ON_EDP], ["eval", ON_HDMI], focus("eDP-1")]


def test_render_mode_mirror_mirrors_edp_onto_the_external():
    calls = dm.render("mirror", [EDP, HDMI], WS)
    assert calls == [["eval", ON_EDP], move(2, "eDP-1"), move(4, "eDP-1"),
                     ["eval", ON_HDMI.replace('mirror = ""', 'mirror = "eDP-1"')], focus("eDP-1")]


def test_render_mode_external_enables_it_first_then_moves_and_disables_the_laptop():
    hdmi_off = dict(HDMI, disabled=True)
    assert dm.render("external", [EDP, hdmi_off], WS) == [
        ["eval", ON_HDMI], move(1, "HDMI-A-1"), off("eDP-1"), focus("HDMI-A-1")]


def test_render_mode_external_restore_brings_the_laptop_back_when_no_external_is_on():
    edp_off = dict(EDP, disabled=True)
    fallback = mon("FALLBACK", 2)
    back = [["eval", ON_EDP], focus("eDP-1")]
    assert dm.restore([edp_off, dict(HDMI, disabled=True), fallback]) == back
    assert dm.restore([edp_off, dict(HDMI, mirrorOf="0")]) == back
    assert dm.restore([edp_off, HDMI]) == []


def test_render_mode_single_monitor_offers_nothing():
    for mode in dm.MODES:
        assert dm.render(mode, [EDP], WS) == []
        assert dm.render(mode, [HDMI], WS) == []   # no laptop screen: nothing to fall back on
    with pytest.raises(ValueError):
        dm.render("bogus", [EDP, HDMI])


def test_render_mode_internal_override_and_fallback_is_ignored():
    a, b = mon("WAYLAND-1", 0), mon("HEADLESS-2", 1)
    calls = dm.render("laptop", [a, b, mon("FALLBACK", 3)], [], internal="WAYLAND-1")
    assert calls[-2:] == [off("HEADLESS-2"), focus("WAYLAND-1")]


# ---- the menu, against stubs -------------------------------------------------------------------

STUB = r'''
import json, sys
from pathlib import Path
d = Path(sys.argv[1]); args = sys.argv[2:]
with open(d / "calls.log", "a") as f:
    f.write(json.dumps(args) + "\n")
state = json.loads((d / "state.json").read_text())
if args[:3] == ["-j", "monitors", "all"]:
    print(json.dumps(state["monitors"]))
elif args[:2] == ["-j", "workspaces"]:
    print(json.dumps(state["workspaces"]))
else:
    print("ok")
'''


@pytest.fixture
def env(tmp_path):
    (tmp_path / "stub.py").write_text(STUB)
    rofi = tmp_path / "rofi"
    rofi.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$(dirname "$0")/rofi.args"\n'
                    'cat > "$(dirname "$0")/rofi.in"\ncat "$(dirname "$0")/pick" 2>/dev/null\n')
    rofi.chmod(0o755)
    e = {k: v for k, v in os.environ.items() if not k.startswith(("HYPRLAND_", "GIT_"))}
    e.update(SL_HYPRCTL=f"{sys.executable} {tmp_path / 'stub.py'} {tmp_path}", SL_ROFI=str(rofi),
             SL_LOCK=str(tmp_path / "menu.lock"), SL_SETTLE="0")
    return tmp_path, e


def run_menu(d, e, monitors, *args, pick=None):
    (d / "state.json").write_text(json.dumps({"monitors": monitors, "workspaces": WS}))
    if pick is not None:
        (d / "pick").write_text(pick + "\n")
    r = subprocess.run([sys.executable, str(MENU), *args], env=e, capture_output=True, text=True,
                       timeout=30)
    log = d / "calls.log"
    calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return r, [c for c in calls if c[0] != "-j"]


def test_menu_applies_the_picked_mode(env):
    d, e = env
    r, calls = run_menu(d, e, [EDP, HDMI], pick="Laptop only")
    assert r.returncode == 0, r.stderr
    assert (d / "rofi.in").read_text().splitlines() == list(dm.MODES.values())
    assert calls == dm.render("laptop", [EDP, HDMI], WS)


def test_menu_with_one_monitor_says_so_and_runs_nothing(env):
    d, e = env
    r, calls = run_menu(d, e, [EDP], pick="Laptop only")
    assert r.returncode == 0 and calls == []
    assert "Only one display is connected (eDP-1)" in (d / "rofi.args").read_text()
    assert (d / "rofi.in").read_text() == ""


def test_menu_external_only_restores_the_laptop_when_the_external_stays_off(env):
    # the stub never changes state: the external stays disabled, so the laptop must come back
    d, e = env
    edp_off, hdmi_off = dict(EDP, disabled=True), dict(HDMI, disabled=True)
    r, calls = run_menu(d, e, [edp_off, hdmi_off], "external")
    assert r.returncode == 1 and "laptop screen is back on" in r.stderr
    assert calls[-2:] == [["eval", ON_EDP], focus("eDP-1")]


def test_menu_second_instance_exits_without_acting(env):
    d, e = env
    with open(d / "menu.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r, calls = run_menu(d, e, [EDP, HDMI], "extend")
    assert r.returncode == 0 and calls == []
    r, calls = run_menu(d, e, [EDP, HDMI], "extend")
    assert calls == dm.render("extend", [EDP, HDMI], WS)
