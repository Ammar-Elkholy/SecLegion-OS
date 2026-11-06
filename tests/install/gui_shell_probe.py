# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_gui_shell under system python3 with GDK_BACKEND=broadway: builds the installer window at
1280 and 700 px wide, prints a JSON summary on the last line. SHELL_SHOTS=<dir> also saves PNGs."""

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
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                          Gtk.STYLE_PROVIDER_PRIORITY_USER)
with open(os.path.join(HERE, "fixtures", "facts.json")) as f:
    facts = json.load(f)
app = Adw.Application(application_id="org.seclegion.InstallerProbe")
app.register(None)
ctx = GLib.MainContext.default()


def pump(n=100):
    for _ in range(n):
        ctx.iteration(False)
        time.sleep(0.02)


def classes(row):
    return sorted(c for c in row.get_css_classes() if c.startswith("step-"))


def shot(win, name):
    d = os.environ.get("SHELL_SHOTS")
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    pump(100)
    w, h = win.get_width(), win.get_height()
    paintable = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    tex = win.get_native().get_renderer().render_texture(snap.to_node(), None)
    tex.save_to_png(os.path.join(d, name))


def window(width, height):
    m = Model(facts)
    win = InstallerWindow(app, m)
    win.set_default_size(width, height)
    win.present()
    pump()
    return m, win


out = {}
m, win = window(1280, 800)
out["wide"] = {
    "collapsed": win.split.get_collapsed(), "sidebar_visible": win.sidebar.get_mapped(),
    "rows": len(win.sidebar.rows), "visible": len(m.visible()), "row0": classes(win.sidebar.rows[0]),
    "title": win.title_label.get_label(), "step_visible": win.step_label.get_visible(),
    "back_sensitive": win.back.get_sensitive(),
    "window_buttons": win.header.get_show_start_title_buttons() or win.header.get_show_end_title_buttons(),
}
shot(win, "shell-1280.png")
m.next()
win.refresh_nav()
out["wide"]["after_next"] = [classes(win.sidebar.rows[0]), classes(win.sidebar.rows[1])]
out["wide"]["back_after_next"] = win.back.get_sensitive()
win.destroy()
m, win = window(700, 700)
m.next()
win.refresh_nav()
pump()
out["narrow"] = {
    "collapsed": win.split.get_collapsed(), "step": win.step_label.get_label(),
    "step_visible": win.step_label.get_visible(), "n": len(m.visible()),
}
shot(win, "shell-700.png")
win.destroy()


def walk(w):
    yield w
    c = w.get_first_child()
    while c:
        yield from walk(c)
        c = c.get_next_sibling()


# header menu: one menu button with Reboot / Power off / About, and no standalone About button
m, win = window(1280, 800)
menu = win.menu_button.get_menu_model()
out["menu"] = {
    "items": [menu.get_item_attribute_value(i, "label", None).get_string()
              for i in range(menu.get_n_items())],
    "actions": [menu.get_item_attribute_value(i, "action", None).get_string()
                for i in range(menu.get_n_items())],
    "tooltip": win.menu_button.get_tooltip_text(), "icon": win.menu_button.get_icon_name(),
    "have": [win.lookup_action(a) is not None for a in ("reboot", "poweroff", "about")],
    "labelled_buttons": [w.get_label() for w in walk(win.header) if isinstance(w, Gtk.Button)
                         and not isinstance(w, Gtk.MenuButton) and w.get_label()],
}
# Next is hidden on the progress and finished pages; the finished page also hides Back
out["footer"] = {}
for key in ("progress", "finished"):
    m.goto(key)
    pump(5)
    out["footer"][key] = {"next": win.nxt.get_visible(), "back": win.back.get_visible()}
m.goto("welcome")
pump(5)
out["footer"]["welcome"] = {"next": win.nxt.get_visible(), "back": win.back.get_visible()}
# disk page: a disk with no partitions shows no "Or replace one partition" group
m.goto("disk")
pump(5)
m.pages["disk"].set_disk(next(d["id"] for d in m.pages["disk"].disks() if d["path"] == "/dev/vda"))
win.render()
pump(10)
out["disk_empty"] = [
    w.get_visible() and w.get_mapped() for w in walk(win.holder)
    if isinstance(w, Adw.PreferencesGroup) and w.get_title() == "Or replace one partition"]
win.destroy()
print(json.dumps(out))
