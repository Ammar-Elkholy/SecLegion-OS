# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page base: a model fragment. Pure Python; pages never call archinstall or touch disks."""

import os
import sys

_INSTALLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "installd")
if _INSTALLD not in sys.path:
    sys.path.insert(0, _INSTALLD)


class Page:
    key = ""
    title = ""

    def __init__(self, ctx):
        self.ctx = ctx  # the shared Model: facts + sibling pages

    def fragment(self):
        """The partial answers dict this page owns."""
        return {}

    def error(self):
        """Human text for why Next is blocked, or None."""
        return None

    def can_next(self):
        return self.error() is None

    def notify(self):
        """Tell the app an entry changed so it can refresh Next."""
        self.ctx.on_change()
