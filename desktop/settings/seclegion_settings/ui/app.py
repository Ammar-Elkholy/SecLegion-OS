# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-settings: [--page ID] [--search TEXT] [--list-pages] [--self-test].

No daemon: the process exits when the window closes. --list-pages needs no display (no gi import).
"""
from __future__ import annotations

import argparse
import os
import sys

from . import pages as P

APP_ID = "org.seclegion.Settings"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seclegion-settings", description="SecLegion Settings")
    p.add_argument("--page", metavar="ID", help="open this page (see --list-pages)")
    p.add_argument("--search", metavar="TEXT", help="start with this search")
    p.add_argument("--list-pages", action="store_true", help="print page ids and labels, then exit")
    p.add_argument("--self-test", action="store_true",
                   help="build every page without showing the window; prints self-test-ok")
    return p


def _gtk():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio
    return Adw, Gdk, Gio


def self_test() -> int:
    Adw, Gdk, _Gio = _gtk()
    from ..backend import registry
    from ..backend.env import Ctx
    from .theme import Theme
    from .window import SettingsWindow

    Adw.init()
    if Gdk.Display.get_default() is None:
        print("seclegion-settings: self-test: no display", file=sys.stderr)
        return 1
    win = SettingsWindow(Ctx(), theme=Theme(dict(os.environ)))
    win.build_all()
    missing = [s.id for s in registry.SETTINGS
               if s.id not in win.rows or getattr(win.rows[s.id].widget, "sl_details", None) is None]
    built = len(win.built)
    win.destroy()
    if missing or built != len(P.PAGES):
        print(f"seclegion-settings: self-test: pages={built} missing details: {missing}", file=sys.stderr)
        return 1
    print("self-test-ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv)
    if args.list_pages:
        for page in P.PAGES:
            print(f"{page.id}\t{page.label}")
        return 0
    if args.page is not None and P.resolve(args.page) is None:
        print(f"seclegion-settings: unknown page {args.page!r}; try --list-pages", file=sys.stderr)
        return 2
    if args.self_test:
        return self_test()

    Adw, _Gdk, Gio = _gtk()
    from ..backend.env import Ctx
    from .theme import Theme
    from .window import SettingsWindow

    # A sandboxed run (SL_HOME) must never hand its window to an instance using the real home.
    flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
    if os.environ.get("SL_HOME"):
        flags |= Gio.ApplicationFlags.NON_UNIQUE
    app = Adw.Application(application_id=APP_ID, flags=flags)
    state = {"theme": None}

    def on_command_line(app, cmdline) -> int:
        try:
            a = _parser().parse_args(cmdline.get_arguments()[1:])
        except SystemExit:
            return 2
        win = app.get_active_window()
        if win is None:
            if state["theme"] is None:
                state["theme"] = Theme(dict(os.environ))
                state["theme"].watch()
            win = SettingsWindow(Ctx(), application=app, theme=state["theme"])
        if a.page:
            win.show_page(a.page)
        if a.search:
            win.search.set_text(a.search)
        win.present()
        return 0

    app.connect("command-line", on_command_line)
    return app.run(["seclegion-settings", *argv])
