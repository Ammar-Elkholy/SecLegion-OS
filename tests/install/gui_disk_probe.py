# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_disk_page under system python3 with GDK_BACKEND=broadway: builds the disk page on the
partitions fixture at 1280x800 and 700x700, reports which partition rows are sensitive and what a click on
p5 does, prints JSON on the last line. DISK_SHOTS=<dir> also saves disk-1280x800.png / disk-700x700.png."""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "ui", "gtk"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from app import InstallerWindow  # noqa: E402
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
from model import Model  # noqa: E402
from theme import load_css  # noqa: E402

if not Gtk.init_check():
    print("NO-DISPLAY")
    sys.exit(3)
Adw.init()
Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
css = Gtk.CssProvider()
css.load_from_string(load_css())
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
with open(os.path.join(HERE, "fixtures", "facts_partitions.json")) as f:
    facts = json.load(f)
app = Adw.Application(application_id="org.seclegion.DiskProbe")
app.register(None)
ctx = GLib.MainContext.default()
NVME = "/dev/nvme0n1"


def pump(n=60):
    for _ in range(n):
        ctx.iteration(False)
        time.sleep(0.02)


def walk(w):
    yield w
    c = w.get_first_child()
    while c:
        yield from walk(c)
        c = c.get_next_sibling()


def shot(win, name):
    d = os.environ.get("DISK_SHOTS")
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    pump(60)
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(win).snapshot(snap, win.get_width(), win.get_height())
    win.get_native().get_renderer().render_texture(snap.to_node(), None).save_to_png(os.path.join(d, name))


def show(width, height, preselect):
    m = Model(facts)
    if preselect:
        m.pages["disk"].set_disk(NVME)
        m.pages["disk"].set_partition("/dev/nvme0n1p5")
    win = InstallerWindow(app, m)
    win.set_default_size(width, height)
    win.present()
    m.next()
    m.next()
    win.render()
    pump()
    return m, win


m, win = show(1280, 800, False)
page = m.pages["disk"]
page_root = win.holder.get_first_child()
out = {"disks": sum(1 for w in walk(page_root) if w.get_name().startswith("card:")),
       "maps": sum(1 for w in walk(page_root) if isinstance(w, Gtk.DrawingArea))}
radio = next(w for w in walk(page_root) if w.get_name() == "disk:" + NVME)
radio.set_active(True)
pump(10)
rows = {w.get_name()[4:]: w for w in walk(page_root) if w.get_name().startswith("row:")}
out["row_sensitive"] = {p: b.get_sensitive() for p, b in rows.items()}
for p in ("/dev/nvme0n1p3", "/dev/nvme0n1p5"):
    rows[p].set_active(True)
pump(10)
out["picked"] = page.partition
out["fragment"] = page.fragment()
out["next_enabled"] = win.nxt.get_sensitive()
win.destroy()
m, win = show(1280, 800, True)
shot(win, "disk-1280x800.png")
win.destroy()
m, win = show(700, 700, True)
shot(win, "disk-700x700.png")
rows = [w for w in walk(win.holder.get_first_child()) if w.get_name().startswith("row:")]
out["narrow_ok"] = len(rows) == 6 and win.split.get_collapsed()
win.destroy()
print(json.dumps(out))
