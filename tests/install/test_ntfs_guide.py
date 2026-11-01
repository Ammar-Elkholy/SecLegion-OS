# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""U3: dual-boot guide detector + configurator wiring. Images generated in tmp, never /dev."""

import importlib.util
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "installd"))
sys.path.insert(0, HERE)
import configurator as c  # noqa: E402
import winguide  # noqa: E402
from test_plan import alongside, answers, load_facts  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "make_fixtures", os.path.join(HERE, "fixtures", "ntfs", "make_fixtures.py"))
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

needs_mkntfs = pytest.mark.skipif(not shutil.which("mkntfs"), reason="mkntfs not installed")
NTFS_PARTS = ("/dev/vdb3", "/dev/vdb4")


def test_ntfs_guide_bitlocker_detected(tmp_path):
    # synthetic: a boot sector with -FVE-FS-, not a real BitLocker volume
    assert winguide.probe(mk.bitlocker(str(tmp_path / "bl.img"))) == "bitlocker"


@needs_mkntfs
def test_ntfs_guide_clean_control_passes(tmp_path):
    p = mk.clean(str(tmp_path / "c.img"))
    before = open(p, "rb").read()
    assert winguide.probe(p) == "clean"
    assert open(p, "rb").read() == before  # probing never writes


@needs_mkntfs
def test_ntfs_guide_hibernated_detected(tmp_path):
    # hibernated = $Volume VOLUME_IS_DIRTY set, the state Windows leaves behind
    assert winguide.probe(mk.hibernated(str(tmp_path / "h.img"))) == "hibernated"


@needs_mkntfs
def test_ntfs_guide_fast_startup_same_mechanism(tmp_path):
    # Fast Startup is a kernel-only hibernation: same dirty-volume state, same refusal
    assert winguide.probe(mk.hibernated(str(tmp_path / "fs.img"))) == "hibernated"
    assert winguide.refusal_for("hibernated")[0] == "windows_hibernated"


def test_ntfs_guide_not_ntfs(tmp_path):
    p = tmp_path / "x.img"
    p.write_bytes(b"\0" * 4096)
    assert winguide.probe(str(p)) == "not_ntfs"


def _facts(**probes):
    f = load_facts()
    f["probes"] = {**f.get("probes", {}), **probes}
    return f


def _validate(mode_answers, facts):
    c.validate(mode_answers, facts)


def test_ntfs_guide_refuse_bitlocker_alongside():
    with pytest.raises(c.Refusal) as e:
        _validate(alongside(confirm="QEMU HARDDISK"), _facts(**{"/dev/vdb3": "bitlocker"}))
    assert e.value.code == "bitlocker"


def test_ntfs_guide_refuse_hibernated_alongside():
    with pytest.raises(c.Refusal) as e:
        _validate(alongside(confirm="QEMU HARDDISK"), _facts(**{"/dev/vdb4": "hibernated"}))
    assert e.value.code == "windows_hibernated"
    assert "shutdown /s /t 0" in e.value.message and "Fast Startup" in e.value.message


def test_ntfs_guide_clean_probes_do_not_block_alongside():
    _validate(alongside(confirm="QEMU HARDDISK"), _facts(**dict.fromkeys(NTFS_PARTS, "clean")))


@pytest.mark.parametrize("mode", ["erase", "erase-luks"])
def test_ntfs_guide_erase_not_blocked(mode):
    a = answers(disk="/dev/disk/by-id/ata-QEMU_HARDDISK_vdb", confirm="QEMU HARDDISK", mode=mode,
                luks=None, luks_passphrase="test-luks-2")
    _validate(a, _facts(**{"/dev/vdb3": "bitlocker", "/dev/vdb4": "hibernated"}))


def test_ntfs_guide_refuse_unreadable_windows_partition_alongside():
    """Fail closed: a partition the probe could not read is not assumed clean."""
    with pytest.raises(c.Refusal) as e:
        _validate(alongside(confirm="QEMU HARDDISK"), _facts(**{"/dev/vdb4": "unreadable"}))
    assert e.value.code == "windows_unreadable"


def test_ntfs_guide_refuse_unprobed_ntfs_partition_alongside():
    """An NTFS partition with no probe result at all is treated as unreadable, not clean."""
    facts = _facts()
    facts["probes"].pop("/dev/vdb4")  # gather() missed it: it must not count as clean
    with pytest.raises(c.Refusal) as e:
        _validate(alongside(confirm="QEMU HARDDISK"), facts)
    assert e.value.code == "windows_unreadable"
