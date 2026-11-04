# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 13: finished. Reboot runs `systemctl reboot` only when the button is clicked."""

import subprocess

from .base import Page

REBOOT_ARGV = ["systemctl", "reboot"]


class FinishedPage(Page):
    key = "finished"
    title = "Installation complete"
    show_back = False

    def reboot(self, runner=subprocess.run):
        """Called from the button handler only."""
        return runner(REBOOT_ARGV, check=False)


def widget(page):
    from gi.repository import Gtk
    from view_util import status_page

    sp = status_page("object-select-symbolic", page.title,
                     "SecLegion OS is installed. Remove the install medium, then reboot.")
    btn = Gtk.Button(label="Reboot now", halign=Gtk.Align.CENTER)
    btn.add_css_class("suggested-action")
    btn.add_css_class("pill")
    btn.connect("clicked", lambda _b: page.reboot())
    sp.set_child(btn)
    return sp
