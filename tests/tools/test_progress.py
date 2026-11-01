# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import importlib.machinery
import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    loader = importlib.machinery.SourceFileLoader(
        "seclegion_progress", str(ROOT / "tools/seclegion-progress")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _items():
    return tomllib.loads((ROOT / "docs/progress.toml").read_text())["item"]


def test_progress_file_is_valid():
    items = _items()
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    for i in items:
        assert i["tier"] in ("1.0", "1.1") and i["status"] in ("done", "doing", "todo") and i["weight"] > 0


def test_1_0_done_is_80_and_all_done_is_100():
    mod = _load()
    items = _items()
    v10 = [dict(i, status="done" if i["tier"] == "1.0" else "todo") for i in items]
    assert round(mod.percent(v10), 6) == 80
    assert round(mod.percent([dict(i, status="done") for i in items]), 6) == 100
    assert mod.percent([dict(i, status="todo") for i in items]) == 0


def test_cli_help_and_all():
    tool = Path(__file__).resolve().parents[2] / "tools" / "seclegion-progress"
    h = subprocess.run([sys.executable, str(tool), "--help"], capture_output=True, text=True)
    assert h.returncode == 0 and "--all" in h.stdout
    out = subprocess.run([sys.executable, str(tool), "--all"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("SecLegion OS [")
