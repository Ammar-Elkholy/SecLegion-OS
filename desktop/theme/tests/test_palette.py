# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Palette tests: identity clamp, contrast clamp (G2 property test), mutation (G3).

Set SL_THEME_TEST_NOCLAMP=1 to run the whole module with the contrast clamp
disabled; the property tests must then fail (that is the G3 mutation check).
"""
import os
import random
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
from seclegion_theme import color as C
from seclegion_theme import palette as P

N_PIPELINE = 320  # synthetic wallpapers through seed -> derive -> finalize
N_RAW = 320  # hostile raw token sets straight into finalize


def setUpModule():
    if os.environ.get("SL_THEME_TEST_NOCLAMP") == "1":
        P.CLAMP_ENABLED = False


def tearDownModule():
    P.CLAMP_ENABLED = True


def synthetic_matugen_colors(rng):
    """(primary, secondary) like a matugen dark scheme, incl. very bright and grey ones."""
    def one():
        kind = rng.random()
        if kind < 0.25:  # very bright / pastel wallpaper
            return C.from_oklch(rng.uniform(0.90, 0.99), rng.uniform(0.0, 0.12), rng.uniform(0, 360))
        if kind < 0.35:  # grey
            return C.from_oklch(rng.uniform(0.1, 0.95), rng.uniform(0.0, 0.015), rng.uniform(0, 360))
        return C.from_oklch(rng.uniform(0.2, 0.95), rng.uniform(0.03, 0.32), rng.uniform(0, 360))

    return one(), one()


def check_tokens(t, *, high, identity, auto_family):
    """Every guarantee the engine makes, as a list of problems (empty = pass)."""
    problems = list(P.violations(t, high))
    d = P.load_defaults()
    for p in P.PROTECTED:
        if t[p] != d["colors"][p]:
            problems.append(f"protected {p} changed: {t[p]}")
    for i, name in P.ANSI_PROTECTED.items():
        if t[f"ansi{i}"] != d["colors"][name]:
            problems.append(f"protected ansi{i} changed")
    if identity and C.to_oklch(t["bg"])[0] > P.BG_L_MAX:
        problems.append(f"bg too light: {C.to_oklch(t['bg'])[0]:.3f}")
    if auto_family:  # zero tolerance on the final 8-bit colours
        lo, hi = P.ACCENT_HUE_RANGE
        for k in ("accent", "accent2"):
            h = C.to_oklch(t[k])[2]
            if not (lo <= h <= hi):
                problems.append(f"{k} hue {h:.1f} outside family")
    return problems


def pipeline_cases():
    rng = random.Random(20261014)
    for _ in range(N_PIPELINE):
        a, b = synthetic_matugen_colors(rng)
        for high in (False, True):
            yield "auto", a, b, high


def raw_cases():
    rng = random.Random(7)
    for _ in range(N_RAW):
        h = rng.uniform(0, 360)
        t = {}
        for k in P.TOKEN_NAMES:
            t[k] = C.from_oklch(rng.uniform(0.0, 1.0), rng.uniform(0.0, 0.3), h + rng.uniform(-60, 60))
        yield t, rng.random() < 0.5


class DefaultTokens(unittest.TestCase):
    def test_default_unchanged_by_normal_clamp(self):
        d = P.default_tokens()
        self.assertEqual(P.finalize(d, high=False, identity=False), d)

    def test_default_meets_rules_normal_and_high(self):
        for high in (False, True):
            t = P.finalize(P.default_tokens(), high=high, identity=False)
            self.assertEqual(check_tokens(t, high=high, identity=False, auto_family=False), [], high)

    def test_all_token_names_present(self):
        self.assertEqual(set(P.default_tokens()), set(P.TOKEN_NAMES))
        self.assertEqual(len(P.ANSI_TOKENS), 16)

    def test_owner_tokens_inside_hue_family(self):
        d = P.default_tokens()
        lo, hi = P.ACCENT_HUE_RANGE
        for k in ("accent", "accent2"):
            self.assertTrue(lo <= C.to_oklch(d[k])[2] <= hi, k)
        self.assertLessEqual(C.to_oklch(d["bg"])[0], P.BG_L_MAX)


class IdentityClamp(unittest.TestCase):
    def test_hue_clamped_into_family(self):
        lo, hi = P.ACCENT_HUE_RANGE
        for h in range(0, 360, 5):
            self.assertTrue(lo <= P.clamp_hue(h) <= hi, h)
        self.assertEqual(P.clamp_hue(170.0), 170.0)  # in family: untouched

    def test_red_wallpaper_and_red_accent_override_both_get_teal_family(self):
        # there is no free-hue (custom) mode: an --accent override is clamped too
        red = C.from_oklch(0.6, 0.2, 25)
        lo, hi = P.ACCENT_HUE_RANGE
        for seed in (P.seed_from_colors(red, None, identity=True), P.seed_from_accent(red)):
            t = P.finalize(P.derive(seed), identity=True)
            for k in ("accent", "accent2"):
                self.assertTrue(lo <= C.to_oklch(t[k])[2] <= hi, (k, t[k]))

    def test_violations_reports_identity_breaks(self):
        d = P.default_tokens()
        self.assertEqual(P.identity_violations(d), [])
        off = P.violations(dict(d, accent=C.from_oklch(0.86, 0.15, 25)))
        self.assertTrue(any(v.startswith("accent hue") for v in off), off)
        edge = C.from_oklch(0.86, 0.15, 149.0)  # just outside: no tolerance
        self.assertTrue(any(v.startswith("accent2 hue") for v in P.violations(dict(d, accent2=edge))))
        light = P.violations(dict(d, bg=C.with_lightness(d["bg"], 0.2)))
        self.assertTrue(any(v.startswith("bg lightness") for v in light), light)

    def test_bright_bg_is_forced_dark(self):
        t = P.derive(P.seed_from_colors("#00ffcc", None, identity=True))
        t["bg"] = "#f5f5f5"
        out = P.finalize(t, identity=True)
        self.assertLessEqual(C.to_oklch(out["bg"])[0], P.BG_L_MAX)


class ContrastProperty(unittest.TestCase):
    """G2."""

    def test_pipeline_from_synthetic_wallpapers(self):
        n = 0
        for _mode, a, b, high in pipeline_cases():
            seed = P.seed_from_colors(a, b, identity=True)
            t = P.finalize(P.derive(seed), high=high, identity=True)
            self.assertEqual(check_tokens(t, high=high, identity=True, auto_family=True), [], (a, b, high))
            n += 1
        self.assertGreaterEqual(n, 300)

    def test_accent_override_any_hue_is_clamped(self):
        rng = random.Random(3)
        for _ in range(N_PIPELINE):
            acc = C.from_oklch(rng.uniform(0.1, 1.0), rng.uniform(0.0, 0.3), rng.uniform(0, 360))
            for high in (False, True):
                t = P.finalize(P.derive(P.seed_from_accent(acc)), high=high, identity=True)
                self.assertEqual(check_tokens(t, high=high, identity=True, auto_family=True), [], (acc, high))

    def test_hostile_raw_tokens(self):
        n = 0
        for raw, high in raw_cases():
            t = P.finalize(raw, high=high, identity=True)
            self.assertEqual(check_tokens(t, high=high, identity=True, auto_family=False), [], (raw, high))
            n += 1
        self.assertGreaterEqual(n, 300)

    def test_finalize_is_idempotent(self):
        for raw, high in list(raw_cases())[:60]:
            once = P.finalize(raw, high=high, identity=True)
            self.assertEqual(P.finalize(once, high=high, identity=True), once)

    def test_lift_keeps_hue(self):
        c = C.from_oklch(0.45, 0.14, 150)
        out = C.lift_to_contrast(c, ["#050f0e"], 7.0)
        self.assertGreaterEqual(C.contrast(out, "#050f0e"), 7.0)
        self.assertLess(C.hue_distance(C.to_oklch(out)[2], 150), 6)

    def test_protected_never_derived_bg_adjusted_instead(self):
        t = P.derive(P.seed_from_colors("#00ffcc", None, identity=True))
        t["bg"], t["surface"] = "#2a2a2a", "#303030"  # too light for crit at 4.5:1
        out = P.finalize(t, identity=True)
        self.assertEqual(out["crit"], P.default_tokens()["crit"])
        self.assertGreaterEqual(C.contrast(out["crit"], out["surface"]), 4.5)
        self.assertLess(C.to_oklch(out["bg"])[0], C.to_oklch("#2a2a2a")[0])


class BuiltinThemes(unittest.TestCase):
    def test_manager_builtins_pass_the_identity_and_contrast_clamps(self):
        from seclegion_theme import manager

        for tid, _, _ in manager.BUILTINS:
            for high in (False, True):
                t = manager.builtin_tokens(tid, "high" if high else "normal")
                self.assertEqual(check_tokens(t, high=high, identity=tid != "seclegion-dark",
                                              auto_family=True), [], (tid, high))


class Mutation(unittest.TestCase):
    """G3: the property checker must notice when the contrast clamp is off."""

    def test_checker_detects_disabled_clamp(self):
        with mock.patch.object(P, "CLAMP_ENABLED", False):
            bad = 0
            for raw, high in raw_cases():
                t = P.finalize(raw, high=high, identity=True)
                if check_tokens(t, high=high, identity=True, auto_family=False):
                    bad += 1
            self.assertGreater(bad, N_RAW // 2)

    def test_protected_still_restored_with_clamp_off(self):
        # the clamp switch must not disable the protected-semantics reset
        with mock.patch.object(P, "CLAMP_ENABLED", False):
            raw, _ = next(iter(raw_cases()))
            t = P.finalize(raw, identity=True)
            self.assertEqual(t["crit"], P.default_tokens()["crit"])

    def test_identity_clamp_holds_with_contrast_clamp_off(self):
        # the identity (hue family, dark bg) is not part of the contrast switch
        with mock.patch.object(P, "CLAMP_ENABLED", False):
            for raw, high in raw_cases():
                t = P.finalize(raw, high=high, identity=True)
                self.assertEqual(P.identity_violations(t), [], raw)


if __name__ == "__main__":
    unittest.main()
