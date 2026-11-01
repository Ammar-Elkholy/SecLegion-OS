# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Tier-1 catalog: batch 1 entries are valid and loopback-only; lint rejects bad entries; CLI."""

import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "catalog"
TOOL = REPO / "tools" / "seclegion-tools"

BATCH1 = {
    "nmap": "arch-extra",
    "masscan": "arch-extra",
    "wireshark-cli": "arch-extra",
    "tcpdump": "arch-extra",
    "netcat": "arch-extra",
    "socat": "arch-extra",
    "nikto": "arch-extra",
    "gobuster": "arch-extra",
    "ffuf": "seclegion",
    "sqlmap": "arch-extra",
}


def _load_cli():
    loader = importlib.machinery.SourceFileLoader("seclegion_tools", str(TOOL))
    spec = importlib.util.spec_from_loader("seclegion_tools", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


st = _load_cli()
ENTRIES = {e["name"]: e for _, e in st.load_catalog(CATALOG)[0]}


def good(**over):
    entry = copy.deepcopy(ENTRIES["socat"])
    entry.update(over)
    return entry


# ---- batch 1 ---------------------------------------------------------------------------


def test_batch1_catalog_has_no_lint_errors():
    assert st.lint_catalog(CATALOG) == []


def test_batch1_entries_present_with_expected_source():
    assert {n: ENTRIES[n]["source"] for n in BATCH1} == BATCH1


@pytest.mark.parametrize("name", sorted(BATCH1))
def test_batch1_entry_valid_and_safe_test_loopback_only(name):
    entry = ENTRIES[name]
    assert st.lint_entry(entry) == []
    assert entry["needs_internet"] is False
    assert isinstance(entry["safe_test"], list)


def test_batch1_package_names_not_aliases():
    assert ENTRIES["netcat"]["package"] == "openbsd-netcat"
    assert ENTRIES["wireshark-cli"]["package"] == "wireshark-cli"


# ---- negative lint (G63) ---------------------------------------------------------------


def test_catalog_lint_good_entry_passes():
    assert st.lint_entry(good()) == []


def test_catalog_lint_rejects_missing_safe_test():
    entry = good()
    del entry["safe_test"]
    assert any("missing field 'safe_test'" in e for e in st.lint_entry(entry))


def test_catalog_lint_rejects_external_ip():
    errs = st.lint_entry(good(safe_test=["socat", "-V", "8.8.8.8"]))
    assert any("not loopback" in e for e in errs)


def test_catalog_lint_rejects_cidr_10_0_0_0_8():
    errs = st.lint_entry(good(name="nmap", safe_test=["nmap", "-sT", "10.0.0.0/8"]))
    assert any("must be exactly 127.0.0.1" in e for e in errs)


def test_catalog_lint_rejects_shell_string():
    errs = st.lint_entry(good(safe_test="socat -V; curl http://evil.example"))
    assert any("shell string" in e for e in errs)


def test_catalog_lint_rejects_non_arch_source():
    errs = st.lint_entry(good(source="aur"))
    assert any("source 'aur'" in e for e in errs)


def test_catalog_lint_seclegion_source_allowed():
    assert st.lint_entry(good(source="seclegion")) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["curl", "https://example.com/"],
        ["curl", "http://localhost:80/", "--proxy=203.0.113.9:3128"],
        ["ping", "example.org"],
        ["tcpdump", "-i", "eth0", "-c", "1"],
        ["nmap", "-sT", "127.0.0.1-5"],
        ["nmap", "-sT", "127.*"],
        ["masscan", "127.0.0.0/24", "-p1"],
        ["nmap", "-iL", "targets.txt"],
        ["sh", "-c", "true"],
        ["socat", "-V", "::2"],
    ],
)
def test_catalog_lint_rejects_more_unsafe_argv(argv):
    assert st.lint_entry(good(safe_test=argv)) != []


@pytest.mark.parametrize(
    "argv",
    [
        ["curl", "http://localhost:8080/"],
        ["curl", "-s", "http://[::1]:8080/x"],
        ["tcpdump", "-i", "lo", "-c", "1"],
        ["nmap", "-sT", "-p", "1", "127.0.0.1"],
        ["ncat", "-z", "::1", "80"],
    ],
)
def test_catalog_lint_accepts_loopback_argv(argv):
    assert st.lint_entry(good(safe_test=argv)) == []


def test_catalog_lint_rejects_needs_internet_and_long_timeout():
    errs = st.lint_entry(good(needs_internet=True, safe_test_timeout=60))
    assert any("needs_internet" in e for e in errs)
    assert any("safe_test_timeout" in e for e in errs)


def test_catalog_lint_duplicate_names_across_files(tmp_path):
    for fname in ("a.toml", "b.toml"):
        (tmp_path / fname).write_text((CATALOG / "web.toml").read_text())
    errs = st.lint_catalog(tmp_path)
    assert any("duplicate name" in e for e in errs)


def test_catalog_lint_empty_directory(tmp_path):
    assert st.lint_catalog(tmp_path)


# ---- CLI -------------------------------------------------------------------------------


@pytest.fixture
def fake_pacman(monkeypatch):
    have = {"socat": "1.8-1", "nmap": "7.9-1"}
    monkeypatch.setattr(st, "installed_version", lambda pkg: have.get(pkg))
    return have


def test_cli_lint_ok(capsys):
    assert st.main(["lint"]) == 0
    assert "catalog ok" in capsys.readouterr().out


def test_cli_list_json_status_and_category(fake_pacman, capsys):
    assert st.main(["list", "--json", "--category", "network"]) == 0
    rows = {r["name"]: r for r in json.loads(capsys.readouterr().out)}
    assert set(rows) == {"wireshark-cli", "tcpdump", "netcat", "socat"}
    assert rows["socat"]["status"] == "installed"
    assert rows["socat"]["version"] == "1.8-1"
    assert rows["tcpdump"]["status"] == "missing"


def test_cli_info(fake_pacman, capsys):
    assert st.main(["info", "socat"]) == 0
    out = capsys.readouterr().out
    assert "package: socat" in out
    assert "version: 1.8-1" in out
    assert st.main(["info", "nope"]) == 2


def test_cli_test_all_skips_missing_and_passes(fake_pacman, monkeypatch, capsys):
    monkeypatch.setattr(st, "run_safe_test", lambda e: ("PASS", ""))
    assert st.main(["test", "--all"]) == 0
    out = capsys.readouterr().out
    assert "PASS socat" in out
    assert "SKIP tcpdump" in out


def test_cli_test_failure_exits_nonzero(fake_pacman, monkeypatch, capsys):
    monkeypatch.setattr(st, "run_safe_test", lambda e: ("FAIL", "boom"))
    assert st.main(["test", "--all"]) == 1
    assert "FAIL socat: boom" in capsys.readouterr().out


def test_cli_test_named_missing_tool(fake_pacman, capsys):
    assert st.main(["test", "tcpdump"]) == 3
    assert "SKIP tcpdump" in capsys.readouterr().out


def test_run_safe_test_checks_output_and_exit():
    entry = good(safe_test=["python3", "-c", "print('hello'); raise SystemExit(1)"])
    assert st.run_safe_test(entry)[0] == "FAIL"
    entry["safe_test_exit"] = 1
    entry["safe_test_expect"] = "hello"
    assert st.run_safe_test(entry)[0] == "PASS"
    entry["safe_test_expect"] = "absent"
    assert st.run_safe_test(entry)[0] == "FAIL"
