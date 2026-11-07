# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_disk_page under system python3 with GDK_BACKEND=broadway: builds the disk page on the
partitions fixture at 1280x800 and 700x700, reports which partition rows are sensitive and what a click on
p5 does, prints JSON on the last line. DISK_SHOTS=<dir> also saves disk-1280.png / disk-700.png."""

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
    m.next()  # welcome, language, time zone, then the disk page
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
shot(win, "disk-1280.png")
win.destroy()
m, win = show(700, 700, True)
shot(win, "disk-700.png")
rows = [w for w in walk(win.holder.get_first_child()) if w.get_name().startswith("row:")]
out["narrow_ok"] = len(rows) == 6 and win.split.get_collapsed()
win.destroy()
# a refused disk still shows its analysis: the reason, the map and one read-only row per partition
refused = dict(facts, install_mode=False)
m = Model(refused)
win = InstallerWindow(app, m)
win.set_default_size(1280, 800)
win.present()
m.next()
m.next()
m.next()
win.render()
pump()
root = win.holder.get_first_child()
out["refused"] = {"why": any(w.get_name() == "why:" + NVME for w in walk(root)),
                  "maps": sum(1 for w in walk(root) if isinstance(w, Gtk.DrawingArea)),
                  "info": sorted(w.get_name() for w in walk(root) if w.get_name().startswith("info:"))}
win.destroy()
# shrink option (stubbed configurator.shrink_choices: the real one is on another branch)
import configurator as cfg  # noqa: E402


def _stub(disk, _facts):
    return [{"path": p["path"], "name": p["name"], "fstype": p.get("fstype"), "label": p.get("label"),
             "size": int(p["size"]), "min_size": 120 << 30, "max_size": int(p["size"]),
             "code": None if p["path"] == "/dev/nvme0n1p3" else "shrink_too_small"}
            for p in disk["children"]]


cfg.shrink_choices = _stub
m = Model(facts)
m.pages["disk"].set_disk(NVME)
win = InstallerWindow(app, m)
win.set_default_size(1280, 800)
win.present()
m.next()
m.next()
m.next()
win.render()
pump()
root = win.holder.get_first_child()
byname = {w.get_name(): w for w in walk(root) if w.get_name()}
byname["shrink:" + NVME].set_active(True)
pump(10)
byname = {w.get_name(): w for w in walk(root) if w.get_name()}
scale = byname["shrinkscale:" + NVME]
out["shrink"] = {"group_visible": byname["shrinkpart:/dev/nvme0n1p3"].get_mapped(),
                 "p5_sensitive": byname["shrinkpart:/dev/nvme0n1p5"].get_sensitive(),
                 "label": byname["shrinklabel:" + NVME].get_label(),
                 "range": [scale.get_adjustment().get_lower(), scale.get_adjustment().get_upper()],
                 "mode": m.pages["disk"].mode, "fragment": m.pages["disk"].fragment()}
scale.set_value(150)
pump(10)
out["shrink"]["moved"] = [byname["shrinklabel:" + NVME].get_label(), m.pages["disk"].fragment()["shrink_size"]]
win.destroy()
del cfg.shrink_choices
# alongside page: the disk map, the gap, the guide, all in rows
m = Model(facts)
m.pages["disk"].set_disk(NVME)
m.pages["disk"].set_mode("alongside")
win = InstallerWindow(app, m)
win.set_default_size(1280, 800)
win.present()
m.next()
m.next()
m.next()
m.next()  # the time zone page sits between language and disk
win.render()
pump()
root = win.holder.get_first_child()
out["alongside"] = {"key": m.current.key, "type": type(root).__name__,
                    "maps": sum(1 for w in walk(root) if isinstance(w, Gtk.DrawingArea)),
                    "groups": sum(1 for w in walk(root) if isinstance(w, Adw.PreferencesGroup))}
shot(win, "alongside-1280.png")
win.destroy()
# About: the header button presents an Adw.AboutDialog on the window
m = Model(facts)
win = InstallerWindow(app, m)
win.set_default_size(1280, 800)
win.present()
pump()
win.activate_action("win.about", None)
pump(80)
dlg = win.get_visible_dialog()
kind = "AdwAboutDialog" if isinstance(dlg, Adw.AboutDialog) else type(dlg).__name__
out["about"] = {"type": kind, "name": dlg.get_application_name() if dlg else None,
                "license": int(dlg.get_license_type()) if dlg else None,
                "mit": int(Gtk.License.MIT_X11), "version": dlg.get_version() if dlg else None,
                "site": dlg.get_website() if dlg else None}
shot(win, "about-1280.png")
win.destroy()
print(json.dumps(out))
