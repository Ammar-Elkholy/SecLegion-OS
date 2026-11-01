# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""matugen runner and JSON parser.

Verified against matugen 4.2.0 (real run, 2026-10-14): the layout is
`colors.<name>.dark.color`. The older `colors.dark.<name>` layout is parsed too
but only checked against a hand-written fixture. `--prefer` is mandatory:
without it matugen exits 1 on images with several candidate source colours
when no terminal is attached.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import color as C
from .palette import Seed, ThemeError, seed_from_colors

TIMEOUT_S = 30


class MatugenMissing(ThemeError):
    pass


def argv(image: Path) -> list[str]:
    # --dry-run: print colours only, never run templates from ~/.config/matugen.
    return ["matugen", "image", str(image), "--json", "hex", "--dry-run", "--mode", "dark",
            "--prefer", "saturation"]


def run(image: Path, *, runner=subprocess.run, which=shutil.which) -> dict:
    exe = which("matugen")
    if not exe:
        raise MatugenMissing("matugen is not installed (needed for --mode auto)")
    cmd = argv(image)
    cmd[0] = exe
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as e:
        raise ThemeError(f"matugen timed out after {TIMEOUT_S}s") from e
    if proc.returncode != 0:
        raise ThemeError(f"matugen failed ({proc.returncode}): {proc.stderr.strip()[:300]}")
    out = proc.stdout
    start = out.find("{")
    if start < 0:
        raise ThemeError("matugen produced no JSON")
    try:
        return json.loads(out[start:])
    except json.JSONDecodeError as e:
        raise ThemeError(f"matugen JSON unreadable: {e}") from e


def _as_hex(v) -> str | None:
    if isinstance(v, dict):
        for k in ("color", "hex", "value"):
            if k in v:
                return _as_hex(v[k])
        return None
    if isinstance(v, str) and v.startswith("#") and len(v) in (7, 9):
        try:
            return C.normalize_hex(v[:7])
        except ValueError:
            return None
    return None


def _lookup(colors: dict, name: str) -> str | None:
    """Dark-scheme colour `name` in either known layout."""
    scheme = colors.get("dark")
    if isinstance(scheme, dict) and name in scheme:  # v2: colors.dark.primary
        return _as_hex(scheme[name])
    entry = colors.get(name)
    if isinstance(entry, dict):  # v3: colors.primary.dark
        return _as_hex(entry.get("dark"))
    return None


def seed_from_json(data: dict, *, identity: bool = True) -> Seed:
    colors = data.get("colors") if isinstance(data, dict) else None
    if not isinstance(colors, dict):
        raise ThemeError("matugen JSON has no 'colors'")
    primary = _lookup(colors, "primary")
    if not primary:
        raise ThemeError("matugen JSON has no dark 'primary' colour")
    second = _lookup(colors, "tertiary") or _lookup(colors, "secondary")
    return seed_from_colors(primary, second, identity=identity)
