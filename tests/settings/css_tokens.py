#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G3: every @sl_* token used by the Settings stylesheet is defined in the theme's colors.css, and
window_bg_color maps to @sl_bg. Prints sl_bg-mapped and exits 0; exits 1 with the reason otherwise.

    python3 tests/settings/css_tokens.py [path/to/settings.css]
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "desktop" / "settings" / "seclegion_settings" / "ui" / "css" / "settings.css"
COLORS = REPO / "desktop" / "theme" / "default" / "colors.css"


def main(argv):
    css_path = Path(argv[0]) if argv else CSS
    css = css_path.read_text()
    defined = set(re.findall(r"@define-color\s+(sl_\w+)\s", COLORS.read_text()))
    used = set(re.findall(r"@(sl_\w+)", css))
    missing = sorted(used - defined)
    if not used:
        print(f"css_tokens: no @sl_ tokens found in {css_path}", file=sys.stderr)
        return 1
    if missing:
        print(f"css_tokens: undefined in colors.css: {', '.join(missing)}", file=sys.stderr)
        return 1
    m = re.search(r"@define-color\s+window_bg_color\s+@(\w+)\s*;", css)
    if not m or m.group(1) != "sl_bg":
        print(f"css_tokens: window_bg_color does not map to @sl_bg ({m.group(1) if m else 'undefined'})",
              file=sys.stderr)
        return 1
    print("sl_bg-mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
