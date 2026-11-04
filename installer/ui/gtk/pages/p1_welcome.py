# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 1: welcome. Owns no answers."""

from .base import Page

TAGLINE = "A security-focused Arch Linux. Answer a few questions, review every step, then install."
TEXT = ("Welcome to SecLegion OS. This installer asks a few questions, shows you exactly what it "
        "will do, and changes nothing on your disks until you confirm on the last page.")


class WelcomePage(Page):
    key = "welcome"
    title = "Welcome"


def widget(page):
    import release
    from sidebar import logo_path
    from view_util import status_page

    sp = status_page(logo_path() or "system-run-symbolic", "SecLegion OS",
                     f"{TAGLINE}\n{release.build_label()}")
    return sp
