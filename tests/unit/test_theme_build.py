# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""iso/grub-theme/build-theme.sh with a fake grub-mkfont (the real one runs in the container).

Pins: the same inputs and SOURCE_DATE_EPOCH give the same sha file, colours come from
desktop/theme/tokens.toml, a bad token fails the build, and no generated binary is tracked.
"""

import os
import shutil
import subprocess

import pytest

from tests.unit.conftest import REPO

INPUTS = ("iso/grub-theme/build-theme.sh", "iso/grub-theme/theme.txt.in",
          "desktop/theme/tokens.toml", "Grub Splash.png")


def shim(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def theme_tree(tmp_path):
    """A copy of just the inputs of build-theme.sh, a fake grub-mkfont and a fake TTF dir."""
    root = tmp_path / "repo"
    for rel in INPUTS:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(REPO, rel), root / rel)
    ttf = tmp_path / "ttf"
    ttf.mkdir()
    for name in ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf"):
        (ttf / name).write_bytes(b"fake ttf " + name.encode())
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim(bindir, "grub-mkfont",
         'while [ $# -gt 0 ]; do case $1 in -s) s=$2; shift;; -o) o=$2; shift;; *) f=$1;; esac; '
         'shift; done; { printf "NAME\\000\\000\\000\\031"; '
         'printf "JetBrains Mono Fake %s\\000" "$s"; cat "$f"; } > "$o"')

    def run(tag, epoch="1700000000"):
        sha = tmp_path / f"{tag}.sha256"
        dest = tmp_path / f"theme-{tag}"
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "SOURCE_DATE_EPOCH": epoch,
               "SECLEGION_TTF_DIR": str(ttf)}
        proc = subprocess.run(["bash", str(root / "iso/grub-theme/build-theme.sh"), str(dest),
                               str(sha)], env=env, capture_output=True, text=True, check=False)
        return proc, dest, sha

    run.root = root
    run.bindir = bindir
    return run


def test_theme_build_is_reproducible_and_covers_every_file(theme_tree):
    one, dest1, sha1 = theme_tree("a")
    two, _dest2, sha2 = theme_tree("b")
    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert sha1.read_bytes() == sha2.read_bytes()
    listed = [line.split("  ", 1)[1] for line in sha1.read_text().splitlines()]
    assert listed == ["background.png", "jetbrains-mono-18.pf2",
                      "jetbrains-mono-bold-28.pf2", "theme.txt"]
    assert (dest1 / "background.png").read_bytes() == (theme_tree.root / "Grub Splash.png").read_bytes()


def test_theme_colours_and_font_names_come_from_the_tokens_and_the_fonts(theme_tree):
    proc, dest, _sha = theme_tree("c")
    assert proc.returncode == 0, proc.stderr
    text = (dest / "theme.txt").read_text()
    assert "@" not in text
    assert 'desktop-color: "#050F0E"' in text and 'selected_item_color = "#00FF88"' in text
    assert 'item_font = "JetBrains Mono Fake 18"' in text
    assert 'font = "JetBrains Mono Fake 28"' in text


def test_the_source_file_mode_does_not_leak_into_the_theme(theme_tree):
    (theme_tree.root / "Grub Splash.png").chmod(0o750)
    proc, dest, _sha = theme_tree("m")
    assert proc.returncode == 0, proc.stderr
    assert (dest / "background.png").stat().st_mode & 0o777 == 0o644


def test_a_changed_token_changes_the_theme_and_its_hash(theme_tree):
    _proc, _dest, before = theme_tree("d")
    tokens = theme_tree.root / "desktop/theme/tokens.toml"
    tokens.write_text(tokens.read_text().replace('accent = "#00FF88"', 'accent = "#112233"', 1))
    proc, dest, after = theme_tree("e")
    assert proc.returncode == 0, proc.stderr
    assert "#112233" in (dest / "theme.txt").read_text()
    assert before.read_bytes() != after.read_bytes()


def test_a_bad_colour_token_fails_the_build(theme_tree):
    tokens = theme_tree.root / "desktop/theme/tokens.toml"
    tokens.write_text(tokens.read_text().replace('bg = "#050F0E"', 'bg = "red"', 1))
    proc, _dest, _sha = theme_tree("f")
    assert proc.returncode == 1 and "not #RRGGBB" in proc.stderr


def test_theme_build_refuses_without_source_date_epoch_or_grub(theme_tree):
    proc, _d, _s = theme_tree("g", epoch="")
    assert proc.returncode != 0
    (theme_tree.bindir / "grub-mkfont").unlink()
    proc, _d, _s = theme_tree("h")
    assert proc.returncode == 1 and "grub-mkfont not found" in proc.stderr


def test_no_generated_theme_binaries_are_tracked():
    out = subprocess.run(["git", "ls-files", "iso/grub-theme"], cwd=REPO, capture_output=True,
                         text=True, check=True, env={"PATH": "/usr/bin:/bin"}).stdout
    assert out.split()  # the sources are there: this is not a vacuous pass
    assert not [f for f in out.split() if f.endswith((".pf2", ".png"))]
