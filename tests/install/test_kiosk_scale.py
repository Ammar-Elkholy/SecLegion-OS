# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""HiDPI kiosk: scale_for picks the output scale; the helper never fails the kiosk."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import kiosk_scale  # noqa: E402

SCALE = os.path.join(REPO, "iso/profile/airootfs/usr/share/seclegion/kiosk/scale")


@pytest.mark.parametrize("width,want", [(1366, None), (1920, None), (2559, None), (2560, 1.5),
                                        (3000, 1.5), (3840, 2.0), (5120, 2.0)])
def test_scale_for(width, want):
    assert kiosk_scale.scale_for(width) == want


def fake_run(outputs, calls):
    def run(argv, **kw):
        calls.append(argv)
        if "--json" in argv:
            return SimpleNamespace(returncode=0, stdout=json.dumps(outputs))
        return SimpleNamespace(returncode=0, stdout="")
    return run


OUTPUTS = [
    {"name": "HDMI-A-1", "enabled": False, "modes": [{"width": 3840, "current": True}]},
    {"name": "eDP-1", "enabled": True,
     "modes": [{"width": 1920, "current": False}, {"width": 2560, "height": 1600, "current": True}]},
]


def test_main_scales_the_enabled_output():
    calls = []
    assert kiosk_scale.main(fake_run(OUTPUTS, calls)) == 0
    assert calls[-1] == ["wlr-randr", "--output", "eDP-1", "--scale", "1.5"]


def test_main_leaves_a_1080p_panel_alone():
    calls = []
    outs = [{"name": "eDP-1", "enabled": True, "modes": [{"width": 1920, "current": True}]}]
    assert kiosk_scale.main(fake_run(outs, calls)) == 0
    assert len(calls) == 1  # only the --json query


@pytest.mark.parametrize("exc", [FileNotFoundError(), subprocess.TimeoutExpired("x", 1), ValueError()])
def test_main_never_fails(exc):
    def run(argv, **kw):
        raise exc
    assert kiosk_scale.main(run) == 0


def test_main_survives_bad_json():
    def run(argv, **kw):
        return SimpleNamespace(returncode=0, stdout="not json")
    assert kiosk_scale.main(run) == 0


def test_wrapper_execs_the_gui_with_the_same_args():
    text = open(SCALE).read()
    assert text.splitlines()[-1] == 'exec "$@"'
    assert "|| true" in text  # a failing helper cannot stop the kiosk
