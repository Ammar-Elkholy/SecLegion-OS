# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Disk map: a proportional bar of one disk. segments()/palette()/human() are pure (no GTK) so the tests
need no display; DiskMap() builds the Gtk.DrawingArea lazily. Colours come from desktop/theme/tokens.toml
through theme.tokens_path(), never from hex literals here."""

import os
import pathlib
import sys
import tomllib

_INSTALLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "installd")
if _INSTALLD not in sys.path:
    sys.path.insert(0, _INSTALLD)
import configurator as cfg  # noqa: E402
from theme import tokens_path  # noqa: E402

_WINDOWS_FS = ("ntfs", "bitlocker", "refs", "exfat")
_LINUX_FS = ("ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs")
MIN_PART_PX = 4


def human(n):
    """Size in plain units: 260 MiB, 200 GiB, 1.0 TiB."""
    n = int(n)
    if n >= 1 << 40:
        return f"{n / (1 << 40):.1f} TiB"
    if n >= 10 << 30:
        return f"{n / (1 << 30):.0f} GiB"
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GiB"
    return f"{n / (1 << 20):.0f} MiB"


def role_of(part):
    """Colour role of an lsblk partition node."""
    parttype = (part.get("parttype") or "").lower()
    fstype = (part.get("fstype") or "").lower()
    if parttype == cfg.ESP_GUID:
        return "esp"
    if parttype in cfg._WINDOWS_PARTTYPES:  # MSR / recovery
        return "windows_system"
    if fstype in _WINDOWS_FS:
        return "windows"
    if fstype in _LINUX_FS or (not fstype and parttype == "0fc63daf-8483-4772-8e79-3d69d8477de4"):
        return "linux"
    if fstype == "swap":
        return "swap"
    if fstype == "crypto_luks":
        return "luks"
    return "other"


def segments(disk):
    """[{name, path, start, size, fstype, kind: part|free, role}] covering the disk from byte 0 to its end,
    in order, without overlap. Gaps (and the tail) are kind free."""
    sec = int(disk.get("log-sec") or 512)
    total = int(disk["size"])
    parts = sorted((p for p in disk.get("children") or [] if p.get("type") == "part"),
                   key=lambda p: int(p["start"]))
    out, pos = [], 0

    def free(end):
        if end > pos:
            out.append({"name": "free", "path": None, "start": pos, "size": end - pos, "fstype": None,
                        "kind": "free", "role": "free"})

    for p in parts:
        start = max(int(p["start"]) * sec, pos)  # fail safe: never overlap the previous segment
        end = min(int(p["start"]) * sec + int(p["size"]), total)
        if end <= start:
            continue
        free(start)
        out.append({"name": p.get("name") or os.path.basename(p.get("path") or ""), "path": p.get("path"),
                    "start": start, "size": end - start, "fstype": p.get("fstype"), "kind": "part",
                    "role": role_of(p)})
        pos = end
    free(total)
    return out


def palette(path=None):
    """role -> '#RRGGBB', all read from the theme tokens."""
    t = tomllib.loads(pathlib.Path(path or tokens_path()).read_text())
    c, ansi = t["colors"], t["ansi"]["colors"]
    return {"esp": c["warn"], "windows": ansi[4], "windows_system": ansi[12], "linux": c["ok"],
            "swap": ansi[5], "luks": ansi[13], "other": c["muted"], "free": c["surface2"],
            "hatch": c["muted"], "text": c["bg"], "label": c["text"], "selected": c["accent"],
            "bg": c["bg"]}


def pixel_widths(segs, total_px, min_px=MIN_PART_PX):
    """Pixel width per segment: proportional, a partition never thinner than min_px, free gaps may vanish."""
    total = sum(s["size"] for s in segs) or 1
    raw = [s["size"] / total * total_px for s in segs]
    fixed = [s["kind"] == "part" and r < min_px for s, r in zip(segs, raw, strict=True)]
    left = total_px - sum(min_px for f in fixed if f)
    rest = sum(r for r, f in zip(raw, fixed, strict=True) if not f) or 1
    return [float(min_px) if f else r * max(left, 0) / rest for r, f in zip(raw, fixed, strict=True)]


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def DiskMap(disk, height=64, selected=None):
    """Gtk.DrawingArea of the disk. area.set_selected(path) outlines one partition (the one to replace)."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gtk, Pango, PangoCairo

    segs = segments(disk)
    pal = palette()
    area = Gtk.DrawingArea(content_height=height, hexpand=True, height_request=height)
    area.selected = selected
    area.segs = segs
    area.add_css_class("diskmap")
    summary = ", ".join(f"{s['name']} {human(s['size'])}" + (f" {s['fstype']}" if s["fstype"] else "")
                        for s in segs)
    area.update_property([Gtk.AccessibleProperty.LABEL], [f"Disk layout: {summary}"])

    def spans(w):
        x, out = 0.0, []
        for s, sw in zip(segs, pixel_widths(segs, w), strict=True):
            out.append((s, x, sw))
            x += sw
        return out

    def label(s):
        name = "Free space" if s["kind"] == "free" else s["name"]
        detail = human(s["size"]) + (f" · {s['fstype']}" if s["fstype"] else "")
        return name, detail

    def draw(_a, cr, w, h):
        font = Pango.FontDescription("Sans 9")
        cr.save()
        r = 8
        cr.new_sub_path()
        for cx, cy, a0 in ((w - r, r, -90), (w - r, h - r, 0), (r, h - r, 90), (r, r, 180)):
            cr.arc(cx, cy, r, a0 * 3.14159265 / 180, (a0 + 90) * 3.14159265 / 180)
        cr.close_path()
        cr.clip()
        for s, x, sw in spans(w):
            if sw <= 0:
                continue
            cr.set_source_rgb(*_rgb(pal[s["role"]]))
            cr.rectangle(x, 0, sw, h)
            cr.fill()
            if s["kind"] == "free":
                cr.save()
                cr.rectangle(x, 0, sw, h)
                cr.clip()
                cr.set_source_rgba(*_rgb(pal["hatch"]), 0.45)
                cr.set_line_width(1)
                for hx in range(int(x) - h, int(x + sw), 9):
                    cr.move_to(hx, h)
                    cr.line_to(hx + h, 0)
                cr.stroke()
                cr.restore()
            color = pal["label"] if s["kind"] == "free" else pal["text"]
            name, detail = label(s)
            for text in (f"{name}\n{detail}", name, ""):
                lay = area.create_pango_layout(text)
                lay.set_font_description(font)
                tw, th = lay.get_pixel_size()
                if text and tw <= sw - 10 and th <= h - 6:
                    cr.set_source_rgb(*_rgb(color))
                    cr.move_to(x + 6, (h - th) / 2)
                    PangoCairo.show_layout(cr, lay)
                    break
            cr.set_source_rgb(*_rgb(pal["bg"]))  # a thin gap between neighbours
            cr.rectangle(x + sw - 1, 0, 1, h)
            cr.fill()
        cr.restore()
        if area.selected:
            for s, x, sw in spans(w):
                if s["path"] == area.selected and sw > 0:
                    cr.set_source_rgb(*_rgb(pal["selected"]))
                    cr.set_line_width(3)
                    cr.rectangle(x + 1.5, 1.5, max(sw - 3, 1), h - 3)
                    cr.stroke()

    def tip(_a, x, _y, _kb, tooltip):
        for s, sx, sw in spans(area.get_width()):
            if sx <= x < sx + sw:
                name, detail = label(s)
                tooltip.set_text(f"{name}: {detail}")
                return True
        return False

    def set_selected(path):
        area.selected = path
        area.queue_draw()

    area.set_draw_func(draw)
    area.set_has_tooltip(True)
    area.connect("query-tooltip", tip)
    area.set_selected = set_selected
    return area
