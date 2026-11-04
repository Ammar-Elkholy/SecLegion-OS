# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 12: optional tiers. Gaming and virtualisation, both default off; they become post hints."""

from .base import Page

NOTE = ("The installer works offline. Optional sets are installed from what the install image "
        "carries; once you are online you can update or add packages as usual.")


class TiersPage(Page):
    key = "tiers"
    title = "Optional extras"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.gaming = False
        self.virt = False

    def set_gaming(self, on):
        self.gaming = bool(on)

    def set_virt(self, on):
        self.virt = bool(on)

    def hints(self):
        """Only toggled-on tiers appear (hint keys read by seclegion-post)."""
        return {k: True for k, on in (("gaming", self.gaming), ("virt", self.virt)) if on}


def widget(page):
    from view_util import page_box, switch_row, text_label

    box = page_box(page.title, "Both are off by default. Turn on what you want installed.")
    box.append(switch_row("Gaming", page.gaming, page.set_gaming, "Steam, Proton and drivers"))
    box.append(switch_row("Virtualisation", page.virt, page.set_virt, "libvirt and QEMU"))
    box.append(text_label(NOTE, "dim-label"))
    return box
