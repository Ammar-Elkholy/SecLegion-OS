# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_wifi_ui.py under a private Broadway display (never the live session): builds the Wi-Fi
panel on a fake NM.Client (no NetworkManager, no D-Bus, nothing changes the host's Wi-Fi), drives it
and prints one JSON line of what it saw."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "desktop", "wifi"))
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("NM", "1.0")
from gi.repository import NM, Adw, Gdk, GLib  # noqa: E402

Adw.init()
if Gdk.Display.get_default() is None:
    print("NO-DISPLAY")
    sys.exit(0)

from seclegion_wifi.ui import theme  # noqa: E402
from seclegion_wifi.ui.window import WifiWindow  # noqa: E402

PSK, SAE, EAP = 0x100, 0x400, 0x200
calls = []
hidden_flags = []  # the wireless `hidden` property of each connection handed to AddAndActivateConnection2


class Obj:
    """Signals and async replies the way pygobject delivers them: handlers get the source first;
    async callbacks run later from the main loop with (source, result)."""
    fail = None  # a GLib.Error the next async call finishes with

    def __init__(self):
        self._h, self._n = {}, 0

    def connect(self, name, cb, *extra):
        self._n += 1
        self._h[self._n] = (name, cb, extra)
        return self._n

    def disconnect(self, hid):
        self._h.pop(hid, None)

    def emit(self, name, *args):
        for n, cb, extra in list(self._h.values()):
            if n == name:
                cb(self, *args, *extra)

    def _reply(self, cb):
        err, Obj.fail = Obj.fail, None
        GLib.idle_add(lambda: cb(self, err) and False)

    @staticmethod
    def _finish(result):
        if result is not None:
            raise result
        return True


class Bytes:
    def __init__(self, s):
        self.s = s.encode()

    def get_data(self):
        return self.s


class AP:
    def __init__(self, ssid, strength, rsn=0, path=""):
        self.ssid, self.strength, self.rsn, self.path = ssid, strength, rsn, path

    def get_ssid(self):
        return Bytes(self.ssid) if self.ssid else None

    def get_strength(self):
        return self.strength

    def get_flags(self):
        return 1 if self.rsn else 0

    def get_wpa_flags(self):
        return 0

    def get_rsn_flags(self):
        return self.rsn

    def get_path(self):
        return self.path


class Setting:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get_ssid(self):
        return Bytes(self.ssid)

    def get_timestamp(self):
        return self.ts


class Conn(Obj):
    def __init__(self, ssid, ts=0):
        super().__init__()
        self.ssid, self.ts = ssid, ts

    def get_connection_type(self):
        return "802-11-wireless"

    def get_setting_wireless(self):
        return Setting(ssid=self.ssid)

    def get_setting_connection(self):
        return Setting(ts=self.ts)

    def delete_async(self, _cancel, cb):
        calls.append(["delete", self.ssid, self.ts])
        self._reply(cb)

    def delete_finish(self, r):
        return self._finish(r)


class Device(Obj):
    def __init__(self, aps, active):
        super().__init__()
        self.aps, self.active = aps, active

    def get_device_type(self):
        return NM.DeviceType.WIFI

    def get_access_points(self):
        return self.aps

    def get_active_access_point(self):
        return self.active

    def request_scan_async(self, _cancel, cb):
        calls.append(["scan"])
        self._reply(cb)

    def request_scan_finish(self, r):
        return self._finish(r)

    def disconnect_async(self, _cancel, cb):
        calls.append(["disconnect"])
        self._reply(cb)

    def disconnect_finish(self, r):
        return self._finish(r)


class Client(Obj):
    def __init__(self, device, conns):
        super().__init__()
        self.device, self.conns, self.enabled = device, conns, True

    def get_devices(self):
        return [self.device]

    def get_connections(self):
        return self.conns

    def wireless_get_enabled(self):
        return self.enabled

    def dbus_set_property(self, path, iface, prop, value, _timeout, _cancel, cb):
        calls.append(["set", path, iface, prop, value.unpack()])
        self._reply(cb)

    def dbus_set_property_finish(self, r):
        return self._finish(r)

    def activate_connection_async(self, conn, dev, ap_path, _cancel, cb):
        calls.append(["activate", conn.ssid, conn.ts, dev is self.device, ap_path])
        self._reply(cb)

    def activate_connection_finish(self, r):
        return self._finish(r)

    def add_and_activate_connection2(self, conn, dev, ap_path, options, _cancel, cb):
        sec = conn.get_setting_wireless_security()
        hidden_flags.append(conn.get_setting_wireless().get_hidden())
        calls.append(["add", conn.get_id(), conn.get_setting_wireless().get_ssid().get_data().decode(),
                      sec.get_key_mgmt() if sec else None, sec.get_psk() if sec else None,
                      dev is self.device, ap_path, options.unpack()])
        self._reply(cb)

    def add_and_activate_connection2_finish(self, r):
        return self._finish(r)


def spin(sec, until=lambda: False):
    ctx, end = GLib.MainContext.default(), time.monotonic() + sec
    while time.monotonic() < end and not until():
        ctx.iteration(False)
        time.sleep(0.01)


def settle():
    spin(0.3)


home = AP("Home", 70, PSK, "/ap/home")
aps = [home, AP("Home", 30, PSK, "/ap/home2"), AP("Cafe", 50, 0, "/ap/cafe"),
       AP("Attic", 60, SAE, "/ap/attic"), AP("Corp", 40, EAP, "/ap/corp"),
       AP("Neighbour", 35, PSK, "/ap/nb"), AP("Office", 20, PSK, "/ap/office"), AP("", 90, 0, "/ap/h")]
dev = Device(aps, home)
client = Client(dev, [Conn("Home", 5), Conn("Office", 1), Conn("Office", 9)])
out = {"theme": theme.apply(dict(os.environ), Gdk.Display.get_default()) is not None}
win = WifiWindow(client=client)
win.present()
settle()
row = {r.get_title(): r for r in win.net_rows}
out["rows"] = [(r.get_title(), r.get_subtitle()) for r in win.net_rows]
out["current"] = [win.current.get_title(), win.current.get_subtitle(), win.disconnect_btn.get_visible()]
out["radio"] = win.radio.get_active()
out["scan_on_open"] = calls.count(["scan"])
out["forget_buttons"] = sorted(t for t, r in row.items() if getattr(r, "sl_forget", None))

calls.clear()
row["Cafe"].emit("activated")
settle()
row["Office"].emit("activated")
settle()
out["open_and_saved"] = list(calls)

calls.clear()
row["Corp"].emit("activated")
settle()
out["corp"] = [win.last_toast, list(calls)]

row["Neighbour"].emit("activated")
d = win.password_dialog
win.password_entry.set_text("1234567")
short = d.get_response_enabled("connect")
win.password_entry.set_text("12345678")
out["psk_dialog"] = [d.get_heading(), short, d.get_response_enabled("connect")]
d.emit("response", "connect")
settle()
dev.active = None  # off Home: the current row shows the join in progress
row["Attic"].emit("activated")
d = win.password_dialog
empty = d.get_response_enabled("connect")
win.password_entry.set_text("s")
out["sae_dialog"] = [empty, d.get_response_enabled("connect")]
d.emit("response", "connect")
settle()
out["added"] = list(calls)
out["connecting"] = win.current.get_title()

dev.emit("state-changed", NM.DeviceState.FAILED, NM.DeviceState.CONFIG, 7)
settle()
out["failed"] = [win.last_toast, win.current.get_title()]

calls.clear()
dev.active = home
dev.emit("notify::active-access-point", None)
settle()
win.disconnect_btn.emit("clicked")
settle()
win.net_rows[0].sl_forget.emit("clicked")
win.forget_dialog.emit("response", "forget")
settle()
out["disconnect_forget"] = list(calls)

calls.clear()
Obj.fail = GLib.Error("GDBus.Error:org.freedesktop.NetworkManager.PermissionDenied: Not authorized")
row["Cafe"].emit("activated")
settle()
out["denied"] = win.last_toast
Obj.fail = GLib.Error("GDBus.Error:org.freedesktop.NetworkManager.Failed: 802-11-wireless.ssid: bad")
row["Cafe"].emit("activated")
settle()
out["generic"] = win.last_toast

# hidden network: the entry in the list opens a dialog (name, security, password for a secured one)
calls.clear()
hidden_flags.clear()
win.hidden_row.emit("activated")
d = win.hidden_dialog
out["hidden_open"] = [win.hidden_row.get_title(), d.get_heading(), win.hidden_security.get_selected(),
                      win.hidden_password.get_visible(), d.get_response_enabled("connect")]
steps = []


def attempt(name, text):
    win.hidden_name.set_text(name)
    win.hidden_password.set_text(text)
    steps.append([d.get_response_enabled("connect"), win.hidden_hint.get_label()])


attempt("", "12345678")
attempt("Ghost", "1234567")
attempt("x" * 33, "12345678")
attempt("Ghost", "12345678")
out["hidden_validation"] = steps
d.emit("response", "connect")
settle()
out["hidden_psk"] = [list(calls), list(hidden_flags), win.hidden_dialog is None]

calls.clear()
hidden_flags.clear()
win.hidden_row.emit("activated")
d = win.hidden_dialog
win.hidden_security.set_selected(0)  # Open
out["hidden_open_security"] = [win.hidden_password.get_visible(), d.get_response_enabled("connect")]
win.hidden_name.set_text("Ghost2")
out["hidden_open_ready"] = d.get_response_enabled("connect")
d.emit("response", "connect")
settle()
out["hidden_open_join"] = [list(calls), list(hidden_flags)]

win.hidden_row.emit("activated")
d = win.hidden_dialog
win.hidden_name.set_text("Ghost3")
win.hidden_password.set_text("hunter2hunter2")
Obj.fail = GLib.Error("GDBus.Error:org.freedesktop.NetworkManager.Failed: psk hunter2hunter2")
d.emit("response", "connect")
settle()
out["hidden_failed_toast"] = [win.last_toast, "hunter2" in win.last_toast]
win.hidden_row.emit("activated")
d = win.hidden_dialog
d.emit("response", "cancel")
settle()
out["hidden_cancel"] = [win.hidden_dialog is None, hidden_flags.count(True)]

calls.clear()
win.radio.set_active(False)
settle()
client.enabled = False
client.emit("notify::wireless-enabled", None)
settle()
out["radio_off"] = [list(calls), win.radio.get_active(), len(win.net_rows),
                    win.list_group.get_description(), win.scan_btn.get_sensitive()]
win.destroy()
print(json.dumps(out))
