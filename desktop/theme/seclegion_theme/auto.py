# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Auto theme: the on/off state and `sync`, run by the user path unit when the
owner's wallpaper scripts write ~/.cache/current_wallpaper (or the video frame).

sync never raises for a missing, unreadable or non-image wallpaper: the answer
is `skipped`. A failed derivation (matugen) raises ThemeError from the engine
before anything is swapped, so the old theme stays.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import engine, store

# leading bytes of the formats matugen reads from a wallpaper
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"BM")
FRAME_TYPES = ("gif", "video")


def state_file(env=None) -> Path:
    return store.state_root(env) / "auto"


def is_on(env=None) -> bool:
    try:
        return state_file(env).read_text(encoding="utf-8").strip() == "on"
    except (OSError, ValueError):
        return False


def set_auto(on: bool, env=None) -> None:
    f = state_file(env)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".auto.{os.getpid()}")
    tmp.write_text("on\n" if on else "off\n", encoding="utf-8")
    os.replace(tmp, f)


def _home(env) -> Path:
    return Path((env or os.environ).get("HOME") or os.path.expanduser("~"))


def _is_image(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
    except OSError:
        return False
    return head.startswith(_MAGIC) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None


def pick_image(env=None) -> Path | None:
    """The image to derive from: the current wallpaper, or the extracted frame
    for a gif or video; None when there is none or it is not an image."""
    cache = _home(env) / ".cache"
    named = _read_text(cache / "current_wallpaper")
    if not named:
        return None
    kind = _read_text(cache / "current_wallpaper_type") or "image"
    img = cache / "wallpaper_frame.png" if kind in FRAME_TYPES else Path(named)
    return img if img.is_file() and _is_image(img) else None


def sync(env=None, **apply_kw) -> str:
    """One line for the caller: `skipped: why`, `unchanged`, or `applied NAME`."""
    env = dict(os.environ) if env is None else env
    if not is_on(env):
        return "skipped: auto theme is off"
    img = pick_image(env)
    if img is None:
        return "skipped: no usable wallpaper image"
    try:
        cur = store.read_current(store.state_root(env))
        want = store.file_sha256(img)
    except OSError:
        return "skipped: wallpaper unreadable"
    if isinstance(cur, dict) and isinstance(cur.get("source"), dict) \
            and cur["source"].get("sha256") == want:
        return "unchanged"
    # the wallpaper tool that wrote current_wallpaper has painted it: no repaint (it would cut its transition)
    apply_kw.setdefault("paint_wallpaper", False)
    res = engine.apply_theme(wallpaper=img, mode="auto", env=env, **apply_kw)
    return f"applied {res.name}"
