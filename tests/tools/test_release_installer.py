# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Release mode (SECLEGION_RELEASE=1 or /etc/seclegion/release) disables DEV-only installer behaviour."""

import subprocess
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
INSTALLD = REPO / "installer" / "installd"
sys.path.insert(0, str(INSTALLD))
import facts  # noqa: E402
import release  # noqa: E402

NOMARK = "/nonexistent/seclegion-release-marker"


def test_release_key_mode_detection(tmp_path):
    assert release.is_release({"SECLEGION_RELEASE": "1"}, NOMARK)
    assert not release.is_release({}, NOMARK)
    assert not release.is_release({"SECLEGION_RELEASE": "0"}, NOMARK)
    marker = tmp_path / "release"
    marker.write_text("")
    assert release.is_release({}, str(marker))


def test_release_key_dev_switches_refused_only_in_release():
    env = {"SECLEGION_POST_SKIP_MISSING": "1"}
    assert release.dev_violations(True, True, env, NOMARK) == []
    rel = dict(env, SECLEGION_RELEASE="1")
    assert release.dev_violations(True, True, rel, NOMARK) == [
        "--force-install-mode",
        "--dev",
        "SECLEGION_POST_SKIP_MISSING",
    ]
    assert release.dev_violations(env={"SECLEGION_RELEASE": "1"}, marker=NOMARK) == []


def fake_gather(monkeypatch, env):
    for k in ("SECLEGION_RELEASE",):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(release, "MARKER", NOMARK)
    monkeypatch.setattr(
        release,
        "is_release",
        lambda e=None, marker=NOMARK: release.os.environ.get("SECLEGION_RELEASE") == "1",
    )
    run = mock.Mock(return_value=mock.Mock(stdout='{"blockdevices": []}'))
    monkeypatch.setattr(facts.subprocess, "run", run)
    return facts.gather(install_mode=True)


def test_release_key_gather_dev_build_default_dev(monkeypatch):
    assert fake_gather(monkeypatch, {})["dev_build"] is True


def test_release_key_gather_dev_build_false_in_release_even_if_asked(monkeypatch):
    assert fake_gather(monkeypatch, {"SECLEGION_RELEASE": "1"})["dev_build"] is False
    assert facts.gather(install_mode=True, dev_build=True)["dev_build"] is False


def run_tool(name, *args, release_env=True):
    env = {"PATH": "/usr/bin:/bin"}
    if release_env:
        env["SECLEGION_RELEASE"] = "1"
    return subprocess.run(
        [sys.executable, str(INSTALLD / name), *args], capture_output=True, text=True, env=env
    )


def test_release_key_install_refuses_dev_switches():
    r = run_tool("seclegion-install", "--answers", "/dev/null", "--force-install-mode")
    assert r.returncode == 2 and "--force-install-mode" in r.stderr
    r = run_tool("seclegion-install", "--answers", "/dev/null", "--dev")
    assert r.returncode == 2 and "--dev" in r.stderr


def test_release_key_install_refuses_made_up_facts():
    # the kiosk user runs seclegion-install as root (pkexec): --facts would defeat the disk guards
    assert release.dev_violations(env={"SECLEGION_RELEASE": "1"}, marker=NOMARK, facts=True) == ["--facts"]
    assert release.dev_violations(env={}, marker=NOMARK, facts=True) == []
    r = run_tool("seclegion-install", "--answers", "/dev/null", "--facts", "/dev/null")
    assert r.returncode == 2 and "--facts" in r.stderr


def test_release_key_configure_refuses_force_install_mode():
    r = run_tool("seclegion-configure", "--gather-facts", "--force-install-mode", "--out", "/dev/null")
    assert r.returncode == 2 and "refused" in r.stderr


def test_release_key_post_refuses_skip_missing():
    env = {"PATH": "/usr/bin:/bin", "SECLEGION_RELEASE": "1", "SECLEGION_POST_SKIP_MISSING": "1"}
    r = subprocess.run(
        [sys.executable, str(INSTALLD / "seclegion-post"), "--root", "/nonexistent", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 2 and "SECLEGION_POST_SKIP_MISSING" in r.stderr
