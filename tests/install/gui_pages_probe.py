# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_gui_adw_pages under system python3 with GDK_BACKEND=broadway: checks the libadwaita
helpers, the restyled pages, the RTL switch and the review Edit buttons; prints a JSON summary on the last
line. SHELL_SHOTS=<dir> also saves welcome/review/progress PNGs at 1280x800 and 700x700."""

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
from sidebar import logo_path  # noqa: E402
from theme import load_css  # noqa: E402
from view import build_widget  # noqa: E402
from view_util import (  # noqa: E402
    choice_group,
    entry_row,
    label_box,
    page_box,
    status_page,
    switch_row,
)

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
    FACTS = json.load(f)
VDA = "/dev/disk/by-id/ata-QEMU_HARDDISK_vda"
app = Adw.Application(application_id="org.seclegion.InstallerPagesProbe")
app.register(None)
ctx = GLib.MainContext.default()


def pump(n=40):
    for _ in range(n):
        ctx.iteration(False)
        time.sleep(0.02)


def kind(w):
    """First Adw* GType name up the class chain (a Python subclass reports its Adw base)."""
    for cls in type(w).__mro__:
        name = getattr(getattr(cls, "__gtype__", None), "name", "")
        if name.startswith("Adw"):
            return name
    return type(w).__name__


def walk(w):
    yield w
    c = w.get_first_child()
    while c:
        yield from walk(c)
        c = c.get_next_sibling()


def model():
    m = Model(FACTS)
    m.pages["disk"].set_disk(VDA)
    u = m.pages["user"]
    u.set_username("ammar")
    u.set_password("pw")
    u.set_confirm("pw")
    m.pages["hardware"].loader = lambda: {"messages": ["GPU: test", "second line"], "packages": ["x"]}
    m.pages["progress"].lines = ["line one", "line two"]
    return m


def window(m, width, height):
    win = InstallerWindow(app, m)
    win.set_default_size(width, height)
    win.present()
    pump()
    return win


def shot(win, name):
    d = os.environ.get("SHELL_SHOTS")
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    pump(60)
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(win).snapshot(snap, win.get_width(), win.get_height())
    win.get_native().get_renderer().render_texture(snap.to_node(), None).save_to_png(os.path.join(d, name))


def helpers():
    out = {}
    pb = page_box("T", "sub")
    a, b = entry_row("E", "", lambda v: None), switch_row("S", False, lambda v: None)
    pb.append(a)
    pb.append(b)
    boxed = [w for w in walk(pb) if isinstance(w, Gtk.ListBox) and w.has_css_class("boxed-list")]
    out["page_box"] = {"type": kind(pb), "max": pb.get_maximum_size(),
                       "append_ok": a.get_parent() is not None,
                       "rows_in_boxed_list": bool(boxed) and a.get_parent() is b.get_parent() is boxed[0]}
    m = model()
    t = m.pages["tiers"]
    calls = []
    sw = switch_row("S", t.gaming, lambda v: (calls.append(v), t.set_gaming(v)))
    sw.set_active(True)
    mid = sw.get_active() == t.gaming
    sw.set_active(False)
    out["switch"] = {"type": kind(sw), "calls": calls, "follows_model": mid and sw.get_active() == t.gaming}
    got = []
    en = entry_row("E", "", got.append)
    en.set_text("a")
    out["entry"] = {"type": kind(en), "calls": got}
    out["secret"] = kind(entry_row("P", "", lambda v: None, secret=True))
    picked = []
    grp = choice_group("T", {"a": "A", "b": "B", "c": "C"}, "a", picked.append, disabled=("c",))
    rows = [w for w in walk(grp) if isinstance(w, Adw.ActionRow)]
    checks = [r.get_activatable_widget() for r in rows]
    checks[1].set_active(True)
    out["choice"] = {"type": kind(grp), "rows": [kind(r) for r in rows],
                     "grouped": not checks[0].get_active(),
                     "activatable": all(isinstance(c, Gtk.CheckButton) for c in checks),
                     "disabled": [not r.get_sensitive() for r in rows], "picked": picked}
    sp = status_page("emblem-ok-symbolic", "T", "B")
    out["status_icon"] = {"type": kind(sp), "icon": sp.get_icon_name(),
                          "paintable": sp.get_paintable() is not None}
    sp = status_page(logo_path(), "T", "B")
    out["status_logo"] = {"type": kind(sp), "paintable": sp.get_paintable() is not None}
    out["label_box"] = kind(label_box("T", "text"))
    return out


def rtl():
    m = model()
    win = window(m, 1000, 700)
    m.goto("language")
    pump()

    def pick(label):
        for r in walk(win.holder):
            if isinstance(r, Adw.ActionRow) and r.get_title() == label:
                r.get_activatable_widget().set_active(True)
                return r
        raise SystemExit("no row " + label)

    pick("العربية")
    pump()
    out = {"ar_sidebar": win.sidebar.get_direction().value_nick.upper(),
           "ar_default": Gtk.Widget.get_default_direction().value_nick.upper()}
    arabic = [r for r in walk(win.holder) if isinstance(r, Adw.ActionRow) and r.get_title() == "العربية"]
    out["ar_selected_after_rerender"] = arabic[0].get_activatable_widget().get_active()
    pick("English")
    pump()
    out["en_sidebar"] = win.sidebar.get_direction().value_nick.upper()
    out["en_default"] = Gtk.Widget.get_default_direction().value_nick.upper()
    win.destroy()
    return {k: out[k] for k in ("ar_sidebar", "ar_default", "en_sidebar", "en_default",
                                "ar_selected_after_rerender")}


def review():
    m = model()
    win = window(m, 1280, 800)
    m.goto("review")
    pump()
    rows = [r for r in walk(win.holder) if isinstance(r, Adw.ActionRow)
            and any(isinstance(w, Gtk.Button) and w.get_label() == "Edit" for w in walk(r))]
    out = {"titles": [r.get_title() for r in rows], "edit_buttons": len(rows),
           "confirm_entry": any(isinstance(w, Adw.EntryRow) and w.get_title() == "Disk name"
                                for w in walk(win.holder)), "edit_jumps": []}
    shot(win, "review-1280.png")
    for i in range(len(rows)):
        m.goto("review")
        pump(5)
        rs = [r for r in walk(win.holder) if isinstance(r, Adw.ActionRow)
              and any(isinstance(w, Gtk.Button) and w.get_label() == "Edit" for w in walk(r))]
        next(w for w in walk(rs[i]) if isinstance(w, Gtk.Button) and w.get_label() == "Edit").emit("clicked")
        pump(5)
        out["edit_jumps"].append(m.current.key)
    win.destroy()
    return out


def progress_and_welcome():
    out = {}
    m = model()
    win = window(m, 1280, 800)
    sp = next(x for x in walk(win.holder) if isinstance(x, Adw.StatusPage))
    out["welcome"] = {"type": kind(sp), "title": sp.get_title(), "paintable": sp.get_paintable() is not None,
                      "body_has_build": "build" in sp.get_description().lower()}
    shot(win, "welcome-1280.png")
    m.goto("progress")
    pump()
    sp = next(x for x in walk(win.holder) if isinstance(x, Adw.StatusPage))
    exp = next(x for x in walk(sp) if isinstance(x, Gtk.Expander))
    named = {x.get_name(): x for x in walk(sp)}
    m.pages["progress"].lines.append("line three")
    win.refresh_progress()
    pump(5)
    out["progress"] = {"type": kind(sp), "bar": any(isinstance(x, Gtk.ProgressBar) for x in walk(sp)),
                       "expander": exp.get_label(), "expanded": exp.get_expanded(),
                       "step": named["progress-step"].get_label(),
                       "log_updates": any(isinstance(x, Gtk.Label) and "line three" in x.get_label()
                                           for x in walk(exp.get_child()))}
    shot(win, "progress-1280.png")
    win.destroy()
    m = model()
    win = window(m, 700, 700)
    shot(win, "welcome-700.png")
    m.goto("review")
    pump()
    shot(win, "review-700.png")
    m.goto("progress")
    pump()
    shot(win, "progress-700.png")
    win.destroy()
    return out


def unchanged_and_types():
    m = model()
    before = m.answers()
    types = {}
    for key, page in m.pages.items():
        if key in ("hardware", "progress"):
            m.pages[key].fragment()
        w = build_widget(page)
        if key == "about":  # a dialog, presented on the window; it cannot be a window child
            assert isinstance(w, Adw.AboutDialog)
            continue
        win = Gtk.Window()
        win.set_child(w)
        win.present()
        pump(5)
        if key in ("encryption", "user", "error", "hardware", "tiers", "finished", "kiosk_error"):
            types[key] = kind(w)
        win.destroy()
    return m.answers() == before, types


out = {"helpers": helpers()}
out.update(progress_and_welcome())
out["rtl"] = rtl()
out["review"] = review()
out["answers_unchanged"], out["types"] = unchanged_and_types()
print(json.dumps(out))
