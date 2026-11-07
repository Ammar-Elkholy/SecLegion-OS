# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Keyboard layouts for the installer (GTK-free): the XKB list, the console keymap, the xkb switch string.

The lists are read at run time from the live ISO's own xkeyboard-config (rules/base.lst) and systemd
(kbd-model-map); nothing is copied into the repository."""
import re

BASE_LST = "/usr/share/X11/xkb/rules/base.lst"
KBD_MODEL_MAP = "/usr/share/systemd/kbd-model-map"
TOGGLE = "grp:alt_shift_toggle"
# Shown first (layout ids), in this order; the rest follow alphabetically.
COMMON = ["us", "gb", "de", "fr", "es", "it", "ara", "tr", "ru", "pt", "br", "pl", "nl", "se", "ca", "jp",
          "kr", "cn", "in", "il", "ua", "gr", "cz", "ch"]
_LAYOUT_RE = re.compile(r"^\s+(\S+)\s+(.+?)\s*$")
_VARIANT_RE = re.compile(r"^\s+(\S+)\s+([^\s:]+):\s*(.+?)\s*$")


def xkb_layouts(path=None):
    """[(layout, variant, description)] from the `! layout` and `! variant` sections; variant "" = base."""
    layouts, variants, section = [], [], None
    with open(path or BASE_LST, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!"):
                section = line[1:].strip()
                continue
            if section == "layout" and (m := _LAYOUT_RE.match(line)):
                layouts.append((m.group(1), "", m.group(2)))
            elif section == "variant" and (m := _VARIANT_RE.match(line)):
                variants.append((m.group(2), m.group(1), m.group(3)))
    return layouts + variants


def ordered(entries):
    """COMMON layouts first (base layout, then its variants), then everything else by description."""
    rank = {name: n for n, name in enumerate(COMMON)}
    common = sorted((e for e in entries if e[0] in rank), key=lambda e: (rank[e[0]], e[1] != "", e[2]))
    rest = sorted((e for e in entries if e[0] not in rank), key=lambda e: (e[2].lower(), e[1]))
    return common + rest


def known(layout, variant="", path=None):
    """True when (layout, variant) is in the list. A missing list file accepts anything well-formed."""
    try:
        entries = xkb_layouts(path)
    except OSError:
        return bool(re.fullmatch(r"[a-z0-9_]+", layout)) and bool(re.fullmatch(r"[A-Za-z0-9_]*", variant))
    return (layout, variant) in {(lo, va) for lo, va, _ in entries}


def console_keymap(layout, variant="", path=None):
    """vconsole keymap for an XKB layout (+variant) from kbd-model-map; "us" when the map has none."""
    best = {}
    try:
        with open(path or KBD_MODEL_MAP, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                cols = line.split()
                if len(cols) < 4 or line.startswith("#"):
                    continue
                key = (cols[1], "" if cols[3] == "-" else cols[3])
                best.setdefault(key, cols[0])
    except OSError:
        return "us"
    return best.get((layout, variant)) or best.get((layout, "")) or "us"


def xkb_spec(layout, variant=""):
    """(layouts, variants) strings for Hyprland and regreet. A password typed in the installer is US, so
    "us" is always in the list: Arabic is "us,ara" (US first, as before); any other layout "<chosen>,us"."""
    if layout == "us":
        return "us", variant
    if layout == "ara":
        return "us,ara", f",{variant}" if variant else ""
    return f"{layout},us", f"{variant}," if variant else ""
