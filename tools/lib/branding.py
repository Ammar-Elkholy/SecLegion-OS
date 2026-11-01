# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The branding rule for what a booted ISO shows: no Arch branding on serial or screen.

Forbidden: the word "arch" on its own and the names "Arch Linux" / "archlinux" (any case).
Not branding, so allowed: the kernel release tag (`7.2.9-arch1-1`, the `arch` there is followed
by a digit) and archiso tool identifiers (`archiso`, `archisobasedir`), which are package and
mkinitcpio names, not something the product calls itself. M2 renames the rest.
"""

import re

BRAND_RE = re.compile(r"arch[ _-]?linux|\barch\b", re.IGNORECASE)
# Files on an installed system name the base distro technically (PKGBUILD `arch=`, `ID_LIKE=arch`,
# `arch-chroot`, the `arch-extra` package source); only the product name is branding there (D-BR-2).
NAME_RE = re.compile(r"arch[ _-]?linux", re.IGNORECASE)
# same as tests/lib/serial.py
ANSI_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\r")


def scan(text):
    """Return the forbidden hits in `text` as short one-line contexts (empty = clean)."""
    clean = ANSI_RE.sub("", text)
    hits = []
    for match in BRAND_RE.finditer(clean):
        start, end = max(0, match.start() - 20), match.end() + 20
        hits.append(" ".join(clean[start:end].split()))
    return hits
