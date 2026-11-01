# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G16b: seclegion-hwreport output carries no serial, MAC, UUID, hostname or user name."""

import ast
import json
import re

import pytest
from conftest import FIXTURES, HW, PKG
from seclegion_hw import report

DECOY_FILES = [
    "sys/class/dmi/id/product_serial",
    "sys/class/dmi/id/product_uuid",
    "sys/class/dmi/id/board_serial",
    "sys/class/dmi/id/chassis_serial",
    "proc/sys/kernel/hostname",
    "etc/machine-id",
    "sys/class/net/wlan0/address",
]
MAC = re.compile(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", re.IGNORECASE)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


@pytest.mark.parametrize("name", FIXTURES)
def test_redact_report_has_no_identifiers(name):
    root = HW / "fixtures" / name / "root"
    text = json.dumps(report.build_report(root, HW))
    for rel in DECOY_FILES:
        value = (root / rel).read_text().strip()
        assert value and value not in text, f"{rel} leaked"
    assert not MAC.search(text) and not UUID.search(text)
    assert "alice" not in text


def test_redact_scrubs_identifiers_smuggled_into_allowed_fields(fixture_root):
    root = fixture_root("intel")
    dmi = root / "sys/class/dmi/id"
    (dmi / "product_name").write_text("XPS aa:bb:cc:dd:ee:ff 4c4c4544-0042-3510-8051-b9c04f4a4e32\n")
    (dmi / "bios_version").write_text("see /home/alice/notes and SN-9F3A77C1D2\n")
    text = json.dumps(report.build_report(root, HW))
    for leaked in ("aa:bb:cc:dd:ee:ff", "4c4c4544", "/home/alice", "SN-9F3A77C1D2"):
        assert leaked not in text
    assert report.REDACTED in text


def test_redact_report_keeps_the_useful_parts():
    data = report.build_report(HW / "fixtures/intel-rtx4060/root", HW)
    assert data["dmi"]["product_name"] == "82XV"
    assert {d["pci_id"] for d in data["pci"]} >= {"10de:28e0", "8086:a7a8"}
    assert data["plan"]["packages"] and data["cpu"]["vendor"] == "GenuineIntel"


def test_redact_cli_writes_only_the_named_file(tmp_path, capsys):
    out = tmp_path / "report.json"
    args = ["--root", str(HW / "fixtures/vm/root"), "--hw-dir", str(HW), "-o", str(out)]
    assert report.main(args) == 0
    assert capsys.readouterr().out == ""
    assert json.loads(out.read_text())["schema"] == report.REPORT_SCHEMA
    assert report.main(args) == 2  # refuses to overwrite
    assert report.main([*args, "--force"]) == 0
    assert report.main(args[:-2]) == 0 and json.loads(capsys.readouterr().out)["notice"]


def test_hwreport_has_no_network_code():
    banned = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "requests", "asyncio", "subprocess"}
    for path in (PKG / "python/seclegion_hw").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in banned, f"{path.name} imports {name}"


def test_launchers_use_isolated_python_and_the_libdir():
    for name in ("seclegion-hwdetect", "seclegion-hwreport"):
        text = (PKG / "bin" / name).read_text()
        assert text.startswith("#!/usr/bin/python3 -I\n")
        assert "/usr/lib/seclegion/python" in text
