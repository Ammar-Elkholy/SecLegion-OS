# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Theme and font packages (plan r14 R3b): pinned upstream sources and shipped licence texts."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.pkgs.test_packages import PKGS, clean_env, words

THEME_PKGS = ["seclegion-themes-graphite", "seclegion-themes-bibata", "seclegion-fonts-figtree"]
# package -> text its shipped licence must contain
LICENCE_TEXT = {
    "seclegion-themes-graphite": "GNU GENERAL PUBLIC LICENSE",
    "seclegion-themes-bibata": "GNU GENERAL PUBLIC LICENSE",
    "seclegion-fonts-figtree": "SIL OPEN FONT LICENSE",
}


def remote_sources(pkg):
    text = (PKGS / pkg / "PKGBUILD").read_text()
    sources = words(text, "source")
    sums = words(text, "sha256sums")
    return text, sources, sums


@pytest.mark.parametrize("pkg", THEME_PKGS)
def test_theme_src_sha(pkg):
    """G13b: every remote source has a real sha256 (no SKIP), one per source."""
    _, sources, sums = remote_sources(pkg)
    remote = [s for s in sources if "://" in s]
    assert remote, "no remote source"
    assert len(sums) == len(sources)
    for src, digest in zip(sources, sums, strict=True):
        if "://" in src:
            assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{src}: sha256 {digest!r}"


@pytest.fixture(scope="session")
def downloaded(tmp_path_factory):
    """The figtree source downloaded once (SRCDEST); the test skips when it cannot be fetched."""
    if shutil.which("makepkg") is None:
        pytest.skip("makepkg is not installed")
    srcdest = tmp_path_factory.mktemp("srcdest")
    work = tmp_path_factory.mktemp("good")
    shutil.copy(PKGS / "seclegion-fonts-figtree" / "PKGBUILD", work)
    r = subprocess.run(["makepkg", "--verifysource", "--nocolor"], cwd=work, capture_output=True,
                       text=True, env=clean_env(SRCDEST=str(srcdest)))
    if r.returncode != 0:
        pytest.skip(f"cannot download or verify the figtree source (offline?): {r.stderr[-300:]}")
    return srcdest


def test_theme_src_sha_mismatch_is_rejected(downloaded, tmp_path):
    """G13b negative: one changed character in the sha256 makes makepkg --verifysource fail."""
    work = tmp_path / "bad"
    work.mkdir()
    text = (PKGS / "seclegion-fonts-figtree" / "PKGBUILD").read_text()
    digest = words(text, "sha256sums")[0]
    flipped = ("1" if digest[0] == "0" else "0") + digest[1:]
    (work / "PKGBUILD").write_text(text.replace(digest, flipped))
    r = subprocess.run(["makepkg", "--verifysource", "--nocolor"], cwd=work, capture_output=True,
                       text=True, env=clean_env(SRCDEST=str(downloaded)))
    assert r.returncode != 0
    assert "FAILED" in r.stdout + r.stderr


@pytest.mark.parametrize("pkg", THEME_PKGS)
def test_theme_licences(pkg):
    """G13c: the built package ships the GPL or OFL text under usr/share/licenses/<pkg>/."""
    repo = os.environ.get("SECLEGION_TEST_REPO")
    if not repo:
        pytest.skip("SECLEGION_TEST_REPO is not set (run tools/build-pkgs first)")
    built = sorted(Path(repo).glob(f"{pkg}-[0-9]*.pkg.tar.zst"))
    assert built, f"{pkg} is not in {repo}"
    listing = subprocess.run(["bsdtar", "-tf", str(built[-1])], capture_output=True, text=True,
                             check=True).stdout.split()
    files = [n for n in listing if n.startswith(f"usr/share/licenses/{pkg}/") and not n.endswith("/")]
    assert files, f"no file under usr/share/licenses/{pkg}/"
    body = subprocess.run(["bsdtar", "-xOf", str(built[-1]), files[0]], capture_output=True,
                          text=True, check=True).stdout
    assert LICENCE_TEXT[pkg] in body.upper()
