# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Tier-1 catalog: batch 2 entries (G64) are valid and loopback-only; generated docs (G65)."""

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "catalog"
TOOL = REPO / "tools" / "seclegion-tools"
DOCS = REPO / "docs" / "security-tools.md"

BATCH2 = {
    "john": "arch-extra",
    "hashcat": "arch-extra",
    "hydra": "arch-extra",
    "responder": "seclegion",
    "impacket": "arch-extra",
    "aircrack-ng": "arch-extra",
    "exploitdb": "arch-extra",
}


def _load_cli():
    loader = importlib.machinery.SourceFileLoader("seclegion_tools", str(TOOL))
    spec = importlib.util.spec_from_loader("seclegion_tools", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


st = _load_cli()
ENTRIES = {e["name"]: e for _, e in st.load_catalog(CATALOG)[0]}


# ---- G64: batch 2 lint ------------------------------------------------------------------


def test_batch2_catalog_has_no_lint_errors():
    assert st.lint_catalog(CATALOG) == []


def test_batch2_entries_present_with_expected_source():
    assert {n: ENTRIES[n]["source"] for n in BATCH2} == BATCH2


@pytest.mark.parametrize("name", sorted(BATCH2))
def test_batch2_entry_valid_and_safe_test_loopback_only(name):
    entry = ENTRIES[name]
    assert st.lint_entry(entry) == []
    assert entry["needs_internet"] is False
    assert isinstance(entry["safe_test"], list)


def test_hydra_safe_test_is_version_help_only_no_attack():
    """hydra's safe test must only print the banner/help, never a target or module."""
    argv = ENTRIES["hydra"]["safe_test"]
    assert argv == ["hydra", "-h"]
    assert "://" not in " ".join(argv)


def test_hashcat_safe_test_is_version_not_benchmark():
    argv = ENTRIES["hashcat"]["safe_test"]
    assert argv == ["hashcat", "--version"]
    assert "-b" not in argv and "--benchmark" not in argv


def test_aircrack_ng_safe_test_has_no_interface():
    argv = ENTRIES["aircrack-ng"]["safe_test"]
    assert not (set(argv) & st.IFACE_FLAGS)


def test_only_responder_is_batch2_seclegion_source():
    assert ENTRIES["responder"]["source"] == "seclegion"
    assert {n for n in BATCH2 if ENTRIES[n]["source"] == "seclegion"} == {"responder"}


# ---- G65: generated docs ----------------------------------------------------------------


def test_tools_docs_matches_committed_file():
    entries = sorted(
        [e for _, e in st.load_catalog(CATALOG)[0]], key=lambda e: (e["category"], e["name"])
    )
    generated = st.render_docs(entries)
    assert generated == DOCS.read_text(encoding="utf-8")


def test_cli_docs_check_passes_on_committed_file(capsys):
    assert st.main(["docs", "--check", str(DOCS)]) == 0


def test_cli_docs_check_fails_on_modified_copy(tmp_path, capsys):
    stale = tmp_path / "security-tools.md"
    stale.write_text(DOCS.read_text(encoding="utf-8") + "\nstale\n", encoding="utf-8")
    assert st.main(["docs", "--check", str(stale)]) == 1
    assert "stale" in capsys.readouterr().err


def test_cli_docs_prints_markdown(capsys):
    assert st.main(["docs"]) == 0
    out = capsys.readouterr().out
    assert "do not hand-edit" in out
    assert "## passwords" in out
    assert "john" in out
