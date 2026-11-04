# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 15: About. widget() builds an Adw.AboutDialog (the header button presents it on the window); its
Licences section holds the output of `tools/licence-check` when the tool is shipped, else a short pointer.
Not in the Next/Back flow."""

import os
import subprocess

from .base import Page

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools",
                    "licence-check")


def licence_text(tool=TOOL, runner=subprocess.run):
    if not os.path.exists(tool):
        return "SecLegion OS is free software. See /usr/share/licenses on the installed system."
    try:
        r = runner([tool], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "Licence list unavailable."
    return (r.stdout or r.stderr or "").strip() or "Licence list unavailable."


class AboutPage(Page):
    key = "about"
    title = "About and licences"

    def text(self):
        return licence_text()


WEBSITE = "https://github.com/Ammar-Elkholy/SecLegion-OS"
ART_NOTICE = ("The SecLegion name, logo and branding artwork are (c) 2026 Ammar Elkholy. All rights "
              "reserved. The MIT licence covers the code, not the artwork.")


def widget(page):
    """The About dialog (Adw.AboutDialog); the window presents it with dialog.present(window)."""
    import sys

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                                    "installd"))
    import release
    from sidebar import logo_path

    dialog = Adw.AboutDialog(application_name="SecLegion OS", version=release.build_label(),
                             developer_name="Ammar Elkholy", website=WEBSITE,
                             license_type=Gtk.License.MIT_X11)
    logo = logo_path()
    if logo:  # the icon theme also finds unthemed <name>.png files in a search-path directory
        Gtk.IconTheme.get_for_display(page_display()).add_search_path(os.path.dirname(logo))
        dialog.set_application_icon(os.path.splitext(os.path.basename(logo))[0])
    dialog.add_legal_section("Licences", None, Gtk.License.CUSTOM, page.text())
    dialog.add_legal_section("Branding artwork", None, Gtk.License.CUSTOM, ART_NOTICE)
    return dialog


def page_display():
    from gi.repository import Gdk

    return Gdk.Display.get_default()
