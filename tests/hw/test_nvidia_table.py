# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G15/G16: hw/tools/check-nvidia-table against a synthetic supportedchips.html and a planted edit."""

import hashlib
import subprocess
import sys

import pytest
from conftest import HW, VENDOR_HTML

TOOL = HW / "tools" / "check-nvidia-table"
SYNTH_HTML = HW / "fixtures/nvidia/supportedchips-synthetic.html"
SYNTH_TABLE = HW / "fixtures/nvidia/table-synthetic.toml"


def run(*args):
    cmd = [sys.executable, "-I", str(TOOL), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def synthetic(table=SYNTH_TABLE, *extra):
    return run("--table", str(table), "--sha256-file", "-", *extra, str(SYNTH_HTML))


def test_supportedchips_parser_and_table_agree_on_synthetic_fixture():
    result = synthetic()
    assert result.returncode == 0, result.stdout + result.stderr
    # base IDs only: the OEM sub-rows (1F9D 1043 128D) fold into 1F9D
    assert "Current=3" in result.stdout and "legacy_580.xx=2" in result.stdout


def test_supportedchips_emit_roundtrips(tmp_path):
    emitted = run("--emit", str(SYNTH_HTML))
    assert emitted.returncode == 0
    table = tmp_path / "emitted.toml"
    table.write_text(emitted.stdout)
    assert synthetic(table).returncode == 0


@pytest.mark.parametrize(
    ("old", "new", "expect"),
    [
        ('"1F9D", "28E0"', '"1F9D", "28E1"', "28E0 in the HTML, missing"),  # edited ID
        ('"1F82", ', "", "1F82 in the HTML, missing"),  # dropped ID
        ('ids = ["1180"]', 'ids = ["1180", "1181"]', "1181 in the table, not in the HTML"),  # added ID
    ],
)
def test_planted_table_edit_fails(tmp_path, old, new, expect):
    text = SYNTH_TABLE.read_text()
    assert old in text
    bad = tmp_path / "table.toml"
    bad.write_text(text.replace(old, new))
    result = synthetic(bad)
    assert result.returncode == 1
    assert expect in result.stdout


def test_planted_table_moved_to_wrong_section_fails(tmp_path):
    bad = tmp_path / "table.toml"
    bad.write_text(SYNTH_TABLE.read_text().replace('ids = ["1180"]', 'ids = []'))
    assert synthetic(bad).returncode == 1


def test_planted_table_missing_section_fails(tmp_path):
    text = SYNTH_TABLE.read_text()
    bad = tmp_path / "table.toml"
    bad.write_text(text[: text.index('[[section]]\nanchor = "legacy_470.xx"')])
    result = synthetic(bad)
    assert result.returncode == 1 and "legacy_470.xx: in the HTML but not in the table" in result.stdout


def test_sha256_pin(tmp_path):
    pin = tmp_path / "pin"
    args = ["--table", str(SYNTH_TABLE), "--sha256-file", str(pin), str(SYNTH_HTML)]
    pin.write_text("UNPINNED\n# note\n")
    assert run(*args).returncode == 0
    assert run("--require-pinned", *args).returncode == 1
    pin.write_text(hashlib.sha256(SYNTH_HTML.read_bytes()).hexdigest() + "\n")
    assert run("--require-pinned", *args).returncode == 0
    pin.write_text("0" * 64 + "\n")
    assert run(*args).returncode == 1


def test_html_without_tables_is_a_usage_error(tmp_path):
    empty = tmp_path / "e.html"
    empty.write_text("<html></html>")
    assert run("--sha256-file", "-", str(empty)).returncode == 2


def test_committed_pin_file_is_unpinned_or_hex():
    word = (HW / "nvidia-html.sha256").read_text().split("#")[0].split()[0]
    assert word == "UNPINNED" or len(word) == 64


@pytest.mark.skipif(not VENDOR_HTML.is_file(), reason="nvidia-utils not installed")
def test_committed_table_agrees_with_installed_vendor_html():
    result = run("--sha256-file", "-", str(VENDOR_HTML))
    assert result.returncode == 0, result.stdout
