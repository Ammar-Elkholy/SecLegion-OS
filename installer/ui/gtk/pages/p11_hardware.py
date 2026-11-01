# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 11: hardware report. Summarises seclegion-hwreport's plan (GPU driver choice message)."""

import json
import subprocess

from .base import Page

REPORT = "seclegion-hwreport"


def load_plan():
    """Run seclegion-hwreport; return its plan dict or None (tool missing/failed)."""
    try:
        r = subprocess.run([REPORT], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout)["plan"] if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None


def summarize(plan):
    if plan is None:
        return "Hardware report unavailable: the installer will use generic drivers."
    msgs = plan.get("messages") or []
    pk = [p for p in plan.get("packages", [])]
    head = msgs[0] if msgs else "No special GPU driver needed: open-source drivers will be used."
    out = [head, *msgs[1:]]
    if pk:
        out.append("Hardware packages: " + ", ".join(pk))
    return "\n".join(out)


class HardwarePage(Page):
    key = "hardware"
    title = "Hardware report"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.loader = load_plan
        self._plan = False  # not loaded yet

    def plan(self):
        if self._plan is False:
            self._plan = self.loader()
        return self._plan

    def text(self):
        return summarize(self.plan())


def widget(page):
    from view_util import label_box

    return label_box(page.title, page.text())
