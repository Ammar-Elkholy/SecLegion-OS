# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""`seclegion-theme list` and `apply --theme`: built-ins, wallpaper entries from the kept
theme dirs, the current marker, and a rejected id leaving the current theme untouched."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from seclegion_theme import cli, engine, manager, store
from seclegion_theme import palette as P

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PNG = b"\x89PNG\r\n\x1a\n"


def which(name):
    return "/usr/bin/matugen"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-manager-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {
            "HOME": str(self.tmp),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "XDG_RUNTIME_DIR": str(self.tmp),
        }
        out = (FIXTURES / "matugen_v2.json").read_text()
        self.runner = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, out, "")
        old = dict(os.environ)
        os.environ.update(self.env)  # cli.main reads the process environment
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(old)))

    def wall(self, name, extra):
        p = self.tmp / name
        p.write_bytes(PNG + extra)
        return p

    def apply_wall(self, p):
        return engine.apply_theme(
            wallpaper=p, mode="auto", env=self.env, run_hooks=False, matugen_runner=self.runner, which=which
        )

    def current(self):
        return store.read_current(store.state_root(self.env))

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class BuiltIns(Base):
    def test_shape_and_builtins_pass_the_clamps(self):  # G1, G2
        themes = manager.list_themes(self.env)
        self.assertEqual([t["id"] for t in themes], ["seclegion-dark", "seclegion-teal", "seclegion-cyan"])
        for t in themes:
            self.assertEqual(set(t), {"id", "label", "accent", "bg", "surface", "text", "current"})
        for tid, _, _ in manager.BUILTINS:
            for high in (False, True):
                with self.subTest(tid=tid, high=high):
                    toks = manager.builtin_tokens(tid, "high" if high else "normal")
                    self.assertEqual(P.violations(toks, high), [])
        lo, hi = P.ACCENT_HUE_RANGE
        for tid, _, hue in manager.BUILTINS:
            self.assertTrue(hue is None or lo <= hue <= hi, tid)

    def test_cli_list_json(self):
        rc, out, _ = self.cli("list", "--json")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertTrue(all("accent" in t for t in d))
        self.assertEqual([t["id"] for t in d if t["current"]], ["seclegion-dark"])

    def test_apply_builtin_marks_it_current(self):
        rc, _, _ = self.cli("apply", "--theme", "seclegion-teal", "--no-hooks")
        self.assertEqual(rc, 0)
        cur = {t["id"] for t in manager.list_themes(self.env) if t["current"]}
        self.assertEqual(cur, {"seclegion-teal"})
        self.assertEqual(
            self.current()["tokens"]["accent"], manager.builtin_tokens("seclegion-teal")["accent"]
        )
        self.cli("apply", "--theme", "seclegion-dark", "--no-hooks")
        self.assertEqual(self.current()["mode"], "default")

    def test_g4_unknown_id_is_rejected_and_current_unchanged(self):
        self.cli("apply", "--theme", "seclegion-cyan", "--no-hooks")
        before = (store.state_root(self.env) / "current").resolve()
        rc, _, err = self.cli("apply", "--theme", "nope", "--no-hooks")
        self.assertEqual(rc, 2)
        self.assertIn("unknown theme", err)
        self.assertEqual((store.state_root(self.env) / "current").resolve(), before)
        rc, _, _ = self.cli("apply", "--theme", "wallpaper:deadbeef", "--no-hooks")
        self.assertEqual(rc, 2)

    def test_theme_conflicts_with_mode_wallpaper_accent(self):
        for extra in (["--mode", "auto"], ["--wallpaper", "x.png"], ["--accent", "#00ff88"]):
            rc, _, err = self.cli("apply", "--theme", "seclegion-dark", *extra)
            self.assertEqual(rc, 2, extra)
            self.assertIn("cannot be combined", err)


class Wallpapers(Base):
    def test_recent_wallpapers_are_listed_and_reapplied(self):
        a, b = self.wall("a.png", b"a"), self.wall("b.png", b"b")
        self.apply_wall(a)
        self.apply_wall(b)
        sha_a, sha_b = (f"wallpaper:{store.file_sha256(p)[:8]}" for p in (a, b))
        listed = manager.list_themes(self.env)
        self.assertEqual([t["id"] for t in listed][3:], [sha_b, sha_a])
        self.assertEqual([t["id"] for t in listed if t["current"]], [sha_b])
        kw = manager.resolve(sha_a, self.env)
        self.assertEqual(kw, {"mode": "auto", "wallpaper": a})
        engine.apply_theme(**kw, env=self.env, run_hooks=False, matugen_runner=self.runner, which=which)
        self.assertEqual(self.current()["source"]["sha256"], store.file_sha256(a))

    def test_vanished_wallpaper_and_accent_variants_are_not_listed(self):
        a = self.wall("a.png", b"a")
        self.apply_wall(a)
        a.unlink()
        self.assertEqual(len(manager.list_themes(self.env)), 3)
        b = self.wall("b.png", b"b")
        engine.apply_theme(wallpaper=b, mode="auto", accent="#3df0cb", env=self.env, run_hooks=False)
        self.assertEqual(len(manager.list_themes(self.env)), 3)

    def test_theme_apply_keeps_the_current_contrast(self):
        engine.apply_theme(mode="default", contrast="high", env=self.env, run_hooks=False)
        self.assertEqual(manager.current_contrast(self.env), "high")
        self.cli("apply", "--theme", "seclegion-teal", "--no-hooks")
        self.assertEqual(self.current()["contrast"], "high")


if __name__ == "__main__":
    unittest.main()
