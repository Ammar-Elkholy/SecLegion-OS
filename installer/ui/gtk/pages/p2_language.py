# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 2: language + keyboard (us / ara). Arabic keyboard = layout us plus keyboard_extra=["ara"]."""

from .base import Page

ARABIC = "العربية"
LANGUAGES = {  # id -> (label shown, locale)
    "en": ("English", "en_US.UTF-8"),
    "ar": (ARABIC, "ar_EG.UTF-8"),
}
KEYBOARDS = {  # id -> (label, archinstall kb_layout, keyboard_extra)
    "us": ("English (US)", "us", ()),
    "ara": (f"{ARABIC} (Arabic)", "us", ("ara",)),
}


class LanguagePage(Page):
    key = "language"
    title = "Language and keyboard"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.language = "en"
        self.keyboard = "us"

    def set_language(self, lang):
        self.language = lang

    def set_keyboard(self, kb):
        self.keyboard = kb

    def error(self):
        if self.language not in LANGUAGES:
            return "Choose a language."
        if self.keyboard not in KEYBOARDS:
            return "Choose a keyboard layout."
        return None

    def fragment(self):
        _, layout, extra = KEYBOARDS[self.keyboard]
        return {"locale": LANGUAGES[self.language][1], "keyboard": layout,
                "keyboard_extra": list(extra)}


def apply_direction(lang):
    """Arabic reads right to left: flip every widget the app draws from now on (and the open ones)."""
    from gi.repository import Gtk

    Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if lang == "ar" else Gtk.TextDirection.LTR)


def widget(page):
    from gi.repository import GLib
    from view_util import choice_group, page_box

    def redraw():
        page.ctx.on_render()
        return GLib.SOURCE_REMOVE

    def pick_language(lang):
        page.set_language(lang)
        apply_direction(lang)
        GLib.idle_add(redraw)  # after the toggle has finished: the page widget is about to be replaced

    box = page_box(page.title, "Choose the language and the keyboard layout for the new system.")
    box.append(choice_group("Language", {k: v[0] for k, v in LANGUAGES.items()},
                            page.language, pick_language))
    box.append(choice_group("Keyboard", {k: v[0] for k, v in KEYBOARDS.items()},
                            page.keyboard, page.set_keyboard))
    return box
