# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 13: finished. Reboot runs `systemctl reboot` only when the button is clicked."""

import subprocess

from .base import Page

REBOOT_ARGV = ["systemctl", "reboot"]
POWEROFF_ARGV = ["systemctl", "poweroff"]
_POWER = {"reboot": REBOOT_ARGV, "poweroff": POWEROFF_ARGV}


def power(action, runner=subprocess.run):
    """Reboot or power off; the header menu and the Reboot button call this, nothing else does."""
    if action not in _POWER:
        raise ValueError(f"unknown power action: {action!r}")
    return runner(_POWER[action], check=False)


class FinishedPage(Page):
    key = "finished"
    title = "Installation complete"
    show_back = False
    show_next = False

    def reboot(self, runner=subprocess.run):
        """Called from the button handler only."""
        return power("reboot", runner)


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
