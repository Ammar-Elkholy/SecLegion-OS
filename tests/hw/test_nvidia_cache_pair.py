# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""sl_check_nvidia_pair: the ISO build refuses cached NVIDIA modules of another driver release."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def check(tmp_path, lines):
    f = tmp_path / "cache.resolved"
    f.write_text("\n".join(lines) + "\n")
    lib = REPO / "tools" / "lib" / "seclegion-iso.sh"
    return subprocess.run(["bash", "-c", f'source "{lib}" && sl_check_nvidia_pair "{f}"'],
                          capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})


def test_nvidia_kernel_pair_cache_match_passes(tmp_path):
    r = check(tmp_path, ["extra nvidia-open 615.78.08-3 u", "extra nvidia-open-lts 1:615.78.08-2 u",
                         "extra nvidia-utils 615.78.08-1 u", "core linux 7.2.11.arch1-1 u"])
    assert r.returncode == 0, r.stderr


def test_nvidia_kernel_pair_cache_mismatch_is_refused(tmp_path):
    r = check(tmp_path, ["extra nvidia-open 615.78.08-3 u", "extra nvidia-open-lts 610.10.01-1 u",
                         "extra nvidia-utils 615.78.08-1 u"])
    assert r.returncode == 1 and "nvidia-open-lts 610.10.01" in r.stderr


def test_nvidia_kernel_pair_check_runs_in_the_cache_build():
    text = (REPO / "tools" / "container-build.sh").read_text()
    assert "sl_check_nvidia_pair /work/cache.resolved" in text
