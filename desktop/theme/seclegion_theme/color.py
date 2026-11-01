# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Colour maths: sRGB <-> OKLab/OKLCH, WCAG 2.x contrast, gamut mapping.

Colours are '#rrggbb' strings at the API boundary. Contrast is always
computed on the final 8-bit values so a reported ratio is the real one.
"""
from __future__ import annotations

import math
import re

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(value: str) -> str:
    m = _HEX_RE.match(value.strip())
    if not m:
        raise ValueError(f"not a #rrggbb colour: {value!r}")
    return "#" + m.group(1).lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = normalize_hex(value)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(value: str) -> float:
    """WCAG 2.x relative luminance."""
    r, g, b = (_to_linear(x / 255) for x in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def _linear_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    ln = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = math.cbrt(ln), math.cbrt(m), math.cbrt(s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    ln, m, s = l_**3, m_**3, s_**3
    return (
        4.0767416621 * ln - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * ln + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * ln - 0.7034186147 * m + 1.7076147010 * s,
    )


def to_oklch(value: str) -> tuple[float, float, float]:
    """Return (L 0..1, C, h degrees 0..360)."""
    r, g, b = (_to_linear(x / 255) for x in hex_to_rgb(value))
    L, a, bb = _linear_to_oklab(r, g, b)
    C = math.hypot(a, bb)
    h = math.degrees(math.atan2(bb, a)) % 360.0 if C > 1e-4 else 0.0
    return L, C, h


def _in_gamut(rgb: tuple[float, float, float]) -> bool:
    return all(-1e-6 <= c <= 1 + 1e-6 for c in rgb)


def from_oklch(L: float, C: float, h: float) -> str:
    """OKLCH -> '#rrggbb'. Out-of-gamut colours keep L and h; C is reduced."""
    L = max(0.0, min(1.0, L))
    if L >= 1.0:
        return "#ffffff"
    if L <= 0.0:
        return "#000000"
    hr = math.radians(h)
    ca, sa = math.cos(hr), math.sin(hr)
    C = max(0.0, C)
    if not _in_gamut(_oklab_to_linear(L, C * ca, C * sa)):
        lo, hi = 0.0, C
        for _ in range(24):
            mid = (lo + hi) / 2
            if _in_gamut(_oklab_to_linear(L, mid * ca, mid * sa)):
                lo = mid
            else:
                hi = mid
        C = lo
    lin = _oklab_to_linear(L, C * ca, C * sa)
    r, g, b = (round(_from_linear(c) * 255) for c in lin)
    return rgb_to_hex((r, g, b))


def with_lightness(value: str, L: float) -> str:
    """Same hue and chroma, new OKLCH lightness (chroma gamut-mapped)."""
    _, C, h = to_oklch(value)
    return from_oklch(L, C, h)


def min_contrast(value: str, backgrounds: list[str]) -> float:
    return min(contrast(value, bg) for bg in backgrounds)


def lift_to_contrast(value: str, backgrounds: list[str], ratio: float) -> str:
    """Lighten `value` (hue and chroma kept) until it reaches `ratio` against
    every background. Unchanged if it already passes. If white still fails the
    result is the best effort (white); callers verify with min_contrast."""
    if min_contrast(value, backgrounds) >= ratio:
        return value
    lo, _, _ = to_oklch(value)
    hi = 1.0
    best = with_lightness(value, hi)
    if min_contrast(best, backgrounds) < ratio:
        return best
    for _ in range(24):
        mid = (lo + hi) / 2
        cand = with_lightness(value, mid)
        if min_contrast(cand, backgrounds) >= ratio:
            hi, best = mid, cand
        else:
            lo = mid
    return best


def hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)
