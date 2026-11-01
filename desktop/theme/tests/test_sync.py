# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""`seclegion-theme auto` and `sync`: a fixture HOME with the owner's wallpaper
cache files, fake matugen, no hooks. Nothing touches the real HOME or state."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from seclegion_theme import auto, cli, engine, hooks, matugen, store
from seclegion_theme.palette import ThemeError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PNG = b"\x89PNG\r\n\x1a\n"


def WHICH(name):
    return "/usr/bin/matugen"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-sync-test-"))
        self.assertTrue(str(self.tmp).startswith(tempfile.gettempdir()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.cache = self.home / ".cache"
        self.cache.mkdir(parents=True)
        self.env = {"HOME": str(self.home), "XDG_STATE_HOME": str(self.tmp / "state"),
                    "XDG_RUNTIME_DIR": str(self.tmp)}
        self.matugen_calls = []
        out = self.fixture = (FIXTURES / "matugen_v2.json").read_text()

        def runner(argv, **kw):
            self.matugen_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, out, "")

        self.runner = runner

    def image(self, name="wall.png", extra=b"a"):
        p = self.home / name
        p.write_bytes(PNG + extra)
        return p

    def point_at(self, path, kind="image"):
        (self.cache / "current_wallpaper").write_text(f"{path}\n")
        (self.cache / "current_wallpaper_type").write_text(f"{kind}\n")

    def sync(self):
        return auto.sync(self.env, run_hooks=False, matugen_runner=self.runner, which=WHICH)

    def current(self):
        return store.read_current(store.state_root(self.env))


class AutoState(Base):
    def test_default_is_off_and_file_lives_in_the_theme_state_dir(self):
        self.assertFalse(auto.is_on(self.env))
        auto.set_auto(True, self.env)
        self.assertTrue(auto.is_on(self.env))
        self.assertEqual(auto.state_file(self.env), self.tmp / "state" / "seclegion" / "theme" / "auto")
        auto.set_auto(False, self.env)
        self.assertFalse(auto.is_on(self.env))


class Gates(Base):
    def test_g1_off_means_no_apply(self):
        self.point_at(self.image())
        self.assertTrue(self.sync().startswith("skipped"))
        self.assertEqual(self.matugen_calls, [])
        self.assertIsNone(self.current())

    def test_applies_then_g3_second_run_is_unchanged(self):
        auto.set_auto(True, self.env)
        self.point_at(self.image())
        self.assertTrue(self.sync().startswith("applied "))
        self.assertEqual(len(self.matugen_calls), 1)
        self.assertEqual(self.sync(), "unchanged")
        self.assertEqual(len(self.matugen_calls), 1)

    def test_sync_does_not_repaint_the_wallpaper(self):
        # the wallpaper tool painted it (with its transition); the theme hook must not repaint
        auto.set_auto(True, self.env)
        self.point_at(self.image())
        with mock.patch.object(engine, "apply_theme", return_value=mock.Mock(name="r")) as apply:
            auto.sync(self.env, run_hooks=False)
        self.assertIs(apply.call_args.kwargs["paint_wallpaper"], False)

    def test_new_wallpaper_content_applies_again(self):
        auto.set_auto(True, self.env)
        w = self.image()
        self.point_at(w)
        self.sync()
        w.write_bytes(PNG + b"different")
        self.assertTrue(self.sync().startswith("applied "))
        self.assertEqual(self.current()["source"]["sha256"], store.file_sha256(w))

    def test_missing_and_non_image_wallpapers_are_skipped(self):
        auto.set_auto(True, self.env)
        self.assertTrue(self.sync().startswith("skipped"))  # no cache files at all
        self.point_at(self.home / "gone.png")
        self.assertTrue(self.sync().startswith("skipped"))
        txt = self.home / "wall.png"
        txt.write_text("not an image")
        self.point_at(txt)
        self.assertTrue(self.sync().startswith("skipped"))
        (self.cache / "current_wallpaper").write_text("\n")
        self.assertTrue(self.sync().startswith("skipped"))
        self.assertEqual(self.matugen_calls, [])
        self.assertIsNone(self.current())

    def test_matugen_failure_keeps_the_old_theme(self):
        auto.set_auto(True, self.env)
        self.point_at(self.image())
        self.sync()
        before = self.current()
        self.point_at(self.image("other.png", b"zzz"))

        def failing(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, "", "boom")

        with self.assertRaises(ThemeError):
            auto.sync(self.env, run_hooks=False, matugen_runner=failing, which=WHICH)
        self.assertEqual(self.current(), before)


class FrameFallback(Base):
    def test_gif_and_video_derive_from_the_frame(self):
        auto.set_auto(True, self.env)
        frame = self.cache / "wallpaper_frame.png"
        frame.write_bytes(PNG + b"frame")
        for kind in ("gif", "video"):
            self.matugen_calls.clear()
            self.point_at(self.home / "live.mp4", kind)  # the video itself is not an image
            (self.home / "live.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
            shutil.rmtree(self.tmp / "state", ignore_errors=True)  # a fresh theme, so the frame is applied
            auto.set_auto(True, self.env)
            self.assertTrue(self.sync().startswith("applied "), kind)
            self.assertEqual(self.matugen_calls[0][2], str(frame))
            self.assertEqual(self.current()["source"]["wallpaper"], str(frame))

    def test_video_without_a_frame_is_skipped(self):
        auto.set_auto(True, self.env)
        self.point_at(self.image(), "video")  # a real image, but the type says use the frame
        self.assertTrue(self.sync().startswith("skipped"))
        self.assertEqual(self.matugen_calls, [])


class Cli(Base):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out), \
             contextlib.redirect_stderr(err), \
             mock.patch.object(matugen, "run", side_effect=lambda img, **kw: json.loads(self.fixture)), \
             mock.patch.object(hooks, "run_hooks", return_value=[]), \
             mock.patch.object(hooks, "running_pids", return_value={}):
            code = cli.main(list(argv))
        return code, out.getvalue().strip(), err.getvalue()

    def test_auto_on_off_status_and_sync_lines(self):
        self.point_at(self.image())
        self.assertEqual(self.run_cli("auto", "status")[1], "off")
        code, out, _ = self.run_cli("sync")
        self.assertEqual((code, out.split(":")[0]), (0, "skipped"))
        self.assertEqual(self.run_cli("auto", "on")[0], 0)
        self.assertEqual(self.run_cli("auto", "status")[1], "on")
        self.assertTrue(self.run_cli("sync")[1].startswith("applied "))
        self.assertEqual(self.run_cli("sync"), (0, "unchanged", ""))
        self.run_cli("auto", "off")
        self.assertEqual(self.run_cli("auto", "status")[1], "off")
        self.assertTrue(self.run_cli("sync")[1].startswith("skipped"))

    def test_sync_error_exits_2_with_a_message(self):
        self.run_cli("auto", "on")
        self.point_at(self.image())
        with mock.patch.object(engine, "apply_theme", side_effect=ThemeError("matugen failed (1): boom")):
            code, out, err = self.run_cli("sync")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("matugen failed", err)


class Units(unittest.TestCase):
    D = Path(__file__).resolve().parents[1] / "systemd"

    def test_path_unit_watches_both_files_with_a_trigger_limit(self):
        t = (self.D / "seclegion-theme-sync.path").read_text()
        self.assertIn("PathChanged=%h/.cache/current_wallpaper\n", t)
        self.assertIn("PathChanged=%h/.cache/wallpaper_frame.png\n", t)
        self.assertIn("TriggerLimitIntervalSec=10\n", t)
        # REUSE-IgnoreStart
        self.assertTrue(t.startswith("# SPDX-License-Identifier: MIT\n"))
        # REUSE-IgnoreEnd

    def test_service_is_a_debounced_oneshot_running_sync(self):
        t = (self.D / "seclegion-theme-sync.service").read_text()
        self.assertIn("Type=oneshot\n", t)
        self.assertIn("ExecStartPre=/usr/bin/sleep 1\n", t)
        self.assertRegex(t, r"(?m)^ExecStart=.* sync$")
        # REUSE-IgnoreStart
        self.assertTrue(t.startswith("# SPDX-License-Identifier: MIT\n"))
        # REUSE-IgnoreEnd


if __name__ == "__main__":
    unittest.main()
