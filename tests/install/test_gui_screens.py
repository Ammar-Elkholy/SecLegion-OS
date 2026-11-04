# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""gui_screens.py renders every installer page to PNG under Broadway (skipped, never faked, when Broadway or
gi is missing)."""

import json
import os
import shutil
import subprocess
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = ("welcome", "language", "disk", "disk-partition", "alongside", "encryption", "user", "hardware",
         "extras", "review", "review-partition", "progress", "finished", "error", "kiosk-error", "about")
ARABIC = ("welcome", "language", "disk", "review")


def _free_display():
    run = os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")
    for n in range(60, 90):
        if not os.path.exists(os.path.join(run, f"broadway{n}.socket")):
            return n
    return 60


@pytest.mark.skipif(not os.environ.get("SECLEGION_SCREENS"),
                    reason="3 minutes: opt in with SECLEGION_SCREENS=1 (D6 owner screenshots)")
def test_gui_screens_render_every_page_under_broadway(tmp_path):
    broadwayd = shutil.which("gtk4-broadwayd")
    py = "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi; gi.require_version('Gtk','4.0');"
                       "gi.require_version('Adw','1')"], capture_output=True).returncode:
        pytest.skip("gi GTK4/libadwaita not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    shots = tmp_path / "shots"
    n = _free_display()
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}",
               SCREENS=str(shots))
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "gui_screens.py")], env=env,
                           capture_output=True, text=True, timeout=600)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])["shots"]
    seen = {(s["page"], s["lang"], s["asked"]) for s in got}
    for asked in ("1280x800", "800x600"):
        for page in PAGES:
            assert (page, "en", asked) in seen, (page, asked)
        for page in ARABIC:
            assert (page, "ar", asked) in seen, (page, asked)
    for s in got:
        png = shots / s["file"]
        assert png.is_file() and png.stat().st_size > 1000, s["file"]
        assert f"-{s['width']}x{s['height']}-{s['lang']}.png" in s["file"]
        assert s["direction"] == ("rtl" if s["lang"] == "ar" else "ltr"), s["file"]
    assert any(s["page"] == "disk" and s["lang"] == "ar" and s["direction"] == "rtl" for s in got)
