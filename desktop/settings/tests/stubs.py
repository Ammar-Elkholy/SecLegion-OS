# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Test harness: fake HOME, fake sysfs, fake /etc and a PATH of stub tools.

The environment handed to the backend has a PATH containing only the stub directory, so no test
can reach a real powerprofilesctl, wpctl or friends, and never the owner's real config.
"""

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from seclegion_settings.backend.env import Ctx

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
GOLDEN = FIXTURES / "golden"
STUB_TOOL = HERE / "stub_tool.py"
TOOLS = (
    "powerprofilesctl",
    "brightnessctl",
    "wpctl",
    "nmcli",
    "rfkill",
    "bluetoothctl",
    "swaync-client",
    "xdg-mime",
    "xdg-settings",
    "upower",
    "hyprctl",
    "hyprsunset",
    "seclegion-theme",
    "seclegion-autolock",
    "systemctl",
    "systemd-inhibit",
    "df",
    "gio",
    "checkupdates",
    "blueman-manager",
    "xdg-terminal-exec",
    "snapper",
    "wl-copy",
    "ss",
    "sshd",
    "ufw",
    "timedatectl",
    "seclegion-display-menu",
)


def make_bin(bindir: Path, tools=TOOLS) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    for t in tools:
        p = bindir / t
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{STUB_TOOL}" "{t}" "$@"\n')
        p.chmod(p.stat().st_mode | stat.S_IXUSR)


def snapshot(root: Path) -> dict:
    """Every path under root with its mode, mtime_ns and content hash."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for n in sorted(dirs + files):
            p = Path(dirpath) / n
            st = p.lstat()
            h = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else ""
            out[str(p.relative_to(root))] = (stat.S_IMODE(st.st_mode), st.st_mtime_ns, h)
    return out


class StubCase(unittest.TestCase):
    SYSFS = "sysfs-full"
    TOOLS = TOOLS

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-settings-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.etc = self.tmp / "etc"
        self.etc.mkdir()
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.sysfs = self.tmp / "sysfs"  # a copy: writes (conservation_mode) must not edit the fixture
        shutil.copytree(FIXTURES / self.SYSFS, self.sysfs)
        self.bin = self.tmp / "bin"
        make_bin(self.bin, self.TOOLS)
        self.environ = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "SL_HOME": str(self.home),
            "SL_SYSFS": str(self.sysfs),
            "SL_ETC": str(self.etc),
            "SL_STUB_STATE": str(self.state),
            # display rows need a session; hyprctl here is the stub (PATH holds only stubs)
            "HYPRLAND_INSTANCE_SIGNATURE": "sl-test-not-a-live-instance",
        }

    def ctx(self, dry_run=False) -> Ctx:
        return Ctx(self.environ, dry_run=dry_run)

    def stub_state(self) -> dict:
        p = self.state / "state.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def mutations(self) -> list[str]:
        p = self.state / "mutations.log"
        return p.read_text().splitlines() if p.exists() else []

    def calls(self) -> list[list[str]]:
        p = self.state / "calls.log"
        return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []

    def golden(self, name: str) -> str:
        return (GOLDEN / name).read_text()
