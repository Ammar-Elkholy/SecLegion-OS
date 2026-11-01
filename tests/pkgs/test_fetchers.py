# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Vendor fetchers (plan r14 R5): strict sha256 in the fetch script, docs/third-party.md completeness,
the update canary. Offline: the fetch script runs against file:// payloads and a fake installer."""

import hashlib
import json
import re
import stat
import subprocess
import tomllib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

import pytest

from tests.pkgs.test_packages import PKGS, REPO, clean_env, words

FETCH = REPO / "tools" / "seclegion-vendor-fetch"
CANARY = REPO / "tools" / "canary"
DOC = REPO / "docs" / "third-party.md"
MANIFESTS = sorted(PKGS.glob("seclegion-*-fetch/*.toml"))
PAYLOAD = b"pretend vendor tarball\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def env(tmp_path):
    """A manifest for PAYLOAD (pinned correctly), a tmp root the fake installer writes to, the script."""
    root = tmp_path / "root"
    root.mkdir()
    payload = tmp_path / "vendor.bin"
    payload.write_bytes(PAYLOAD)
    installer = tmp_path / "installer"
    installer.write_text(f'#!/bin/sh\ncp "$VENDOR_PAYLOAD" "{root}/installed-$VENDOR_VERSION"\n')
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    link = tmp_path / "seclegion-test-fetch"
    link.symlink_to(FETCH)

    def run(url=None, digest=None, hash_url=None, extra=()):
        manifest = tmp_path / "test.toml"
        manifest.write_text(
            f'name = "test"\nversion = "1.2.3"\nurl = "{url or payload.as_uri()}"\n'
            f'sha256 = "{digest or sha(PAYLOAD)}"\nhash_url = "{hash_url or ""}"\n')
        work = tmp_path / "work"
        r = subprocess.run([str(link), "--manifest", str(manifest), "--workdir", str(work), *extra],
                           capture_output=True, text=True,
                           env=clean_env(SECLEGION_FETCH_INSTALLER=str(installer), HOME=str(tmp_path)))
        return r, work

    run.root = root
    run.tmp = tmp_path
    return run


def test_fetch_good_sha(env):
    r, work = env()
    assert r.returncode == 0, r.stderr
    assert (env.root / "installed-1.2.3").read_bytes() == PAYLOAD
    assert not (work / "payload").exists() and not (work / "payload.part").exists()


def test_fetch_bad_sha(env):
    """G17: a payload that does not match the pinned sha256 is rejected and nothing is installed."""
    r, work = env(digest=sha(b"something else"))
    assert r.returncode != 0
    assert "sha256 mismatch" in r.stderr and "nothing was installed" in r.stderr
    assert list(env.root.iterdir()) == []
    assert not (work / "payload").exists() and not (work / "payload.part").exists()


def test_fetch_refuses_http(env):
    r, work = env(url="http://127.0.0.1:9/vendor.bin")
    assert r.returncode != 0
    assert "http://" in r.stderr and "not allowed" in r.stderr
    assert list(env.root.iterdir()) == []
    assert not work.exists()


def test_fetch_vendor_hash_file_must_agree(env):
    hashfile = env.tmp / "vendor.sha256"
    hashfile.write_text(f"{sha(b'other')}  vendor.bin\n")
    r, _ = env(hash_url=hashfile.as_uri())
    assert r.returncode != 0 and "vendor-published hash" in r.stderr
    assert list(env.root.iterdir()) == []
    hashfile.write_text(f"{sha(PAYLOAD)}  vendor.bin\n")
    r, _ = env(hash_url=hashfile.as_uri())
    assert r.returncode == 0, r.stderr
    assert (env.root / "installed-1.2.3").exists()


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: p.stem)
def test_real_manifests(manifest):
    m = tomllib.loads(manifest.read_text())
    assert re.fullmatch(r"[0-9a-f]{64}", m["sha256"])
    assert m["url"].startswith("https://") and m["version"] in m["url"]
    pkgbuild = (manifest.parent / "PKGBUILD").read_text()
    assert f"pkgver={m['version']}\n" in pkgbuild
    assert (manifest.parent / f"{m['name']}.PKGBUILD").exists()
    if m["hash_url"]:
        assert m["hash_url"].startswith("https://")


# ---- docs/third-party.md (G18) ----------------------------------------------------------------

REQUIRED = ("source", "version", "sha256", "licence", "trust model", "update owner", "removal")


def sections(doc):
    parts = re.split(r"(?m)^#{2,3} ", doc)
    return parts


def check_third_party(doc, repo=REPO):
    """Problems in `doc`: a remote-source package or fetcher manifest without a complete row."""
    problems = []
    secs = sections(doc)
    subjects = []  # (name, digests-or-per-manifest, version-or-None)
    for pkgbuild in sorted((repo / "pkgs").glob("*/PKGBUILD")):
        text = pkgbuild.read_text()
        srcs = words(text, "source")
        sums = words(text, "sha256sums")
        remote = [d for s, d in zip(srcs, sums, strict=False) if re.search(r"://", s)]
        if remote:
            subjects.append((pkgbuild.parent.name, remote, None))
    for manifest in sorted((repo / "pkgs").glob("seclegion-*-fetch/*.toml")):
        m = tomllib.loads(manifest.read_text())
        subjects.append((manifest.parent.name, ["per-manifest", m["sha256"]], m["version"]))
    for name, digests, version in subjects:
        rows = []
        for sec in secs:
            lines = sec.splitlines()
            table = [ln for ln in lines if ln.startswith("|")]
            if len(table) < 3:
                continue
            header = [c.strip().lower() for c in table[0].strip("|").split("|")]
            prose = " ".join(ln for ln in lines if not ln.startswith("|")).lower()
            for line in table[2:]:
                if f"`{name}`" in line.split("|")[1]:
                    cells = dict(zip(header, [c.strip() for c in line.strip("|").split("|")], strict=False))
                    rows.append((header, prose, cells))
        if not rows:
            problems.append(f"{name}: no row in the doc")
            continue
        header, prose, cells = rows[0]
        for field in REQUIRED:
            col = next((h for h in header if h.startswith(field)), None)
            if col is None:
                if field not in prose:
                    problems.append(f"{name}: no '{field}' column or statement")
            elif not cells.get(col):
                problems.append(f"{name}: empty '{field}' cell")
        sha_cell = next((v for k, v in cells.items() if k.startswith("sha256")), "")
        if version:  # a fetcher: the pin lives in the manifest
            if "per-manifest" not in sha_cell and digests[1] not in sha_cell:
                problems.append(f"{name}: sha256 cell is neither 'per-manifest' nor the pin")
        else:
            problems.extend(f"{name}: sha256 {d} not recorded" for d in digests if d not in doc)
        if version and version not in cells.get("version", ""):
            problems.append(f"{name}: doc version is not the manifest version {version}")
    return problems


def test_third_party_complete():
    """G18: every remote-source package and fetcher manifest has a complete row."""
    assert check_third_party(DOC.read_text()) == []


def test_third_party_missing_row_fails(tmp_path):
    doc = "\n".join(ln for ln in DOC.read_text().splitlines() if "`seclegion-vscode-fetch`" not in ln)
    assert any("seclegion-vscode-fetch: no row" in p for p in check_third_party(doc))
    no_owner = DOC.read_text().replace("Update owner", "Maintainer").replace("update owner", "maintainer")
    assert any("update owner" in p for p in check_third_party(no_owner))
    old_ver = DOC.read_text().replace("| 1.142.0 |", "| 1.141.0 |")
    assert any("manifest version" in p for p in check_third_party(old_ver))


# ---- canary -----------------------------------------------------------------------------------

def canary(tmp_path, latest):
    f = tmp_path / "latest.json"
    f.write_text(json.dumps(latest))
    return subprocess.run([str(CANARY), "--offline", str(f)], capture_output=True, text=True, env=clean_env())


def pinned():
    return {tomllib.loads(m.read_text())["name"]: tomllib.loads(m.read_text()) for m in MANIFESTS}


def test_canary_offline_ok_and_eight_days_behind(tmp_path):
    from datetime import date, timedelta  # noqa: PLC0415

    p = pinned()

    def latest(days):
        return {n: {"version": "9.9.9",
                    "released": (date.fromisoformat(m["released"]) + timedelta(days=days)).isoformat()}
                for n, m in p.items()}

    ok = canary(tmp_path, latest(7))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    late = canary(tmp_path, latest(8))
    assert late.returncode == 1
    assert "LATE" in late.stdout and "8" in late.stdout


def test_canary_missing_vendor_is_an_error(tmp_path):
    r = canary(tmp_path, {})
    assert r.returncode == 2


def test_vendor_bump_rewrites_only_the_named_keys():
    loader = SourceFileLoader("vb", str(REPO / "tools" / "vendor-bump"))
    bump = module_from_spec(spec_from_loader("vb", loader))
    loader.exec_module(bump)
    text = 'name = "x"\nversion = "1.0.0"\n# note\nsha256 = "aa"\n'
    out = bump.update_manifest(text, {"version": "2.0.0", "sha256": "bb"})
    assert out == 'name = "x"\nversion = "2.0.0"\n# note\nsha256 = "bb"\n'
    with pytest.raises(ValueError):
        bump.update_manifest(text, {"missing": "1"})


# ---- Claude Code fetcher ----------------------------------------------------------------------

CLAUDE = PKGS / "seclegion-claude-fetch"


def test_claude_fetcher_is_registered_everywhere():
    """The fetcher is a package with manifest and template, is installed, offered and bumped."""
    m = tomllib.loads((CLAUDE / "claude.toml").read_text())
    assert m["name"] == "claude" and m["url"].startswith("https://downloads.claude.ai/claude-code-releases/")
    assert m["url"].endswith(f"/{m['version']}/linux-x64/claude")
    assert m["hash_source"].endswith(f"/{m['version']}/manifest.json") and m["hash_url"] == ""
    pkgbuild = (CLAUDE / "PKGBUILD").read_text()
    assert "/usr/bin/seclegion-claude-fetch" in pkgbuild and "claude.PKGBUILD" in pkgbuild
    assert "tools/seclegion-vendor-fetch" in (CLAUDE / "source.list").read_text()
    for path in ("installer/installd/post-packages.list", "pkgs/seclegion-firstboot/seclegion-firstboot",
                 "desktop/welcome/python/seclegion_welcome/model.py"):
        assert "seclegion-claude-fetch" in (REPO / path).read_text(), path


def test_claude_template_takes_the_verified_payload_and_disables_the_updater():
    text = (CLAUDE / "claude.PKGBUILD").read_text()
    assert "VENDOR_PAYLOAD:?" in text and "VENDOR_SHA256:?" in text
    assert "/opt/claude-code/claude" in text
    wrapper = re.search(r"cat > \"\$pkgdir/usr/bin/claude\" <<'EOF'\n(.*?)\nEOF\n", text, re.S).group(1)
    out = subprocess.run(["sh", "-c", wrapper.replace("exec /opt/claude-code/claude", "exec env")],
                         capture_output=True, text=True, check=True, env={"PATH": "/usr/bin:/bin"}).stdout
    assert "DISABLE_AUTOUPDATER=1" in out and "DISABLE_UPDATES=1" in out


def test_vendor_bump_reads_the_claude_manifest():
    loader = SourceFileLoader("vb2", str(REPO / "tools" / "vendor-bump"))
    bump = module_from_spec(spec_from_loader("vb2", loader))
    loader.exec_module(bump)
    assert "claude" in bump.LATEST
    d = bump.claude_from_manifest(
        {"version": "2.1.308", "buildDate": "2026-10-22T03:48:37Z",
         "platforms": {"linux-x64": {"checksum": "a" * 64}, "linux-x64-musl": {"checksum": "b" * 64}}},
        "https://downloads.claude.ai/claude-code-releases/2.1.308/manifest.json")
    assert d["published_sha256"] == "a" * 64 and d["released"] == "2026-10-22"
    assert d["url"].endswith("/2.1.308/linux-x64/claude") and d["extra"]["hash_url"] == ""
    assert d["extra"]["signature"].endswith("manifest.json.sig")
