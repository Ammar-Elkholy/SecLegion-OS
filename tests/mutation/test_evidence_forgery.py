# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Mutation tests for tools/verify-evidence: each forgery is internally consistent and must
be REJECTED; the honest baseline must be ACCEPTED (so a rejection means the mutation, not
a broken fixture)."""

import pytest

from tests.mutation.forge import (
    COMMIT_DATE,
    HONEST_SERIAL,
    OTHER_SHA,
    PATTERNS,
    add_run,
    git,
    make_repo,
    regenerate,
    verify,
)


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def reject(root, needle, *extra):
    regenerate(root)  # TESTING.md matches the forged results: only the checks can object
    proc = verify(root, *extra)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert needle in proc.stderr, proc.stderr


def test_honest_run_is_accepted(repo):
    root, head = repo
    add_run(root, head)
    regenerate(root)
    proc = verify(root)
    assert proc.returncode == 0, proc.stderr


def test_pass_without_an_iso_reference_fails_unless_rows_only(repo):
    """No out/SHA256SUMS and no --iso: the ISO check cannot run, which is a failure, not a skip."""
    root, head = repo
    add_run(root, head, sums=None)
    reject(root, "no ISO reference")
    assert verify(root, "--rows-only").returncode == 0


def test_no_iso_reference_is_fine_when_no_pass_is_recorded(repo):
    root, head = repo
    add_run(root, head, sums=None, status="FAIL", exit_code=1)
    regenerate(root)
    assert verify(root).returncode == 0


def test_the_reported_forgery_is_rejected(repo):
    """Hand-written PASS: commit deadbeef, ISO matching nothing, timestamp 'whenever'."""
    root, head = repo
    add_run(root, head, commit="deadbeef", iso_sha256=OTHER_SHA, timestamp="whenever")
    regenerate(root)
    proc = verify(root)
    assert proc.returncode == 1
    for needle in ("not a full 40-hex sha", "not ISO-8601", "matches no known ISO"):
        assert needle in proc.stderr


@pytest.mark.parametrize("commit", ["deadbeef", "de" * 20])
def test_fake_commit_rejected(repo, commit):
    root, head = repo
    add_run(root, head, commit=commit)
    reject(root, "full 40-hex sha" if len(commit) < 40 else "does not exist")


def test_commit_not_an_ancestor_of_head_rejected(repo):
    root, head = repo
    git(root, "checkout", "-q", "-b", "side")
    (root / "side").write_text("s\n")
    git(root, "add", "side")
    git(root, "commit", "-q", "-m", "side")
    side = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "-q", "-")
    assert side != head
    add_run(root, head, commit=side)
    reject(root, "is not an ancestor of HEAD")


def test_dirty_pass_rejected(repo):
    root, head = repo
    add_run(root, head, commit=head + "-dirty")
    reject(root, "dirty tree")


def test_future_timestamp_rejected(repo):
    root, head = repo
    add_run(root, head, timestamp="2999-01-01T00:00:00Z")
    reject(root, "in the future")


def test_timestamp_before_the_commit_date_rejected(repo):
    """A run cannot predate the code it claims to have tested."""
    root, head = repo
    add_run(root, head, timestamp="2026-10-14T19:59:59Z")  # one second before COMMIT_DATE
    reject(root, "earlier than the commit's committer date")


def test_timestamp_at_the_commit_date_accepted(repo):
    root, head = repo
    add_run(root, head, timestamp=COMMIT_DATE)
    regenerate(root)
    assert verify(root).returncode == 0


def test_non_iso_timestamp_rejected(repo):
    root, head = repo
    add_run(root, head, timestamp="whenever")
    reject(root, "not ISO-8601")


def test_wrong_iso_sha_rejected_against_sha256sums(repo):
    root, head = repo
    add_run(root, head, iso_sha256=OTHER_SHA, sums="b" * 64)
    reject(root, "matches no known ISO")


def test_wrong_iso_sha_rejected_against_explicit_iso(repo, tmp_path):
    root, head = repo
    add_run(root, head, sums=None)
    iso = tmp_path / "real.iso"
    iso.write_bytes(b"not the iso that was tested")
    reject(root, "matches no known ISO", "--iso", str(iso))


def test_rows_only_skips_the_iso_check_and_nothing_else(repo):
    root, head = repo
    add_run(root, head, iso_sha256=OTHER_SHA, sums="b" * 64)
    regenerate(root)
    assert verify(root).returncode == 1
    assert verify(root, "--rows-only").returncode == 0  # only the ISO hash is skipped


def test_serial_log_not_matching_expected_rejected(repo):
    root, head = repo
    add_run(root, head, serial="Install SecLegion OS\nkernel panic\n")  # no login
    reject(root, "does not match /seclegion login:|root@seclegion/")


def test_serial_patterns_out_of_order_rejected(repo):
    root, head = repo
    add_run(root, head, serial="seclegion login: \nInstall SecLegion OS\n")
    reject(root, "does not match /seclegion login:|root@seclegion/")


@pytest.mark.parametrize("patterns", [
    [""], [".*"], ["Try SecLegion OS"], list(PATTERNS[:1]), list(PATTERNS[::-1]),
    [*PATTERNS, ""], [PATTERNS[0], "seclegion login:"],
], ids=["empty-string", "match-all", "wrong", "first-only", "reversed", "extra", "narrowed-login"])
def test_weakened_patterns_rejected(repo, patterns):
    """A forger sets serial_patterns to something any text satisfies: not the canonical oracle."""
    root, head = repo
    add_run(root, head, serial_patterns=patterns)  # the stored log is honest: only the oracle differs
    reject(root, "differ from the canonical patterns")


def test_pass_for_a_test_without_canonical_patterns_rejected(repo):
    root, head = repo
    add_run(root, head, test_id="X-unregistered")
    reject(root, "has no canonical serial patterns")


def test_pass_without_serial_patterns_rejected(repo):
    root, head = repo
    add_run(root, head, serial_patterns=[])
    reject(root, "without serial_patterns")


def test_missing_artifact_rejected_even_rows_only(repo):
    root, head = repo
    run_dir = add_run(root, head, artifacts=["serial.log", "screen.png"])
    (run_dir / "screen.png").unlink()
    reject(root, "artifact screen.png is missing")
    assert verify(root, "--rows-only").returncode == 1  # rows-only never skips artifacts


def test_edited_serial_log_rejected(repo):
    root, head = repo
    run_dir = add_run(root, head)
    (run_dir / "serial.log").write_text(HONEST_SERIAL + "typed afterwards\n")
    reject(root, "sha256 differs")


def test_directory_must_match_timestamp(repo):
    root, head = repo
    run_dir = add_run(root, head)
    run_dir.rename(run_dir.parent / "20200101T000000Z")
    reject(root, "directory does not match")
