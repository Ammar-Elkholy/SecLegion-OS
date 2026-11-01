# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Lock screen: the password text must stay legible on the input field.

Reads the real desktop/hypr/hyprlock.conf, resolves the tokens its input-field
uses for font_color and inner_color, and checks their contrast (>= 7:1) for the
default palette and for engine-derived wallpaper palettes. Deleting the
font_color line, or pointing it at a low-contrast token, turns this red.

Set SL_LOCK_CONF=/path/to/hyprlock.conf to test another copy (the negative check).
"""

import os
import random
import re
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from seclegion_theme import color as C
from seclegion_theme import palette as P
from test_palette import synthetic_matugen_colors

REPO = Path(__file__).resolve().parents[3]
CONF = Path(os.environ.get("SL_LOCK_CONF", REPO / "desktop" / "hypr" / "hyprlock.conf"))
MIN_RATIO = 7.0
N_WALLPAPERS = 120


def input_field_tokens(text: str) -> dict[str, str]:
    """key -> token name for every `key = $sl_<token>` line in input-field { }."""
    m = re.search(r"^input-field\s*\{(.*?)^\}", text, re.S | re.M)
    if not m:
        raise AssertionError("no input-field block in " + str(CONF))
    out = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^\s*([a-z_]+)\s*=\s*\$sl_([a-z0-9_]+)\s*$", line)
        if kv:
            out[kv.group(1)] = kv.group(2)
    return out


def palettes():
    yield "default", P.finalize(P.default_tokens(), high=False, identity=False)
    rng = random.Random(20261015)
    for i in range(N_WALLPAPERS):
        a, b = synthetic_matugen_colors(rng)
        high = i % 2 == 1
        seed = P.seed_from_colors(a, b, identity=True)
        yield f"wallpaper {a} {b} high={high}", P.finalize(P.derive(seed), high=high, identity=True)


class LockContrast(unittest.TestCase):
    def setUp(self):
        self.tokens = input_field_tokens(CONF.read_text())

    def test_font_color_and_inner_color_are_theme_tokens(self):
        self.assertIn(
            "font_color",
            self.tokens,
            "input-field has no font_color = $sl_<token>: dots draw in hyprlock's dark default",
        )
        self.assertIn("inner_color", self.tokens)
        for name in self.tokens.values():
            self.assertIn(name, P.TOKEN_NAMES)

    def test_dots_contrast_on_field(self):
        fg, bg = self.tokens["font_color"], self.tokens["inner_color"]
        n = 0
        for label, t in palettes():
            ratio = C.contrast(t[fg], t[bg])
            self.assertGreaterEqual(ratio, MIN_RATIO, f"{fg} on {bg}: {ratio:.2f}:1 for {label}")
            n += 1
        self.assertGreater(n, 100)


if __name__ == "__main__":
    unittest.main()
