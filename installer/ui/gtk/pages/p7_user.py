# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 7: user account + hostname. Validation reuses the configurator's own rules."""

import configurator as c

from .base import Page

_MSG = {"bad_username": "Username: lowercase letters, digits, - and _, starting with a letter.",
        "bad_hostname": "Hostname: letters, digits and -, up to 63 characters."}


class UserPage(Page):
    key = "user"
    title = "Your account"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.username = ""
        self.password = ""
        self.confirm = ""
        self.hostname = "seclegion"

    def set_username(self, v):
        self.username = v
        self.notify()

    def set_password(self, v):
        self.password = v
        self.notify()

    def set_confirm(self, v):
        self.confirm = v
        self.notify()

    def set_hostname(self, v):
        self.hostname = v
        self.notify()

    def error(self):
        try:
            c.Answers(disk="x", username=self.username, password="x", hostname=self.hostname)
        except c.Refusal as r:
            return _MSG.get(r.code, r.message)
        if not self.password:
            return "Choose a password."
        if self.password != self.confirm:
            return "The passwords do not match."
        return None

    def fragment(self):
        return {"username": self.username, "password": self.password, "hostname": self.hostname}


def widget(page):
    from view_util import entry_row, page_box

    box = page_box(page.title)
    box.append(entry_row("Username", page.username, page.set_username))
    box.append(entry_row("Password", page.password, page.set_password, secret=True))
    box.append(entry_row("Confirm password", page.confirm, page.set_confirm, secret=True))
    box.append(entry_row("Computer name", page.hostname, page.set_hostname))
    return box
