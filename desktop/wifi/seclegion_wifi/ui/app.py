# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-wifi: the Wi-Fi panel.

One instance (org.seclegion.Wifi). A second launch toggles it: the window closes when it has focus
(a second click on the bar module), otherwise it comes forward. No daemon: the process exits when the
window closes. The NetworkManager client is made with NM.Client.new_async, off the first paint.
"""
from __future__ import annotations

import os
import sys

APP_ID = "org.seclegion.Wifi"


def make_app(new_client=None):
    """The application. `new_client(ready, win)` starts the NetworkManager client and calls
    `ready(source, result, win)` when it is up (the default is NM.Client.new_async); tests pass a fake
    so no real NetworkManager is touched. The application id makes it a single instance on the session
    bus: a second process forwards its command line to the first and exits."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("NM", "1.0")
    from gi.repository import NM, Adw, Gdk, Gio, GLib

    from . import theme
    from .window import WifiWindow

    if new_client is None:
        def new_client(ready, win):
            NM.Client.new_async(None, ready, win)

    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    state = {"themed": False}

    def client_ready(_src, result, win) -> None:
        try:
            client = NM.Client.new_finish(result)
        except GLib.Error:
            win.client_failed()
            return
        win.attach(client)

    def on_command_line(app, _cmdline) -> int:
        if not state["themed"]:
            theme.apply(dict(os.environ), Gdk.Display.get_default())
            state["themed"] = True
        win = app.get_active_window()
        if win is not None and win.get_visible() and win.is_active():
            win.close()
            return 0
        if win is None:
            win = WifiWindow(application=app)
            new_client(client_ready, win)
        win.present()
        return 0

    app.connect("command-line", on_command_line)
    return app


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return make_app().run(["seclegion-wifi", *argv])
