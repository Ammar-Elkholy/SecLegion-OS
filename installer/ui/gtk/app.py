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
from gi.repository import GLib, Gtk  # noqa: E402
from model import Model  # noqa: E402
from view import build_widget  # noqa: E402


class InstallerWindow(Gtk.ApplicationWindow):
    def __init__(self, app, model, kiosk_error=False):
        super().__init__(application=app, title="SecLegion OS installer", default_width=900,
                         default_height=640)
        self.model = model
        self.kiosk_error = kiosk_error
        model.on_change = self.refresh_nav
        self.running = False
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.holder = Gtk.Box(vexpand=True)
        root.append(self.holder)
        bar = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=24, margin_end=24)
        self.about = Gtk.Button(label="About")
        self.about.connect("clicked", lambda _b: self.show_page(model.pages["about"]))
        self.back = Gtk.Button(label="Back")
        self.back.connect("clicked", self.on_back)
        self.msg = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.nxt = Gtk.Button(label="Next")
        self.nxt.add_css_class("suggested-action")
        self.nxt.connect("clicked", self.on_next)
        for w in (self.about, self.msg, self.back, self.nxt):
            bar.append(w)
        root.append(bar)
        self.set_child(root)
        self.render()

    def show_page(self, page):
        child = self.holder.get_first_child()
        if child:
            self.holder.remove(child)
        self.holder.append(build_widget(page))

    def render(self):
        self.show_page(self.kiosk_page() if self.kiosk_error else self.model.current)
        self.refresh_nav()

    def kiosk_page(self):
        return self.model.pages["kiosk_error"]

    def refresh_nav(self):
        if self.kiosk_error:
            self.back.set_visible(False)
            self.nxt.set_visible(False)
            return
        page = self.model.current
        self.nxt.set_label(getattr(page, "next_label", "Next"))
        self.nxt.set_visible(getattr(page, "show_next", True))
        self.back.set_visible(getattr(page, "show_back", True))
        self.back.set_sensitive(not self.running)
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
            ok = page.run(lambda _l: GLib.idle_add(self.show_page, page))
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


class InstallerApp(Gtk.Application):
    def __init__(self, facts, kiosk_error=False, log_path=None, kiosk=False):
        super().__init__(application_id="org.seclegion.Installer")
        self.facts = facts
        self.kiosk_error = kiosk_error
        self.kiosk = kiosk
        self.log_path = log_path

    def do_activate(self):
        model = Model(self.facts)
        if self.kiosk:
            model.pages["progress"].use_pkexec()
        if self.log_path:
            model.pages["progress"].log_path = self.log_path
            model.pages["kiosk_error"].log = self.log_path
        InstallerWindow(self, model, self.kiosk_error).present()


def main(facts, kiosk_error=False, log_path=None, kiosk=False):
    return InstallerApp(facts, kiosk_error, log_path, kiosk).run([])
