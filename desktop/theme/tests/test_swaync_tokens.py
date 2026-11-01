# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""swaync popups and the OSD popup follow the theme tokens (plan r11 J1).

desktop/swaync/style.css must hold no colour literal, import the engine's
swaync-colors.css, and use only @sl_* names that file defines. Runs both as
`unittest discover -s desktop/theme/tests` and as
`python3 -m unittest desktop.theme.tests.test_swaync_tokens`.

SL_SWAYNC_STYLE=<file> points the checks at another style sheet (the negative
gate runs it against a copy that uses an undefined token).
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

from seclegion_theme import palette as P  # noqa: E402
from seclegion_theme import render  # noqa: E402

STYLE = Path(os.environ.get("SL_SWAYNC_STYLE") or ROOT / "desktop" / "swaync" / "style.css")
DEFAULT_COLORS = HERE.parent / "default" / "swaync-colors.css"
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b")
USED = re.compile(r"@(sl_[A-Za-z0-9_]+)")
DEFINED = re.compile(r"@define-color\s+(sl_[A-Za-z0-9_]+)\s")


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def undefined_tokens(css: str, colors: str) -> set[str]:
    return set(USED.findall(strip_comments(css))) - set(DEFINED.findall(colors))


class SwayncTokens(unittest.TestCase):
    def test_style_has_no_colour_literal(self):
        self.assertEqual(LITERAL.findall(strip_comments(STYLE.read_text())), [])

    def test_style_imports_swaync_colors_not_colors_css(self):
        css = STYLE.read_text()
        self.assertEqual(css.count("current/swaync-colors.css"), 1)
        self.assertNotIn("current/colors.css", css)

    def test_every_used_token_is_defined_by_the_default_export(self):
        self.assertEqual(undefined_tokens(STYLE.read_text(), DEFAULT_COLORS.read_text()), set())

    def test_every_used_token_is_defined_by_the_renderer(self):
        colors = render._swaync(P.default_tokens())
        self.assertEqual(undefined_tokens(STYLE.read_text(), colors), set())

    def test_osd_popup_and_bar_use_osd_tokens(self):
        css = strip_comments(STYLE.read_text())
        low = re.search(r"\.notification\.low\s*\{([^}]*)\}", css).group(1)
        for tok in ("sl_osd_bg", "sl_osd_fg", "sl_osd_frame"):
            self.assertIn(f"@{tok}", low)
        self.assertRegex(css, r"progressbar trough\s*\{[^}]*@sl_osd_track")
        self.assertRegex(css, r"progressbar progress\s*\{[^}]*@sl_osd_bar")

    def test_default_export_is_in_sync_with_the_renderer(self):
        self.assertEqual(DEFAULT_COLORS.read_text(), render._swaync(P.default_tokens()))

    def test_negative_undefined_token_is_reported(self):
        bad = STYLE.read_text() + "\n.x { color: @sl_nope; }\n"
        self.assertEqual(undefined_tokens(bad, DEFAULT_COLORS.read_text()), {"sl_nope"})
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "style.css"
            copy.write_text(bad)
            self.assertIn("sl_nope", undefined_tokens(copy.read_text(), DEFAULT_COLORS.read_text()))

    def test_negative_literal_is_reported(self):
        self.assertEqual(LITERAL.findall(strip_comments(".x { color: #00ffcc; }")), ["#00ffcc"])


if __name__ == "__main__":
    unittest.main()
