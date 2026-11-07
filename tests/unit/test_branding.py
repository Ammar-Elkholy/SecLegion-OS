# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tools/check-branding and the branding rule, without a VM."""

import subprocess
import sys

import pytest

import branding
import evidence
from tests.unit.conftest import REPO

TOOL = f"{REPO}/tools/check-branding"


def scan_file(tmp_path, text, *extra):
    path = tmp_path / "serial.log"
    path.write_text(text)
    return subprocess.run([sys.executable, TOOL, "--scan-file", str(path), *extra],
                          capture_output=True, text=True, check=False)


def test_clean_boot_text_is_branding_ok(tmp_path):
    text = "Install SecLegion OS\nSecLegion OS 7.2.9-arch1-1 (ttyS0)\narchisobasedir=seclegion\n"
    done = scan_file(tmp_path, text)
    assert done.returncode == 0 and done.stdout.strip() == "branding-ok"


@pytest.mark.parametrize("planted", ["Arch Linux", "archlinux", "ARCH LINUX", "Welcome to arch!"])
def test_planted_string_makes_it_print_branding_fail(tmp_path, planted):
    done = scan_file(tmp_path, f"boot ok\n{planted}\nlogin:\n")
    assert done.returncode == 1 and done.stdout.startswith("branding-FAIL")
    assert scan_file(tmp_path, "boot ok\n", "--plant", planted).stdout.startswith("branding-FAIL")


def test_ansi_around_a_hit_does_not_hide_it():
    assert branding.scan("\x1b[1mArch Linux\x1b[0m")


def test_a_pass_whose_serial_log_shows_arch_is_rejected(tmp_path):
    (tmp_path / "serial.log").write_text(
        "Install SecLegion OS\nSECLEGION-MODE=install\nWelcome to Arch Linux\nseclegion login:\n")
    problems = evidence.check_serial(str(tmp_path), {
        "test_id": "M1-branding", "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS["M1-branding"],
        "artifacts": {"serial.log": "x"}})
    assert problems and "forbidden" in problems[0]


@pytest.mark.parametrize("text,hit", [
    ("Arch Linux", True), ("archlinux", True), ("arch_linux", True),
    ("arch=('x86_64')", False), ("ID_LIKE=arch", False), ("step arch-chroot /mnt", False),
    ('source = "arch-extra"', False),
])
def test_name_rule_for_installed_files(text, hit):
    """D-BR-2: on installed files only the product name counts; technical uses of `arch` stay."""
    assert bool(branding.NAME_RE.search(text)) is hit


# --- logo sizes: a 64 px logo upscaled in the installer was blurry ---

BRANDING = f"{REPO}/desktop/branding"


def png_width(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR", path
    return int.from_bytes(head[16:20], "big")


def test_logo_files_are_sharp():
    import glob

    files = sorted(glob.glob(f"{BRANDING}/seclegion-logo*.png"))
    assert len(files) >= 6, files
    for f in files:
        if f.endswith("seclegion-logo-64.png"):
            assert png_width(f) == 64  # the explicit small size
        else:
            assert png_width(f) >= 128, f


def test_installer_sidebar_picks_a_logo_of_at_least_512():
    import ast

    tree = ast.parse(open(f"{REPO}/installer/ui/gtk/sidebar.py").read())
    names = next(ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and n.targets[0].id == "LOGO_FILES")
    # the first choice is what gets drawn when it exists
    assert png_width(f"{BRANDING}/{names[0]}") >= 512
