# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Theme loading, as the System Monitor does it: libadwaita dark, then the current SecLegion colors.css
(state theme, else the packaged default, else this checkout's), then wifi.css (sl_* tokens onto
libadwaita's named colours). The colours are read at start; a theme change applies on the next start.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIFI_CSS = HERE / "css" / "wifi.css"
SYSTEM_COLORS = Path("/usr/share/seclegion/theme/default/colors.css")
REPO_COLORS = HERE.parents[2] / "theme" / "default" / "colors.css"


def colors_css_candidates(environ: dict) -> list[Path]:
    if environ.get("SL_HOME"):
        state = Path(environ["SL_HOME"]) / ".local" / "state"
    elif environ.get("XDG_STATE_HOME"):
        state = Path(environ["XDG_STATE_HOME"])
    else:
        state = Path(environ.get("HOME") or os.path.expanduser("~")) / ".local" / "state"
    return [state / "seclegion" / "theme" / "current" / "colors.css", SYSTEM_COLORS, REPO_COLORS]


def apply(environ: dict, display) -> Path | None:
    """Install the two providers on `display`; returns the colors.css used (None: libadwaita only)."""
    from gi.repository import Adw, Gtk

    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    colors = next((p for p in colors_css_candidates(environ) if p.is_file()), None)
    prio = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    if colors is not None:
        cp = Gtk.CssProvider()
        cp.load_from_path(str(colors))
        Gtk.StyleContext.add_provider_for_display(display, cp, prio)
        sp = Gtk.CssProvider()  # refers to @sl_*: only meaningful with the colours loaded
        sp.load_from_path(str(WIFI_CSS))
        Gtk.StyleContext.add_provider_for_display(display, sp, prio + 1)
    return colors
