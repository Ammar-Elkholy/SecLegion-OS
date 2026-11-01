# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 15: about / licences. The plan's 15th page was unclear, so it is this: the output of
`tools/licence-check` when the tool is shipped, else a short pointer. Opened from the header, not in the
Next/Back flow."""

import os
import subprocess

from .base import Page

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools",
                    "licence-check")


def licence_text(tool=TOOL, runner=subprocess.run):
    if not os.path.exists(tool):
        return "SecLegion OS is free software. See /usr/share/licenses on the installed system."
    try:
        r = runner([tool], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "Licence list unavailable."
    return (r.stdout or r.stderr or "").strip() or "Licence list unavailable."


class AboutPage(Page):
    key = "about"
    title = "About and licences"

    def text(self):
        return licence_text()


def widget(page):
    from view_util import mono_view, page_box

    box = page_box(page.title)
    box.append(mono_view(page.text(), scroll=True))
    return box
