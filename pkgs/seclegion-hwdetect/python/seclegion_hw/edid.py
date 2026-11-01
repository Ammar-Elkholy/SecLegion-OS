# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""HiDPI from EDID: panel density from the first detailed timing block, mapped to a scale factor."""

from pathlib import Path

EDID_HEADER = bytes([0, 255, 255, 255, 255, 255, 255, 0])


def parse_edid(blob):
    """Return {width_px, height_px, width_mm, height_mm, dpi} or None if the blob is not a usable EDID."""
    if len(blob) < 128 or blob[:8] != EDID_HEADER:
        return None
    if blob[54] == 0 and blob[55] == 0:  # first descriptor is not a detailed timing
        return None
    width_px = blob[56] | ((blob[58] & 0xF0) << 4)
    height_px = blob[59] | ((blob[61] & 0xF0) << 4)
    width_mm = blob[66] | ((blob[68] & 0xF0) << 4) or blob[21] * 10
    height_mm = blob[67] | ((blob[68] & 0x0F) << 8) or blob[22] * 10
    if not (width_px and width_mm):
        return None
    return {
        "width_px": width_px,
        "height_px": height_px,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "dpi": round(width_px / (width_mm / 25.4)),
    }


def scale_for(dpi):
    if dpi >= 192:
        return 2.0
    if dpi >= 144:
        return 1.5
    return 1.0


def read_displays(root):
    """Connected DRM outputs that expose an EDID, eDP first."""
    displays = []
    base = Path(root) / "sys/class/drm"
    for entry in sorted(base.iterdir()) if base.is_dir() else []:
        status = entry / "status"
        edid = entry / "edid"
        if not (status.is_file() and edid.is_file()):
            continue
        if status.read_text().strip() != "connected":
            continue
        info = parse_edid(edid.read_bytes())
        if info:
            name = entry.name.split("-", 1)[-1]  # card1-eDP-1 -> eDP-1
            displays.append({"connector": name, **info, "scale": scale_for(info["dpi"])})
    displays.sort(key=lambda d: (not d["connector"].startswith("eDP"), d["connector"]))
    return displays
