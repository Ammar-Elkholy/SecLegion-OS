# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tools/licence-check: real repo is clean; each kind of gap is reported (RL1a, G76)."""

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "licence-check"


def load():
    loader = importlib.machinery.SourceFileLoader("licence_check", str(TOOL))
    spec = importlib.util.spec_from_loader("licence_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


TP_OK = """| Component | Version | Pinned | Licence |
|---|---|---|---|
| `a` | 1.0 | 2026-10-01 | MIT |
"""


def make_repo(
    tmp_path,
    pkgbuild="license=('MIT')\npackage() {\n  :\n}\n",
    name="hello",
    catalog='[[tool]]\nname = "t"\nlicence = "MIT"\n',
    tp=TP_OK,
):
    (tmp_path / "pkgs" / name).mkdir(parents=True)
    (tmp_path / "pkgs" / name / "PKGBUILD").write_text(pkgbuild)
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "x.toml").write_text(catalog)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "third-party.md").write_text(tp)
    return tmp_path


def gaps(repo):
    return [r for r in load().check(str(repo)) if r[3]]


def test_licences_real_repo_clean():
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "0 gap(s)" in r.stdout


def test_licences_synthetic_repo_clean(tmp_path):
    assert gaps(make_repo(tmp_path)) == []


def test_licences_empty_and_unknown_license(tmp_path):
    assert any("missing" in g[3] for g in gaps(make_repo(tmp_path, "license=()\n")))
    assert any("unknown SPDX" in g[3] for g in gaps(make_repo(tmp_path / "b", "license=('Proprietary')\n")))


def test_licences_theme_package_must_install_licence_files(tmp_path):
    repo = make_repo(
        tmp_path, "license=('MIT')\npackage() {\n  install -d x\n}\n", name="seclegion-themes-foo"
    )
    assert any(g[0] == "pkg-files" for g in gaps(repo))
    good = make_repo(
        tmp_path / "g",
        "license=('MIT')\npackage() {\n  install -Dm644 L \"$pkgdir/usr/share/licenses/x/L\"\n}\n",
        name="seclegion-fonts-foo",
    )
    assert gaps(good) == []


def test_licences_catalog_entry_needs_licence(tmp_path):
    assert any(g[0] == "catalog" for g in gaps(make_repo(tmp_path, catalog='[[tool]]\nname = "t"\n')))


def test_licences_vendor_row_needs_licence_version_and_pin_date(tmp_path):
    tp = (
        "| Component | Version | Pinned | Licence |\n|---|---|---|---|\n"
        "| `a` |  | 2026-10-01 | MIT |\n| `b` | 1 | soon | MIT |\n"
    )
    g = [x for x in gaps(make_repo(tmp_path, tp=tp)) if x[0] == "vendor"]
    assert len(g) == 2
    assert "version" in g[0][3] and "pinned" in g[1][3]


def test_licences_exit_code_one_on_gap(tmp_path):
    repo = make_repo(tmp_path, "license=()\n")
    r = subprocess.run([sys.executable, str(TOOL), "--repo", str(repo)], capture_output=True, text=True)
    assert r.returncode == 1 and "FAIL" in r.stdout
