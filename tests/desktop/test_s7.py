# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""S7 (decision O4): screensaver ships only with a recorded PASS measurement, else the O4 failure entry."""

import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _pass_evidence():
    for path in glob.glob(os.path.join(HERE, "fixtures", "s7-*.json")):
        data = json.load(open(path, encoding="utf-8"))
        if data.get("result") == "PASS" and data.get("measurement"):
            return path
    return None


def _failure_entry():
    text = open(os.path.join(ROOT, "docs", "decisions.md"), encoding="utf-8").read()
    return re.search(r"S7 not proven: \S[^\n]*1\.0 ships the branded hyprlock screen", text)


def test_s7_result():
    assert _pass_evidence() or _failure_entry(), "S7: neither a PASS fixture nor the O4 'S7 not proven' entry"
