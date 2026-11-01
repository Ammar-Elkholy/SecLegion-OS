# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Maintainer helper: record a trimmed real matugen output as a fixture.

    matugen image IMG --json hex --dry-run --mode dark --prefer saturation | \
        python3 trim_fixture.py > fixtures/matugen_<version>_real.json
"""

import json
import sys

d = json.load(sys.stdin)
json.dump(
    {"colors": d["colors"], "mode": d.get("mode"), "is_dark_mode": d.get("is_dark_mode")},
    sys.stdout,
    indent=1,
)
