# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 5: manual = choose an existing free gap explicitly, or open the dual-boot guide.
No partition editor. The configurator always uses the largest gap, so only that gap is accepted;
picking a smaller one is refused with an explanation rather than silently ignored."""

from .base import Page


class ManualPage(Page):
    key = "manual"
    title = "Choose free space"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.gap = None  # index into the alongside page's gaps

    def set_gap(self, index):
        self.gap = index

    def gaps(self):
        return self.ctx.pages["alongside"].gaps()

    def error(self):
        gaps = self.gaps()
        if self.gap is None or not 0 <= self.gap < len(gaps):
            return "Choose a free gap, or open the dual-boot guide."
        if gaps[self.gap][1] != max(g[1] for g in gaps):
            return "The installer uses the largest free gap; choose that one or free up space in Windows."
        return None

    def fragment(self):
        return {}  # the gap is not an answer: configurator picks the largest, which error() enforces


def widget(page):
    from view_util import choice_group, page_box, text_label

    box = page_box(page.title)
    labels = {i: f"{g[1] / (1 << 30):.1f} GiB at {g[0] / (1 << 30):.1f} GiB"
              for i, g in enumerate(page.gaps())}
    box.append(choice_group("Free space", labels, page.gap, page.set_gap))
    box.append(text_label("Need more room? Open the dual-boot guide on the previous page."))
    return box
