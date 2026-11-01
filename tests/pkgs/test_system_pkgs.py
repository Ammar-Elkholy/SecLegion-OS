# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-release, seclegion-base, seclegion-rescue: staged from their PKGBUILD directories into a
temporary root (no root, no container). G10b (the container build) is run by hand, see the report."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PKGS = REPO / "pkgs"
REL, BASE, RESCUE = PKGS / "seclegion-release", PKGS / "seclegion-base", PKGS / "seclegion-rescue"
TMPFILES_LINE = "L+ /etc/os-release - - - - ../usr/lib/seclegion/os-release"


def stage_release(root):
    """Lay the seclegion-release files out as its package() does, plus Arch's /etc and /usr/lib."""
    (root / "usr/lib/seclegion").mkdir(parents=True)
    (root / "usr/lib/tmpfiles.d").mkdir(parents=True)
    (root / "etc").mkdir()
    shutil.copy(REL / "os-release", root / "usr/lib/seclegion/os-release")
    shutil.copy(REL / "00-seclegion-release.conf", root / "usr/lib/tmpfiles.d/00-seclegion-release.conf")
    (root / "usr/lib/os-release").write_text('NAME="Arch Linux"\nID=arch\n')
    (root / "etc/os-release").symlink_to("../usr/lib/os-release")  # what the filesystem package ships


def hook_exec():
    m = re.search(r"^Exec = (.+)$", (REL / "90-seclegion-os-release.hook").read_text(), re.M)
    assert m
    return m.group(1).split()


def run_hook_exec(root):
    """Run the hook's Exec against `root`: same command, with --root and the conf under that root."""
    argv = hook_exec()
    assert argv[0] == "/usr/bin/systemd-tmpfiles" and argv[1] == "--create"
    conf = root / argv[2].lstrip("/")
    assert conf.is_file()
    r = subprocess.run([argv[0], "--root", str(root), "--create", str(conf)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


def os_release_id(path):
    m = re.search(r"^ID=(\S+)$", path.read_text(), re.M)
    return m.group(1) if m else None


def check_os_release(root):
    """Return a list of problems with <root>/etc/os-release (empty when it is SecLegion's)."""
    etc = root / "etc/os-release"
    arch = root / "usr/lib/os-release"
    problems = []
    if not etc.exists():
        return ["/etc/os-release is missing"]
    if arch.exists() and etc.resolve() == arch.resolve():
        problems.append("/etc/os-release resolves to Arch's /usr/lib/os-release")
    if os_release_id(etc) != "seclegion":
        problems.append(f"/etc/os-release has ID={os_release_id(etc)}, not seclegion")
    return problems


def test_osrelease_file():
    text = (REL / "os-release").read_text()
    for line in ('NAME="SecLegion OS"', "ID=seclegion", "ID_LIKE=arch", "BUILD_ID=rolling",
                 "LOGO=seclegion-logo", 'ANSI_COLOR="0;36"'):
        assert line in text.splitlines()
    assert "HOME_URL=" in text and "PRETTY_NAME=" in text


def test_osrelease_tmpfiles(tmp_path):
    assert TMPFILES_LINE in (REL / "00-seclegion-release.conf").read_text().splitlines()
    root = tmp_path / "root"
    stage_release(root)
    arch_before = (root / "usr/lib/os-release").read_text()
    run_hook_exec(root)  # systemd-tmpfiles --root works without root privileges for this line
    link = root / "etc/os-release"
    assert link.is_symlink() and os.readlink(link) == "../usr/lib/seclegion/os-release"
    assert os_release_id(link) == "seclegion"
    assert (root / "usr/lib/os-release").read_text() == arch_before
    assert not (root / "usr/lib/os-release").is_symlink()


def test_osrelease_wins_over_systemd_etc_conf_at_boot(tmp_path):
    """Boot-time tmpfiles reads every conf; systemd's etc.conf also names /etc/os-release and the first
    line per path wins, so ours must sort first (the I2 install booted with Arch's banner otherwise)."""
    root = tmp_path / "root"
    stage_release(root)
    (root / "usr/lib/tmpfiles.d/etc.conf").write_text("L /etc/os-release - - - - ../usr/lib/os-release\n")
    r = subprocess.run(["systemd-tmpfiles", "--root", str(root), "--create"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.readlink(root / "etc/os-release") == "../usr/lib/seclegion/os-release"
    assert os_release_id(root / "etc/os-release") == "seclegion"


def test_osrelease_hook_fires_when_the_package_itself_installs():
    hook = (REL / "90-seclegion-os-release.hook").read_text()
    assert "Target = usr/lib/seclegion/os-release" in hook.splitlines()


def test_osrelease_survives_filesystem_reinstall(tmp_path):
    """G10: a filesystem upgrade restores Arch's symlink; the hook's Exec makes it SecLegion's again."""
    hook = (REL / "90-seclegion-os-release.hook").read_text()
    assert re.search(r"Type = Package\nTarget = filesystem", hook)
    assert "When = PostTransaction" in hook
    root = tmp_path / "root"
    stage_release(root)
    run_hook_exec(root)
    assert check_os_release(root) == []
    (root / "etc/os-release").unlink()  # the filesystem package replaces it ...
    (root / "etc/os-release").symlink_to("../usr/lib/os-release")  # ... with Arch's symlink
    assert check_os_release(root) != []
    run_hook_exec(root)
    assert check_os_release(root) == []
    assert os_release_id(root / "etc/os-release") == "seclegion"


def test_planted_arch_osrelease(tmp_path):
    """G11: the checker fails a root whose /etc/os-release is Arch's, and passes the good one."""
    bad = tmp_path / "bad"
    stage_release(bad)
    problems = check_os_release(bad)
    assert problems and any("Arch" in p for p in problems)
    good = tmp_path / "good"
    stage_release(good)
    run_hook_exec(good)
    assert check_os_release(good) == []
    # a regular file copy of Arch's text is caught as well
    copy = tmp_path / "copy"
    stage_release(copy)
    (copy / "etc/os-release").unlink()
    shutil.copy(copy / "usr/lib/os-release", copy / "etc/os-release")
    assert check_os_release(copy)


def test_no_nopasswd():
    for f in BASE.rglob("*"):
        if f.is_file() and f.name != "PKGBUILD":  # the PKGBUILD names the words it checks for
            assert "NOPASSWD" not in f.read_text(), f
            assert "autologin" not in f.read_text().lower(), f
    sudoers = BASE / "10-seclegion-wheel"
    rules = [ln for ln in sudoers.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert rules == ["%wheel ALL=(ALL:ALL) ALL"]
    visudo = shutil.which("visudo")
    if visudo is None:
        pytest.skip("visudo not available")
    r = subprocess.run([visudo, "-cf", str(sudoers)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_base_zram_config():
    text = (BASE / "seclegion.conf").read_text()
    assert "zram-size = min(ram / 2, 8192)" in text
    assert "compression-algorithm = zstd" in text


def test_uki_hook_warns(tmp_path):
    script = BASE / "seclegion-uki-check"
    assert os.access(script, os.X_OK)
    assert f"Exec = /usr/share/libalpm/scripts/{script.name}" in (
        BASE / "95-seclegion-uki-check.hook").read_text()
    presets = tmp_path / "mkinitcpio.d"
    presets.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["SECLEGION_PRESET_DIR"] = str(presets)
    (presets / "linux.preset").write_text("ALL_kver='/boot/vmlinuz-linux'\nPRESETS=('default')\n")
    r = subprocess.run([str(script)], capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert r.stdout == "" and "linux.preset" in r.stderr and "_uki=" in r.stderr
    (presets / "linux.preset").write_text("PRESETS=('default')\ndefault_uki='/efi/EFI/Linux/a.efi'\n")
    r = subprocess.run([str(script)], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_rescue_cli():
    cli = str(RESCUE / "seclegion-rescue")
    assert os.stat(cli).st_mode & stat.S_IXUSR
    r = subprocess.run([cli, "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "rollback" in r.stdout
    r = subprocess.run([cli, "rollback", "x"], capture_output=True, text=True)
    assert r.returncode == 1 and "positive number" in r.stderr
    # status / list-snapshots / rollback proper: tests/pkgs/test_rescue_rollback.py (stub binaries)
