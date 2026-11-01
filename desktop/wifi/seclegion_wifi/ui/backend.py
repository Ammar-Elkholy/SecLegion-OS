# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The panel's view of NetworkManager, over an NM.Client (or a test double with the same methods).

Every call is libnm's async form: it returns at once and `done(detail)` runs later on the main loop,
detail being None on success or NetworkManager's message on failure (the window turns it into a plain
sentence). Nothing here runs a command or blocks the main loop.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("NM", "1.0")
from gi.repository import NM, GLib  # noqa: E402

from .. import data  # noqa: E402

Done = Callable[[str | None], None]
CLIENT_SIGNALS = ("notify::wireless-enabled", "notify::active-connections", "connection-added",
                  "connection-removed", "device-added", "device-removed")
DEVICE_SIGNALS = ("access-point-added", "access-point-removed", "notify::active-access-point",
                  "notify::last-scan")


def build_connection(ssid: str, kind: str, password: str | None,
                     hidden: bool = False) -> NM.SimpleConnection:
    """The partial connection AddAndActivateConnection2 completes: name, SSID and, for a secured
    network, the key management and its password. `hidden` makes NetworkManager probe for the SSID
    instead of waiting to see it advertised."""
    conn = NM.SimpleConnection.new()
    s_con = NM.SettingConnection.new()
    s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
    s_con.set_property(NM.SETTING_CONNECTION_UUID, NM.utils_uuid_generate())
    s_con.set_property(NM.SETTING_CONNECTION_TYPE, NM.SETTING_WIRELESS_SETTING_NAME)
    conn.add_setting(s_con)
    s_wifi = NM.SettingWireless.new()
    s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode()))
    if hidden:
        s_wifi.set_property(NM.SETTING_WIRELESS_HIDDEN, True)
    conn.add_setting(s_wifi)
    key_mgmt = data.KEY_MGMT[kind]
    if key_mgmt:
        s_sec = NM.SettingWirelessSecurity.new()
        s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, key_mgmt)
        if password:
            s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
        conn.add_setting(s_sec)
    return conn


def _finisher(done: Done, finish: Callable) -> Callable:
    def callback(source, result, *_):
        try:
            finish(source, result)
        except GLib.Error as e:
            done(e.message or "failed")
            return
        done(None)
    return callback


class Backend:
    def __init__(self, client, on_change: Callable[[], None], on_failed: Callable[[str, int], None]):
        self.client, self.on_change, self.on_failed = client, on_change, on_failed
        self.device = None
        self.pending: str | None = None  # the SSID being joined, until it activates or fails
        self._dev_ids: list[int] = []
        self._queued = False
        for sig in CLIENT_SIGNALS:
            client.connect(sig, self._changed)
        self._pick_device()

    # -- state ------------------------------------------------------------------------------------
    def _pick_device(self) -> None:
        dev = next((d for d in self.client.get_devices() or []
                    if d.get_device_type() == NM.DeviceType.WIFI), None)
        if dev is self.device:
            return
        if self.device is not None:
            for hid in self._dev_ids:
                self.device.disconnect(hid)
        self.device, self._dev_ids = dev, []
        if dev is not None:
            self._dev_ids = [dev.connect(s, self._changed) for s in DEVICE_SIGNALS]
            self._dev_ids.append(dev.connect("state-changed", self._state_changed))

    def _changed(self, *_args) -> None:
        if not self._queued:  # a scan fires many signals: one refresh for the lot
            self._queued = True
            GLib.idle_add(self._emit_change)

    def _emit_change(self) -> bool:
        self._queued = False
        self._pick_device()
        self.on_change()
        return GLib.SOURCE_REMOVE

    def _state_changed(self, _dev, new, _old, reason) -> None:
        if new == NM.DeviceState.ACTIVATED:
            self.pending = None
        elif new == NM.DeviceState.FAILED and self.pending:
            ssid, self.pending = self.pending, None
            self.on_failed(ssid, int(reason))
        self._changed()

    @property
    def available(self) -> bool:
        return self.device is not None

    def radio_on(self) -> bool:
        return bool(self.client.wireless_get_enabled())

    def _saved(self) -> dict[str, list]:
        out: dict[str, list] = {}
        for c in self.client.get_connections() or []:
            if c.get_connection_type() != NM.SETTING_WIRELESS_SETTING_NAME:
                continue
            w = c.get_setting_wireless()
            ssid = data.ssid_text(w.get_ssid() if w else None)
            if ssid:
                out.setdefault(ssid, []).append(c)
        return out

    def active_ssid(self) -> str | None:
        ap = self.device.get_active_access_point() if self.device else None
        return (data.ssid_text(ap.get_ssid()) or None) if ap else None

    def networks(self) -> list[data.Network]:
        if self.device is None:
            return []
        aps = [data.AccessPoint(data.ssid_text(ap.get_ssid()), ap.get_strength(), ap.get_flags(),
                                ap.get_wpa_flags(), ap.get_rsn_flags(), ap.get_path())
               for ap in self.device.get_access_points() or []]
        return data.networks(aps, set(self._saved()), self.active_ssid())

    # -- actions ------------------------------------------------------------------------------------
    def set_radio(self, on: bool, done: Done) -> None:
        self.client.dbus_set_property(
            NM.DBUS_PATH, NM.DBUS_INTERFACE, "WirelessEnabled", GLib.Variant("b", on), -1, None,
            _finisher(done, lambda c, r: c.dbus_set_property_finish(r)))

    def rescan(self, done: Done) -> None:
        if self.device is None:
            return done(None)
        self.device.request_scan_async(None, _finisher(done, lambda d, r: d.request_scan_finish(r)))

    def disconnect(self, done: Done) -> None:
        if self.device is None:
            return done(None)
        self.device.disconnect_async(None, _finisher(done, lambda d, r: d.disconnect_finish(r)))

    def _tracked(self, ssid: str, done: Done) -> Done:
        self.pending = ssid

        def wrapped(detail):
            if detail is not None:
                self.pending = None
            done(detail)
        return wrapped

    def activate(self, net: data.Network, done: Done) -> None:
        """Join a saved network with its most recently used profile."""
        conns = self._saved().get(net.ssid, [])
        if not conns:
            return done("no saved connection")
        conn = max(conns, key=lambda c: c.get_setting_connection().get_timestamp())
        self.client.activate_connection_async(
            conn, self.device, net.ref, None,
            _finisher(self._tracked(net.ssid, done), lambda c, r: c.activate_connection_finish(r)))

    def add(self, net: data.Network, password: str | None, done: Done, hidden: bool = False) -> None:
        """Save and join a new network (AddAndActivateConnection2, on the strongest access point; a
        hidden network has none, so net.ref is None and NetworkManager finds it by probing)."""
        conn = build_connection(net.ssid, net.security, password, hidden)
        self.client.add_and_activate_connection2(
            conn, self.device, net.ref, GLib.Variant("a{sv}", {}), None,
            _finisher(self._tracked(net.ssid, done),
                      lambda c, r: c.add_and_activate_connection2_finish(r)))

    def forget(self, ssid: str, done: Done) -> None:
        """Delete every saved profile for `ssid`; done once, with the first failure if any."""
        conns = self._saved().get(ssid, [])
        if not conns:
            return done(None)
        left, errors = [len(conns)], []

        def one(detail):
            if detail is not None:
                errors.append(detail)
            left[0] -= 1
            if left[0] == 0:
                done(errors[0] if errors else None)
        for c in conns:
            c.delete_async(None, _finisher(one, lambda c, r: c.delete_finish(r)))
