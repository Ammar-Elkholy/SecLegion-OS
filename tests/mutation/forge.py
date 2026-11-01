# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Build evidence trees in a throwaway git repo: one honest run, and consistent forgeries.

A forgery here is internally consistent (artifact hashes match, TESTING.md is regenerated),
so only the verifier's outside-world checks (commit, clock, ISO, serial regex) can catch it.
"""

import os
import subprocess
import sys

import evidence
from tests.unit.conftest import REPO

GEN = os.path.join(REPO, "tools", "gen-testing-md")
VERIFY = os.path.join(REPO, "tools", "verify-evidence")
ISO_SHA = "b" * 64
OTHER_SHA = "c" * 64
PATTERNS = list(evidence.CANONICAL_SERIAL_PATTERNS["M0-boot"])
HONEST_SERIAL = "Install SecLegion OS\n[ 1.0 ] boot\nseclegion login: \n"
STAMP = "2026-10-14T20:03:22Z"
COMMIT_DATE = "2026-10-14T20:00:00Z"  # the fixture commit predates STAMP, as a real run's would


def git(root, *args, date=None):
    env = evidence.git_env()
    if date:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = date
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, env=env, check=True)


def make_repo(tmp_path):
    """A fresh repo with one commit, strictly inside tmp_path. Returns (root, head_sha)."""
    root = tmp_path / "repo"
    root.mkdir()
    assert os.path.realpath(root).startswith(os.path.realpath(tmp_path) + os.sep)
    git(root, "init", "-q")
    (root / "README").write_text("x\n")
    git(root, "add", "README")
    git(root, "commit", "-q", "-m", "init", date=COMMIT_DATE)
    return root, git(root, "rev-parse", "HEAD").stdout.strip()


def add_run(root, head, **over):
    """Write one consistent run under root/evidence; `over` overrides record fields.

    Special keys: serial (serial.log text), artifacts (names to hash; default
    ["serial.log"]), sums (iso sha256 to list in out/SHA256SUMS; None = no file).
    """
    serial = over.pop("serial", HONEST_SERIAL)
    names = over.pop("artifacts", ["serial.log"])
    sums = over.pop("sums", ISO_SHA)
    record = {
        "test_id": "M0-boot", "status": "PASS", "class": "AUTO", "commit": head,
        "iso_sha256": ISO_SHA, "env": {"qemu": "x"}, "command": "qemu",
        "expected": "serial matches the patterns", "serial_patterns": PATTERNS,
        "actual": "booted", "exit_code": 0, "timestamp": STAMP,
    }
    record.update(over)
    run_dir = (root / "evidence" / record["test_id"] / record["iso_sha256"]
               / evidence.dir_stamp(str(record["timestamp"])))
    run_dir.mkdir(parents=True)
    (run_dir / "serial.log").write_text(serial)
    (run_dir / "screen.png").write_bytes(b"\x89PNG-ish")
    evidence.write_result(str(root / "evidence"), record, names)
    if sums:
        (root / "out").mkdir(exist_ok=True)
        (root / "out" / "SHA256SUMS").write_text(f"{sums}  archlinux-x86_64.iso\n")
    return run_dir


def regenerate(root):
    subprocess.run([sys.executable, GEN, "--root", str(root)], check=True, capture_output=True)


def verify(root, *extra):
    return subprocess.run([sys.executable, VERIFY, "--root", str(root), *extra],
                          capture_output=True, text=True, check=False)
