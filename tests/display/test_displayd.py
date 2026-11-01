# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""desktop/display/seclegion-displayd against fakes: a recording hyprctl stub (canned, stateful
JSON), a fake socket2 server, a fake DRM root and a fake udev monitor. Nothing reaches a real
Hyprland: SL_HYPRCTL and SL_SOCKET2 always point at the fakes."""

import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

DAEMON = Path(__file__).resolve().parents[2] / "desktop/display/seclegion-displayd"
DISABLE = 'hl.monitor({{ output = "{}", disabled = true }})'
ENABLE = 'hl.monitor({{ output = "{}", disabled = false }})'
MOVE = 'hl.dsp.workspace.move({{ workspace = "{}", monitor = "{}" }})'
FOCUS = 'hl.dsp.focus({{ monitor = "{}" }})'

# hyprctl stub: logs argv (one JSON list per line), answers -j queries from state.json, and
# applies hl.monitor({ output = N, disabled = X }) to the state like Hyprland would.
STUB = r'''
import json, re, sys
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
    m = re.search(r'output = "([^"]+)", disabled = (true|false)', " ".join(args))
    if args[0] == "eval" and m:
        for mon in state["monitors"]:
            if mon["name"] == m.group(1):
                mon["disabled"] = m.group(2) == "true"
        (d / "state.json").write_text(json.dumps(state))
    print("ok")
'''

# awww stub: logs argv (one JSON list per line) to <dir>/awww.log; fails while <dir>/awww-fail counts down
AWWW = r'''
import json, sys
from pathlib import Path
d = Path(sys.argv[1]); args = sys.argv[2:]
with open(d / "awww.log", "a") as f:
    f.write(json.dumps(args) + "\n")
fail = d / "awww-fail"
n = int(fail.read_text()) if fail.exists() else 0
if n > 0:
    fail.write_text(str(n - 1))
    print("output not found", file=sys.stderr)
    sys.exit(1)
'''

# fake udev monitor: prints one drm change line once <dir>/udev-go exists, then idles
UDEV = r'''
import os, sys, time
go = os.path.join(sys.argv[1], "udev-go")
print("monitor will print the received events for:", flush=True)
while not os.path.exists(go):
    time.sleep(0.05)
print("UDEV  [123.456] change   /devices/pci0000:00/0000:01:00.0/drm/card0 (drm)", flush=True)
time.sleep(3600)
'''


def mon(name, focused=False, disabled=False):
    return {"name": name, "focused": focused, "disabled": disabled}


def ws(wid, monitor):
    return {"id": wid, "name": str(wid), "monitor": monitor}


def wait_for(pred, timeout=6.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


class Rig:
    def __init__(self, d, monitors, workspaces, connectors):
        self.d = d
        (d / "state.json").write_text(json.dumps({"monitors": monitors, "workspaces": workspaces}))
        (d / "stub.py").write_text(STUB)
        (d / "udev.py").write_text(UDEV)
        (d / "awww.py").write_text(AWWW)
        self.wallpaper = d / "default.png"
        self.wallpaper.write_bytes(b"png")
        for name, status in connectors.items():
            self.connector(name, status)
        # AF_UNIX paths are short (108 bytes): the socket lives in its own short temp dir
        self.sock_dir = tempfile.mkdtemp(prefix="sl-displayd-")
        self.sock_path = os.path.join(self.sock_dir, "s2.sock")
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(self.sock_path)
        self.srv.listen(1)
        self.srv.settimeout(5)
        self.conn = None
        self.proc = None

    def connector(self, name, status):
        p = self.d / "drm" / f"card0-{name}"
        p.mkdir(parents=True, exist_ok=True)
        (p / "status").write_text(status + "\n")

    def start(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HYPRLAND_", "GIT_"))}
        env.update(
            SL_HYPRCTL=shlex.join([sys.executable, str(self.d / "stub.py"), str(self.d)]),
            SL_SOCKET2=self.sock_path,
            SL_DRM_ROOT=str(self.d / "drm"),
            SL_UDEV_CMD=shlex.join([sys.executable, str(self.d / "udev.py"), str(self.d)]),
            SL_STATE_DIR=str(self.d / "state"),
            # seclegion-wallpaper (started by the daemon) paints through the stub, never the live awww
            SL_AWWW=shlex.join([sys.executable, str(self.d / "awww.py"), str(self.d)]),
            SL_HOME=str(self.d / "home"),
            XDG_STATE_HOME=str(self.d / "xdg-state"),
            SL_DEFAULT_WALLPAPER=str(self.wallpaper),
        )
        env.update(extra)   # a case may override a hook (SL_SOCKET2="": follow the instance dirs)
        self.log = self.d / "daemon.log"
        self.proc = subprocess.Popen([sys.executable, str(DAEMON)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=self.log.open("w"))
        assert wait_for(lambda: "listening" in self.log.read_text()), self.log.read_text()
        self.conn, _ = self.srv.accept()

    def restart(self, **extra):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.conn.close()
        self.start(**extra)

    def send(self, line):
        self.conn.sendall(line.encode() + b"\n")

    def calls(self):
        p = self.d / "calls.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def actions(self):
        """dispatch/eval calls only (the -j queries are reads)."""
        return [c for c in self.calls() if c[0] in ("dispatch", "eval")]

    def awww(self):
        p = self.d / "awww.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def queries(self):
        return sum(1 for c in self.calls() if c[:3] == ["-j", "monitors", "all"])

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        for c in (self.conn, self.srv):
            if c:
                c.close()
        os.unlink(self.sock_path)
        os.rmdir(self.sock_dir)


@pytest.fixture
def rig(tmp_path):
    rigs = []

    def make(monitors, workspaces, connectors):
        r = Rig(tmp_path, monitors, workspaces, connectors)
        rigs.append(r)
        return r

    yield make
    for r in rigs:
        r.stop()


def test_ghost_moves_workspaces_to_focused(rig):
    r = rig([mon("eDP-1"), mon("DP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1"), ws(7, "HDMI-A-1"), ws(2, "DP-1")],
            {"eDP-1": "connected", "DP-1": "connected", "HDMI-A-1": "disconnected"})
    r.start()
    moves = [c for c in r.actions() if c[0] == "dispatch" and "workspace.move" in c[1]]
    assert moves == [["dispatch", MOVE.format(6, "DP-1")], ["dispatch", MOVE.format(7, "DP-1")]]


def test_ghost_none_focused_uses_first(rig):
    r = rig([mon("HDMI-A-1", focused=True), mon("eDP-1"), mon("DP-2")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "DP-2": "connected", "HDMI-A-1": "disconnected"})
    r.start()
    assert ["dispatch", MOVE.format(6, "eDP-1")] in r.actions()
    assert ["dispatch", FOCUS.format("eDP-1")] in r.actions()


def test_ghost_disabled_after_move(rig):
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1"), ws(8, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "disconnected"})
    r.start()
    assert r.actions() == [
        ["dispatch", MOVE.format(6, "eDP-1")],
        ["dispatch", MOVE.format(8, "eDP-1")],
        ["eval", DISABLE.format("HDMI-A-1")],
        ["dispatch", FOCUS.format("eDP-1")],
    ]


def test_ghost_disable_keeps_scale(rig):
    # the first runtime rule replaces the catch-all: without the scale a re-plug comes back at auto
    hdmi = dict(mon("HDMI-A-1"), scale=1.2)
    r = rig([mon("eDP-1", focused=True), hdmi], [ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "disconnected"})
    r.start()
    want = 'hl.monitor({ output = "HDMI-A-1", mode = "preferred", scale = 1.2, disabled = true })'
    assert ["eval", want] in r.actions(), r.actions()


def test_connected_monitor_untouched(rig):
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "connected"})
    r.start()
    assert r.queries() >= 1
    assert r.actions() == []


def test_unmapped_monitor_never_ghost(rig):
    # HEADLESS-2 / WAYLAND-1 have no DRM connector (nested, headless): never a ghost
    r = rig([mon("WAYLAND-1", focused=True), mon("HEADLESS-2")],
            [ws(1, "WAYLAND-1"), ws(7, "HEADLESS-2")],
            {"eDP-1": "disconnected", "HDMI-A-1": "disconnected"})
    r.start()
    assert r.queries() >= 1
    assert r.actions() == []


def test_all_ghost_does_nothing(rig):
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "disconnected", "HDMI-A-1": "disconnected"})
    r.start()
    assert r.queries() >= 1
    assert r.actions() == []
    assert "no other monitor" in r.log.read_text()


def test_udev_change_triggers_reconcile(rig):
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "connected"})
    r.start()
    start_queries = r.queries()
    r.connector("HDMI-A-1", "disconnected")
    time.sleep(1.0)   # no polling: a status change alone triggers nothing
    assert r.queries() == start_queries and r.actions() == []
    (r.d / "udev-go").touch()
    assert wait_for(lambda: ["eval", DISABLE.format("HDMI-A-1")] in r.actions()), r.log.read_text()
    assert r.actions()[0] == ["dispatch", MOVE.format(6, "eDP-1")]


def test_v2_event_parsed(rig):
    loader = SourceFileLoader("displayd", str(DAEMON))
    mod = module_from_spec(spec_from_loader("displayd", loader))
    loader.exec_module(mod)
    assert mod.parse_event("monitorremovedv2>>1,HDMI-A-1,Samsung, Inc. S24") == (
        "monitorremovedv2", "HDMI-A-1")
    assert mod.parse_event("monitorremoved>>HDMI-A-1") == ("monitorremoved", "HDMI-A-1")

    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "connected"})
    r.start()
    r.connector("HDMI-A-1", "disconnected")
    r.send("workspacev2>>6,6")   # not a monitor event: ignored
    r.send("monitorremovedv2>>1,HDMI-A-1,Samsung, Inc. S24")
    assert wait_for(lambda: ["eval", DISABLE.format("HDMI-A-1")] in r.actions()), r.log.read_text()
    # the reconcile logs after its last hyprctl call, so wait for the line too
    assert wait_for(lambda: "monitorremovedv2 HDMI-A-1" in r.log.read_text()), r.log.read_text()


def test_replugged_ghost_enabled_again(rig):
    # the runtime disable outlives the output, so a re-plugged connector must be enabled again
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "disconnected"})
    r.start()
    assert ["eval", DISABLE.format("HDMI-A-1")] in r.actions()
    r.connector("HDMI-A-1", "connected")
    r.send("monitoraddedv2>>1,HDMI-A-1,Samsung S24")
    assert wait_for(lambda: ["eval", ENABLE.format("HDMI-A-1")] in r.actions()), r.log.read_text()


def test_state_survives_restart(rig):
    # disabled_by_us is on disk: a restarted daemon still enables the monitor it disabled
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "disconnected"})
    r.start(HYPRLAND_INSTANCE_SIGNATURE="sig-a")
    assert ["eval", DISABLE.format("HDMI-A-1")] in r.actions()
    saved = json.loads((r.d / "state/displayd.json").read_text())
    assert saved == {"instance": "sig-a", "disabled": ["HDMI-A-1"]}
    r.restart(HYPRLAND_INSTANCE_SIGNATURE="sig-a")
    r.connector("HDMI-A-1", "connected")
    r.send("monitoraddedv2>>1,HDMI-A-1,Samsung S24")
    assert wait_for(lambda: ["eval", ENABLE.format("HDMI-A-1")] in r.actions()), r.log.read_text()
    assert json.loads((r.d / "state/displayd.json").read_text())["disabled"] == []


def test_state_of_another_instance_ignored(rig):
    # a new Hyprland reads its own config: a monitor disabled there is not ours to enable
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1", disabled=True)],
            [ws(1, "eDP-1")],
            {"eDP-1": "connected", "HDMI-A-1": "connected"})
    (r.d / "state").mkdir()
    (r.d / "state/displayd.json").write_text(json.dumps({"instance": "old", "disabled": ["HDMI-A-1"]}))
    r.start(HYPRLAND_INSTANCE_SIGNATURE="new")
    r.send("monitoraddedv2>>1,HDMI-A-1,Samsung S24")
    time.sleep(1.0)
    assert r.actions() == []


def test_no_signature_exits(tmp_path):
    # started before the session exported HYPRLAND_INSTANCE_SIGNATURE: exit 1, the unit retries
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HYPRLAND_", "GIT_", "SL_"))}
    env.update(SL_HYPRCTL="false", SL_STATE_DIR=str(tmp_path))
    p = subprocess.run([sys.executable, str(DAEMON)], env=env, capture_output=True, text=True, timeout=10)
    assert p.returncode == 1 and "HYPRLAND_INSTANCE_SIGNATURE is not set" in p.stderr


def test_stale_signature_follows_newest_instance(rig):
    # Hyprland restarted under a lingering user manager: the old signature's socket2 is gone, so the
    # daemon follows the instance that accepts, with that instance's signature in its state record
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")],
            [ws(1, "eDP-1"), ws(6, "HDMI-A-1")],
            {"eDP-1": "connected", "HDMI-A-1": "connected"})
    rt = Path(tempfile.mkdtemp(prefix="sl-rt-"))
    try:
        (rt / "hypr/old").mkdir(parents=True)
        (rt / "hypr/new").mkdir()
        (rt / "hypr/new/.socket2.sock").symlink_to(r.sock_path)
        r.start(SL_SOCKET2="", XDG_RUNTIME_DIR=str(rt), HYPRLAND_INSTANCE_SIGNATURE="old")
        assert "following Hyprland instance new" in r.log.read_text()
        r.connector("HDMI-A-1", "disconnected")
        r.send("monitorremovedv2>>1,HDMI-A-1,Samsung S24")
        assert wait_for(lambda: (r.d / "state/displayd.json").exists()), r.log.read_text()
        saved = json.loads((r.d / "state/displayd.json").read_text())
        assert saved == {"instance": "new", "disabled": ["HDMI-A-1"]}
    finally:
        (rt / "hypr/new/.socket2.sock").unlink()
        for d in ("hypr/new", "hypr/old", "hypr", "."):
            (rt / d).rmdir()
