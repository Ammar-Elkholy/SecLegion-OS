# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 6: disk encryption passphrase. Empty = use the user password (configurator default).
Shown only when the chosen mode uses LUKS."""

from .base import Page


def strength(pw):
    """Short human hint; never a gate (the user may keep the default)."""
    if not pw:
        return "Left empty: your user password will unlock the disk."
    classes = sum(any(f(ch) for ch in pw) for f in (str.islower, str.isupper, str.isdigit,
                                                    lambda ch: not ch.isalnum()))
    if len(pw) < 8:
        return "Too short: use at least 8 characters."
    if len(pw) >= 20 or (len(pw) >= 14 and classes >= 3):
        return "Strong."
    if classes >= 2:
        return "Fair: longer is better, a few random words work well."
    return "Weak: add length, digits or symbols."


class EncryptionPage(Page):
    key = "encryption"
    title = "Disk encryption"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.passphrase = ""
        self.confirm = ""

    def set_passphrase(self, v):
        self.passphrase = v
        self.notify()

    def set_confirm(self, v):
        self.confirm = v
        self.notify()

    def hint(self):
        return strength(self.passphrase)

    def error(self):
        if self.passphrase != self.confirm:
            return "The passphrases do not match."
        return None

    def fragment(self):
        return {"luks_passphrase": self.passphrase} if self.passphrase else {}


def widget(page):
    from view_util import entry_row, page_box, text_label

    box = page_box(page.title, "The disk is encrypted with LUKS2. Choose a passphrase, or leave both "
                               "fields empty to use your user password.")
    hint = text_label(page.hint(), "dim-label")

    def on_pp(v):
        page.set_passphrase(v)
        hint.set_label(page.hint())

    box.append(entry_row("Passphrase", page.passphrase, on_pp, secret=True))
    box.append(entry_row("Confirm passphrase", page.confirm, page.set_confirm, secret=True))
    box.append(hint)
    return box
