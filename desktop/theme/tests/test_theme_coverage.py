# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""docs/theme-coverage.md audits every engine output and carries the owner include lines (plan r12 L1 G5)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from seclegion_theme import render  # noqa: E402

DOC = (HERE.parents[2] / "docs" / "theme-coverage.md").read_text()
NOT_A_SURFACE = {"colors.json"}  # data for tools, no surface of its own


class ThemeCoverage(unittest.TestCase):
    def test_audit_table_has_enough_rows(self):
        self.assertGreaterEqual(sum(1 for line in DOC.splitlines() if line.startswith("| ")), 14)

    def test_every_engine_output_is_audited(self):
        missing = [f for f in render.FILES if f not in NOT_A_SURFACE and f"`{f}`" not in DOC]
        self.assertEqual(missing, [])

    def test_owner_include_lines_are_present(self):
        base = "~/.local/state/seclegion/theme/current/"
        self.assertIn(f"include {base}kitty-colors.conf", DOC)
        self.assertIn(f'@import "{base}rofi-colors.rasi"', DOC)
        self.assertIn("STARSHIP_CONFIG", DOC)
        self.assertIn("starship-palette.toml", DOC)

    def test_negative_a_missing_output_would_be_caught(self):
        self.assertNotIn("`nonesuch.css`", DOC)


if __name__ == "__main__":
    unittest.main()
