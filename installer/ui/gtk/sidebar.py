# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer sidebar: logo, product title and one row per visible page with its step state."""

import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLED_DIR = "/usr/share/seclegion/branding"
REPO_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "desktop", "branding"))
# The picture is drawn about 96 px high, so the 512 px file is 2x or better on a HiDPI screen. The plain
# name is the fallback (the 256 px file, or an older package that ships only one small file).
LOGO_FILES = ("seclegion-logo-512.png", "seclegion-logo.png")


def logo_path():
    for d in (INSTALLED_DIR, REPO_DIR):
        for name in LOGO_FILES:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


class Sidebar(Gtk.Box):
    def __init__(self, model):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=24,
                         margin_bottom=24, margin_start=18, margin_end=18)
        self.model = model
        self.rows = []
        path = logo_path()
        if path:
            try:
                pic = Gtk.Picture.new_for_filename(path)
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_size_request(-1, 96)
                self.append(pic)
            except Exception:  # an unreadable logo falls back to the text title
                pass
        title = Gtk.Label(label="SecLegion OS", margin_bottom=18)
        title.add_css_class("sidebar-title")
        self.append(title)
        self.steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.steps)
        self.refresh()

    def refresh(self):
        child = self.steps.get_first_child()
        while child:
            self.steps.remove(child)
            child = self.steps.get_first_child()
        self.rows = []
        for i, page in enumerate(self.model.visible()):
            row = Gtk.Label(label=page.title, xalign=0)
            state = "done" if i < self.model.index else "current" if i == self.model.index else "todo"
            row.add_css_class("step-" + state)
            self.steps.append(row)
            self.rows.append(row)
