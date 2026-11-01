# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Render, store, engine, matugen and hook tests. Nothing touches the real
~/.config or state dir: every run uses a temp XDG_STATE_HOME and fake hooks.

Set SL_THEME_TEST_NOGUARD=1 to run with the colour guard in render._hex()
disabled; the injection tests must then fail (the guard mutation check).
"""

import contextlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import _bootstrap  # noqa: F401
except ImportError:  # run as desktop.theme.tests.test_engine
    from . import _bootstrap  # noqa: F401
from seclegion_theme import cli, engine, hooks, matugen, render, store
from seclegion_theme import color as C
from seclegion_theme import palette as P
from seclegion_theme.palette import ThemeError

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def WHICH(name):
    return "/usr/bin/matugen"


RGBA = re.compile(r"^rgba\([0-9a-f]{8}\)$")
# Payloads that are exactly 6 or 8 characters, so they get past the separate
# #rrggbb length check in _rgba(): only the _hex() guard stops them.
SIZED_PAYLOADS = ('")--xx', '"..x--', '")os.ex"', "0x00ff", "00ff8\n")
NO_SOURCE = {"wallpaper": None, "sha256": None, "accent_override": None}


def setUpModule():
    if os.environ.get("SL_THEME_TEST_NOGUARD") == "1":
        render.GUARD_ENABLED = False


def tearDownModule():
    render.GUARD_ENABLED = True


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-theme-test-"))
        self.assertTrue(str(self.tmp).startswith(tempfile.gettempdir()))
        self.env = {"XDG_STATE_HOME": str(self.tmp / "state"), "XDG_RUNTIME_DIR": str(self.tmp)}
        self.wall = self.tmp / "wall with space.png"
        self.wall.write_bytes(b"not really a png")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def apply(self, **kw):
        kw.setdefault("run_hooks", False)
        return engine.apply_theme(env=self.env, **kw)

    def fake_matugen(self, fixture="matugen_v2.json"):
        out = (FIXTURES / fixture).read_text()
        self.calls = []

        def runner(argv, **kw):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, out, "")

        return runner


class Rendering(Base):
    def test_all_outputs_written_with_contract_names(self):
        r = self.apply(mode="default", wallpaper=self.wall)
        names = {p.name for p in r.path.iterdir()}
        self.assertEqual(names, set(render.FILES) | {"wallpaper"})
        self.assertTrue((r.path / "wallpaper").is_symlink())
        self.assertEqual(os.readlink(r.path / "wallpaper"), str(self.wall))
        css = (r.path / "colors.css").read_text()
        for tok in P.TOKEN_NAMES:
            self.assertRegex(css, rf"@define-color sl_{tok} #[0-9a-f]{{6}};")
        j = json.loads((r.path / "colors.json").read_text())
        self.assertEqual(set(j["tokens"]), set(P.TOKEN_NAMES))
        self.assertEqual((j["mode"], j["source"]["wallpaper"]), ("default", str(self.wall)))
        for f in ("swaync-colors.css", "swayosd-colors.css"):
            self.assertIn("@define-color sl_bg #050f0e;", (r.path / f).read_text())
        self.assertIn('palette = "seclegion"', (r.path / "starship.toml").read_text())

    def test_g5_hyprland_lua_only_rgba_never_0x(self):
        for mode, kw in (("default", {}), ("auto", {"accent": "#ff3300"})):
            for contrast in ("normal", "high"):
                r = self.apply(mode=mode, contrast=contrast, **kw)
                for f in ("hyprland-colors.lua", "hyprlock-colors.conf"):
                    text = (r.path / f).read_text()
                    code = "\n".join(ln for ln in text.splitlines() if not ln.startswith(("--", "#")))
                    self.assertNotIn("0x", code.lower())
                    self.assertNotIn("#", code)
                lua = (r.path / "hyprland-colors.lua").read_text()
                values = re.findall(r'= "([^"]*)"', lua)
                self.assertGreaterEqual(len(values), 2)
                for v in values:
                    self.assertRegex(v, RGBA)
                self.assertIn('active_border = "rgba(', lua)

    @unittest.skipUnless(shutil.which("lua"), "lua not installed")
    def test_lua_loads_under_pcall(self):
        r = self.apply(mode="default")
        code = (
            "local ok,t=pcall(dofile,os.getenv('SL_LUA')); assert(ok and type(t)=='table');"
            "assert(t.active_border:match('^rgba%(%x%x%x%x%x%x%x%x%)$'))"
        )
        subprocess.run(["lua", "-e", code], check=True, env={"SL_LUA": str(r.path / "hyprland-colors.lua")})

    def test_injection_is_rejected(self):
        base = P.default_tokens()
        payloads = (
            (
                '")os.execute(',
                '#00ff88"; os.execute("id") --',
                "#00ff88\nrm",
                "0x00ff88",
                "#00ff88ff00",
                "#00ff88\n",
            )
            + SIZED_PAYLOADS
            + tuple("#" + e for e in SIZED_PAYLOADS)
        )
        for key in ("accent", "border_active", "border_inactive", "crit"):  # all reach the Lua via _rgba
            for evil in payloads:
                with self.assertRaises(ThemeError, msg=(key, evil)):
                    render.render_all(
                        dict(base, **{key: evil}),
                        mode="d",
                        requested_mode="d",
                        contrast="normal",
                        source=NO_SOURCE,
                    )
        with self.assertRaises(ThemeError):
            render._rgba("#00ff88", '")')

    def test_validation_layer_alone_rejects_injection(self):
        # the first line of defence (before any template); rgba has its own second layer
        for evil in (
            '")os.execute(',
            '#00ff88"; x',
            "#00FF88",
            "0x00ff88",
            "#00ff88ff00",
            "#00ff88\n",
            "00ff88\n",
        ) + SIZED_PAYLOADS:
            with self.assertRaises(ThemeError, msg=evil):
                render._checked(dict(P.default_tokens(), bg=evil))
        self.assertEqual(render._h("#00ff88ff"), "#00ff88ff")  # 8-digit form is the only other legal one

    def test_weird_wallpaper_path_cannot_break_files_only_json(self):
        evil = self.tmp / "a\"b\n)os.execute('x').png"
        evil.write_bytes(b"x")
        r = self.apply(mode="default", wallpaper=evil)
        self.assertEqual(json.loads((r.path / "colors.json").read_text())["source"]["wallpaper"], str(evil))
        for f in render.FILES:
            if f != "colors.json":
                self.assertNotIn("os.execute", (r.path / f).read_text())

    def test_extra_keys_in_tokens_are_not_rendered(self):
        t = dict(P.default_tokens(), evil='")os.execute(')
        out = render.render_all(t, mode="d", requested_mode="d", contrast="normal", source=NO_SOURCE)
        self.assertFalse(any("os.execute" in v for v in out.values()))

    def test_shipped_default_matches_generator(self):
        shipped = HERE.parent / "default"
        gen = Path(engine.export_default(self.tmp / "gen"))
        for f in render.FILES + ("colors.json.license",):
            self.assertEqual((shipped / f).read_text(), (gen / f).read_text(), f)

    def test_every_generated_file_carries_spdx(self):
        out = render.render_all(
            P.default_tokens(), mode="d", requested_mode="d", contrast="normal", source=NO_SOURCE
        )
        for f, text in out.items():
            if f == "yazi-theme.toml":  # line 1 is the hook's overwrite marker, SPDX is line 2
                self.assertEqual(
                    # REUSE-IgnoreStart
                    text.splitlines()[:2], [render.YAZI_MARKER, "# SPDX-License-Identifier: MIT"]
                    # REUSE-IgnoreEnd
                )
            elif f != "colors.json":  # no comments in JSON: colors.json.license instead
                # REUSE-IgnoreStart
                self.assertIn("SPDX-License-Identifier: MIT", text.splitlines()[0], f)
                # REUSE-IgnoreEnd


class StoreAndEngine(Base):
    def test_g4_same_input_same_dir_and_atomic_symlink(self):
        a = self.apply(mode="default", wallpaper=self.wall)
        before = {p.name: p.read_bytes() for p in a.path.iterdir() if p.is_file() and not p.is_symlink()}
        b = self.apply(mode="default", wallpaper=self.wall)
        self.assertEqual(a.name, b.name)
        root = store.state_root(self.env)
        self.assertEqual(os.readlink(root / "current"), a.name)
        self.assertEqual(
            sorted(p.name for p in root.iterdir() if not p.name.startswith(".")), sorted([a.name, "current"])
        )
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in b.path.iterdir() if p.is_file() and not p.is_symlink()}
        )
        self.assertEqual([p.name for p in root.iterdir() if p.name.startswith(".")], [])  # no tmp leftovers

    def test_g4_auto_deterministic_and_different_inputs_differ(self):
        r1 = self.apply(
            mode="auto", wallpaper=self.wall, matugen_runner=self.fake_matugen("matugen_v2.json"), which=WHICH
        )
        r2 = self.apply(
            mode="auto", wallpaper=self.wall, matugen_runner=self.fake_matugen("matugen_v2.json"), which=WHICH
        )
        r3 = self.apply(
            mode="auto", wallpaper=self.wall, matugen_runner=self.fake_matugen("matugen_v3.json"), which=WHICH
        )
        self.assertEqual(r1.name, r2.name)
        self.assertNotEqual(r1.name, r3.name)
        self.assertEqual(os.readlink(store.state_root(self.env) / "current"), r3.name)

    def test_symlink_swap_is_atomic_for_concurrent_readers(self):
        a = self.apply(mode="default")
        b = self.apply(mode="auto", accent="#ff3300")
        root = store.state_root(self.env)
        stop, bad = threading.Event(), []

        def reader():
            while not stop.is_set():
                try:
                    json.loads((root / "current" / "colors.json").read_text())
                except Exception as e:  # any miss means the link was ever absent/partial
                    bad.append(repr(e))

        th = threading.Thread(target=reader)
        th.start()
        for i in range(300):
            store.swap_current(root, (a, b)[i % 2].name)
        stop.set()
        th.join()
        self.assertEqual(bad, [])

    def test_flock_blocks_second_run(self):
        with store.locked(self.env):
            with self.assertRaises(ThemeError):
                with store.locked(self.env, wait_s=0.1):
                    pass
        with store.locked(self.env, wait_s=0.1):  # released afterwards
            pass

    def test_auto_uses_matugen_with_argv_not_shell(self):
        evil = self.tmp / "x; rm -rf ~ $(id).png"
        evil.write_bytes(b"x")
        runner = self.fake_matugen()
        r = self.apply(mode="auto", wallpaper=evil, matugen_runner=runner, which=lambda n: "/usr/bin/matugen")
        self.assertEqual(self.calls[0][:3], ["/usr/bin/matugen", "image", str(evil)])
        self.assertIn("hex", self.calls[0])
        self.assertEqual(r.mode, "auto")
        lo, hi = P.ACCENT_HUE_RANGE
        for k in ("accent", "accent2"):  # zero tolerance, on the final 8-bit colour
            self.assertTrue(lo <= C.to_oklch(r.tokens[k])[2] <= hi, (k, r.tokens[k]))
        self.assertEqual(P.violations(r.tokens), [])

    def test_real_matugen_4_2_0_fixture_parses(self):
        seed = matugen.seed_from_json(json.loads((FIXTURES / "matugen_4.2.0_real.json").read_text()))
        lo, hi = P.ACCENT_HUE_RANGE
        self.assertTrue(lo <= seed.accent_hue <= hi and lo <= seed.accent2_hue <= hi)
        self.assertIn("--prefer", matugen.argv(self.wall))  # else matugen exits 1 without a tty

    @unittest.skipUnless(shutil.which("matugen"), "matugen not installed")
    def test_live_matugen_end_to_end_on_repo_wallpapers(self):
        ver = subprocess.run(["matugen", "--version"], capture_output=True, text=True).stdout.strip()
        print(f"\n[live matugen: {ver}]")
        root = HERE.parents[2]
        walls = sorted(root.glob("*.png"))
        self.assertTrue(walls)
        for w in walls:
            r = self.apply(mode="auto", wallpaper=w, contrast="normal")
            self.assertEqual(r.mode, "auto", w.name)
            self.assertEqual(P.violations(r.tokens), [], w.name)
            self.assertLessEqual(C.to_oklch(r.tokens["bg"])[0], P.BG_L_MAX, w.name)

    def test_matugen_missing_falls_back_with_clear_message(self):
        r = self.apply(mode="auto", wallpaper=self.wall, which=lambda n: None)
        self.assertEqual((r.mode, r.requested_mode), ("default", "auto"))
        self.assertTrue(any("matugen is not installed" in w for w in r.warnings))
        self.assertEqual(r.tokens, P.finalize(P.default_tokens()))
        with self.assertRaises(matugen.MatugenMissing):
            matugen.run(self.wall, which=lambda n: None)

    def test_matugen_failure_is_an_error_and_changes_nothing(self):
        def boom(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, "", "bad image")

        with self.assertRaises(ThemeError):
            self.apply(mode="auto", wallpaper=self.wall, matugen_runner=boom, which=lambda n: "/x")
        self.assertFalse((store.state_root(self.env) / "current").exists())

    def test_both_matugen_layouts_parse(self):
        for f in ("matugen_v2.json", "matugen_v3.json"):
            seed = matugen.seed_from_json(json.loads((FIXTURES / f).read_text()))
            lo, hi = P.ACCENT_HUE_RANGE
            self.assertTrue(lo <= seed.accent_hue <= hi, f)
        with self.assertRaises(ThemeError):
            matugen.seed_from_json({"colors": {}})

    def test_reset_returns_to_default_and_high_contrast_reuses_wallpaper(self):
        self.apply(mode="auto", wallpaper=self.wall, matugen_runner=self.fake_matugen(), which=lambda n: "/x")
        high = self.apply(
            mode="auto", contrast="high", matugen_runner=self.fake_matugen(), which=lambda n: "/x"
        )
        self.assertEqual(
            json.loads((high.path / "colors.json").read_text())["source"]["wallpaper"], str(self.wall)
        )
        self.assertEqual(P.violations(high.tokens, True), [])
        reset = self.apply(mode="default")
        self.assertEqual(reset.tokens, P.finalize(P.default_tokens()))

    def test_input_validation(self):
        for kw in (
            {"mode": "custom", "accent": "#ff3300"},
            {"mode": "bogus"},
            {"mode": "auto", "accent": "red"},
            {"mode": "default", "accent": "#00ff88"},
            {"mode": "default", "wallpaper": "/nonexistent.png"},
            {"contrast": "max"},
        ):
            with self.assertRaises(ThemeError, msg=str(kw)):
                self.apply(**kw)
        self.assertEqual(engine.MODES, ("auto", "default"))

    def test_accent_override_is_hue_clamped_and_needs_no_matugen(self):
        r = self.apply(mode="auto", accent="#ff3300", which=lambda n: None)
        self.assertEqual(r.mode, "auto")
        self.assertEqual(P.violations(r.tokens), [])  # includes the zero-tolerance hue check
        self.assertEqual(
            json.loads((r.path / "colors.json").read_text())["source"]["accent_override"], "#ff3300"
        )

    def test_concurrent_applies_are_serialised_last_locker_wins(self):
        x, y = self.tmp / "x.png", self.tmp / "y.png"
        x.write_bytes(b"x")
        y.write_bytes(b"y")
        out = (FIXTURES / "matugen_v2.json").read_text()
        events, x_inside, results = [], threading.Event(), {}

        def slow_matugen(argv, **kw):  # X is slow, Y fast: an unlocked Y would finish first
            tag = "X" if argv[2] == str(x) else "Y"
            events.append(tag + "+")
            if tag == "X":
                x_inside.set()
                time.sleep(0.5)
            events.append(tag + "-")
            return subprocess.CompletedProcess(argv, 0, out, "")

        def run(tag, wp):
            try:
                results[tag] = self.apply(mode="auto", wallpaper=wp, matugen_runner=slow_matugen, which=WHICH)
            except Exception as e:  # surfaced by the asserts below
                results[tag] = e

        tx = threading.Thread(target=run, args=("X", x))
        tx.start()
        self.assertTrue(x_inside.wait(5))  # X now holds the lock, inside matugen
        ty = threading.Thread(target=run, args=("Y", y))
        ty.start()
        tx.join(10)
        ty.join(10)
        self.assertIsInstance(results.get("X"), engine.Result, results)
        self.assertIsInstance(results.get("Y"), engine.Result, results)
        self.assertEqual(events, ["X+", "X-", "Y+", "Y-"])  # Y's run never overlapped X's
        root = store.state_root(self.env)
        self.assertEqual(os.readlink(root / "current"), results["Y"].name)
        self.assertEqual(store.read_current(root)["source"]["wallpaper"], str(y))

    def test_files_and_dir_fsynced_before_rename(self):
        order = []
        real_fsync, real_rename = os.fsync, os.rename
        with (
            mock.patch.object(
                store.os, "fsync", side_effect=lambda fd: (order.append("fsync"), real_fsync(fd))
            ),
            mock.patch.object(
                store.os, "rename", side_effect=lambda a, b: (order.append("rename"), real_rename(a, b))
            ),
        ):
            self.apply(mode="default")
        self.assertIn("rename", order)
        self.assertGreaterEqual(order.index("rename"), len(render.FILES) + 1)  # each file + the tmp dir
        self.assertEqual(order[-1], "fsync")  # state dir after the swap

    def test_damaged_existing_dir_is_rebuilt_not_reused(self):
        good = self.apply(mode="default", wallpaper=self.wall)
        ref = {f: (good.path / f).read_text() for f in render.FILES}
        for damage in ("empty", "badjson", "missing", "nolink"):
            if damage == "empty":
                (good.path / "kitty-colors.conf").write_text("")
            elif damage == "badjson":
                (good.path / "colors.json").write_text("{not json")
            elif damage == "missing":
                (good.path / "rofi-colors.rasi").unlink()
            else:
                (good.path / "wallpaper").unlink()
            r = self.apply(mode="default", wallpaper=self.wall)
            self.assertEqual(r.name, good.name, damage)
            self.assertEqual({f: (r.path / f).read_text() for f in render.FILES}, ref, damage)
            self.assertTrue((r.path / "wallpaper").is_symlink(), damage)

    def test_prune_keeps_newest_five_plus_current_and_drops_tmp(self):
        root = store.state_root(self.env)
        names = [
            self.apply(mode="auto", accent=a).name
            for a in ("#00ff88", "#00f0ff", "#00ffcc", "#33ff99", "#00e0aa", "#22ddbb", "#11ccdd")
        ]
        self.assertEqual(len(set(names)), 7)
        left = sorted(n for n in os.listdir(root) if store._is_theme_name(n))
        self.assertEqual(left, sorted(names[-5:]))  # every apply prunes under the lock
        os.mkdir(root / ".tmp-stale")
        os.utime(root / names[-1], ns=(0, 0))  # current's target is now the oldest
        store.prune(root, keep=2)
        left = sorted(n for n in os.listdir(root) if store._is_theme_name(n))
        self.assertEqual(left, sorted(names[-3:-1] + names[-1:]))  # 2 newest others + current's target
        self.assertFalse((root / ".tmp-stale").exists())
        self.assertTrue((root / "current" / "colors.json").is_file())

    def test_reset_keeps_wallpaper_link(self):
        self.apply(mode="auto", wallpaper=self.wall, matugen_runner=self.fake_matugen(), which=WHICH)
        r = self.apply(mode="default")
        self.assertEqual(r.mode, "default")
        self.assertEqual(os.readlink(r.path / "wallpaper"), str(self.wall))
        self.assertEqual(
            store.read_current(store.state_root(self.env))["source"]["wallpaper"], str(self.wall)
        )


class CurrentCommand(Base):
    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def current_json(self, text: str) -> Path:
        r = self.apply(mode="default")
        (r.path / "colors.json").write_text(text)
        return r.path

    def test_undecodable_wallpaper_path_prints_escaped(self):
        # A surrogate-escaped path (non-UTF-8 filename) must not crash a real UTF-8 stdout.
        self.current_json(json.dumps({"mode": "auto", "source": {"wallpaper": "/w/wp\udcff.png"}}))
        tool = Path(__file__).resolve().parents[3] / "tools" / "seclegion-theme"
        res = subprocess.run(
            [str(tool), "current"],
            capture_output=True,
            env={**self.env, "PATH": os.environ["PATH"], "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(b"wp\\udcff.png", res.stdout)

    def test_nothing_applied(self):
        self.assertEqual(self.cli("current")[0], 1)

    def test_missing_keys_do_not_crash(self):
        self.current_json('{"mode": "auto"}')
        code, out, _ = self.cli("current")
        self.assertEqual((code, out.strip()), (0, "mode=auto contrast=- wallpaper=- accent=-"))
        self.current_json("[1, 2]")
        code, _, err = self.cli("current")
        self.assertEqual(code, 2)
        self.assertIn("not a theme description", err)

    def test_damaged_state_gets_plain_messages(self):
        root = store.state_root(self.env)
        path = self.current_json("{}")
        (path / "colors.json").write_bytes(b"\xff\xfe{")
        code, _, err = self.cli("current")
        self.assertEqual(code, 2)
        self.assertIn("is not readable text", err)
        self.current_json("{oops")
        self.assertIn("not valid JSON", self.cli("current")[2])
        os.unlink(root / "current")
        (root / "current").write_text("a file, not a dir")
        code, _, err = self.cli("current")
        self.assertEqual(code, 2)
        self.assertIn("is not a theme directory", err)
        self.assertNotIn("Traceback", err)

    @unittest.skipIf(os.geteuid() == 0, "root reads mode-000 files")
    def test_permission_denied_is_plain(self):
        path = self.current_json("{}")
        os.chmod(path / "colors.json", 0)
        self.addCleanup(os.chmod, path / "colors.json", 0o644)
        code, _, err = self.cli("current")
        self.assertEqual(code, 2)
        self.assertIn("permission denied", err)

    def test_control_characters_stripped_from_printed_paths(self):
        evil = self.tmp / "a\x1b[2Jb\rc\x9bd.png"
        evil.write_bytes(b"x")
        self.apply(mode="default", wallpaper=evil)
        code, out, _ = self.cli("current")
        self.assertEqual(code, 0)
        self.assertFalse(any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in out.rstrip("\n")), repr(out))
        self.assertIn("a[2Jbcd.png", out)
        _, _, err = self.cli(
            "apply", "--mode", "default", "--wallpaper", str(self.tmp / "no\x1bpe.png"), "--no-hooks"
        )
        self.assertIn("nope.png", err)


WD = "wayland-1"


class FakeProc:
    """A fake /proc: pid -> (comm, exe target, WAYLAND_DISPLAY or None)."""

    def __init__(self, tmp, procs):
        self.root = Path(tempfile.mkdtemp(prefix="proc-", dir=tmp))
        for pid, (comm, exe, wd) in procs.items():
            d = self.root / str(pid)
            d.mkdir()
            (d / "comm").write_text(comm + "\n")
            os.symlink(exe, d / "exe")  # dangling is fine: only readlink() is used
            env = [b"HOME=/home/u"] + ([f"WAYLAND_DISPLAY={wd}".encode()] if wd is not None else [])
            (d / "environ").write_bytes(b"\0".join(env) + b"\0")


def P_(comm, exe=None, wd=WD):
    return (comm, exe or f"/usr/bin/{comm}", wd)


def systemd(active=None, listed=""):
    """Fake `systemctl --user`: `active` is what is-active swayosd.service says."""

    def runner(argv, **k):
        if argv[1:2] != ["--user"]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[2] == "is-active":
            return subprocess.CompletedProcess(
                argv, 0 if active == "active" else 3, (active or "inactive") + "\n", ""
            )
        if argv[2] == "list-units":
            return subprocess.CompletedProcess(argv, 0, listed, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    return runner


class Hooks(Base):
    def ctx(self, procs=None, env=None, which=None, runner=None, **kw):
        fp = FakeProc(self.tmp, procs or {})
        self.runs, self.kills = [], []
        inner = runner or systemd()

        def recording(argv, **k):
            self.runs.append(argv)
            return inner(argv, **k)

        return hooks.Ctx(
            active_border="rgba(00ff88ff)",
            inactive_border="rgba(0b1e1cff)",
            env={"HYPRLAND_INSTANCE_SIGNATURE": "x", "WAYLAND_DISPLAY": WD} if env is None else env,
            pids=hooks.running_pids(proc_root=str(fp.root)),
            runner=recording,
            kill=lambda p, s: self.kills.append((p, s)),
            which=which or (lambda n: f"/usr/bin/{n}"),
            proc_root=str(fp.root),
            **kw,
        )

    def test_running_pids_filters_by_name(self):
        c = self.ctx({10: P_("kitty"), 11: P_("bash"), 12: P_("waybar")})
        self.assertEqual((c.pids["kitty"], c.pids["waybar"], c.pids["swaync"]), ([10], [12], []))

    def test_signals_kitty_usr1_waybar_usr2_and_no_remote_control(self):
        c = self.ctx({10: P_("kitty"), 11: P_("kitty"), 12: P_("waybar")})
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(
            sorted(self.kills), [(10, signal.SIGUSR1), (11, signal.SIGUSR1), (12, signal.SIGUSR2)]
        )
        self.assertEqual((res["kitty"].status, res["waybar"].status), ("ok", "ok"))
        self.assertFalse(any("kitty" in " ".join(a) or "remote" in " ".join(a) for a in self.runs))

    def test_only_verified_targets_are_signalled(self):
        c = self.ctx(
            {
                10: P_("kitty"),  # the one real target
                11: P_("kitty", exe="/usr/bin/python3"),  # comm spoofed by another binary
                12: P_("kitty", exe="/tmp/x/kitty-evil"),  # basename not exactly kitty
                13: P_("kitty", exe="/opt/kitty.bin"),
                14: P_("kitty", wd="wayland-2"),  # another Wayland session
                15: P_("kitty", wd=None),  # no WAYLAND_DISPLAY at all
                20: P_("waybar", wd="wayland-10"),  # prefix of nothing: exact match only
                21: P_("waybar", exe="/usr/bin/waybar"),
            }
        )
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(sorted(self.kills), [(10, signal.SIGUSR1), (21, signal.SIGUSR2)])
        self.assertEqual(res["kitty"].detail, "signalled 1/1")

    def test_other_uid_is_never_signalled(self):
        c = self.ctx({10: P_("kitty"), 12: P_("waybar")}, uid=os.getuid() + 1)
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(self.kills, [])
        self.assertEqual((res["kitty"].status, res["waybar"].status), ("skipped", "skipped"))

    def test_no_wayland_display_skips_signals_no_hyprland_sig_skips_hyprctl(self):
        c = self.ctx({10: P_("kitty"), 12: P_("waybar")}, env={})
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(self.kills, [])
        self.assertIn("WAYLAND_DISPLAY unset", res["kitty"].detail)
        self.assertIn("WAYLAND_DISPLAY unset", res["waybar"].detail)
        self.assertEqual(res["hyprland"].status, "skipped")
        self.assertIn("HYPRLAND_INSTANCE_SIGNATURE", res["hyprland"].detail)
        self.assertFalse(any(a[0].endswith("hyprctl") for a in self.runs))

    # -- wallpaper hook: seclegion-wallpaper paints the theme's wallpaper on every output (issue 16)
    HELPER = Path(__file__).resolve().parents[2] / "display" / "seclegion-wallpaper"
    AWWW = "import json, sys\nopen(sys.argv[1], 'a').write(json.dumps(sys.argv[2:]) + '\\n')\n"

    def test_awww_on_apply(self):
        # the real engine and the real helper; only awww is a stub, and no live process is seen
        (self.tmp / "awww.py").write_text(self.AWWW)
        log = self.tmp / "awww.log"
        env = dict(
            self.env,
            HOME=str(self.tmp / "home"),
            WAYLAND_DISPLAY="sl-test-none",
            SL_WALLPAPER=f"{sys.executable} -I {self.HELPER}",
            SL_AWWW=f"{sys.executable} {self.tmp / 'awww.py'} {log}",
            SL_DEFAULT_WALLPAPER=str(self.tmp / "missing.png"),
        )
        # os.environ gets the stub too: a helper that missed env= must still never reach a live awww
        with mock.patch.object(hooks, "running_pids", return_value={}), \
             mock.patch.dict(os.environ, {"SL_AWWW": env["SL_AWWW"]}):
            res = engine.apply_theme(wallpaper=self.wall, mode="default", env=env)
        status = {r.name: r.status for r in res.hook_results}
        self.assertEqual(status["wallpaper"], "ok", res.hook_results)
        self.assertEqual(
            [json.loads(x) for x in log.read_text().splitlines()],
            [["img", str(self.wall), "--transition-type", "none"]],  # no --outputs: every output
        )

    def test_wallpaper_hook_skipped_for_auto_sync(self):
        c = self.ctx({}, env={"WAYLAND_DISPLAY": WD, "SL_WALLPAPER": "/bin/true"}, paint_wallpaper=False)
        self.assertEqual(hooks.hook_wallpaper(c).status, "skipped")
        self.assertEqual(self.runs, [])

    def test_not_running_is_skipped_not_failed(self):
        res = {r.name: r for r in hooks.run_hooks(self.ctx({}, env={}))}
        self.assertEqual({r.status for r in res.values()}, {"skipped"})
        self.assertEqual(self.runs, [])

    # -- hyprland hook: `hyprctl reload` only, and only with the border component applied
    HOST_LUA = Path(__file__).resolve().parents[2] / "hypr" / "seclegion-host.lua"
    SHIPPED_CONTRACT = Path("/usr/share/seclegion/theme/default/hyprland-colors.lua")

    def hypr_world(self, border=True):
        cfg = Path(self.tmp) / "xdg"
        (cfg / "hypr").mkdir(parents=True)
        if border:
            (cfg / "hypr" / "seclegion-host.lua").write_text("-- border component\n")
        log = Path(self.tmp) / "hyprctl.log"
        stub = Path(self.tmp) / "hyprctl"
        stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n')
        stub.chmod(0o755)
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "x", "XDG_CONFIG_HOME": str(cfg)}
        c = self.ctx({}, env=env, which=lambda n: str(stub), runner=subprocess.run)
        return c, log

    def test_hyprland_reload_is_the_only_hyprctl_call(self):
        c, log = self.hypr_world()
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(res["hyprland"].status, "ok")
        self.assertEqual(log.read_text().splitlines(), ["reload"])

    def test_hyprland_no_border_is_skipped_and_stub_log_empty(self):
        c, log = self.hypr_world(border=False)
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertEqual(res["hyprland"].status, "skipped")
        self.assertIn("border component", res["hyprland"].detail)
        self.assertFalse(log.exists())

    def test_hyprland_no_instance_signature_never_runs_hyprctl(self):
        c, log = self.hypr_world()
        c.env.pop("HYPRLAND_INSTANCE_SIGNATURE")
        self.assertEqual(hooks.hook_hyprland(c).status, "skipped")
        self.assertFalse(log.exists())

    def test_hyprland_hook_source_has_no_keyword_or_batch(self):
        src = Path(hooks.__file__).read_text()
        self.assertNotIn("keyword", src)
        self.assertNotIn("--batch", src)

    # -- seclegion-host.lua takes the border from the contract
    def host_lua(self, home):
        code = (
            "local got; hl = {config=function(t) got=t end, workspace_rule=function() end, "
            "env=function() end};"
            "dofile(os.getenv('SL_HOST_LUA'));"
            "print(got.general.col.active_border, got.general.col.inactive_border)"
        )
        out = subprocess.run(
            ["lua", "-e", code],
            check=True,
            capture_output=True,
            text=True,
            env={"HOME": str(home), "SL_HOST_LUA": str(self.HOST_LUA)},
        ).stdout
        return out.splitlines()[-1].split("\t")

    def contract(self, home, body):
        d = Path(home) / ".local/state/seclegion/theme/current"
        d.mkdir(parents=True, exist_ok=True)
        (d / "hyprland-colors.lua").write_text(body)

    @unittest.skipUnless(shutil.which("lua"), "lua not installed")
    def test_hyprland_host_lua_uses_contract_values_as_given(self):
        home = Path(self.tmp) / "h"
        self.contract(home, 'return { active_border = "rgba(12345678)", inactive_border = "rgba(aabbccdd)" }')
        self.assertEqual(self.host_lua(home), ["rgba(12345678)", "rgba(aabbccdd)"])

    @unittest.skipUnless(shutil.which("lua"), "lua not installed")
    @unittest.skipIf(SHIPPED_CONTRACT.exists(), "a shipped default contract is installed on this machine")
    def test_hyprland_host_lua_falls_back_to_green_literal(self):
        home = Path(self.tmp) / "h"
        for body in (None, "this is not lua (", 'return { active_border = "0xff00ff88" }', "return 5"):
            if body is not None:
                self.contract(home, body)
            self.assertEqual(self.host_lua(home), ["rgba(00ff88ff)", "rgba(0b1e1cff)"], body)

    def test_swaync_reload(self):
        c = self.ctx({20: P_("swaync")}, env={})
        res = {r.name: r for r in hooks.run_hooks(c)}
        self.assertIn(["/usr/bin/swaync-client", "--reload-css"], self.runs)
        self.assertEqual(res["swaync"].status, "ok")

    # -- yazi hook: writes theme.toml only over our own file (marker) or into nothing
    def yazi_world(self, existing=None, make_dir=True):
        d = Path(self.tmp) / "ytheme"
        d.mkdir(exist_ok=True)
        (d / "yazi-theme.toml").write_text(hooks.YAZI_MARKER + "\n# new\n")
        cfg = Path(self.tmp) / "yazi-cfg"
        if make_dir:
            cfg.mkdir()
        if existing is not None:
            (cfg / "theme.toml").write_text(existing)
        c = self.ctx({}, env={"YAZI_CONFIG_HOME": str(cfg)}, theme_dir=d)
        return c, cfg / "theme.toml"

    def test_yazi_marker_is_one_string_in_render_and_hooks(self):
        self.assertEqual(render.YAZI_MARKER, hooks.YAZI_MARKER)

    def test_yazi_absent_theme_is_created(self):
        c, t = self.yazi_world()
        r = hooks.hook_yazi(c)
        self.assertEqual(r.status, "ok")
        self.assertTrue(t.read_text().endswith("# new\n"))
        self.assertEqual(
            sorted(p.name for p in t.parent.iterdir()), ["theme.toml", "theme.toml.seclegion-sha256"]
        )

    def test_yazi_marker_file_is_replaced_even_if_edited_further(self):
        c, t = self.yazi_world(hooks.YAZI_MARKER + "\n# my tweak\n")
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        self.assertIn("# new", t.read_text())
        self.assertNotIn("tweak", t.read_text())

    def test_yazi_hand_edited_file_is_adopted_on_first_run(self):
        c, t = self.yazi_world("[manager]\n# mine\n")
        t.chmod(0o600)
        r = hooks.hook_yazi(c)
        orig = t.parent / "theme.toml.seclegion-orig"
        self.assertEqual(r.status, "adopted")
        self.assertIn(str(orig), r.detail)
        self.assertIn(f"mv {orig} {t}", r.detail)
        self.assertEqual(orig.read_bytes(), b"[manager]\n# mine\n")
        self.assertTrue(t.read_text().startswith(hooks.YAZI_MARKER))
        self.assertEqual(t.stat().st_mode & 0o777, 0o600)

    def test_yazi_hand_edited_file_is_kept_when_orig_exists(self):
        c, t = self.yazi_world("[manager]\n# restored\n")
        orig = t.parent / "theme.toml.seclegion-orig"
        orig.write_text("[manager]\n# first\n")
        r = hooks.hook_yazi(c)
        self.assertEqual(r.status, "kept")
        self.assertEqual(t.read_text(), "[manager]\n# restored\n")
        self.assertEqual(orig.read_text(), "[manager]\n# first\n")

    def test_yazi_edited_marker_file_is_backed_up_then_replaced(self):
        c, t = self.yazi_world()
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        bak = t.parent / "theme.toml.seclegion-bak"
        t.write_text(t.read_text() + "# user tweak\n")
        r = hooks.hook_yazi(c)
        self.assertEqual(r.status, "ok-backed-up")
        self.assertIn(str(bak), r.detail)
        self.assertIn("# user tweak", bak.read_text())
        self.assertNotIn("tweak", t.read_text())
        t.write_text(t.read_text() + "# second tweak\n")  # the previous .bak is overwritten
        self.assertEqual(hooks.hook_yazi(c).status, "ok-backed-up")
        self.assertIn("second tweak", bak.read_text())
        self.assertNotIn("user tweak", bak.read_text())

    def test_yazi_unedited_marker_file_makes_no_backup(self):
        c, t = self.yazi_world()
        hooks.hook_yazi(c)
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        self.assertEqual(
            sorted(p.name for p in t.parent.iterdir()), ["theme.toml", "theme.toml.seclegion-sha256"]
        )

    def test_yazi_marker_file_mode_is_preserved(self):
        c, t = self.yazi_world(hooks.YAZI_MARKER + "\n# old\n")
        t.chmod(0o600)
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        self.assertEqual(t.stat().st_mode & 0o777, 0o600)

    def test_yazi_symlinked_config_dir_is_kept_and_untouched(self):
        c, t = self.yazi_world(make_dir=False)
        real = Path(self.tmp) / "dotfiles-yazi"
        real.mkdir()
        t.parent.symlink_to(real)
        r = hooks.hook_yazi(c)
        self.assertEqual(r.status, "kept")
        self.assertIn("config dir is a symlink", r.detail)
        self.assertEqual(list(real.iterdir()), [])

    def test_yazi_symlink_is_never_followed_or_replaced(self):
        c, t = self.yazi_world()
        victim = Path(self.tmp) / "victim.toml"
        victim.write_text(hooks.YAZI_MARKER + "\nkeep\n")  # marker on the target must not matter
        t.symlink_to(victim)
        self.assertEqual(hooks.hook_yazi(c).status, "kept")
        self.assertTrue(t.is_symlink())
        self.assertEqual(victim.read_text(), hooks.YAZI_MARKER + "\nkeep\n")

    def test_yazi_planted_temp_symlink_is_not_followed(self):
        c, t = self.yazi_world()
        victim = Path(self.tmp) / "victim2.toml"
        victim.write_text("precious")
        (t.parent / f".theme.toml.seclegion-{os.getpid()}").symlink_to(victim)
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        self.assertEqual(victim.read_text(), "precious")
        self.assertFalse(t.is_symlink())

    def test_yazi_missing_dir_and_no_yazi_is_skipped(self):
        c, t = self.yazi_world(make_dir=False)
        c.which = lambda n: None
        self.assertEqual(hooks.hook_yazi(c).status, "skipped")
        self.assertFalse(t.parent.exists())

    def test_yazi_missing_dir_but_installed_creates_it(self):
        c, t = self.yazi_world(make_dir=False)
        self.assertEqual(hooks.hook_yazi(c).status, "ok")
        self.assertTrue(t.is_file())

    def test_swayosd_restarted_only_through_its_user_unit(self):
        osd = {21: P_("swayosd-server")}
        c = self.ctx(osd, env={}, runner=systemd(active="active"))
        r = hooks.hook_swayosd(c)
        self.assertEqual(
            (r.status, self.runs[-1]), ("ok", ["/usr/bin/systemctl", "--user", "restart", "swayosd.service"])
        )
        listed = "swayosd-server.service loaded active running SwayOSD\n"
        c = self.ctx(osd, env={}, runner=systemd(listed=listed))
        r = hooks.hook_swayosd(c)
        self.assertEqual(r.status, "ok")
        self.assertEqual(self.runs[-1], ["/usr/bin/systemctl", "--user", "restart", "swayosd-server.service"])
        self.assertEqual(self.kills, [])  # never signalled, never respawned

    def test_swayosd_without_unit_is_left_alone(self):
        for listed in ("", "-evil.service loaded active running x\n", "swayosd.service; rm loaded active\n"):
            c = self.ctx({21: P_("swayosd-server")}, env={}, runner=systemd(listed=listed))
            r = hooks.hook_swayosd(c)
            self.assertEqual(
                (r.status, r.detail), ("skipped", "swayosd: restart manually to restyle"), listed
            )
            self.assertFalse(any("restart" in a for a in self.runs), listed)
            self.assertEqual(self.kills, [])
        c = self.ctx({21: P_("swayosd-server")}, env={}, which=lambda n: None)  # no systemctl
        self.assertEqual(hooks.hook_swayosd(c).detail, "swayosd: restart manually to restyle")

    def test_failing_and_hanging_hooks_never_raise(self):
        def explode(argv, **k):
            raise OSError("boom")

        c = self.ctx({20: P_("swaync")}, runner=explode, timeout=0.2)

        def hang(ctx):
            threading.Event().wait(1.0)
            return hooks.HookResult("slow", "ok")

        def bug(ctx):
            raise RuntimeError("bug")

        res = {r.name: r.status for r in hooks.run_hooks(c, hooks=(hooks.hook_swaync, hang, bug))}
        self.assertEqual(res, {"swaync": "failed", "hang": "timeout", "bug": "failed"})

    def test_apply_succeeds_even_if_every_hook_fails(self):
        def explode(argv, **k):
            raise OSError("boom")

        c = self.ctx({20: P_("swaync")}, runner=explode)
        r = engine.apply_theme(env=self.env, mode="default", hook_ctx=c)
        self.assertEqual(os.readlink(store.state_root(self.env) / "current"), r.name)
        self.assertTrue(any(h.status == "failed" for h in r.hook_results))

    def test_hooks_run_inside_the_lock(self):
        held = []

        def probe(ctx):
            try:
                with store.locked(self.env, wait_s=0.05):
                    held.append(False)
            except ThemeError:
                held.append(True)
            return hooks.HookResult("probe", "ok")

        c = self.ctx({})
        with mock.patch.object(hooks, "run_hooks", side_effect=lambda ctx: [probe(ctx)]):
            engine.apply_theme(env=self.env, mode="default", hook_ctx=c)
        self.assertEqual(held, [True])


if __name__ == "__main__":
    unittest.main()
