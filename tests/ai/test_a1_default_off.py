# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G66 ai_default_off: the package leaves the AI runtime off, loopback-only, with no models."""

import io
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ai" / "cli"))
import seclegion_ai  # noqa: E402

PKGBUILD = (REPO / "pkgs/seclegion-ai/PKGBUILD").read_text()
DROPIN = (REPO / "ai/runtime/10-seclegion.conf").read_text()


def test_ai_default_off_package_ships_no_enabled_unit_or_wants_link():
    assert not re.search(r"\.wants|multi-user\.target|WantedBy|systemctl\s+enable|preset", PKGBUILD)
    assert "[Install]" not in DROPIN
    shipped = [p for p in (REPO / "ai").rglob("*") if p.is_file()]
    assert not [p for p in shipped if p.suffix == ".service" or ".wants" in p.parts]
    assert "ollama" not in re.search(r"^depends=\((.*?)\)", PKGBUILD, re.M | re.S).group(1)
    assert "optdepends=('ollama" in PKGBUILD


def test_ai_default_off_unit_binds_loopback_only():
    hosts = re.findall(r"OLLAMA_HOST=(\S+)", DROPIN)
    assert hosts == ["127.0.0.1:11434"]
    assert "0.0.0.0" not in DROPIN and "::" not in DROPIN
    assert "OLLAMA_NOPRUNE=1" in DROPIN and "OLLAMA_NO_CLOUD=1" in DROPIN


def test_ai_default_off_catalog_ships_no_model_files():
    # .desktop: AI Center launcher (A2); .md: aichat role files (A3)
    allowed = {".toml", ".py", ".conf", ".desktop", ".md"}
    files = [p for p in (REPO / "ai").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    # the only suffix-less file is the AI Center launcher script
    assert {p.suffix for p in files if p != REPO / "ai/center/bin/seclegion-ai-center"} <= allowed
    pkg = REPO / "pkgs/seclegion-ai"
    assert not [p for p in pkg.iterdir() if p.suffix in {".gguf", ".bin", ".safetensors"}]
    assert "gguf" not in (pkg / "source.list").read_text()


def test_ai_default_off_status_reports_disabled():
    def runner(argv):
        return {"systemctl": (1, "disabled\n"), "pacman": (1, ""), "ss": (0, "")}[argv[0]]

    out = io.StringIO()
    assert seclegion_ai.main(["status"], runner=runner, out=out) == 0
    text = out.getvalue()
    assert "AI runtime: disabled" in text
    assert "listener on 127.0.0.1:11434: no" in text
    assert "not installed" in text


def test_ai_default_off_status_only_reads():
    calls = []

    def runner(argv):
        calls.append(argv)
        return 1, ""

    seclegion_ai.main(["status"], runner=runner, out=io.StringIO())
    reads = (["systemctl", "is-enabled"], ["pacman", "-Q"])
    assert calls and all(a[:2] in reads or a[0] == "ss" for a in calls)


def test_ai_default_off_catalog_parses():
    data = tomllib.loads((REPO / "ai/catalog.toml").read_text())
    assert data["model"]
