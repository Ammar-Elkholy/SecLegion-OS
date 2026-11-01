# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tools/release notes and check-iso (RL1a, G76/G77).

No real HW-MANUAL evidence rows exist yet; the format is supported and tested with fixtures:
evidence/<test>/<iso>/<stamp>/result.json with "class": "HW-MANUAL", attested = status PASS,
or "attestation": "not-attested-by-design" plus a non-empty "note"."""

import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "release"
TP = (
    "| Component | Version | Pinned | Licence |\n|---|---|---|---|\n"
    "| `old` | 1.0 | 2026-10-01 | MIT |\n| `new` | 2.0 | 2026-10-20 | MIT |\n"
)


def load():
    loader = importlib.machinery.SourceFileLoader("release_tool", str(TOOL))
    spec = importlib.util.spec_from_loader("release_tool", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def add_row(root, test_id, **fields):
    rec = {"test_id": test_id, "class": "HW-MANUAL", "status": "NOT RUN", "timestamp": "2026-10-20T10:00:00Z"}
    rec.update(fields)
    d = root / test_id / ("0" * 64) / "20261020T100000Z"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps(rec))


def run_notes(tmp_path, evidence):
    tp = tmp_path / "tp.md"
    tp.write_text(TP)
    out = tmp_path / "notes.md"
    r = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "notes",
            "--evidence",
            str(evidence),
            "--out",
            str(out),
            "--third-party",
            str(tp),
            "--today",
            "2026-10-23",
        ],
        capture_output=True,
        text=True,
    )
    return r, out


def test_notes_content_versions_ages_and_no_ai_line(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    add_row(ev, "HW-boot", status="PASS")
    r, out = run_notes(tmp_path, ev)
    assert r.returncode == 0, r.stderr
    text = out.read_text()
    assert "No AI models are shipped in the ISO." in text
    assert "| `old` | 1.0 | 2026-10-01 | 22 |" in text
    assert "| `new` | 2.0 | 2026-10-20 | 3 |" in text
    assert "HW-boot: attested" in text


def test_notes_without_hw_manual_rows_still_written(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    r, out = run_notes(tmp_path, ev)
    assert r.returncode == 0 and "No HW-MANUAL evidence rows" in out.read_text()


def test_notes_refuse_unattested_row(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    add_row(ev, "HW-boot", status="NOT RUN")
    r, out = run_notes(tmp_path, ev)
    assert r.returncode == 1 and "HW-boot" in r.stderr
    assert not out.exists()


def test_notes_refuse_by_design_without_note(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    add_row(ev, "HW-boot", attestation="not-attested-by-design", note="  ")
    assert run_notes(tmp_path, ev)[0].returncode == 1


def test_notes_by_design_row_accepted_and_note_printed_verbatim(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    add_row(ev, "HW-wifi", attestation="not-attested-by-design", note="Needs lab hardware we do not own.")
    add_row(ev, "HW-boot", status="PASS")
    r, out = run_notes(tmp_path, ev)
    assert r.returncode == 0
    assert "Needs lab hardware we do not own." in r.stdout
    assert "not attested by design. Needs lab hardware we do not own." in out.read_text()


def test_notes_non_hw_rows_ignored(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    add_row(ev, "M0-boot", **{"class": "AUTO"})
    assert run_notes(tmp_path, ev)[0].returncode == 0


def test_notes_real_repo_third_party_has_ages():
    tool = load()
    ages = tool.vendor_ages(
        (REPO / "docs" / "third-party.md").read_text(), __import__("datetime").date(2026, 10, 23)
    )
    assert ages and all(a[3] != "" for a in ages)


# release key guard (G77)


def fp_file(tmp_path, name, fp):
    p = tmp_path / name
    p.write_text(fp + "\n")
    return str(p)


def run_check(tmp_path, fingerprint, devs, iso):
    cmd = [sys.executable, str(TOOL), "check-iso", "--iso", str(iso), "--fingerprint", fingerprint]
    for d in devs:
        cmd += ["--dev-fingerprint", d]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_release_key_refuses_dev_fingerprint(tmp_path):
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"not an iso")
    dev = fp_file(tmp_path, "dev", "AAAA BBBB CCCC DDDD")
    rel = fp_file(tmp_path, "rel", "aaaabbbbccccdddd")
    r = run_check(tmp_path, rel, [dev], iso)
    assert r.returncode == 1 and "DEV key" in r.stderr


def test_release_key_accepts_different_key(tmp_path):
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"not an iso")
    dev = fp_file(tmp_path, "dev", "AAAA")
    rel = fp_file(tmp_path, "rel", "BBBB")
    r = run_check(tmp_path, rel, [dev], iso)
    assert r.returncode == 0 and "skipped" in r.stdout


@pytest.mark.skipif(not shutil.which("bsdtar"), reason="bsdtar not installed")
def test_release_key_refuses_dev_uid_in_embedded_keyring(tmp_path):
    src = tmp_path / "src" / "usr" / "share" / "pacman" / "keyrings"
    src.mkdir(parents=True)
    (src / "seclegion.gpg").write_bytes(b"\x99\x01\x02SecLegion DEV (throwaway 2026) <dev@seclegion>")
    iso = tmp_path / "fake.iso"
    with tarfile.open(iso, "w") as t:
        t.add(tmp_path / "src" / "usr", arcname="usr")
    rel = fp_file(tmp_path, "rel", "BBBB")
    r = run_check(tmp_path, rel, [], iso)
    assert r.returncode == 1 and "DEV uid" in r.stderr


@pytest.mark.skipif(not shutil.which("bsdtar"), reason="bsdtar not installed")
def test_release_key_accepts_release_uid_in_embedded_keyring(tmp_path):
    src = tmp_path / "src" / "usr" / "share" / "pacman" / "keyrings"
    src.mkdir(parents=True)
    (src / "seclegion.gpg").write_bytes(b"\x99\x01\x02SecLegion Release Signing <release@seclegion>")
    iso = tmp_path / "fake.iso"
    with tarfile.open(iso, "w") as t:
        t.add(tmp_path / "src" / "usr", arcname="usr")
    r = run_check(tmp_path, fp_file(tmp_path, "rel", "BBBB"), [], iso)
    assert r.returncode == 0 and "skipped" not in r.stdout
