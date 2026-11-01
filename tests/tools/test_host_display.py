# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-host apply display (owner issue 15): the fake-host harness installs, enables and starts
seclegion-displayd as a default.target user unit, and every rollback disables and removes it."""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "tests" / "host" / "test-apply-rollback.sh"


def test_host_stages_displayd():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "HYPRLAND_", "SL_"))}
    p = subprocess.run(["bash", str(HARNESS), "case_display_apply_rollback"], env=env,
                       capture_output=True, text=True, timeout=300, check=False)
    assert p.returncode == 0 and "PASS: case_display_apply_rollback" in p.stdout, p.stdout + p.stderr
