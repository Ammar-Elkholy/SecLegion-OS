# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The apply pipeline: matugen -> tokens -> clamps -> render -> store -> hooks."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import color as C
from . import hooks, matugen, palette, render, store
from .palette import ThemeError

MODES = ("auto", "default")
CONTRASTS = ("normal", "high")


@dataclass
class Result:
    name: str
    path: Path
    mode: str
    requested_mode: str
    tokens: dict
    warnings: list[str] = field(default_factory=list)
    hook_results: list = field(default_factory=list)
    ms_total: float = 0.0
    ms_matugen: float = 0.0
    ms_hooks: float = 0.0


def build_tokens(mode: str, contrast: str, *, seed: palette.Seed | None) -> dict:
    high = contrast == "high"
    if mode == "default":
        return palette.finalize(palette.default_tokens(), high=high, identity=False)
    if seed is None:
        raise ThemeError("internal: no seed")
    return palette.finalize(palette.derive(seed), high=high, identity=True)


def apply_theme(
    *,
    wallpaper: str | os.PathLike | None = None,
    mode: str = "auto",
    accent: str | None = None,
    contrast: str = "normal",
    env: dict | None = None,
    run_hooks: bool = True,
    matugen_runner=subprocess.run,
    which=shutil.which,
    hook_ctx: hooks.Ctx | None = None,
    paint_wallpaper: bool = True,
) -> Result:
    t0 = time.perf_counter()
    env = dict(os.environ) if env is None else env
    if mode not in MODES:
        raise ThemeError(f"unknown mode {mode!r}")
    if contrast not in CONTRASTS:
        raise ThemeError(f"unknown contrast {contrast!r}")
    acc = None
    if accent is not None:
        if mode != "auto":
            raise ThemeError("--accent only works with --mode auto")
        try:
            acc = C.normalize_hex(accent)
        except ValueError as e:
            raise ThemeError(str(e)) from e
    wp: Path | None = None
    if wallpaper is not None:
        wp = Path(os.path.abspath(wallpaper))
        if not wp.is_file():
            raise ThemeError(f"wallpaper not found: {wp}")
    # The whole pipeline runs under the lock: two runs that both read
    # current/wallpaper, derive and swap must not interleave, or an older run
    # could swap last. The last run to take the lock is the one that sticks.
    with store.locked(env):
        return _apply_locked(
            t0, store.state_root(env), env, wp, mode, acc, contrast, run_hooks,
            matugen_runner, which, hook_ctx, paint_wallpaper,
        )


def _apply_locked(t0, root, env, wp, mode, acc, contrast, run_hooks, matugen_runner, which, hook_ctx,
                  paint_wallpaper):
    warnings: list[str] = []
    if wp is None:  # keep the current wallpaper (re-theme, --contrast high, reset)
        cur = root / "current" / "wallpaper"
        if cur.is_symlink() and cur.is_file() and os.path.isabs(os.readlink(cur)):
            wp = Path(os.readlink(cur))

    effective = mode
    seed = None
    ms_matugen = 0.0
    if mode == "auto":
        if acc:  # an override replaces the wallpaper colour, still hue-clamped
            seed = palette.seed_from_accent(acc)
        elif wp is None:
            warnings.append("auto mode has no wallpaper; using SecLegion Dark")
            effective = "default"
        else:
            tm = time.perf_counter()
            try:
                data = matugen.run(wp, runner=matugen_runner, which=which)
                seed = matugen.seed_from_json(data, identity=True)
            except matugen.MatugenMissing as e:
                warnings.append(f"{e}; falling back to SecLegion Dark")
                effective = "default"
            finally:
                ms_matugen = (time.perf_counter() - tm) * 1000

    tokens = build_tokens(effective, contrast, seed=seed)
    for v in palette.violations(tokens, contrast == "high"):
        warnings.append(f"contrast: {v}")

    wp_sha = store.file_sha256(wp) if wp else None
    name = store.content_hash(tokens, effective, contrast, str(wp) if wp else None, wp_sha)
    source = {"wallpaper": str(wp) if wp else None, "sha256": wp_sha, "accent_override": acc}
    files = render.render_all(
        tokens, mode=effective, requested_mode=mode, contrast=contrast, source=source
    )
    path = store.write_theme(root, name, files, wp)
    store.swap_current(root, name)
    store.prune(root)

    res = Result(name, path, effective, mode, tokens, warnings)
    res.ms_matugen = ms_matugen
    if run_hooks:
        th = time.perf_counter()
        ctx = hook_ctx or hooks.Ctx(
            active_border=render._rgba(tokens["border_active"]),
            inactive_border=render._rgba(tokens["border_inactive"]),
            env=env,
            pids=hooks.running_pids(),
            theme_dir=path,
            wallpaper=wp,
            paint_wallpaper=paint_wallpaper,
        )
        res.hook_results = hooks.run_hooks(ctx)
        res.ms_hooks = (time.perf_counter() - th) * 1000
    res.ms_total = (time.perf_counter() - t0) * 1000
    return res


def export_default(dest: str | os.PathLike) -> Path:
    """Write the static default theme files (shipped as the pcall fallback)."""
    tokens = build_tokens("default", "normal", seed=None)
    files = render.render_all(
        tokens, mode="default", requested_mode="default", contrast="normal",
        source={"wallpaper": None, "sha256": None, "accent_override": None},
    )
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    for fname, text in files.items():
        (d / fname).write_text(text, encoding="utf-8")
    # JSON has no comments: REUSE-style companion file carries the licence.
    # REUSE-IgnoreStart
    (d / "colors.json.license").write_text("SPDX-License-Identifier: MIT\n", encoding="utf-8")
    # REUSE-IgnoreEnd
    return d
