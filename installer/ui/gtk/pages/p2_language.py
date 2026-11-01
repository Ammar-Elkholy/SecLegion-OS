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


def widget(page):
    from view_util import choice_group, page_box

    box = page_box(page.title)
    box.append(choice_group("Language", {k: v[0] for k, v in LANGUAGES.items()},
                            page.language, page.set_language))
    box.append(choice_group("Keyboard", {k: v[0] for k, v in KEYBOARDS.items()},
                            page.keyboard, page.set_keyboard))
    return box
