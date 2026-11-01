# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The Settings window (plan-r8 B7): sidebar with 17 grouped pages and search, content pages
generated from the registry, toasts with Undo, and a header menu with "Show details everywhere".

Pages are built on first view (or all at once by `build_all`, used by --self-test).
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from ..backend import registry  # noqa: E402
from ..backend.env import Ctx, WriteResult  # noqa: E402
from . import pages as P  # noqa: E402
from .rows import SettingRow  # noqa: E402
from .theme import Theme, logo_path  # noqa: E402

COMING = "Coming in a later update"
SEARCH_PAGE = "__search__"


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, ctx: Ctx, application=None, theme: Theme | None = None):
        super().__init__(application=application, title="SecLegion Settings")
        self.ctx = ctx
        self.theme = theme
        self.details_everywhere = False
        self.rows: dict[str, SettingRow] = {}
        self.built: dict[str, Gtk.Widget] = {}
        self.last_toast: Adw.Toast | None = None
        self.set_default_size(980, 680)
        self.set_size_request(720, 520)

        group = Gio.SimpleActionGroup()
        act = Gio.SimpleAction.new_stateful("show-details", None, GLib.Variant.new_boolean(False))
        act.connect("change-state", self._on_show_details)
        group.add_action(act)
        self.insert_action_group("win", group)
        self.show_details_action = act

        self.split = Adw.NavigationSplitView(min_sidebar_width=220, max_sidebar_width=280)
        self.split.set_sidebar(self._sidebar())
        self.split.set_content(self._content())
        self.toasts = Adw.ToastOverlay(child=self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 800sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("<Control>f"),
                                           Gtk.CallbackAction.new(self._focus_search)))
        self.add_controller(keys)
        self.connect("destroy", self._on_destroy)
        self.show_page(P.PAGES[0].id)

    # -- layout ---------------------------------------------------------------------------------
    def _sidebar(self) -> Adw.NavigationPage:
        title = Gtk.Box(spacing=8)
        logo = logo_path()
        if logo is not None:
            img = Gtk.Image.new_from_file(str(logo))
            img.set_pixel_size(24)
            title.append(img)
        brand = Gtk.Label(label="SecLegion Settings")
        brand.add_css_class("sl-brand")
        title.append(brand)
        header = Adw.HeaderBar(title_widget=title, show_end_title_buttons=False)

        self.search = Gtk.SearchEntry(placeholder_text="Search settings", margin_start=8,
                                      margin_end=8, margin_bottom=6)
        self.search.connect("search-changed", lambda e: self.run_search(e.get_text()))

        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.add_css_class("navigation-sidebar")
        self.nav_rows: dict[str, Gtk.ListBoxRow] = {}
        for page in P.PAGES:
            box = Gtk.Box(spacing=10, margin_start=4)
            box.append(Gtk.Image.new_from_icon_name(page.icon))
            box.append(Gtk.Label(label=page.label, xalign=0))
            row = Gtk.ListBoxRow(child=box)
            row.sl_page = page
            self.nav.append(row)
            self.nav_rows[page.id] = row
        self.nav.set_header_func(self._nav_header)
        self.nav.connect("row-selected", self._on_nav)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.search)
        body.append(Gtk.ScrolledWindow(child=self.nav, vexpand=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER))
        tv = Adw.ToolbarView(content=body)
        tv.add_top_bar(header)
        return Adw.NavigationPage(title="SecLegion Settings", child=tv)

    @staticmethod
    def _nav_header(row, before) -> None:
        g = row.sl_page.group
        if before is None or before.sl_page.group != g:
            lab = Gtk.Label(label=g, xalign=0)
            lab.add_css_class("sl-group-label")
            row.set_header(lab)
        else:
            row.set_header(None)

    def _content(self) -> Adw.NavigationPage:
        menu = Gio.Menu()
        menu.append("Show details everywhere", "win.show-details")
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                          tooltip_text="Menu")
        header = Adw.HeaderBar()
        header.pack_end(self.menu_button)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        tv = Adw.ToolbarView(content=self.stack)
        tv.add_top_bar(header)
        self.content_page = Adw.NavigationPage(title="Power", child=tv)
        return self.content_page

    # -- pages ----------------------------------------------------------------------------------
    def build_page(self, page: P.Page) -> Gtk.Widget:
        if page.id in self.built:
            return self.built[page.id]
        settings = P.settings_for(page)
        if not settings:
            w = Adw.StatusPage(icon_name=page.icon, title=page.label, description=COMING)
            w.add_css_class("sl-coming")
        else:
            w = Adw.PreferencesPage(title=page.label)
            head = Adw.PreferencesGroup()
            title = Gtk.Label(label=page.label, xalign=0)
            title.add_css_class("title-1")
            head.add(title)
            w.add(head)
            made = [SettingRow(s, self) for s in settings]
            for r in made:
                self.rows[r.s.id] = r
                r.refresh()
                if r.header_widget is not None:
                    g = Adw.PreferencesGroup(title=r.s.label, description=r.s.description)
                    g.add(r.header_widget)
                    g.add(r.widget)
                    w.add(g)
            buckets = (
                ("Status", "", [r for r in made if r.s.readonly and r.header_widget is None]),
                ("Settings", "", [r for r in made if not r.s.readonly and not r.s.privileged
                                  and r.header_widget is None]),
                ("System", "Needs the SecLegion package: these rows show what would be written.",
                 [r for r in made if r.s.privileged and r.header_widget is None]),
            )
            for name, desc, members in buckets:
                if members:
                    g = Adw.PreferencesGroup(title=name, description=desc)
                    for r in members:
                        g.add(r.widget)
                    w.add(g)
            if self.details_everywhere:
                for r in made:
                    r.widget.set_expanded(True)
        self.stack.add_named(w, page.id)
        self.built[page.id] = w
        return w

    def build_all(self) -> None:
        for page in P.PAGES:
            self.build_page(page)

    def show_page(self, page_id: str) -> bool:
        page = P.resolve(page_id)
        if page is None:
            return False
        self.build_page(page)
        self.stack.set_visible_child_name(page.id)
        self.content_page.set_title(page.label)
        nav = self.nav_rows[page.id]
        if self.nav.get_selected_row() is not nav:
            self.nav.select_row(nav)
        self.current_page = page.id
        return True

    def _on_nav(self, _lb, row) -> None:
        if row is None:
            return
        if self.search.get_text():
            self.search.set_text("")
        self.show_page(row.sl_page.id)
        self.split.set_show_content(True)

    # -- search ---------------------------------------------------------------------------------
    def _focus_search(self, *_a) -> bool:
        self.search.grab_focus()
        return True

    def run_search(self, text: str) -> list[registry.Setting]:
        if not text.strip():
            if self.stack.get_visible_child_name() == SEARCH_PAGE:
                self.show_page(getattr(self, "current_page", P.PAGES[0].id))
            return []
        found = P.search(text)
        old = self.stack.get_child_by_name(SEARCH_PAGE)
        if old is not None:
            self.stack.remove(old)
        if found:
            pp = Adw.PreferencesPage(title="Search")
            g = Adw.PreferencesGroup(title=f"{len(found)} matching settings")
            for s in found:
                page = P.page_of(s)
                ar = Adw.ActionRow(title=s.label, subtitle=f"{page.label} · {s.id}", activatable=True)
                ar.set_use_markup(False)
                ar.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                ar.sl_setting_id = s.id
                ar.connect("activated", lambda _r, sid=s.id: self.open_setting(sid))
                g.add(ar)
            pp.add(g)
        else:
            pp = Adw.StatusPage(icon_name="edit-find-symbolic", title="No matching settings",
                                description=f"Nothing matches “{text}”")
        self.search_results = found
        self.stack.add_named(pp, SEARCH_PAGE)
        self.stack.set_visible_child_name(SEARCH_PAGE)
        self.content_page.set_title("Search")
        self.split.set_show_content(True)
        return found

    def open_setting(self, setting_id: str) -> None:
        s = registry.get(setting_id)
        self.search.set_text("")
        self.show_page(P.page_of(s).id)
        r = self.rows[setting_id]
        r.widget.set_expanded(True)
        r.widget.grab_focus()

    # -- feedback -------------------------------------------------------------------------------
    def toast(self, title: str, undo=None) -> Adw.Toast:
        t = Adw.Toast(title=title, use_markup=False, timeout=5)
        if undo is not None:
            t.set_button_label("Undo")
            t.connect("button-clicked", lambda _t: undo())
        self.toasts.add_toast(t)
        self.last_toast = t
        return t

    def saved(self, row: SettingRow, res: WriteResult, previous: str | None, undone: bool = False) -> None:
        msg = "Saved. Applies now." if res.applied_live else "Saved."
        if undone:
            self.toast("Restored the previous value.")
        elif previous is None:  # the old value was unreadable: nothing to undo to
            self.toast(msg)
        else:
            self.toast(msg, undo=lambda: row.apply(previous, undo=True))

    def _on_show_details(self, action, value) -> None:
        action.set_state(value)
        self.details_everywhere = value.get_boolean()
        for r in self.rows.values():
            r.widget.set_expanded(self.details_everywhere)

    def _on_destroy(self, *_a) -> None:
        if self.theme is not None:
            self.theme.stop()
