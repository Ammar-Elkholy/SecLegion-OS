# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Thin GTK4 helpers shared by the page widgets. Needs gi; only the view imports this."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


def page_box(title):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24, margin_bottom=24,
                  margin_start=24, margin_end=24)
    head = Gtk.Label(label=title, xalign=0)
    head.add_css_class("title-1")
    box.append(head)
    return box


def text_label(text, css=None):
    lab = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        lab.add_css_class(css)
    return lab


def label_box(title, text):
    box = page_box(title)
    box.append(text_label(text))
    return box


def choice_group(title, options, current, on_pick, disabled=()):
    """Radio group; options {id: label}. Calls on_pick(id)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.append(Gtk.Label(label=title, xalign=0))
    first = None
    for key, label in options.items():
        btn = Gtk.CheckButton(label=label)
        if first is None:
            first = btn
        else:
            btn.set_group(first)
        btn.set_active(key == current)
        btn.set_sensitive(key not in disabled)
        btn.connect("toggled", lambda b, k=key: b.get_active() and on_pick(k))
        box.append(btn)
    return box


def switch_row(title, active, on_toggle):
    row = Gtk.Box(spacing=12)
    row.append(Gtk.Label(label=title, xalign=0, hexpand=True))
    sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
    sw.connect("notify::active", lambda s, _p: on_toggle(s.get_active()))
    row.append(sw)
    return row


def entry_row(title, value, on_change, secret=False):
    """Labelled text field (password-masked when secret). Calls on_change(text) on every edit."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(Gtk.Label(label=title, xalign=0))
    ent = Gtk.PasswordEntry(show_peek_icon=True) if secret else Gtk.Entry()
    ent.set_text(value)
    ent.connect("changed", lambda e: on_change(e.get_text()))
    box.append(ent)
    return box


def mono_view(text, scroll=False):
    """Read-only monospace text block."""
    view = Gtk.Label(label=text, xalign=0, yalign=0, wrap=True, selectable=True)
    view.add_css_class("monospace")
    if not scroll:
        return view
    sw = Gtk.ScrolledWindow(vexpand=True, min_content_height=240)
    sw.set_child(view)
    return sw
