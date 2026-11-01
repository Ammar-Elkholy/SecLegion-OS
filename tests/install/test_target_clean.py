# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""target_check tests: a clean tmp target tree passes; the CLI prints problems and exits 1."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import target_check  # noqa: E402
import target_fixture as fx  # noqa: E402

CLI = os.path.join(fx.REPO, "installer", "installd", "target_check.py")


def test_target_clean_fixture_has_no_problems(tmp_path):
    root = fx.build_clean(tmp_path)
    assert target_check.check(root, fx.LIVE_ONLY) == []


def test_target_clean_cli_exit_codes(tmp_path):
    root = fx.build_clean(tmp_path / "t")
    ll = tmp_path / "live.list"
    ll.write_text("# c\nmkinitcpio-archiso\ngrub  # boot\n")
    ok = subprocess.run([sys.executable, CLI, "--root", root, "--live-list", str(ll)],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout == ""
    fx.write(root, "etc/sudoers.d/x", "u ALL=(ALL) NOPASSWD: ALL\n")
    bad = subprocess.run([sys.executable, CLI, "--root", root, "--live-list", str(ll)],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "NOPASSWD" in bad.stdout


def test_target_clean_real_live_list_parses():
    ll = os.path.join(fx.REPO, "iso", "packages", "live.list")
    assert "mkinitcpio-archiso" in target_check.read_live_list(ll)


def test_target_clean_accepts_seclegion_release_link_only(tmp_path):
    """seclegion-release makes /etc/os-release its tmpfiles symlink: that one is clean, Arch's is not."""
    root = fx.build_clean(tmp_path)
    fx.write(root, "usr/lib/seclegion/os-release", 'NAME="SecLegion OS"\nID=seclegion\n')
    osr = os.path.join(root, "etc/os-release")
    os.remove(osr)
    os.symlink("../usr/lib/seclegion/os-release", osr)
    assert target_check.check(root, fx.LIVE_ONLY) == []
    os.remove(osr)
    os.symlink("../usr/lib/os-release", osr)
    assert any("symlink" in p for p in target_check.check(root, fx.LIVE_ONLY))


def test_target_clean_live_only_package_as_a_dependency_is_not_a_leftover(tmp_path):
    """mdadm/pcsclite/tpm2-tss arrive as dependencies (udisks2, wpa_supplicant, gnupg): not live traces."""
    root = fx.build_clean(tmp_path)
    fx.write(root, "var/lib/pacman/local/nbd-1-1/desc", "%NAME%\nnbd\n\n%REASON%\n1\n")
    assert target_check.check(root, fx.LIVE_ONLY) == []
    fx.write(root, "var/lib/pacman/local/nbd-1-1/desc", "%NAME%\nnbd\n")  # explicitly installed
    assert target_check.check(root, fx.LIVE_ONLY) == ["live-only package installed: nbd"]


def _explicit_nbd(tmp_path):
    root = fx.build_clean(tmp_path)
    fx.write(root, "var/lib/pacman/local/nbd-1-1/desc", "%NAME%\nnbd\n")
    return root


def test_target_clean_hw_plan_package_is_not_a_live_leftover(tmp_path):
    root = _explicit_nbd(tmp_path)
    fx.write(root, "var/lib/seclegion/hw-packages", "# seclegion-post: plan\nnbd\n")
    assert target_check.check(root, fx.LIVE_ONLY) == []


def test_target_clean_other_live_only_package_still_reported_with_hw_record(tmp_path):
    root = _explicit_nbd(tmp_path)
    fx.write(root, "var/lib/seclegion/hw-packages", "mesa\n")
    assert target_check.check(root, fx.LIVE_ONLY) == ["live-only package installed: nbd"]


def test_target_clean_hw_record_comments_are_ignored(tmp_path):
    root = _explicit_nbd(tmp_path)
    fx.write(root, "var/lib/seclegion/hw-packages", "# nbd\n\n  # nbd\n")
    assert target_check.check(root, fx.LIVE_ONLY) == ["live-only package installed: nbd"]


def test_target_clean_rejects_active_seclegion(tmp_path):
    root = fx.build_clean(tmp_path)
    conf = os.path.join(root, "etc/pacman.conf")
    with open(conf, "a") as fh:
        fh.write("\n[seclegion]\nSigLevel = Required DatabaseRequired\n"
                 "Server = file:///opt/seclegion/cache/seclegion\n")
    assert any("active [seclegion]" in p for p in target_check.check(root, fx.LIVE_ONLY))
