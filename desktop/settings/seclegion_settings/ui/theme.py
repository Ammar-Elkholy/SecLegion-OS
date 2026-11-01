# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Theme loading (plan-r8 B6): libadwaita dark, then the current SecLegion colors.css, then
settings.css (which maps the sl_* tokens onto libadwaita's named colours).

`colors_css_candidates` is pure; `Theme` needs a display. A Gio.FileMonitor reloads the colours
while the window is open; `Theme.stop()` cancels it so nothing outlives the window.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS_CSS = HERE / "css" / "settings.css"
SYSTEM_COLORS = Path("/usr/share/seclegion/theme/default/colors.css")
REPO_COLORS = HERE.parents[2] / "theme" / "default" / "colors.css"
SYSTEM_LOGO = Path("/usr/share/seclegion/branding/seclegion-logo.png")
REPO_LOGO = HERE.parents[2] / "branding" / "seclegion-logo.png"


def state_dir(environ: dict) -> Path:
    """$XDG_STATE_HOME; under SL_HOME (tests, previews) the fake home's ~/.local/state."""
    if environ.get("SL_HOME"):
        return Path(environ["SL_HOME"]) / ".local" / "state"
    xdg = environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg)
    return Path(environ.get("HOME") or os.path.expanduser("~")) / ".local" / "state"


def theme_root(environ: dict) -> Path:
    return state_dir(environ) / "seclegion" / "theme"


def colors_css_candidates(environ: dict) -> list[Path]:
    return [theme_root(environ) / "current" / "colors.css", SYSTEM_COLORS, REPO_COLORS]


def find_colors_css(environ: dict) -> Path | None:
    return next((p for p in colors_css_candidates(environ) if p.is_file()), None)


def logo_path() -> Path | None:
    return next((p for p in (SYSTEM_LOGO, REPO_LOGO) if p.is_file()), None)


class Theme:
    """Owns the two CSS providers and the file monitors for one display."""

    def __init__(self, environ: dict, display=None):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gio, GLib, Gtk

        self._Gio, self._GLib = Gio, GLib
        self.environ = environ
        self.display = display or Gdk.Display.get_default()
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self.colors = Gtk.CssProvider()
        self.settings = Gtk.CssProvider()
        prio = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        Gtk.StyleContext.add_provider_for_display(self.display, self.colors, prio)
        Gtk.StyleContext.add_provider_for_display(self.display, self.settings, prio + 1)
        self.settings.load_from_path(str(SETTINGS_CSS))
        self.colors_path: Path | None = None
        self.reloads = 0
        self._monitors: list = []
        self.load_colors()

    def load_colors(self) -> None:
        self.colors_path = find_colors_css(self.environ)
        if self.colors_path is not None:
            self.colors.load_from_path(str(self.colors_path))
        # settings.css refers to @sl_*; re-parse it so it resolves against the new colours.
        self.settings.load_from_path(str(SETTINGS_CSS))
        self.reloads += 1

    def watch(self) -> None:
        """Reload on a change of colors.css or of the theme's `current` link (seclegion-theme
        swaps that symlink atomically, which a monitor on the file alone would miss)."""
        Gio, GLib = self._Gio, self._GLib
        self.stop()
        targets = []
        if self.colors_path is not None:
            targets.append(("file", Gio.File.new_for_path(str(self.colors_path))))
        root = theme_root(self.environ)
        if root.is_dir():
            targets.append(("dir", Gio.File.new_for_path(str(root))))
        for kind, f in targets:
            try:
                m = (f.monitor_file if kind == "file" else f.monitor_directory)(
                    Gio.FileMonitorFlags.WATCH_MOVES, None)
            except GLib.Error:  # no inotify: a theme change then needs a restart, nothing else
                continue
            m.connect("changed", self._changed, kind)
            self._monitors.append(m)

    def _changed(self, _mon, file, other, event, kind) -> None:
        Gio = self._Gio
        names = {file.get_basename() if file else "", other.get_basename() if other else ""}
        if kind == "dir" and "current" not in names:
            return
        if event in (Gio.FileMonitorEvent.ATTRIBUTE_CHANGED, Gio.FileMonitorEvent.PRE_UNMOUNT):
            return
        before = self.colors_path
        self.load_colors()
        if self.colors_path != before:
            self.watch()

    def stop(self) -> None:
        for m in self._monitors:
            m.cancel()
        self._monitors = []
