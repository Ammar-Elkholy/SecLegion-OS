# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 14: kiosk error, shown on its own by the kiosk error unit when the installer cannot start."""

from .base import Page


class KioskErrorPage(Page):
    key = "kiosk_error"
    title = "The installer could not start"
    show_next = False
    show_back = False

    def __init__(self, ctx, log_path="/var/log/seclegion-installer.log"):
        super().__init__(ctx)
        self.log = log_path

    def text(self):
        return (f"The installer failed to start and your disks were not touched.\n"
                f"Log file: {self.log}\n"
                "Power off, or switch to a text console to read the log.")

    def error(self):
        return "Installer unavailable."


def widget(page):
    from view_util import label_box

    return label_box(page.title, page.text())
