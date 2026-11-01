# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Theme manager: the themes `seclegion-theme list` offers and how `apply --theme ID` runs one.

A theme id is one of
  seclegion-dark                  the static SecLegion Dark tokens
  seclegion-teal, seclegion-cyan  built-in seed accents, derived through the same clamps as a wallpaper
  wallpaper:<sha8>                a recent wallpaper, found in the kept theme dirs

Unknown ids raise ThemeError before anything is written, so the current theme stays.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import color as C
from . import engine, palette, store
from .palette import ThemeError

# (id, label, accent hue in OKLCH degrees). Hues sit inside palette.ACCENT_HUE_RANGE.
BUILTINS = (
    ("seclegion-dark", "SecLegion Dark", None),
    ("seclegion-teal", "SecLegion Teal", 175.0),
    ("seclegion-cyan", "SecLegion Cyan", 200.0),
)
SEED_CHROMA = 0.15
WALLPAPER_PREFIX = "wallpaper:"
SHA_LEN = 8
MAX_WALLPAPERS = store.KEEP


def seed_accent(theme_id: str) -> str | None:
    """The seed accent (#rrggbb) of a built-in, None for seclegion-dark."""
    for tid, _, hue in BUILTINS:
        if tid == theme_id and hue is not None:
            return C.from_oklch(palette.ACCENT_L, SEED_CHROMA, hue)
    return None


def builtin_tokens(theme_id: str, contrast: str = "normal") -> dict:
    acc = seed_accent(theme_id)
    if acc is None:
        return engine.build_tokens("default", contrast, seed=None)
    return engine.build_tokens("auto", contrast, seed=palette.seed_from_accent(acc))


def _entry(theme_id: str, label: str, tokens: dict, current: bool) -> dict:
    return {
        "id": theme_id,
        "label": label,
        "current": current,
        "accent": tokens["accent"],
        "bg": tokens["bg"],
        "surface": tokens["surface"],
        "text": tokens["text"],
    }


def current_id(cur: dict | None) -> str:
    """Which listed theme the active colors.json is. No theme applied yet is SecLegion Dark;
    a hand-picked --accent is none of them ("")."""
    if not isinstance(cur, dict):
        return BUILTINS[0][0]
    src = cur.get("source") if isinstance(cur.get("source"), dict) else {}
    override = src.get("accent_override")
    if override:
        for tid, _, _ in BUILTINS:
            if seed_accent(tid) == override:
                return tid
        return ""
    if cur.get("mode") != "auto":
        return BUILTINS[0][0]
    sha = src.get("sha256")
    return WALLPAPER_PREFIX + sha[:SHA_LEN] if isinstance(sha, str) and len(sha) >= SHA_LEN else ""


def _kept(root: Path) -> list[tuple[dict, Path]]:
    """Complete kept theme dirs with a wallpaper link, newest first, as (colors.json, wallpaper)."""
    try:
        ents = [
            e for e in os.scandir(root) if e.is_dir(follow_symlinks=False) and store._is_theme_name(e.name)
        ]
    except OSError:
        return []
    found = []
    for e in sorted(ents, key=lambda e: e.stat(follow_symlinks=False).st_mtime_ns, reverse=True):
        d = Path(e.path)
        if not store._is_complete(d, None):
            continue
        try:
            data = json.loads((d / "colors.json").read_text(encoding="utf-8"))
            wall = Path(os.readlink(d / "wallpaper"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            found.append((data, wall))
    return found


def _wallpaper_themes(root: Path) -> dict[str, tuple[dict, Path]]:
    """sha8 -> (colors.json, wallpaper) for plain wallpaper themes whose image still exists."""
    out: dict[str, tuple[dict, Path]] = {}
    for data, wall in _kept(root):
        src = data.get("source") if isinstance(data.get("source"), dict) else {}
        sha, toks = src.get("sha256"), data.get("tokens")
        if not isinstance(sha, str) or len(sha) < SHA_LEN or not isinstance(toks, dict):
            continue
        if data.get("mode") != "auto" or data.get("contrast") != "normal" or src.get("accent_override"):
            continue
        if not all(isinstance(toks.get(k), str) for k in ("accent", "bg", "surface", "text")):
            continue
        if sha[:SHA_LEN] not in out and wall.is_file():
            out[sha[:SHA_LEN]] = (data, wall)
    return out


def _current(root: Path) -> dict | None:
    try:
        return store.read_current(root)
    except ThemeError:
        return None


def list_themes(env=None) -> list[dict]:
    root = store.state_root(env)
    cur = current_id(_current(root))
    out = [_entry(tid, label, builtin_tokens(tid), tid == cur) for tid, label, _ in BUILTINS]
    for sha8, (data, wall) in list(_wallpaper_themes(root).items())[:MAX_WALLPAPERS]:
        tid = WALLPAPER_PREFIX + sha8
        out.append(_entry(tid, wall.name or tid, data["tokens"], tid == cur))
    return out


def resolve(theme_id: str, env=None) -> dict:
    """The apply_theme arguments (mode, wallpaper, accent) that produce `theme_id`."""
    for tid, _, _ in BUILTINS:
        if tid == theme_id:
            acc = seed_accent(tid)
            return {"mode": "default"} if acc is None else {"mode": "auto", "accent": acc}
    if theme_id.startswith(WALLPAPER_PREFIX):
        hit = _wallpaper_themes(store.state_root(env)).get(theme_id[len(WALLPAPER_PREFIX) :])
        if hit is not None:
            return {"mode": "auto", "wallpaper": hit[1]}
    known = ", ".join(t["id"] for t in list_themes(env))
    raise ThemeError(f"unknown theme {theme_id!r}; known: {known}")


def current_contrast(env=None) -> str:
    cur = _current(store.state_root(env))
    c = cur.get("contrast") if isinstance(cur, dict) else None
    return c if c in engine.CONTRASTS else "normal"
