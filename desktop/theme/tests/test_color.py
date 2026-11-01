# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import unittest

import _bootstrap  # noqa: F401
from seclegion_theme import color as C


class ColorMath(unittest.TestCase):
    def test_wcag_reference_values(self):
        self.assertAlmostEqual(C.contrast("#000000", "#ffffff"), 21.0, places=6)
        self.assertAlmostEqual(C.contrast("#777777", "#ffffff"), 4.48, places=2)

    def test_oklch_roundtrip(self):
        for c in ("#050f0e", "#00ff88", "#00f0ff", "#ff2266", "#e0fff4"):
            self.assertEqual(C.from_oklch(*C.to_oklch(c)), c)

    def test_out_of_gamut_keeps_lightness_and_hue(self):
        out = C.from_oklch(0.8, 0.4, 150)
        L, _, h = C.to_oklch(out)
        self.assertAlmostEqual(L, 0.8, delta=0.01)
        self.assertLess(C.hue_distance(h, 150), 3)

    def test_bad_hex_rejected(self):
        for bad in ("", "#12345", "#gggggg", '")os.execute('):
            with self.assertRaises(ValueError):
                C.normalize_hex(bad)


if __name__ == "__main__":
    unittest.main()
