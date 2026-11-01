# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Semantic token derivation plus the identity and contrast clamps.

Both `default` and `auto` palettes go through `finalize()`, so the same
guarantees hold in every mode (see `violations()` for the exact rules).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import color as C

# --- Tunables -------------------------------------------------------------
# Identity clamp (auto only; default mode is the owner's static tokens, which
# already satisfy it). `violations()` checks it on every final token set.
BG_L_MAX = 0.18  # OKLCH lightness ceiling of the dark base (owner bg is 0.157)
SURFACE_L_MAX = 0.24  # surface / surface2 ceilings (owner: 0.218 / 0.285)
SURFACE2_L_MAX = 0.32
CAP_SLACK = 0.003  # land just under a cap so 8-bit rounding cannot re-trigger it
# Accent hue family (OKLCH degrees). The owner's #00FF88 is 152.5 and #00F0FF
# is 202.9, so the family is 150..205 rather than a tighter 150..200. TUNABLE.
ACCENT_HUE_RANGE = (150.0, 205.0)
HUE_SLACK = 2.0  # an out-of-family hue lands this far inside, so 8-bit rounding stays in
FAMILY_TOKENS = ("accent", "accent2")
ACCENT_CHROMA_RANGE = (0.11, 0.20)
ACCENT_L = 0.86
BG_L = 0.15
# Contrast: aim this far above a threshold so the rounded 8-bit colour and
# other WCAG calculators (slightly different cut-offs) still pass.
MARGIN = 0.05
TEXT_TARGET = 7.0

# Test hook: the mutation test flips this to prove the property test notices.
CLAMP_ENABLED = True

PROTECTED = ("ok", "warn", "err", "crit")
BASE_TOKENS = (
    "bg", "surface", "surface2", "text", "muted", "accent", "accent2",
    "border_active", "border_inactive", "ok", "warn", "err", "crit",
)
ANSI_TOKENS = tuple(f"ansi{i}" for i in range(16))
TOKEN_NAMES = BASE_TOKENS + ANSI_TOKENS
# ansi slots that mirror protected semantics; they are fixed, never derived.
ANSI_PROTECTED = {1: "err", 2: "ok", 3: "warn", 9: "crit"}
BG_GROUP = ("bg", "surface", "surface2", "border_inactive")


class ThemeError(Exception):
    """User-facing failure (bad input, missing tool)."""


@dataclass(frozen=True)
class Seed:
    accent_hue: float
    accent_chroma: float
    accent2_hue: float


_DEFAULTS_CACHE: dict | None = None


def tokens_path() -> Path:
    for cand in (
        Path(__file__).resolve().parent.parent / "tokens.toml",
        Path("/usr/share/seclegion/theme/tokens.toml"),
    ):
        if cand.is_file():
            return cand
    raise ThemeError("tokens.toml not found")


def load_defaults() -> dict:
    """Parsed tokens.toml with colours normalised to '#rrggbb'."""
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is None:
        with open(tokens_path(), "rb") as fh:
            raw = tomllib.load(fh)
        colors = {k: C.normalize_hex(v) for k, v in raw["colors"].items()}
        ansi = [C.normalize_hex(v) for v in raw["ansi"]["colors"]]
        crit_n = {k: C.normalize_hex(v) for k, v in raw["notification"]["critical"].items()}
        if len(ansi) != 16 or set(colors) != set(BASE_TOKENS):
            raise ThemeError("tokens.toml: wrong token set")
        _DEFAULTS_CACHE = {"colors": colors, "ansi": ansi, "notification_critical": crit_n}
    return _DEFAULTS_CACHE


def default_tokens() -> dict[str, str]:
    d = load_defaults()
    t = dict(d["colors"])
    for i, v in enumerate(d["ansi"]):
        t[f"ansi{i}"] = v
    return t


# --- Hue helpers ----------------------------------------------------------
def clamp_hue(h: float, rng: tuple[float, float] = ACCENT_HUE_RANGE) -> float:
    lo, hi = rng
    h %= 360.0
    if lo <= h <= hi:
        return h
    return lo if C.hue_distance(h, lo) <= C.hue_distance(h, hi) else hi


def seed_from_colors(primary: str, secondary: str | None, *, identity: bool) -> Seed:
    """Seed from a wallpaper-derived primary (+ secondary/tertiary) colour."""
    d = default_tokens()
    _, c1, h1 = C.to_oklch(primary)
    dl_h = C.to_oklch(d["accent"])[2]
    dl_h2 = C.to_oklch(d["accent2"])[2]
    if c1 < 0.02:  # grey wallpaper: hue is meaningless, keep the brand hues
        return Seed(dl_h, ACCENT_CHROMA_RANGE[0], dl_h2)
    acc_h = clamp_hue(h1) if identity else h1
    h2 = None
    if secondary:
        _, c2, hh = C.to_oklch(secondary)
        if c2 >= 0.02:
            h2 = clamp_hue(hh) if identity else hh
    lo, hi = ACCENT_HUE_RANGE
    if h2 is None or C.hue_distance(h2, acc_h) < 20.0:
        if identity:
            h2 = acc_h + 30.0 if acc_h + 30.0 <= hi else acc_h - 30.0
            h2 = max(lo, min(hi, h2))
        else:
            h2 = (acc_h + 40.0) % 360.0
    return Seed(acc_h, c1, h2)


def seed_from_accent(accent: str) -> Seed:
    """Seed from an --accent override. Always hue-clamped into the family."""
    return seed_from_colors(accent, None, identity=True)


# --- Derivation -----------------------------------------------------------
def derive(seed: Seed) -> dict[str, str]:
    """Build the unclamped token set from a seed. Protected values come from
    tokens.toml, never from the seed."""
    d = load_defaults()
    h, h2 = seed.accent_hue, seed.accent2_hue
    ac = max(ACCENT_CHROMA_RANGE[0], min(ACCENT_CHROMA_RANGE[1], seed.accent_chroma))
    t: dict[str, str] = {
        "bg": C.from_oklch(BG_L, 0.016, h),
        "surface": C.from_oklch(BG_L + 0.05, 0.024, h),
        "surface2": C.from_oklch(BG_L + 0.10, 0.032, h),
        "text": C.from_oklch(0.965, 0.02, h),
        "muted": C.from_oklch(0.74, 0.04, h),
        "accent": C.from_oklch(ACCENT_L, ac, h),
        "accent2": C.from_oklch(ACCENT_L, ac, h2),
    }
    t["border_active"] = t["accent"]
    t["border_inactive"] = t["surface"]
    for p in PROTECTED:
        t[p] = d["colors"][p]
    a = d["ansi"]
    for i in range(16):
        t[f"ansi{i}"] = a[i]  # fixed slots (protected + notification-safe)
    t["ansi0"] = t["surface2"]
    t["ansi4"] = C.from_oklch(0.72, 0.13, 255)
    t["ansi5"] = C.from_oklch(0.74, 0.14, 325)
    t["ansi6"] = t["accent2"]
    t["ansi7"] = C.from_oklch(0.86, 0.02, h)
    t["ansi8"] = C.from_oklch(0.62, 0.04, h)
    t["ansi10"] = t["accent"]
    t["ansi12"] = C.from_oklch(0.80, 0.11, 255)
    t["ansi13"] = C.from_oklch(0.82, 0.12, 325)
    t["ansi14"] = C.from_oklch(0.92, 0.09, h2)
    t["ansi15"] = t["text"]
    return t


# --- Contrast rules -------------------------------------------------------
def _rules(t: dict[str, str], high: bool) -> list[tuple[str, list[str], float, float]]:
    """(token, backgrounds, hard minimum, aim). Single source of truth for both
    the clamp and `violations()`."""
    bg, s, s2 = t["bg"], t["surface"], t["surface2"]
    body = 7.0 if high else 4.5
    rules: list[tuple[str, list[str], float, float]] = [
        ("text", [bg, s, s2], body, TEXT_TARGET),
        ("muted", [bg, s, s2], body, body),
        ("accent", [bg, s], body, body),
        ("accent2", [bg, s], body, body),
        ("border_active", [bg, s], 7.0 if high else 3.0, 7.0 if high else 3.0),
    ]
    if high:
        # Inactive borders are exempt from 3:1 normally (WCAG 1.4.11 inactive
        # components); in high-contrast mode they must still be visible.
        rules.append(("border_inactive", [bg], 3.0, 3.0))
    for p in PROTECTED:
        rules.append((p, [bg, s], 4.5, 4.5))  # fixed: cannot reach 7 (crit max 5.7)
    for i in range(1, 16):
        if i in ANSI_PROTECTED:
            continue
        rules.append((f"ansi{i}", [bg, s], body, body))
    return rules


def identity_violations(t: dict[str, str]) -> list[str]:
    """The SecLegion identity on the final 8-bit colours, zero tolerance:
    accent/accent2 hue inside ACCENT_HUE_RANGE, bg OKLCH L <= BG_L_MAX."""
    lo, hi = ACCENT_HUE_RANGE
    out = []
    for k in FAMILY_TOKENS:
        h = C.to_oklch(t[k])[2]
        if not lo <= h <= hi:
            out.append(f"{k} hue {h:.2f} outside {lo:g}..{hi:g}")
    L = C.to_oklch(t["bg"])[0]
    if L > BG_L_MAX:
        out.append(f"bg lightness {L:.4f} > {BG_L_MAX}")
    return out


def violations(t: dict[str, str], high: bool = False) -> list[str]:
    out = identity_violations(t)
    for name, bgs, hard, _ in _rules(t, high):
        for bg in bgs:
            r = C.contrast(t[name], bg)
            if r < hard:
                out.append(f"{name} on {bg}: {r:.2f} < {hard}")
    return out


def _shift_group(t: dict[str, str], dl: float) -> dict[str, str]:
    out = dict(t)
    for k in BG_GROUP:
        L, _, _ = C.to_oklch(t[k])
        out[k] = C.with_lightness(t[k], max(0.0, L - dl))
    return out


def _into_family(value: str) -> str:
    """Move an out-of-family colour's hue just inside ACCENT_HUE_RANGE."""
    lo, hi = ACCENT_HUE_RANGE
    L, c, h = C.to_oklch(value)
    if lo <= h <= hi:
        return value
    h = clamp_hue(h, (lo + HUE_SLACK, hi - HUE_SLACK))
    c = max(c, ACCENT_CHROMA_RANGE[0])
    # near white / near black have no chroma left, so no hue; the lift re-raises L
    L = max(0.5, min(L, ACCENT_L))
    while True:
        out = C.from_oklch(L, c, h)
        if lo <= C.to_oklch(out)[2] <= hi or L <= 0.3:
            return out
        L -= 0.02


def _cap_lightness(value: str, cap: float) -> str:
    L = C.to_oklch(value)[0]
    target = cap - CAP_SLACK
    while L > cap and target > 0.0:  # 8-bit rounding can land above the cap
        value = C.with_lightness(value, target)
        L, target = C.to_oklch(value)[0], target - CAP_SLACK
    return value


def finalize(tokens: dict[str, str], *, high: bool = False, identity: bool = False) -> dict[str, str]:
    """Apply identity clamp, restore protected semantics, then the contrast clamp.

    identity=True (auto): bg lightness <= BG_L_MAX, accent hues in the family
    (also re-checked after the contrast lift, which can drift the hue by
    rounding). Protected tokens are
    always reset to tokens.toml; when they fail 4.5:1 the bg group is darkened
    instead. Other tokens are lightened in OKLCH keeping hue and chroma.
    """
    d = load_defaults()
    t = {k: tokens[k] for k in TOKEN_NAMES}
    for p in PROTECTED:
        t[p] = d["colors"][p]
    for i, name in ANSI_PROTECTED.items():
        t[f"ansi{i}"] = d["colors"][name]
    if identity:
        for key, cap in (("bg", BG_L_MAX), ("surface", SURFACE_L_MAX), ("surface2", SURFACE2_L_MAX)):
            t[key] = _cap_lightness(t[key], cap)
        for key in FAMILY_TOKENS:
            t[key] = _into_family(t[key])
    if not CLAMP_ENABLED:
        return t

    # Protected semantics fail -> darken the dark base, never the semantics.
    def prot_ok(x: dict[str, str]) -> bool:
        return all(C.min_contrast(x[p], [x["bg"], x["surface"]]) >= 4.5 + MARGIN for p in PROTECTED)

    if not prot_ok(t):
        lo, hi = 0.0, max(C.to_oklch(t[k])[0] for k in BG_GROUP)
        best = _shift_group(t, hi)
        for _ in range(20):
            mid = (lo + hi) / 2
            cand = _shift_group(t, mid)
            if prot_ok(cand):
                hi, best = mid, cand
            else:
                lo = mid
        t = best

    def lift(name: str, bgs: list[str], hard: float, aim: float) -> None:
        t[name] = C.lift_to_contrast(t[name], bgs, aim + MARGIN)
        if C.min_contrast(t[name], bgs) < hard:  # aim unreachable: best effort above
            t[name] = C.lift_to_contrast(t[name], bgs, hard + MARGIN)

    rules = _rules(t, high)
    for rule in rules:
        if rule[0] in PROTECTED:
            continue  # fixed: reported by violations(), never lifted
        lift(*rule)
    if identity:  # the lift re-rounds; a hue on the family edge can step out
        for rule in rules:
            if rule[0] in FAMILY_TOKENS and t[rule[0]] != _into_family(t[rule[0]]):
                t[rule[0]] = _into_family(t[rule[0]])
                lift(*rule)
    return t
