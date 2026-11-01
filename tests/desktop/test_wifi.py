# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-wifi data layer (no GTK, no libnm, never the real NetworkManager)."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop", "wifi"))
from seclegion_wifi import data  # noqa: E402
from seclegion_wifi.data import AccessPoint  # noqa: E402

PSK, SAE = data.SEC_KEY_MGMT_PSK, data.SEC_KEY_MGMT_SAE
EAP, OWE = data.SEC_KEY_MGMT_802_1X, data.SEC_KEY_MGMT_OWE


def test_dedupe_keeps_the_strongest_and_sorts_by_signal():
    aps = [AccessPoint("Home", 40, 1, 0, PSK, "/ap/1"), AccessPoint("Home", 81, 1, 0, PSK, "/ap/2"),
           AccessPoint("Cafe", 60, 0, 0, 0, "/ap/3"), AccessPoint("", 99, 0, 0, 0, "/ap/hidden"),
           AccessPoint("attic", 60, 1, 0, SAE, "/ap/4")]
    nets = data.networks(aps, saved={"Home"}, active="Home")
    assert [(n.ssid, n.strength, n.ref) for n in nets] == [
        ("Home", 81, "/ap/2"), ("attic", 60, "/ap/4"), ("Cafe", 60, "/ap/3")]
    home, attic, cafe = nets
    assert (home.saved, home.active, home.label, home.secured) == (True, True, "WPA2", True)
    assert (attic.saved, attic.active, attic.label, attic.needs_password) == (False, False, "WPA3", True)
    assert (cafe.label, cafe.secured, cafe.needs_password, cafe.joinable) == ("Open", False, False, True)
    assert not home.needs_password  # saved: NetworkManager already has its password


@pytest.mark.parametrize("flags,wpa,rsn,kind", [
    (0, 0, 0, data.OPEN),
    (1, 0, 0, data.WEP),
    (1, PSK, 0, data.PSK),
    (1, 0, PSK, data.PSK),
    (1, 0, SAE, data.SAE),
    (1, 0, PSK | SAE, data.PSK),  # WPA2/WPA3 transition: joined as WPA-PSK
    (1, 0, EAP, data.ENTERPRISE),
    (1, 0, EAP | PSK, data.ENTERPRISE),
    (1, 0, data.SEC_KEY_MGMT_EAP_SUITE_B_192, data.ENTERPRISE),
    (0, 0, OWE, data.OWE),
    (0, 0, data.SEC_KEY_MGMT_OWE_TM, data.OWE),
])
def test_security(flags, wpa, rsn, kind):
    assert data.security(flags, wpa, rsn) == kind


def test_key_mgmt_and_joinable():
    assert data.KEY_MGMT == {data.OPEN: None, data.OWE: "owe", data.PSK: "wpa-psk", data.SAE: "sae"}
    wep = data.Network("old", 50, data.WEP, False, False)
    eap = data.Network("corp", 50, data.ENTERPRISE, False, False)
    assert not wep.joinable and not eap.joinable
    assert data.Network("corp", 50, data.ENTERPRISE, True, False).joinable  # saved elsewhere: activate
    assert "802.1X" in data.unsupported_sentence(eap)
    assert "WEP" in data.unsupported_sentence(wep)


def test_ssid_text():
    class Bytes:
        def get_data(self):
            return "Café".encode()
    assert data.ssid_text(None) == ""
    assert data.ssid_text(b"") == ""
    assert data.ssid_text(Bytes()) == "Café"
    assert data.ssid_text(b"bad\xff") == "bad�"


@pytest.mark.parametrize("strength,icon", [
    (100, "excellent"), (80, "excellent"), (79, "good"), (55, "good"), (54, "ok"), (30, "ok"),
    (29, "weak"), (5, "weak"), (4, "none"), (0, "none")])
def test_signal_icon(strength, icon):
    assert data.signal_icon(strength) == f"network-wireless-signal-{icon}-symbolic"


@pytest.mark.parametrize("kind,password,ok", [
    (data.PSK, "12345678", True),
    (data.PSK, "1234567", False),
    (data.PSK, "x" * 63, True),
    (data.PSK, "x" * 64, False),
    (data.PSK, "zB" * 32, False),       # 64 characters, not all hex
    (data.PSK, "0aF9" * 16, True),      # a raw 64-hex-digit key
    (data.PSK, "pässwort1", False),     # outside printable ASCII
    (data.SAE, "", False),
    (data.SAE, "x", True),
])
def test_password_problem(kind, password, ok):
    problem = data.password_problem(kind, password)
    assert (problem is None) == ok
    if problem:
        assert problem.endswith(".")


@pytest.mark.parametrize("ssid,ok", [
    ("Home", True),
    ("a", True),
    ("x" * 32, True),
    ("x" * 33, False),
    ("", False),
    ("é" * 16, True),      # 32 bytes of UTF-8
    ("é" * 17, False),     # 34 bytes: the limit counts bytes, not characters
    ("\U0001F4F6" * 8, True),
    ("\U0001F4F6" * 9, False),
    ("bad\udcff", False),  # not encodable as UTF-8
])
def test_ssid_problem(ssid, ok):
    problem = data.ssid_problem(ssid)
    assert (problem is None) == ok
    if problem:
        assert problem.endswith(".") and problem[0].isupper()


@pytest.mark.parametrize("ssid,kind,password,ok", [
    ("Ghost", data.OPEN, "", True),
    ("Ghost", data.OPEN, "ignored", True),       # an open network has no password to check
    ("Ghost", data.PSK, "12345678", True),
    ("Ghost", data.PSK, "0aF9" * 16, True),      # 64 hex characters
    ("Ghost", data.PSK, "", False),
    ("Ghost", data.PSK, "1234567", False),
    ("Ghost", data.PSK, "x" * 64, False),
    ("", data.OPEN, "", False),
    ("", data.PSK, "12345678", False),
    ("x" * 33, data.PSK, "12345678", False),
])
def test_hidden_problem(ssid, kind, password, ok):
    problem = data.hidden_problem(ssid, kind, password)
    assert (problem is None) == ok
    if password and problem:
        assert password not in problem  # a sentence for the screen never repeats the password


def test_hidden_choices_and_network():
    assert [k for k, _label in data.HIDDEN_SECURITY] == [data.OPEN, data.PSK, data.SAE]
    assert [label for _k, label in data.HIDDEN_SECURITY] == ["Open", "WPA/WPA2 Personal", "WPA3 Personal"]
    assert data.hidden_problem("Lab", data.SAE, "") == "Enter the network password."
    assert data.hidden_problem("Lab", data.SAE, "short") is None  # SAE has no length rule
    net = data.hidden_network("Ghost", data.PSK)
    assert (net.ssid, net.security, net.saved, net.active, net.ref) == ("Ghost", data.PSK, False, False, None)
    assert net.joinable and net.needs_password
    assert data.hidden_network("Ghost", data.OPEN).joinable


def test_build_connection_hidden_flag():
    """build_connection(hidden=True) sets the wireless setting's `hidden` property (real libnm, no
    NetworkManager: it only builds an in-memory connection)."""
    probe = (
        "import json, sys; sys.path.insert(0, sys.argv[1])\n"
        "from seclegion_wifi.ui.backend import build_connection\n"
        "def show(c):\n"
        "    w, s = c.get_setting_wireless(), c.get_setting_wireless_security()\n"
        "    return [w.get_hidden(), w.get_ssid().get_data().decode(),\n"
        "            s.get_key_mgmt() if s else None, s.get_psk() if s else None]\n"
        "print(json.dumps([show(build_connection('Ghost', 'wpa-psk', '12345678', hidden=True)),\n"
        "                  show(build_connection('Ghost', 'open', None, hidden=True)),\n"
        "                  show(build_connection('Seen', 'wpa-psk', '12345678')),\n"
        "                  show(build_connection('Seen', 'open', None, hidden=False))]))\n")
    py = "/usr/bin/python3"
    if not os.path.exists(py) or subprocess.run(
            [py, "-c", "import gi; gi.require_version('NM', '1.0'); from gi.repository import NM"],
            capture_output=True).returncode:
        pytest.skip("libnm typelib not importable by system python3")
    r = subprocess.run([py, "-c", probe, os.path.join(ROOT, "desktop", "wifi")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [[True, "Ghost", "wpa-psk", "12345678"], [True, "Ghost", None, None],
                                    [False, "Seen", "wpa-psk", "12345678"], [False, "Seen", None, None]]


def test_sentences_are_plain_and_never_name_a_command():
    lines = [data.failure_sentence("Home", r) for r in (7, 8, 10, 11, 53, 39, 999)]
    lines += [data.error_sentence(a, "Home", "GDBus.Error:org.freedesktop.NetworkManager.Failed: x")
              for a in data.ACTIONS]
    lines.append(data.error_sentence("connect", "Home", "Insufficient privileges: not authorized"))
    assert data.failure_sentence("Home", 7) == "Could not join Home: the password was not accepted."
    assert "out of range" in data.failure_sentence("Home", 53)
    assert data.error_sentence("forget", "Home", "boom") == "Could not forget Home."
    assert data.error_sentence("connect", "", "not authorized") == \
        "You are not allowed to change Wi-Fi settings here."
    for line in lines:
        assert line.endswith(".") and line[0].isupper(), line
        for word in ("nmcli", "sudo", "GDBus", "org.freedesktop", "$", "`"):
            assert word not in line, line


def test_nm_constants_match_libnm():
    """The data layer copies libnm's numbers so it can stay gi-free; check them where libnm exists."""
    probe = (
        "import gi; gi.require_version('NM', '1.0'); from gi.repository import NM\n"
        "S = getattr(NM, '80211ApSecurityFlags'); R = NM.DeviceStateReason\n"
        "print(int(getattr(NM, '80211ApFlags').PRIVACY), int(S.KEY_MGMT_PSK), int(S.KEY_MGMT_802_1X),"
        " int(S.KEY_MGMT_SAE), int(S.KEY_MGMT_OWE), int(S.KEY_MGMT_OWE_TM), int(S.KEY_MGMT_EAP_SUITE_B_192),"
        " int(R.NO_SECRETS), int(R.SUPPLICANT_DISCONNECT), int(R.SUPPLICANT_FAILED),"
        " int(R.SUPPLICANT_TIMEOUT), int(R.USER_REQUESTED), int(R.SSID_NOT_FOUND))\n")
    if not os.path.exists("/usr/bin/python3"):
        pytest.skip("no system python3")
    r = subprocess.run(["/usr/bin/python3", "-c", probe], capture_output=True, text=True)
    if r.returncode:
        pytest.skip("libnm typelib not importable: " + r.stderr[-200:])
    d = data
    assert [int(x) for x in r.stdout.split()] == [
        d.AP_FLAGS_PRIVACY, d.SEC_KEY_MGMT_PSK, d.SEC_KEY_MGMT_802_1X, d.SEC_KEY_MGMT_SAE,
        d.SEC_KEY_MGMT_OWE, d.SEC_KEY_MGMT_OWE_TM, d.SEC_KEY_MGMT_EAP_SUITE_B_192, d.REASON_NO_SECRETS,
        d.REASON_SUPPLICANT_DISCONNECT, d.REASON_SUPPLICANT_FAILED, d.REASON_SUPPLICANT_TIMEOUT,
        d.REASON_USER_REQUESTED, d.REASON_SSID_NOT_FOUND]
