# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Thin GTK4/libadwaita view over model.py: one row per visible button."""

from __future__ import annotations

import argparse
import sys

from . import model


def _gui() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    def activate(app):
        win = Adw.ApplicationWindow(application=app, title="Welcome to SecLegion", default_width=480)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        group = Adw.PreferencesGroup(title="Welcome to SecLegion", description="A few places to start.")
        for side in ("top", "bottom", "start", "end"):
            getattr(group, f"set_margin_{side}")(12)
        for b in model.visible_buttons(model.read_pending()):
            row = Adw.ActionRow(title=b.label, subtitle=b.description, activatable=True)
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", lambda _r, b=b: model.launch(b))
            group.add(row)
        box.append(group)
        win.set_content(box)
        win.present()
        model.mark_done()

    app = Adw.Application(application_id="org.seclegion.Welcome")
    app.connect("activate", activate)
    return app.run([sys.argv[0]])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="seclegion-welcome")
    ap.add_argument("--autostart", action="store_true", help="session start: show only until welcome.done")
    ap.add_argument("--fetch", metavar="FETCHER", help="(terminal helper) run a vendor fetcher as the user")
    a = ap.parse_args(argv)
    if a.fetch:
        rc = model.run_fetch(a.fetch)
        try:
            input("Press Enter to close. ")
        except EOFError:
            pass
        return rc
    if a.autostart and not model.should_autostart():
        return 0
    return _gui()
