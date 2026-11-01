# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-sysmon: [--page overview|gpu|processes] [--list-pages].

One instance: a second launch brings the window forward on the asked page. No daemon: the process
exits when the window closes. --list-pages needs no display.
"""
from __future__ import annotations

import argparse
import os
import sys

APP_ID = "org.seclegion.Sysmon"
PAGE_IDS = ("overview", "gpu", "processes")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seclegion-sysmon", description="SecLegion System Monitor")
    p.add_argument("--page", choices=PAGE_IDS, help="open this page")
    p.add_argument("--list-pages", action="store_true", help="print the page ids, then exit")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv)
    if args.list_pages:
        print("\n".join(PAGE_IDS))
        return 0
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio

    from . import theme
    from .window import SysmonWindow

    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    state = {"themed": False}

    def on_command_line(app, cmdline) -> int:
        try:
            a = _parser().parse_args(cmdline.get_arguments()[1:])
        except SystemExit:
            return 2
        if not state["themed"]:
            theme.apply(dict(os.environ), Gdk.Display.get_default())
            state["themed"] = True
        win = app.get_active_window() or SysmonWindow(application=app)
        if a.page:
            win.show_page(a.page)
        win.present()
        return 0

    app.connect("command-line", on_command_line)
    return app.run(["seclegion-sysmon", *argv])
