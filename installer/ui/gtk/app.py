# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""GTK4 installer window: Back/Next over the Model's pages. All logic lives in the model; this only
renders the current page, enables Next from model.can_next(), and runs the install in a thread."""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
from model import Model  # noqa: E402
from sidebar import Sidebar  # noqa: E402
from theme import load_css  # noqa: E402
from view import build_widget  # noqa: E402


class InstallerWindow(Adw.ApplicationWindow):
    def __init__(self, app, model, kiosk_error=False):
        super().__init__(application=app, title="SecLegion OS installer", default_width=1100,
                         default_height=720, resizable=True)
        self.model = model
        self.kiosk_error = kiosk_error
        model.on_change = self.refresh_nav
        model.on_render = self.render
        self.page_widget = None
        self.running = False
        self.sidebar = Sidebar(model)
        self.title_label = Gtk.Label()
        self.title_label.add_css_class("title")
        self.step_label = Gtk.Label(visible=False)
        self.step_label.add_css_class("dim-label")
        # No window buttons: under the cage kiosk, closing the window would end the kiosk (error screen).
        self.header = header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.set_title_widget(self.title_label)
        self.about = Gtk.Button(label="About")
        self.about.connect("clicked", lambda _b: self.show_page(model.pages["about"]))
        header.pack_end(self.about)
        header.pack_start(self.step_label)
        self.holder = Gtk.Box(vexpand=True)
        bar = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=24, margin_end=24)
        self.back = Gtk.Button(label="Back")
        self.back.connect("clicked", self.on_back)
        self.msg = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.nxt = Gtk.Button(label="Next")
        self.nxt.add_css_class("suggested-action")
        self.nxt.connect("clicked", self.on_next)
        for w in (self.msg, self.back, self.nxt):
            bar.append(w)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.holder)
        toolbar.add_bottom_bar(bar)
        self.split = Adw.OverlaySplitView(sidebar=self.sidebar, content=toolbar,
                                          min_sidebar_width=240, max_sidebar_width=300)
        self.set_content(self.split)
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        bp.add_setter(self.split, "collapsed", True)
        bp.connect("apply", lambda _b: self.refresh_nav())
        bp.connect("unapply", lambda _b: self.refresh_nav())
        self.add_breakpoint(bp)
        self.render()

    def show_page(self, page):
        child = self.holder.get_first_child()
        if child:
            self.holder.remove(child)
        self.page_widget = widget = build_widget(page)
        if not isinstance(widget, Adw.StatusPage):  # a status page scrolls itself
            sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
            sw.set_child(widget)
            widget = sw
        self.holder.append(widget)

    def refresh_progress(self):
        """A new install output line: update the progress page in place (keeps Details open)."""
        update = getattr(self.page_widget, "update", None)
        if update and self.model.current.key == "progress":
            update()
        return GLib.SOURCE_REMOVE

    def render(self):
        self.show_page(self.kiosk_page() if self.kiosk_error else self.model.current)
        self.refresh_nav()

    def kiosk_page(self):
        return self.model.pages["kiosk_error"]

    def refresh_nav(self):
        self.sidebar.refresh()
        self.title_label.set_label("" if self.kiosk_error else self.model.current.title)
        self.step_label.set_label(f"Step {self.model.index + 1} of {len(self.model.visible())}")
        self.step_label.set_visible(self.split.get_collapsed() and not self.kiosk_error)
        if self.kiosk_error:
            self.back.set_visible(False)
            self.nxt.set_visible(False)
            return
        page = self.model.current
        self.nxt.set_label(getattr(page, "next_label", "Next"))
        self.nxt.set_visible(getattr(page, "show_next", True))
        self.back.set_visible(getattr(page, "show_back", True))
        self.back.set_sensitive(not self.running and (self.model.index > 0 or self.model.failed))
        self.nxt.set_sensitive(not self.running and self.model.can_next())
        self.msg.set_label("" if self.running else (self.model.error() or ""))

    def on_back(self, _b):
        if self.model.failed:
            self.model.retry_from_review()
        else:
            self.model.back()
        self.render()

    def on_next(self, _b):
        if not self.model.next():
            return
        self.render()
        if self.model.current.key == "progress":
            self.start_install()

    def start_install(self):
        page = self.model.pages["progress"]
        self.running = True
        self.refresh_nav()

        def work():
            ok = page.run(lambda _l: GLib.idle_add(self.refresh_progress))
            GLib.idle_add(self.install_done, ok)

        threading.Thread(target=work, daemon=True).start()

    def install_done(self, ok):
        self.running = False
        if ok:
            self.model.next()
        else:
            self.model.install_failed()
        self.render()
        return False


class InstallerApp(Adw.Application):
    def __init__(self, facts, kiosk_error=False, log_path=None, kiosk=False):
        super().__init__(application_id="org.seclegion.Installer")
        self.facts = facts
        self.kiosk_error = kiosk_error
        self.kiosk = kiosk
        self.log_path = log_path

    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        css = Gtk.CssProvider()
        css.load_from_string(load_css())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        model = Model(self.facts)
        if self.kiosk:
            model.pages["progress"].use_pkexec()
        if self.log_path:
            model.pages["progress"].log_path = self.log_path
            model.pages["kiosk_error"].log = self.log_path
        InstallerWindow(self, model, self.kiosk_error).present()


def main(facts, kiosk_error=False, log_path=None, kiosk=False):
    return InstallerApp(facts, kiosk_error, log_path, kiosk).run([])
