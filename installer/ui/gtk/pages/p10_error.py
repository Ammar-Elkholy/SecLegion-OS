# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 10: install failed. Shows the log path and the last lines; Back returns to review."""

from .base import Page


class ErrorPage(Page):
    key = "error"
    title = "Installation failed"
    show_next = False

    def log_path(self):
        return self.ctx.pages["progress"].log_path

    def text(self):
        tail = "\n".join(self.ctx.pages["progress"].lines[-15:])
        return (f"The installation did not finish. Nothing more will be done automatically.\n"
                f"Log file: {self.log_path()}\n\n{tail}")

    def error(self):
        return "Installation failed."


def widget(page):
    from gi.repository import Adw, Gtk
    from view_util import mono_view, status_page

    sp = status_page("dialog-error-symbolic", page.title,
                     "Go back to the review page to try again, or reboot and check the log.")
    details = Gtk.Expander(label="Details", expanded=True)
    details.set_child(mono_view(page.text(), scroll=True))
    sp.set_child(Adw.Clamp(maximum_size=640, child=details))
    return sp
