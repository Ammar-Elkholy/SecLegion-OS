# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G67 ai_refusals and ai_catalog: pull consent/cloud/catalog/RAM refusals; catalog lint."""

import copy
import io
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ai" / "cli"))
import seclegion_ai as ai  # noqa: E402

GOOD = "sha256:" + "ab" * 32
CAT = [{"name": "tiny", "tag": "tiny:1b", "digest": GOOD, "licence": "MIT", "size_mb": 500, "ram_mb": 1000}]


class Fake:
    """Fake runner: records calls; `ollama show` returns a modelfile naming `blob`."""

    def __init__(self, blob="ab" * 32, listening=True):
        self.calls, self.blob, self.listening = [], blob, listening

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[0] == "ss":
            return 0, "LISTEN 0 4096 127.0.0.1:11434\n" if self.listening else ""
        if argv[:2] == ["ollama", "show"]:
            return 0, f"# Modelfile\nFROM /usr/share/ollama/blobs/sha256-{self.blob}\n"
        return 0, ""

    def pulled(self):
        return [c for c in self.calls if c[:2] == ["ollama", "pull"]]


def pull(args, fake=None, mem=lambda: 8000, interactive=False, ask=None, catalog=CAT):
    fake = fake or Fake()
    err = io.StringIO()
    old, sys.stderr = sys.stderr, err
    try:
        rc = ai.main(
            ["pull", *args],
            runner=fake,
            catalog=catalog,
            mem=mem,
            interactive=interactive,
            ask=ask or (lambda _: ""),
            out=io.StringIO(),
        )
    finally:
        sys.stderr = old
    return rc, fake, err.getvalue()


def test_ai_refusals_pull_without_consent():
    rc, fake, err = pull(["tiny"])
    assert rc == 1 and "consent" in err and not fake.pulled()


def test_ai_refusals_interactive_wrong_name_refused_right_name_accepted():
    rc, fake, _ = pull(["tiny"], interactive=True, ask=lambda _: "nope")
    assert rc == 1 and not fake.pulled()
    rc, fake, _ = pull(["tiny"], interactive=True, ask=lambda _: "tiny")
    assert rc == 0 and fake.pulled() == [["ollama", "pull", "tiny:1b"]]


@pytest.mark.parametrize("name", ["llama3:8b-cloud", "gpt-oss:120b-cloud", "x:cloud", "foo-cloud"])
def test_ai_refusals_cloud_tags_even_with_every_override(name):
    rc, fake, err = pull([name, "--yes", "--allow-uncatalogued"])
    assert rc == 1 and "cloud" in err and not fake.pulled()


def test_ai_refusals_uncatalogued():
    rc, fake, err = pull(["other:7b", "--yes"])
    assert rc == 1 and "not in the catalog" in err and not fake.pulled()
    rc, fake, _ = pull(["other:7b", "--yes", "--allow-uncatalogued"])
    assert rc == 0 and fake.pulled() == [["ollama", "pull", "other:7b"]]


def test_ai_refusals_ram_need_exceeds_available():
    rc, fake, err = pull(["tiny", "--yes"], mem=lambda: 512)
    assert rc == 1 and "1000 MiB" in err and "512 MiB" in err and not fake.pulled()


def test_ai_refusals_runtime_not_running():
    rc, fake, err = pull(["tiny", "--yes"], fake=Fake(listening=False))
    assert rc == 1 and "not running" in err and not fake.pulled()


def test_ai_refusals_digest_mismatch_removes_model():
    rc, fake, err = pull(["tiny", "--yes"], fake=Fake(blob="cd" * 32))
    assert rc == 1 and "digest mismatch" in err
    assert ["ollama", "rm", "tiny:1b"] in fake.calls


def test_ai_refusals_digest_match_succeeds():
    rc, fake, _ = pull(["tiny", "--yes"])
    assert rc == 0 and ["ollama", "rm", "tiny:1b"] not in fake.calls


def test_ai_refusals_enable_does_not_install_without_confirmation():
    calls = []

    def runner(argv):
        calls.append(argv)
        return (1, "") if argv[:2] == ["pacman", "-Q"] else (0, "")

    err, old = io.StringIO(), sys.stderr
    sys.stderr = err
    try:
        rc = ai.main(["enable"], runner=runner, interactive=False, out=io.StringIO())
    finally:
        sys.stderr = old
    assert rc == 1 and not [c for c in calls if "-S" in c]


def raw():
    return tomllib.loads((REPO / "ai/catalog.toml").read_text())


def test_ai_catalog_lint_real_catalog_clean():
    assert ai.lint_catalog(raw()) == []


@pytest.mark.parametrize("field", ai.FIELDS)
def test_ai_catalog_lint_negative_entry_missing_field_fails(field):
    data = raw()
    del data["model"][0][field]
    assert any(f"missing {field}" in p for p in ai.lint_catalog(data))


def test_ai_catalog_lint_negative_bad_digest_and_cloud():
    data = copy.deepcopy(raw())
    data["model"][0]["digest"] = "md5:abc"
    data["model"][1]["tag"] = "foo:70b-cloud"
    problems = ai.lint_catalog(data)
    assert any("digest is not sha256" in p for p in problems)
    assert any("cloud-backed" in p for p in problems)


def test_ai_catalog_load_refuses_invalid(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[[model]]\nname="a"\ntag="a:1"\nlicence="MIT"\nsize_mb=1\nram_mb=1\n')
    with pytest.raises(ai.Abort):
        ai.load_catalog(f)
