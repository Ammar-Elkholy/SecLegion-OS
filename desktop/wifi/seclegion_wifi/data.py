# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The Wi-Fi panel's data layer: no GTK, no libnm. Access points come in as plain records (the ui
adapter reads them off libnm), go out as one Network per SSID, strongest first.

Flag values are NetworkManager's (NM80211ApFlags, NM80211ApSecurityFlags, NMDeviceStateReason);
tests/desktop/test_wifi.py checks them against libnm when it is importable.
"""
from __future__ import annotations

from dataclasses import dataclass

AP_FLAGS_PRIVACY = 0x1
SEC_KEY_MGMT_PSK = 0x100
SEC_KEY_MGMT_802_1X = 0x200
SEC_KEY_MGMT_SAE = 0x400
SEC_KEY_MGMT_OWE = 0x800
SEC_KEY_MGMT_OWE_TM = 0x1000
SEC_KEY_MGMT_EAP_SUITE_B_192 = 0x2000

# Security kinds. `KEY_MGMT` is what the panel puts in 802-11-wireless-security.key-mgmt; a kind
# without an entry is one the panel cannot join itself (WEP, enterprise).
OPEN, OWE, WEP, PSK, SAE, ENTERPRISE = "open", "owe", "wep", "wpa-psk", "sae", "enterprise"
LABELS = {OPEN: "Open", OWE: "Open (encrypted)", WEP: "WEP", PSK: "WPA2", SAE: "WPA3",
          ENTERPRISE: "Enterprise"}
KEY_MGMT = {OPEN: None, OWE: "owe", PSK: "wpa-psk", SAE: "sae"}
# What the "hidden network" dialog offers: nothing is advertised, so the panel cannot read the
# security off the air. WPA-PSK joins WPA2 and WPA2/WPA3 transition networks; a WPA3-only network
# needs SAE, so it is its own choice.
HIDDEN_SECURITY = ((OPEN, "Open"), (PSK, "WPA/WPA2 Personal"), (SAE, "WPA3 Personal"))
SECURED = (PSK, SAE)
SSID_MAX_BYTES = 32

REASON_NO_SECRETS = 7
REASON_SUPPLICANT_DISCONNECT = 8
REASON_SUPPLICANT_FAILED = 10
REASON_SUPPLICANT_TIMEOUT = 11
REASON_USER_REQUESTED = 39
REASON_SSID_NOT_FOUND = 53


@dataclass(frozen=True)
class AccessPoint:
    """One radio as libnm reports it; `ref` is opaque to this module (the ui keeps its D-Bus path)."""
    ssid: str
    strength: int
    flags: int = 0
    wpa_flags: int = 0
    rsn_flags: int = 0
    ref: object = None


@dataclass(frozen=True)
class Network:
    """One SSID: the strongest access point that carries it, and what the panel knows about it."""
    ssid: str
    strength: int
    security: str
    saved: bool
    active: bool
    ref: object = None

    @property
    def label(self) -> str:
        return LABELS[self.security]

    @property
    def secured(self) -> bool:
        return self.security not in (OPEN, OWE)

    @property
    def needs_password(self) -> bool:
        """A new network the panel must ask a password for (saved ones already have theirs)."""
        return not self.saved and self.security in (PSK, SAE)

    @property
    def joinable(self) -> bool:
        return self.saved or self.security in KEY_MGMT


def ssid_text(raw) -> str:
    """The SSID bytes as text ('' for a hidden network). Accepts bytes or anything with get_data()."""
    if raw is None:
        return ""
    if hasattr(raw, "get_data"):
        raw = raw.get_data()
    return bytes(raw or b"").decode("utf-8", errors="replace").strip("\x00")


def security(flags: int, wpa_flags: int, rsn_flags: int) -> str:
    """The kind of security an access point advertises. SAE wins only when there is no PSK beside it:
    a WPA2/WPA3 transition network is joined as WPA-PSK, which every client and driver supports."""
    keys = wpa_flags | rsn_flags
    if keys & (SEC_KEY_MGMT_802_1X | SEC_KEY_MGMT_EAP_SUITE_B_192):
        return ENTERPRISE
    if keys & SEC_KEY_MGMT_PSK:
        return PSK
    if keys & SEC_KEY_MGMT_SAE:
        return SAE
    if keys & (SEC_KEY_MGMT_OWE | SEC_KEY_MGMT_OWE_TM):
        return OWE
    if flags & AP_FLAGS_PRIVACY:
        return WEP
    return OPEN


def networks(aps: list[AccessPoint], saved: set[str], active: str | None) -> list[Network]:
    """One Network per SSID (hidden ones dropped), keeping its strongest access point; sorted by signal,
    strongest first, then by name."""
    best: dict[str, AccessPoint] = {}
    for ap in aps:
        if ap.ssid and (ap.ssid not in best or ap.strength > best[ap.ssid].strength):
            best[ap.ssid] = ap
    out = [Network(ssid, ap.strength, security(ap.flags, ap.wpa_flags, ap.rsn_flags), ssid in saved,
                   ssid == active, ap.ref) for ssid, ap in best.items()]
    return sorted(out, key=lambda n: (-n.strength, n.ssid.casefold(), n.ssid))


def signal_icon(strength: int) -> str:
    for floor, name in ((80, "excellent"), (55, "good"), (30, "ok"), (5, "weak")):
        if strength >= floor:
            return f"network-wireless-signal-{name}-symbolic"
    return "network-wireless-signal-none-symbolic"


def password_problem(kind: str, password: str) -> str | None:
    """Why `password` cannot be a key for `kind`, as a sentence; None when it can."""
    if kind == SAE:
        return None if password else "Enter the network password."
    if len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password):
        return None  # a raw 256-bit key
    if not 8 <= len(password) <= 63:
        return "A WPA password has 8 to 63 characters."
    if not all(" " <= c <= "~" for c in password):
        return "A WPA password uses only plain letters, digits and symbols."
    return None


def ssid_problem(ssid: str) -> str | None:
    """Why `ssid` cannot be a network name (1 to 32 bytes of UTF-8), as a sentence; None when it can."""
    try:
        size = len(ssid.encode("utf-8"))
    except UnicodeEncodeError:
        return "The network name uses characters that cannot be sent."
    if size == 0:
        return "Enter the network name."
    if size > SSID_MAX_BYTES:
        return f"A network name is at most {SSID_MAX_BYTES} bytes long."
    return None


def hidden_problem(ssid: str, kind: str, password: str) -> str | None:
    """The first reason the hidden-network form cannot be submitted, as a sentence; None when it can.
    The password is checked only for a secured network and never appears in the sentence."""
    return ssid_problem(ssid) or (password_problem(kind, password) if kind in SECURED else None)


def hidden_network(ssid: str, kind: str) -> Network:
    """The Network the join path takes for a hidden SSID: no access point, not saved, not active."""
    return Network(ssid, 0, kind, False, False)


def failure_sentence(ssid: str, reason: int) -> str:
    """A device failure reason (NMDeviceStateReason) as one plain sentence."""
    if reason in (REASON_NO_SECRETS, REASON_SUPPLICANT_DISCONNECT):
        return f"Could not join {ssid}: the password was not accepted."
    if reason in (REASON_SUPPLICANT_TIMEOUT, REASON_SUPPLICANT_FAILED):
        return f"Could not join {ssid}: the network did not answer in time."
    if reason == REASON_SSID_NOT_FOUND:
        return f"Could not join {ssid}: the network is out of range."
    return f"Could not join {ssid}."


def unsupported_sentence(network: Network) -> str:
    if network.security == ENTERPRISE:
        return f"{network.ssid} is an enterprise (802.1X) network, which this panel cannot join yet."
    return f"{network.ssid} uses WEP, which is not secure and is not supported."


ACTIONS = {
    "connect": "Could not join {ssid}.",
    "forget": "Could not forget {ssid}.",
    "disconnect": "Could not disconnect from {ssid}.",
    "radio": "Could not switch Wi-Fi on or off.",
    "scan": "Could not look for networks right now.",
    "client": "NetworkManager is not running, so Wi-Fi cannot be managed.",
}


def error_sentence(action: str, ssid: str = "", detail: str = "") -> str:
    """A failed call as a plain sentence. NetworkManager's own message is never shown: it can name
    D-Bus methods and setting keys; only a refused authorization gets its own sentence."""
    if "not authorized" in detail.lower() or "permission" in detail.lower():
        return "You are not allowed to change Wi-Fi settings here."
    return ACTIONS[action].format(ssid=ssid or "the network")
