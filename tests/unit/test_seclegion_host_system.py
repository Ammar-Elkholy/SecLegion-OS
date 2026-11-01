# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-host --system: static checks that need no package build."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_system_root_reexec_drops_roots_session_env():
    """As root, --system USER re-runs itself as USER; root's XDG_RUNTIME_DIR (/run/user/0) made the theme
    lock unwritable in the installer's post step, so the re-exec must clear the session variables."""
    text = (REPO / "tools" / "seclegion-host").read_text()
    start = text.index('exec runuser -u "$SYS_USER"')
    reexec = text[start : text.index("\n", text.index('--system --root "$SYS_ROOT" "$SYS_USER"', start))]
    for var in (
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "WAYLAND_DISPLAY",
        "HYPRLAND_INSTANCE_SIGNATURE",
    ):
        assert f"-u {var}" in reexec, var
