# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""UI smoke test of seclegion-sysmon under a private gtk4-broadwayd (the pattern of
tests/install/test_gui_pages_a.py): never the live Wayland/X display. Skips when broadwayd, the system
python3 with GTK4 or psutil is missing."""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _free_display(run):
    return next(n for n in range(40, 90) if not os.path.exists(os.path.join(run, f"broadway{n}.socket")))


def test_sysmon_ui_smoke_under_broadway(tmp_path):
    broadwayd, py = shutil.which("gtk4-broadwayd"), "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi, psutil; gi.require_version('Gtk','4.0')"],
                      capture_output=True).returncode:
        pytest.skip("gi GTK4 or psutil not importable by system python3")
    drm = tmp_path / "drm"
    for card, vendor, status in (("card0", "0x10de", "suspended"), ("card1", "0x1002", "unsupported")):
        (drm / card / "device" / "power").mkdir(parents=True)
        (drm / card / "device" / "vendor").write_text(vendor + "\n")
        (drm / card / "device" / "power" / "runtime_status").write_text(status + "\n")
    (drm / "card1" / "device" / "gpu_busy_percent").write_text("12\n")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display(str(run))
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}",
               HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"))
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "sysmon_ui_probe.py"), str(drm)], env=env,
                           capture_output=True, text=True, timeout=60)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    print(json.dumps(got), file=sys.stderr)
    assert got["theme"] is True
    assert (got["polling_before_map"], got["polling_mapped"], got["polling_hidden"]) == (False, True, False)
    assert got["cpu_label"].endswith("%")
    assert got["gpu"] == [["AMD card1", ""], ["NVIDIA card0", "dGPU sleeping"]]
    assert (got["rows"], got["filtered"], got["first_by_cpu"]) == (2, 1, "mine")
    assert (got["other_user_end_enabled"], got["own_end_enabled"]) == (False, True)
    assert got["sent_after_cancel"] == []
    assert got["sent"] == [[4242, got["sigkill"]]]


def test_list_pages_needs_no_display():
    r = subprocess.run([sys.executable, "-m", "seclegion_sysmon", "--list-pages"],
                       capture_output=True, text=True, cwd=os.path.join(ROOT, "desktop", "sysmon"),
                       env={"PATH": os.environ.get("PATH", "")})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["overview", "gpu", "processes"]
