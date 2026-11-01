# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The Wi-Fi panel: the radio switch, the current connection, and the networks in range.

Click a saved network to join it, a new secured one to be asked its password, an open one to join it
directly; "Connect to a hidden network…" asks for the name, the security and the password.
Every NetworkManager call is async (ui/backend.py); failures are one plain sentence in a toast.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import data  # noqa: E402
from .backend import Backend  # noqa: E402

LOCK_ICON = "channel-secure-symbolic"
HIDDEN_TITLE = "Connect to a hidden network…"


class WifiWindow(Adw.ApplicationWindow):
    def __init__(self, client=None, **kw):
        super().__init__(title="Wi-Fi", default_width=440, default_height=600, **kw)
        self.backend: Backend | None = None
        self.last_toast = ""
        self.password_dialog = self.forget_dialog = self.hidden_dialog = None
        self.net_rows: list[Adw.ActionRow] = []
        self._shown: tuple | None = None
        self._syncing = False

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.scan_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Look for networks")
        self.scan_btn.connect("clicked", lambda _b: self.rescan(quiet=False))
        header.pack_start(self.scan_btn)
        view.add_top_bar(header)

        page = Adw.PreferencesPage()
        top = Adw.PreferencesGroup()
        self.radio = Adw.SwitchRow(title="Wi-Fi")
        self.radio.connect("notify::active", self._radio_toggled)
        top.add(self.radio)
        self.current = Adw.ActionRow(title="Not connected", use_markup=False)
        self.current_icon = Gtk.Image(icon_name="network-wireless-offline-symbolic")
        self.current.add_prefix(self.current_icon)
        self.disconnect_btn = Gtk.Button(label="Disconnect", valign=Gtk.Align.CENTER, visible=False)
        self.disconnect_btn.connect("clicked", self._disconnect)
        self.current.add_suffix(self.disconnect_btn)
        top.add(self.current)
        page.add(top)
        self.list_group = Adw.PreferencesGroup(title="Networks")
        page.add(self.list_group)
        self.hidden_group = Adw.PreferencesGroup()
        self.hidden_row = Adw.ActionRow(title=HIDDEN_TITLE, use_markup=False, activatable=True)
        self.hidden_row.add_prefix(Gtk.Image(icon_name="list-add-symbolic"))
        self.hidden_row.connect("activated", lambda _r: self.ask_hidden())
        self.hidden_group.add(self.hidden_row)
        page.add(self.hidden_group)
        self.toasts.set_child(page)
        view.set_content(self.toasts)
        self.set_content(view)
        self._set_enabled(False)
        if client is not None:
            self.attach(client)

    # -- NetworkManager ------------------------------------------------------------------------------
    def attach(self, client) -> None:
        self.backend = Backend(client, self.refresh, self._failed)
        self.refresh()
        self.rescan(quiet=True)

    def client_failed(self) -> None:
        self.current.set_title(data.error_sentence("client"))
        self.toast(data.error_sentence("client"))

    def _set_enabled(self, on: bool) -> None:
        for w in (self.radio, self.scan_btn, self.list_group, self.hidden_group):
            w.set_sensitive(on)

    def refresh(self) -> None:
        b = self.backend
        radio = b.radio_on()
        self._syncing = True
        self.radio.set_active(radio)
        self._syncing = False
        self._set_enabled(True)
        self.scan_btn.set_sensitive(radio and b.available)
        self.hidden_group.set_sensitive(radio and b.available)
        nets = b.networks() if radio else []
        active = next((n for n in nets if n.active), None)
        if active is None and b.active_ssid():
            active = data.Network(b.active_ssid(), 0, data.OPEN, True, True)
        self._show_current(active, radio)
        if not b.available:
            desc = "No Wi-Fi adapter was found."
        elif not radio:
            desc = "Wi-Fi is off."
        elif not nets:
            desc = "No networks in range."
        else:
            desc = ""
        self.list_group.set_description(desc or None)
        shown = tuple((n.ssid, n.strength // 5, n.security, n.saved, n.active) for n in nets)
        if shown != self._shown:  # rebuild only when something visible changed
            self._shown = shown
            for row in self.net_rows:
                self.list_group.remove(row)
            self.net_rows = [self._row(n) for n in nets]
            for row in self.net_rows:
                self.list_group.add(row)

    def _show_current(self, active: data.Network | None, radio: bool) -> None:
        b = self.backend
        if active is not None:
            self.current.set_title(active.ssid)
            self.current.set_subtitle(f"Connected, signal {active.strength}%" if active.strength
                                      else "Connected")
            self.current_icon.set_from_icon_name(data.signal_icon(active.strength))
        elif b.pending:
            self.current.set_title(f"Connecting to {b.pending}")
            self.current.set_subtitle("")
            self.current_icon.set_from_icon_name("network-wireless-acquiring-symbolic")
        else:
            self.current.set_title("Not connected" if radio else "Wi-Fi is off")
            self.current.set_subtitle("")
            self.current_icon.set_from_icon_name("network-wireless-offline-symbolic")
        self.disconnect_btn.set_visible(active is not None)

    def _row(self, n: data.Network) -> Adw.ActionRow:
        state = "Connected" if n.active else "Saved" if n.saved else ""
        parts = [p for p in (n.label, state, f"{n.strength}%") if p]
        row = Adw.ActionRow(title=n.ssid, subtitle=", ".join(parts), use_markup=False, activatable=True)
        row.add_prefix(Gtk.Image(icon_name=data.signal_icon(n.strength)))
        if n.secured:
            row.add_suffix(Gtk.Image(icon_name=LOCK_ICON, tooltip_text="Needs a password"))
        if n.saved:
            forget = Gtk.Button(label="Forget", valign=Gtk.Align.CENTER, css_classes=["flat"])
            forget.connect("clicked", lambda _b, ssid=n.ssid: self.ask_forget(ssid))
            row.add_suffix(forget)
            row.sl_forget = forget
        row.sl_network = n
        row.connect("activated", lambda _r, net=n: self.join(net))
        return row

    # -- actions -------------------------------------------------------------------------------------
    def toast(self, text: str) -> None:
        self.last_toast = text
        self.toasts.add_toast(Adw.Toast(title=text, timeout=5))

    def _reporter(self, action: str, ssid: str = ""):
        def done(detail):
            if detail is not None:
                self.toast(data.error_sentence(action, ssid, detail))
            self.refresh()
        return done

    def _failed(self, ssid: str, reason: int) -> None:
        self.toast(data.failure_sentence(ssid, reason))

    def _radio_toggled(self, row, _pspec) -> None:
        if not self._syncing and self.backend is not None:
            self.backend.set_radio(row.get_active(), self._reporter("radio"))

    def rescan(self, quiet: bool) -> None:
        if self.backend is not None and self.backend.available and self.backend.radio_on():
            def done(detail):
                if detail is not None and not quiet:
                    self.toast(data.error_sentence("scan"))
            self.backend.rescan(done)

    def _disconnect(self, _btn) -> None:
        ssid = self.backend.active_ssid() or ""
        self.backend.disconnect(self._reporter("disconnect", ssid))

    def join(self, net: data.Network) -> None:
        if net.active:
            return
        if not net.joinable:
            self.toast(data.unsupported_sentence(net))
        elif net.saved:
            self.backend.activate(net, self._reporter("connect", net.ssid))
        elif net.needs_password:
            self.ask_password(net)
        else:
            self.backend.add(net, None, self._reporter("connect", net.ssid))
        self.refresh()

    def ask_password(self, net: data.Network) -> None:
        dlg = Adw.AlertDialog(heading=f"Join {net.ssid}",
                              body=f"{net.label} network. Enter its password.")
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        entry = Adw.PasswordEntryRow(title="Password", activates_default=True)
        box.append(entry)
        hint = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, visible=False)
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        extra.append(box)
        extra.append(hint)
        dlg.set_extra_child(extra)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("connect", "Connect")
        dlg.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("connect")
        dlg.set_close_response("cancel")
        dlg.set_response_enabled("connect", False)

        def changed(_e):
            problem = data.password_problem(net.security, entry.get_text())
            dlg.set_response_enabled("connect", problem is None)
            hint.set_label(problem or "")
            hint.set_visible(bool(problem) and bool(entry.get_text()))

        def respond(_d, response):
            self.password_dialog = None
            if response == "connect":
                self.backend.add(net, entry.get_text(), self._reporter("connect", net.ssid))
                self.refresh()

        entry.connect("changed", changed)
        dlg.connect("response", respond)
        self.password_dialog, self.password_entry = dlg, entry
        dlg.present(self)

    def ask_hidden(self) -> None:
        """Join a network that does not advertise its name: ask for the name, the security and, for a
        secured one, the password. The password only ever goes to NetworkManager."""
        dlg = Adw.AlertDialog(heading="Connect to a hidden network",
                              body="Enter the network's name and how it is secured.")
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        name = Adw.EntryRow(title="Network name", activates_default=True)
        security = Adw.ComboRow(title="Security")
        security.set_model(Gtk.StringList.new([label for _kind, label in data.HIDDEN_SECURITY]))
        security.set_selected(1)  # WPA: the usual reason for hiding a network
        password = Adw.PasswordEntryRow(title="Password", activates_default=True)
        for row in (name, security, password):
            box.append(row)
        hint = Gtk.Label(css_classes=["dim-label", "caption"], wrap=True, xalign=0, visible=False)
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        extra.append(box)
        extra.append(hint)
        dlg.set_extra_child(extra)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("connect", "Connect")
        dlg.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("connect")
        dlg.set_close_response("cancel")

        def kind() -> str:
            return data.HIDDEN_SECURITY[security.get_selected()][0]

        def changed(*_a):
            password.set_visible(kind() in data.SECURED)
            problem = data.hidden_problem(name.get_text(), kind(), password.get_text())
            dlg.set_response_enabled("connect", problem is None)
            hint.set_label(problem or "")
            hint.set_visible(bool(problem) and bool(name.get_text() or password.get_text()))

        def respond(_d, response):
            self.hidden_dialog = None
            secret = password.get_text() if kind() in data.SECURED else None
            if response == "connect" and data.hidden_problem(name.get_text(), kind(), secret or "") is None:
                net = data.hidden_network(name.get_text(), kind())
                self.backend.add(net, secret, self._reporter("connect", net.ssid), hidden=True)
                self.refresh()
            password.set_text("")

        name.connect("changed", changed)
        password.connect("changed", changed)
        security.connect("notify::selected", changed)
        dlg.connect("response", respond)
        self.hidden_dialog = dlg
        self.hidden_name, self.hidden_security, self.hidden_password = name, security, password
        self.hidden_hint = hint
        changed()
        dlg.present(self)

    def ask_forget(self, ssid: str) -> None:
        dlg = Adw.AlertDialog(heading=f"Forget {ssid}?",
                              body="Its saved password is removed; joining it again asks for it.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("forget", "Forget")
        dlg.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_close_response("cancel")

        def respond(_d, response):
            self.forget_dialog = None
            if response == "forget":
                self.backend.forget(ssid, self._reporter("forget", ssid))

        dlg.connect("response", respond)
        self.forget_dialog = dlg
        dlg.present(self)
