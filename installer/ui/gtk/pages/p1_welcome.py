# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 1: welcome. Owns no answers."""

from .base import Page

TEXT = ("Welcome to SecLegion OS. This installer asks a few questions, shows you exactly what it "
        "will do, and changes nothing on your disks until you confirm on the last page.")


class WelcomePage(Page):
    key = "welcome"
    title = "Welcome"


def widget(page):
    from view_util import label_box

    return label_box(page.title, TEXT)
