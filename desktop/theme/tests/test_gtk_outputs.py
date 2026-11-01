# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""File-manager look outputs: gtk3.css, gtk4.css, kde.colors, qt6ct.conf,
yazi-theme.toml. Golden values for the default palette, parse checks (tomllib,
configparser, Gtk.CssProvider), no 0x colours, WCAG contrast on the text pairs
each file uses (default palette plus engine-derived wallpaper palettes), and
the injection guard on every new renderer.

SL_THEME_TEST_NOGUARD=1 disables the guard in render._hex(); the injection
test here must then fail, like the one in test_engine.
"""

import configparser
import os
import random
import re
import subprocess
import sys
import tomllib
import unittest

import _bootstrap  # noqa: F401
from seclegion_theme import color as C
from seclegion_theme import palette as P
from seclegion_theme import render
from seclegion_theme.palette import ThemeError
from test_palette import synthetic_matugen_colors

NEW = ("gtk3.css", "gtk4.css", "kde.colors", "qt6ct.conf", "yazi-theme.toml")
RENDERERS = (render._gtk3, render._gtk4, render._kde, render._qt6ct, render._yazi)
NO_SOURCE = {"wallpaper": None, "sha256": None, "accent_override": None}
TEXT_MIN = 4.5
BORDER_MIN = 3.0  # WCAG 1.4.11 non-text contrast
DEFINE = re.compile(r"^@define-color ([a-z_]+) (#[0-9a-f]{6});$")


def setUpModule():
    if os.environ.get("SL_THEME_TEST_NOGUARD") == "1":
        render.GUARD_ENABLED = False


def tearDownModule():
    render.GUARD_ENABLED = True


def render_new(tokens):
    out = render.render_all(tokens, mode="d", requested_mode="d", contrast="normal", source=NO_SOURCE)
    return {f: out[f] for f in NEW}


def palettes(n=40):
    yield "default", P.finalize(P.default_tokens(), high=False, identity=False)
    yield "default high", P.finalize(P.default_tokens(), high=True, identity=False)
    rng = random.Random(20261015)
    for i in range(n):
        a, b = synthetic_matugen_colors(rng)
        seed = P.seed_from_colors(a, b, identity=True)
        yield f"wallpaper {a} {b}", P.finalize(P.derive(seed), high=i % 2 == 1, identity=True)


def css_colors(text):
    return dict(m.groups() for m in map(DEFINE.match, text.splitlines()) if m)


def ini(text):
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # KDE keys are case-sensitive
    cp.read_string(text)
    return cp


def kde_rgb(value):
    r, g, b = (int(x) for x in value.split(","))
    return C.rgb_to_hex((r, g, b))


def yazi_pairs(doc):
    """(where, fg, bg) for every style that sets fg; bg None = terminal bg."""
    for section, keys in doc.items():
        if section == "filetype":
            for i, rule in enumerate(keys["rules"]):
                if "fg" in rule:
                    yield f"filetype[{i}]", rule["fg"], rule.get("bg")
            continue
        for key, style in keys.items():
            if isinstance(style, dict) and "fg" in style:
                yield f"{section}.{key}", style["fg"], style.get("bg")


class Golden(unittest.TestCase):
    """Exact values for SecLegion Dark (the full files are also pinned by
    test_engine's shipped-default comparison)."""

    def setUp(self):
        self.out = render_new(P.default_tokens())

    def test_gtk3_named_colours(self):
        got = css_colors(self.out["gtk3.css"])
        for name, want in {
            "theme_bg_color": "#050f0e",
            "theme_fg_color": "#e0fff4",
            "theme_base_color": "#0b1e1c",
            "theme_text_color": "#e0fff4",
            "theme_selected_bg_color": "#00ff88",
            "theme_selected_fg_color": "#050f0e",
            "borders": "#8fb5ab",
            "insensitive_bg_color": "#0b1e1c",
            "insensitive_fg_color": "#8fb5ab",
            "warning_color": "#ffcc66",
            "error_color": "#ff6666",
            "success_color": "#3ddc84",
            "theme_unfocused_bg_color": "#050f0e",
            "theme_unfocused_fg_color": "#e0fff4",
            "theme_unfocused_selected_bg_color": "#12302c",
        }.items():
            self.assertEqual(got.get(name), want, name)

    def test_gtk4_named_colours_and_no_import(self):
        text = self.out["gtk4.css"]
        got = css_colors(text)
        for name in (
            "window_bg_color",
            "window_fg_color",
            "view_bg_color",
            "view_fg_color",
            "accent_bg_color",
            "accent_fg_color",
            "accent_color",
            "headerbar_bg_color",
            "headerbar_fg_color",
            "sidebar_bg_color",
            "sidebar_fg_color",
            "card_bg_color",
            "popover_bg_color",
            "dialog_bg_color",
            "destructive_bg_color",
            "success_color",
            "warning_color",
            "error_color",
        ):
            self.assertIn(name, got)
        self.assertEqual(
            (got["window_bg_color"], got["accent_bg_color"], got["accent_fg_color"]),
            ("#050f0e", "#00ff88", "#050f0e"),
        )
        self.assertIn("  --window-bg-color: #050f0e;", text)
        self.assertNotIn("@import", text)  # overrides only: the host file imports Graphite-Mono

    def test_kde_sections_and_keys(self):
        cp = ini(self.out["kde.colors"])
        self.assertEqual((cp["General"]["ColorScheme"], cp["General"]["Name"]), ("SecLegion", "SecLegion"))
        keys = {
            "BackgroundNormal",
            "BackgroundAlternate",
            "ForegroundNormal",
            "ForegroundInactive",
            "ForegroundActive",
            "ForegroundLink",
            "ForegroundVisited",
            "ForegroundNegative",
            "ForegroundNeutral",
            "ForegroundPositive",
            "DecorationFocus",
            "DecorationHover",
        }
        for s in ("Window", "View", "Button", "Selection", "Tooltip", "Header", "Complementary"):
            sec = cp[f"Colors:{s}"]
            self.assertEqual(set(sec), keys, s)
            for v in sec.values():
                self.assertRegex(v, r"^\d{1,3},\d{1,3},\d{1,3}$")
        self.assertEqual(cp["Colors:Window"]["BackgroundNormal"], "5,15,14")
        self.assertEqual(cp["Colors:Selection"]["BackgroundNormal"], "0,255,136")

    def test_qt6ct_has_three_groups_of_21(self):
        cp = ini(self.out["qt6ct.conf"])
        self.assertEqual(set(cp["ColorScheme"]), {"active_colors", "disabled_colors", "inactive_colors"})
        for k, v in cp["ColorScheme"].items():
            entries = [e.strip() for e in v.split(",")]
            self.assertEqual(len(entries), 21, k)
            for e in entries:
                self.assertRegex(e, r"^#ff[0-9a-f]{6}$")
        active = [e.strip() for e in cp["ColorScheme"]["active_colors"].split(",")]
        roles = dict(zip(render.QT_ROLES, active, strict=False))
        self.assertEqual(
            (roles["Window"], roles["Highlight"], roles["HighlightedText"]),
            ("#ff050f0e", "#ff00ff88", "#ff050f0e"),
        )

    def test_yazi_toml_marker_and_sections(self):
        text = self.out["yazi-theme.toml"]
        self.assertEqual(text.splitlines()[0], "# generated by seclegion-theme")
        doc = tomllib.loads(text)
        for s in ("mgr", "mode", "status", "input", "pick", "tasks", "which", "help", "notify", "filetype"):
            self.assertIn(s, doc)
        self.assertNotIn("manager", doc)  # renamed to mgr in yazi 25.x
        self.assertEqual(doc["indicator"]["current"], {"fg": "#050f0e", "bg": "#00ff88", "bold": True})
        self.assertEqual(doc["filetype"]["rules"][-1], {"url": "*", "fg": "#e0fff4"})


class Parse(unittest.TestCase):
    def test_no_0x_colours_anywhere(self):
        for name, t in palettes(4):
            for f, text in render_new(t).items():
                self.assertNotIn("0x", text.lower(), (name, f))

    def _gtk_parse(self, version, text):
        code = (
            "import sys, gi\n"
            f"gi.require_version('Gtk', '{version}')\n"
            "from gi.repository import Gtk, GLib\n"
            "p = Gtk.CssProvider(); errs = []\n"
            "p.connect('parsing-error', lambda _p, _s, e: errs.append(e.message))\n"
            "data = sys.stdin.read()\n"
            "try:\n"
            "    p.load_from_string(data) if hasattr(p, 'load_from_string') "
            "else p.load_from_data(data.encode())\n"
            "except GLib.Error as e:\n"
            "    errs.append(e.message)\n"
            "print('\\n'.join(errs)); sys.exit(1 if errs else 0)\n"
        )
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        return subprocess.run(
            [sys.executable, "-c", code], input=text, capture_output=True, text=True, timeout=30, env=env
        )

    def _gtk_available(self, version):
        p = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import gi; gi.require_version('Gtk', '{version}'); from gi.repository import Gtk",
            ],
            capture_output=True,
            timeout=30,
        )
        return p.returncode == 0

    def test_gtk_css_parses_in_real_gtk(self):
        out = render_new(P.default_tokens())
        for version, f in (("3.0", "gtk3.css"), ("4.0", "gtk4.css")):
            with self.subTest(f):
                if not self._gtk_available(version):
                    self.skipTest(f"python gi with Gtk {version} not importable")
                p = self._gtk_parse(version, out[f])
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                bad = self._gtk_parse(version, out[f] + "@define-color broken #zz;\n")
                self.assertNotEqual(bad.returncode, 0, "parser check cannot see errors")

    def test_ini_and_toml_parse(self):
        for _name, t in palettes(4):
            out = render_new(t)
            ini(out["kde.colors"])
            ini(out["qt6ct.conf"])
            tomllib.loads(out["yazi-theme.toml"])


class Contrast(unittest.TestCase):
    """Text >= 4.5:1 on every text/background pair the files use."""

    def check(self, name, where, fg, bg):
        r = C.contrast(fg, bg)
        self.assertGreaterEqual(r, TEXT_MIN, f"{name}: {where} {fg} on {bg} = {r:.2f}")

    def test_gtk_pairs(self):
        gtk3 = (
            ("theme_fg_color", "theme_bg_color"),
            ("theme_text_color", "theme_base_color"),
            ("theme_selected_fg_color", "theme_selected_bg_color"),
            ("insensitive_fg_color", "insensitive_bg_color"),
            ("theme_unfocused_fg_color", "theme_unfocused_bg_color"),
            ("theme_unfocused_text_color", "theme_unfocused_base_color"),
            ("theme_unfocused_selected_fg_color", "theme_unfocused_selected_bg_color"),
            ("warning_color", "theme_bg_color"),
            ("error_color", "theme_bg_color"),
            ("success_color", "theme_base_color"),
        )
        for name, t in palettes():
            out = render_new(t)
            c3, c4 = css_colors(out["gtk3.css"]), css_colors(out["gtk4.css"])
            for fg, bg in gtk3:
                self.check(name, f"gtk3 {fg}/{bg}", c3[fg], c3[bg])
            for k in c4:
                if k.endswith("_fg_color"):
                    bg = k.replace("_fg_color", "_bg_color")
                    self.check(name, f"gtk4 {k}", c4[k], c4[bg])
            for k in ("accent_color", "destructive_color", "success_color", "warning_color", "error_color"):
                for bg in ("window_bg_color", "view_bg_color"):
                    self.check(name, f"gtk4 {k}/{bg}", c4[k], c4[bg])

    def test_kde_pairs(self):
        for name, t in palettes():
            cp = ini(render_new(t)["kde.colors"])
            for s in cp.sections():
                if not s.startswith("Colors:"):
                    continue
                sec = cp[s]
                for k, v in sec.items():
                    if k.startswith("Foreground"):
                        for bg in ("BackgroundNormal", "BackgroundAlternate"):
                            self.check(name, f"{s} {k}/{bg}", kde_rgb(v), kde_rgb(sec[bg]))

    def test_qt6ct_pairs(self):
        pairs = (
            ("WindowText", "Window"),
            ("Text", "Base"),
            ("Text", "AlternateBase"),
            ("ButtonText", "Button"),
            ("HighlightedText", "Highlight"),
            ("ToolTipText", "ToolTipBase"),
            ("PlaceholderText", "Base"),
            ("Link", "Base"),
            ("LinkVisited", "Base"),
            ("Link", "Window"),
            ("BrightText", "Window"),
        )
        for name, t in palettes():
            cp = ini(render_new(t)["qt6ct.conf"])
            for group, v in cp["ColorScheme"].items():
                roles = dict(zip(render.QT_ROLES, ("#" + e.strip()[3:] for e in v.split(",")), strict=False))
                for fg, bg in pairs:
                    self.check(name, f"qt6ct {group} {fg}/{bg}", roles[fg], roles[bg])

    def test_yazi_pairs(self):
        for name, t in palettes():
            doc = tomllib.loads(render_new(t)["yazi-theme.toml"])
            for where, fg, bg in yazi_pairs(doc):
                key = where.split(".")[-1]
                if key.startswith("marker_"):
                    continue  # solid marker blocks (fg == bg) are not text
                # fg-only styles draw on the terminal background (kitty: bg) or
                # yazi's surface panes; both are checked.
                for back in [bg] if bg else [t["bg"], t["surface"]]:
                    self.check(name, f"yazi {where}", fg, back)

    def test_borders_have_3_to_1_against_bg_and_surface(self):
        def need(name, where, fg, bg):
            r = C.contrast(fg, bg)
            self.assertGreaterEqual(r, BORDER_MIN, f"{name}: {where} {fg} on {bg} = {r:.2f}")

        for name, t in palettes():
            out = render_new(t)
            c3 = css_colors(out["gtk3.css"])
            for k in ("borders", "unfocused_borders"):
                for bg in ("theme_bg_color", "theme_base_color"):
                    need(name, f"gtk3 {k}/{bg}", c3[k], c3[bg])
            doc = tomllib.loads(out["yazi-theme.toml"])
            seen = 0
            for where, fg, _bg in yazi_pairs(doc):
                if "border" in where.split(".")[-1]:
                    seen += 1
                    for back in (t["bg"], t["surface"]):
                        need(name, f"yazi {where}", fg, back)
            self.assertGreater(seen, 1, "no yazi border keys found")
            cp = ini(out["kde.colors"])
            for s in cp.sections():
                if s.startswith("Colors:") and s != "Colors:Selection":  # Selection's bg is the accent itself
                    for k in ("DecorationFocus", "DecorationHover"):
                        need(name, f"kde {s} {k}", kde_rgb(cp[s][k]), kde_rgb(cp[s]["BackgroundNormal"]))


class Injection(unittest.TestCase):
    PAYLOADS = (
        '")os.execute(',
        '#00ff88"; x',
        "#00FF88",
        "0x00ff88",
        "#00ff88ff00",
        "#00ff88\n",
        '#00ff88" }\n[mgr]\nx = "',
        "1,2,3",
        "#ff00ff88",
    )

    def test_every_new_renderer_refuses_bad_tokens_itself(self):
        # Called directly, past _checked(): each renderer must re-validate.
        base = {k: "#" + v.lstrip("#").lower() for k, v in P.default_tokens().items()}
        for fn in RENDERERS:
            for key in ("bg", "text", "accent", "surface"):  # used by all five
                for evil in self.PAYLOADS:
                    with self.assertRaises(ThemeError, msg=(fn.__name__, key, evil)):
                        fn(dict(base, **{key: evil}))

    def test_render_all_refuses_bad_tokens(self):
        for evil in self.PAYLOADS:
            with self.assertRaises(ThemeError, msg=evil):
                render_new(dict(P.default_tokens(), muted=evil))


if __name__ == "__main__":
    unittest.main()
