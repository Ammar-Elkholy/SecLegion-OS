# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_wifi_ui.py under a private Broadway display and a private session bus (never the live
session): `primary` is the running panel; it launches `second` twice, which is what a second click on
the bar module does, and prints one JSON line with what it saw. The NetworkManager client is replaced
by a no-op, so nothing here touches the host's Wi-Fi."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "desktop", "wifi"))
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib  # noqa: E402

Adw.init()
if Gdk.Display.get_default() is None:
    print("NO-DISPLAY")
    sys.exit(0)

from seclegion_wifi.ui import app as wifi_app  # noqa: E402
from seclegion_wifi.ui import window  # noqa: E402

mode = sys.argv[1]
presented = []

if mode == "second":
    def forbidden(*_a, **_k):  # a second launch must never build a window of its own
        os._exit(3)
    window.WifiWindow.__init__ = forbidden
else:
    window.WifiWindow.is_active = lambda self: False  # no window manager under Broadway: not focused
    real_present = window.WifiWindow.present

    def counting_present(self):
        presented.append(self)
        real_present(self)
    window.WifiWindow.present = counting_present

app = wifi_app.make_app(new_client=lambda _ready, _win: None)
if mode == "second":
    sys.exit(app.run(["seclegion-wifi"]))

state = {"step": 0, "procs": [], "rcs": [], "first": None}


def spawn():
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "second"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    state["procs"].append(p)


def tick():
    if state["step"] == 0:
        if not app.get_windows():
            return GLib.SOURCE_CONTINUE
        state["first"] = app.get_windows()[0]
        spawn()
        state["step"] = 1
    elif state["procs"][-1].poll() is not None:
        state["rcs"].append(state["procs"][-1].returncode)
        if len(state["procs"]) < 2:
            spawn()
        else:
            wins = app.get_windows()
            print(json.dumps({"second_rcs": state["rcs"], "windows": len(wins),
                              "same_window": wins[0] is state["first"], "presented": len(presented),
                              "stderr": [p.stderr.read()[-300:] for p in state["procs"]]}))
            app.quit()
            return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


def timed_out():
    print("TIMEOUT")
    app.quit()
    return GLib.SOURCE_REMOVE


GLib.timeout_add(100, tick)
GLib.timeout_add_seconds(30, timed_out)
sys.exit(app.run(["seclegion-wifi"]))
