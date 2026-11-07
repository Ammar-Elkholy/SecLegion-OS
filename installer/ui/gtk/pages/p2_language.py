# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 2: language (English / Arabic) and keyboard (every XKB layout and variant, searchable).

The answers carry the XKB layout and variant; `keyboard` is its console keymap. Arabic keeps
keyboard_extra=["ara"] for compatibility."""

from .base import Page

ARABIC = "العربية"
LANGUAGES = {  # id -> (label shown, locale)
    "en": ("English", "en_US.UTF-8"),
    "ar": (ARABIC, "ar_EG.UTF-8"),
}
FALLBACK_KEYBOARDS = [("us", "", "English (US)"), ("ara", "", f"{ARABIC} (Arabic)")]


def keyboard_entries():
    """Every XKB layout and variant of the live ISO, COMMON first; a short list if the file is missing."""
    import keymaps

    try:
        entries = keymaps.xkb_layouts()
    except OSError:
        entries = []
    return keymaps.ordered(entries) if entries else list(FALLBACK_KEYBOARDS)


class LanguagePage(Page):
    key = "language"
    title = "Language and keyboard"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.language = "en"
        self.xkb_layout = "us"
        self.xkb_variant = ""

    def set_language(self, lang):
        self.language = lang

    def set_keyboard(self, layout, variant=""):
        self.xkb_layout, self.xkb_variant = layout, variant

    def error(self):
        if self.language not in LANGUAGES:
            return "Choose a language."
        if (self.xkb_layout, self.xkb_variant) not in {(lo, va) for lo, va, _ in keyboard_entries()}:
            return "Choose a keyboard layout."
        return None

    def fragment(self):
        import keymaps

        return {"locale": LANGUAGES[self.language][1],
                "keyboard": keymaps.console_keymap(self.xkb_layout, self.xkb_variant),
                "xkb_layout": self.xkb_layout, "xkb_variant": self.xkb_variant,
                "keyboard_extra": ["ara"] if self.xkb_layout == "ara" else []}


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
    box.append(keyboard_group(page))
    return box


def keyboard_group(page):
    """Searchable layout list plus a field to try the keys on."""
    from gi.repository import Adw, Gtk

    entries = keyboard_entries()
    group = Adw.PreferencesGroup(title="Keyboard")
    search = Gtk.SearchEntry(placeholder_text="Search layouts")
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    listbox.add_css_class("boxed-list")
    rows = {}
    for layout, variant, desc in entries:
        row = Adw.ActionRow(title=desc, subtitle=f"{layout} ({variant})" if variant else layout)
        rows[row] = (layout, variant)
        listbox.append(row)
        if (layout, variant) == (page.xkb_layout, page.xkb_variant):
            listbox.select_row(row)

    def visible(row):
        q = search.get_text().strip().lower()
        return not q or q in f"{row.get_title()} {row.get_subtitle()}".lower()

    listbox.set_filter_func(visible)
    search.connect("search-changed", lambda _s: listbox.invalidate_filter())
    listbox.connect("row-selected", lambda _l, row: row and page.set_keyboard(*rows[row]))
    scroller = Gtk.ScrolledWindow(min_content_height=220, max_content_height=260,
                                  propagate_natural_height=True)
    scroller.set_child(listbox)
    test = Gtk.Entry(placeholder_text="Test your keyboard")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for w in (search, scroller, test):
        box.append(w)
    group.add(box)
    return group
