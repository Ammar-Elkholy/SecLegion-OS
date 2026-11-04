# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""libadwaita helpers shared by the page widgets. Needs gi; only the view imports this."""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

CONTENT_WIDTH = 760  # px; page content sits centred in a clamp this wide


class _Appender:
    """Gives the page clamp the old box API: `append` adds to the inner box, and rows (Adw.ActionRow,
    EntryRow, SwitchRow...) appended in a run land together in one boxed-list card."""

    def __init__(self, box):
        self.box = box
        self.cards = None  # the boxed-list that the last appended row went into

    def __call__(self, widget):
        if isinstance(widget, Gtk.ListBoxRow):
            if self.cards is None:
                self.cards = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
                self.cards.add_css_class("boxed-list")
                self.box.append(self.cards)
            self.cards.append(widget)
            return
        self.cards = None
        self.box.append(widget)


def page_box(title, subtitle=None):
    """Adw.Clamp (760 px) around a vertical box. AdwClamp is final, so `append` is set on the instance: it
    keeps the box API that every page uses (a caller that wants the plain box reads `.box`)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=24, margin_bottom=24,
                  margin_start=24, margin_end=24)
    page = Adw.Clamp(maximum_size=CONTENT_WIDTH, tightening_threshold=CONTENT_WIDTH - 160, child=box)
    page.box = box
    page.append = _Appender(box)
    head = Gtk.Label(label=title, xalign=0, wrap=True)
    head.add_css_class("title-1")
    page.append(head)
    if subtitle:
        page.append(text_label(subtitle, "dim-label"))
    return page


def text_label(text, css=None):
    lab = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        lab.add_css_class(css)
    return lab


def label_box(title, text):
    box = page_box(title)
    box.append(text_label(text))
    return box


def status_page(icon_or_logo, title, body):
    """Centred Adw.StatusPage. The first argument is an icon name, or a file path for a picture."""
    page = Adw.StatusPage(title=title, description=body, hexpand=True, vexpand=True)
    if icon_or_logo and os.path.isfile(icon_or_logo):
        try:
            page.set_paintable(Gdk.Texture.new_from_filename(icon_or_logo))
        except Exception:  # an unreadable picture falls back to the plain page
            pass
    elif icon_or_logo:
        page.set_icon_name(icon_or_logo)
    return page


def choice_group(title, options, current, on_pick, disabled=()):
    """Radio group; options {id: label}. Calls on_pick(id)."""
    group = Adw.PreferencesGroup(title=title)
    first = None
    for key, label in options.items():
        btn = Gtk.CheckButton()
        if first is None:
            first = btn
        else:
            btn.set_group(first)
        btn.set_active(key == current)
        btn.connect("toggled", lambda b, k=key: b.get_active() and on_pick(k))
        row = Adw.ActionRow(title=label, sensitive=key not in disabled, activatable_widget=btn)
        row.add_prefix(btn)
        group.add(row)
    return group


def switch_row(title, active, on_toggle, subtitle=None):
    row = Adw.SwitchRow(title=title, active=active)
    if subtitle:
        row.set_subtitle(subtitle)
    row.connect("notify::active", lambda r, _p: on_toggle(r.get_active()))
    return row


def entry_row(title, value, on_change, secret=False):
    """Labelled text field (password-masked when secret). Calls on_change(text) on every edit."""
    row = Adw.PasswordEntryRow(title=title) if secret else Adw.EntryRow(title=title)
    row.set_text(value)
    row.connect("changed", lambda r: on_change(r.get_text()))
    return row


def mono_view(text, scroll=False):
    """Read-only monospace text block."""
    view = Gtk.Label(label=text, xalign=0, yalign=0, wrap=True, selectable=True)
    view.add_css_class("monospace")
    if not scroll:
        return view
    sw = Gtk.ScrolledWindow(vexpand=True, min_content_height=240)
    sw.set_child(view)
    return sw
