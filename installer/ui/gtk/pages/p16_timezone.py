# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 16: time zone. A searchable list of the system's zoneinfo names. The default follows the language
page (Arabic -> Africa/Cairo, else UTC); an explicit pick always wins. Owns `timezone`."""

import os
from pathlib import Path

from .base import Page

ZONEINFO = "/usr/share/zoneinfo"
REGIONS = ("Africa", "America", "Antarctica", "Arctic", "Asia", "Atlantic", "Australia", "Europe",
           "Indian", "Pacific")


def load_zones(root=ZONEINFO):
    """Sorted zone names: Region/City lines of tzdata.zi ("Z" zones, "L" links), else a walk of root.
    "UTC" is always listed."""
    names = set()
    try:
        for line in Path(root, "tzdata.zi").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) > 2 and parts[0] == "Z":
                names.add(parts[1])
            elif len(parts) > 2 and parts[0] == "L":
                names.add(parts[2])
    except OSError:
        for region in REGIONS:
            for dirpath, _dirs, files in os.walk(os.path.join(root, region)):
                for fn in files:
                    names.add(os.path.relpath(os.path.join(dirpath, fn), root))
    names = {n for n in names if n.split("/", 1)[0] in REGIONS and "/" in n}
    names.add("UTC")
    return sorted(names)


class TimezonePage(Page):
    key = "timezone"
    title = "Time zone"

    def __init__(self, ctx, zones=None):
        super().__init__(ctx)
        self._zones = list(zones) if zones is not None else None  # injectable for tests
        self.zone = None  # None = the default for the chosen language

    def zones(self):
        if self._zones is None:
            self._zones = load_zones()
        return self._zones

    def default(self):
        return "Africa/Cairo" if self.ctx.pages["language"].language == "ar" else "UTC"

    @property
    def current(self):
        return self.zone if self.zone is not None else self.default()

    def set_zone(self, zone):
        self.zone = zone

    def matching(self, text):
        t = text.strip().lower().replace(" ", "_")
        return [z for z in self.zones() if t in z.lower()]

    def error(self):
        z = self.current
        if z == "UTC" or z in self.zones():
            return None
        return "Choose a time zone."

    def fragment(self):
        return {"timezone": self.current}


def widget(page):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk
    from view_util import page_box

    box = page_box(page.title, "Choose the time zone for the new system. Type to search.")
    search = Gtk.SearchEntry(placeholder_text="Search (for example Cairo)")
    box.append(search)
    lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    lst.add_css_class("boxed-list")
    rows = {}
    for z in page.zones():
        row = Adw.ActionRow(title=z.replace("_", " "))
        row.zone = z
        row.set_name("tz:" + z)
        lst.append(row)
        rows[z] = row
    guard = {"busy": True}

    def on_selected(_l, row):
        if row is not None and not guard["busy"]:
            page.set_zone(row.zone)
            page.notify()

    def on_search(entry):
        hits = set(page.matching(entry.get_text()))
        for z, row in rows.items():
            row.set_visible(z in hits)

    lst.connect("row-selected", on_selected)
    search.connect("search-changed", on_search)
    if page.current in rows:
        lst.select_row(rows[page.current])
    guard["busy"] = False
    scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=360,
                                hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(lst)
    box.append(scroll)
    return box
