# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""regreet.css is built from tokens only (plan r12 L1 G1).

Every colour in the file is a @define-color holding a colors.json token value, every
rule reaches colours through those names, and nothing else is a colour literal.
Runs as `unittest discover -s desktop/theme/tests` and as
`python3 -m pytest -q tests/theme -k regreet_tokens`.
"""

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from seclegion_theme import palette as P  # noqa: E402
from seclegion_theme import render  # noqa: E402

NO_SOURCE = {"wallpaper": None, "sha256": None, "accent_override": None}
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
DEFINE = re.compile(r"@define-color\s+(sl_[A-Za-z0-9_]+)\s+(#[0-9a-f]{6});")
USED = re.compile(r"@(sl_[A-Za-z0-9_]+)")


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def problems(css: str, token_values: set[str]) -> list[str]:
    """Reasons css is not tokens-only: a define that is no token value, a literal
    outside the defines, or a @name that is never defined."""
    body = strip_comments(css)
    out = []
    defined = {}
    for name, value in DEFINE.findall(body):
        defined[name] = value
        if value not in token_values:
            out.append(f"{name} {value} is not a token value")
    rules = DEFINE.sub("", body)
    out += [f"literal outside the defines: {m}" for m in LITERAL.findall(rules)]
    out += [f"undefined @{n}" for n in sorted(set(USED.findall(rules)) - set(defined))]
    return out


def render_css(tokens: dict) -> tuple[str, set[str]]:
    files = render.render_all(
        tokens, mode="default", requested_mode="default", contrast="normal", source=NO_SOURCE
    )
    values = set(json.loads(files["colors.json"])["tokens"].values())
    return files["regreet.css"], values


class RegreetTokens(unittest.TestCase):
    def test_regreet_tokens_default(self):
        css, values = render_css(P.default_tokens())
        self.assertEqual(problems(css, values), [])
        self.assertIn("@sl_bg", css)

    def test_regreet_tokens_follow_the_tokens(self):
        tokens = dict(P.default_tokens(), accent="#123456", bg="#010203")
        css, values = render_css(tokens)
        self.assertEqual(problems(css, values), [])
        self.assertIn("@define-color sl_accent #123456;", css)
        self.assertIn("@define-color sl_bg #010203;", css)

    def test_regreet_tokens_negative_literal_and_unknown_name(self):
        css, values = render_css(P.default_tokens())
        self.assertEqual(
            problems(css + ".x { color: #00ffcc; }", values), ["literal outside the defines: #00ffcc"]
        )
        self.assertEqual(
            problems(css + ".x { color: rgba(0,0,0,1); }", values), ["literal outside the defines: rgba("]
        )
        self.assertEqual(problems(css + ".x { color: @sl_nope; }", values), ["undefined @sl_nope"])
        self.assertEqual(
            problems(css + "@define-color sl_x #abcdef;", values), ["sl_x #abcdef is not a token value"]
        )

    def test_regreet_tokens_is_standalone(self):
        css, _ = render_css(P.default_tokens())
        self.assertNotIn("@import", strip_comments(css))
        # REUSE-IgnoreStart
        self.assertTrue(css.startswith("/* SPDX-License-Identifier: MIT */\n"))
        # REUSE-IgnoreEnd


if __name__ == "__main__":
    unittest.main()
