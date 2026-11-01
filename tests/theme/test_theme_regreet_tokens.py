# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""pytest entry for the engine's regreet token test (plan r12 L1 G1); the tests live in
desktop/theme/tests/test_regreet_tokens.py so `unittest discover` runs them too."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop" / "theme" / "tests"))

from test_regreet_tokens import RegreetTokens  # noqa: E402,F401
