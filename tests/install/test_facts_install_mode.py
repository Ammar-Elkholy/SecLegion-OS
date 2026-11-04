# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Install mode = cmdline token AND target active/activating (a laptop without network stays activating)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "installer", "installd"))
import facts  # noqa: E402

INSTALL = "BOOT_IMAGE=x seclegion.mode=install systemd.unit=seclegion-install.target"


@pytest.mark.parametrize(
    "cmdline,state,want",
    [
        (INSTALL, "activating", True),
        (INSTALL, "active", True),
        ("BOOT_IMAGE=x seclegion.mode=install", "inactive", False),
        ("BOOT_IMAGE=x seclegion.mode=live systemd.unit=seclegion-live.target", "active", False),
        ("BOOT_IMAGE=x seclegion.mode=install", "failed", False),
        ("BOOT_IMAGE=x xseclegion.mode=install", "active", False),
    ],
)
def test_detect_install_mode(cmdline, state, want):
    assert facts.detect_install_mode(cmdline, state) is want


def test_gather_reports_install_mode_while_the_target_is_activating(monkeypatch):
    class Done:
        stdout = json.dumps({"blockdevices": []})

    def fake_out(argv):
        return "activating" if argv[:2] == ["systemctl", "is-active"] else ""

    monkeypatch.setattr(facts, "_out", fake_out)
    monkeypatch.setattr(facts, "_read_cmdline", lambda: INSTALL)
    monkeypatch.setattr(facts.subprocess, "run", lambda *a, **k: Done())
    monkeypatch.setattr(facts.os.path, "isdir", lambda p: False)
    assert facts.gather()["install_mode"] is True
