# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Shared paths for the hwdetect tests; the package is imported straight from the source tree."""

import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HW = REPO / "hw"
PKG = REPO / "pkgs" / "seclegion-hwdetect"
sys.path.insert(0, str(PKG / "python"))

FIXTURES = [
    "intel", "amd", "amd-gtx1650", "intel-rtx4060", "pascal", "unknown-gpu", "vm", "lts-kernel",
    "legion-slim5-16ahp9-hybrid", "legion-slim5-16ahp9-discrete",
]
VENDOR_HTML = Path("/usr/share/doc/nvidia/html/supportedchips.html")


@pytest.fixture
def fixture_root(tmp_path):
    """Copy of a fixture's root dir that a test may edit."""

    def make(name):
        dest = tmp_path / name
        shutil.copytree(HW / "fixtures" / name / "root", dest)
        return dest

    return make
