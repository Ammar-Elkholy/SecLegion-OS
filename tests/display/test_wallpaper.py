# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""desktop/display/seclegion-wallpaper (owner issue 16) against an awww stub, and the two places
seclegion-displayd runs it (start: every output; monitoradded: that output). Nothing reaches the
live awww: SL_AWWW always points at the stub, or PATH holds no awww at all."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from test_displayd import AWWW, Rig, mon, wait_for

HELPER = Path(__file__).resolve().parents[2] / "desktop/display/seclegion-wallpaper"


def img(args):
    """The image an `awww img ...` call paints (the argument before --transition-type)."""
    return args[args.index("--transition-type") - 1]


class World:
    def __init__(self, d):
        self.d = d
        (d / "awww.py").write_text(AWWW)
        self.home = d / "home"
        (self.home / ".cache").mkdir(parents=True)
        self.state = d / "state"
        self.default = d / "default.png"
        self.default.write_bytes(b"png")

    def image(self, name):
        p = self.d / name
        p.write_bytes(b"png")
        return p

    def cache(self, path, kind=None):
        (self.home / ".cache/current_wallpaper").write_text(f"{path}\n")
        if kind:
            (self.home / ".cache/current_wallpaper_type").write_text(f"{kind}\n")

    def theme(self, path):
        cur = self.state / "seclegion/theme/current"
        cur.mkdir(parents=True, exist_ok=True)
        (cur / "wallpaper").unlink(missing_ok=True)
        os.symlink(path, cur / "wallpaper")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HYPRLAND_", "GIT_", "SL_", "XDG_STATE"))}
        env.update(SL_AWWW=shlex.join([sys.executable, str(self.d / "awww.py"), str(self.d)]),
                   SL_HOME=str(self.home), XDG_STATE_HOME=str(self.state),
                   SL_DEFAULT_WALLPAPER=str(self.default))
        env.update(extra)
        return env

    def run(self, *args, **extra):
        (self.d / "awww.log").unlink(missing_ok=True)
        return subprocess.run([sys.executable, "-I", str(HELPER), *args], env=self.env(**extra),
                              capture_output=True, text=True, timeout=30)

    def calls(self):
        p = self.d / "awww.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_wallpaper_order(w):
    cached, themed = w.image("cached.png"), w.image("themed.png")
    w.cache(cached)
    w.theme(themed)
    assert w.run().returncode == 0 and img(w.calls()[0]) == str(cached)
    cached.unlink()   # the cache names a file that is gone: the theme's wallpaper
    assert w.run().returncode == 0 and img(w.calls()[0]) == str(themed)
    themed.unlink()   # the theme link dangles: the shipped default
    assert w.run().returncode == 0 and img(w.calls()[0]) == str(w.default)
    w.default.unlink()   # nothing at all: no awww call, still exit 0
    r = w.run()
    assert r.returncode == 0 and w.calls() == [] and "no wallpaper image" in r.stderr


def test_wallpaper_per_output_argv(w):
    assert w.run("--output", "HDMI-A-1").returncode == 0
    assert w.calls() == [["img", "--outputs", "HDMI-A-1", str(w.default), "--transition-type", "none"]]
    assert w.run().returncode == 0
    assert w.calls() == [["img", str(w.default), "--transition-type", "none"]]   # every output


def test_wallpaper_retries(w):
    (w.d / "awww-fail").write_text("2")   # the daemon is not up for the first two tries
    r = w.run("--output", "DP-1")
    assert r.returncode == 0 and len(w.calls()) == 3, r.stderr
    (w.d / "awww-fail").write_text("99")
    r = w.run("--output", "DP-1", "--tries", "4")
    assert r.returncode == 1 and len(w.calls()) == 4 and "failed 4 times" in r.stderr


def test_wallpaper_video_skipped(w):
    video, themed = w.image("clip.mp4"), w.image("themed.png")
    w.cache(video, kind="video")   # mpvpaper plays it; awww gets the theme's still instead
    w.theme(themed)
    assert w.run().returncode == 0 and img(w.calls()[0]) == str(themed)
    w.cache(w.image("anim.gif"), kind="gif")   # awww plays gifs itself
    assert w.run().returncode == 0 and img(w.calls()[0]) == str(w.d / "anim.gif")


def test_wallpaper_awww_absent(w):
    empty = w.d / "empty-bin"
    empty.mkdir()
    env = w.env(PATH=str(empty))
    del env["SL_AWWW"]
    r = subprocess.run([sys.executable, "-I", str(HELPER), "--output", "HDMI-A-1"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.fixture
def rig(tmp_path):
    rigs = []

    def make(monitors, connectors):
        r = Rig(tmp_path, monitors, [], connectors)
        rigs.append(r)
        return r

    yield make
    for r in rigs:
        r.stop()


def test_wallpaper_on_start_all_outputs(rig):
    r = rig([mon("eDP-1", focused=True), mon("HDMI-A-1")], {"eDP-1": "connected", "HDMI-A-1": "connected"})
    r.start()
    want = ["img", str(r.wallpaper), "--transition-type", "none"]
    assert wait_for(lambda: want in r.awww()), (r.awww(), r.log.read_text())
    assert all("--outputs" not in c for c in r.awww())


def test_wallpaper_on_monitor_added(rig):
    r = rig([mon("eDP-1", focused=True)], {"eDP-1": "connected"})
    r.start()
    assert wait_for(lambda: len(r.awww()) == 1), r.log.read_text()   # the start paint
    r.send("monitoraddedv2>>2,HDMI-A-1,Samsung, Inc. S24")
    want = ["img", "--outputs", "HDMI-A-1", str(r.wallpaper), "--transition-type", "none"]
    assert wait_for(lambda: want in r.awww()), (r.awww(), r.log.read_text())
    assert r.proc.poll() is None   # the event loop kept running
