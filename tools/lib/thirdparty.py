# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Parse docs/third-party.md: vendor rows (tables that have a Licence column) and their dates."""

import re

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def vendor_rows(text):
    """[{component, version, licence, pinned}] for every row of a table whose header has a Licence column.

    A missing column yields an empty string for that field, so the caller reports it as a gap."""
    rows, header = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = _cells(line)
        low = [c.lower() for c in cells]
        if header is None:
            header = low if any(c.startswith("licence") for c in low) else False
            continue
        if not header or set("".join(cells)) <= set("-: "):
            continue

        def col(prefix, header=header, cells=cells):
            for i, h in enumerate(header):
                if h.startswith(prefix) and i < len(cells):
                    return cells[i]
            return ""
        rows.append({"component": cells[0], "version": col("version"), "licence": col("licence"),
                     "pinned": col("pinned")})
    return rows
