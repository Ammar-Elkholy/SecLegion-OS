# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_gui_pages_a under system python3 (has gi) with GDK_BACKEND=broadway: renders each
page widget in a window, pumps the main loop, prints {page key: fragment} as JSON on the last line."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "ui", "gtk"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402
from model import Model  # noqa: E402
from view import build_widget  # noqa: E402

if not Gtk.init_check():
    print("NO-DISPLAY")
    sys.exit(3)
with open(os.path.join(HERE, "fixtures", "facts.json")) as f:
    facts = json.load(f)
facts["probes"] = {"/dev/vdb3": "clean", "/dev/vdb4": "clean"}
m = Model(facts)
m.pages["disk"].set_disk("/dev/disk/by-id/ata-QEMU_HARDDISK_vdb")
m.pages["disk"].set_mode("alongside")
m.open_manual()
m.pages["manual"].set_gap(0)
out = {}
for page in m.visible()[:5]:
    win = Gtk.Window()
    win.set_child(build_widget(page))
    win.present()
    ctx = GLib.MainContext.default()
    for _ in range(50):
        ctx.iteration(False)
    out[page.key] = page.fragment()
    win.destroy()
print(json.dumps(out))
