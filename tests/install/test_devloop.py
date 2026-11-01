# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer dev loop: facts parsing (pure) and a VM smoke test of the configurator dry run."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import facts  # noqa: E402

from tests.lib import bootgate, devloop  # noqa: E402

PASSWORD = "test-pass-1"


def lsblk():
    def disk(name, children=()):
        return {"name": name, "path": f"/dev/{name}", "type": "disk", "children": list(children)}
    return {"blockdevices": [
        disk("sda", [{"name": "sda1", "path": "/dev/sda1", "type": "part"}]),
        disk("sdb"),
        {"name": "sr0", "path": "/dev/sr0", "type": "rom"},
    ]}


def test_facts_parent_disk_resolves_partitions_and_disks():
    assert facts.parent_disk(lsblk(), "/dev/sda1") == "/dev/sda"
    assert facts.parent_disk(lsblk(), "/dev/sdb") == "/dev/sdb"
    assert facts.parent_disk(lsblk(), "/dev/nope") is None


def test_facts_by_id_drops_partition_links():
    pairs = [("/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_SLTARGET", "/dev/sdb"),
             ("/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_SLTARGET-part1", "/dev/sdb1")]
    assert facts.parse_by_id(pairs) == {pairs[0][0]: "/dev/sdb"}


def test_facts_build_has_the_keys_the_configurator_reads():
    built = facts.build_facts(lsblk(), [], "rootfs", "/dev/sda1", True, True)
    assert built["install_mode"] is True and built["dev_build"] is True
    assert built["boot_medium"] == "/dev/sda"
    assert built["root_disk"] is None  # tmpfs/airootfs root is not a disk
    assert set(built) == {"install_mode", "dev_build", "boot_medium", "root_disk", "by_id", "lsblk"}
    json.dumps(built)


@pytest.mark.iso
def test_devloop_smoke():
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO (set SECLEGION_ISO)")
    answers = {"disk": devloop.TARGET_BY_ID, "mode": "erase-luks", "username": "tester",
               "password": PASSWORD, "hostname": "seclegion", "confirm": "QEMU HARDDISK",
               "timezone": "UTC"}
    extra = {"dev/answers.json": json.dumps(answers)}
    root = devloop.MOUNT
    with devloop.devloop_vm(iso, extra_files=extra) as vm:
        out = devloop.run(vm, f"python {root}/installd/facts.py --force-install-mode > /tmp/f.json "
                              "&& grep -c SLTARGET /tmp/f.json", "DL-FACTS", 60)
        assert "DL-FACTS 0" in out, out[-500:]
        out = devloop.run(vm, f"python {root}/installd/seclegion-configure --facts /tmp/f.json "
                              f"--answers {root}/dev/answers.json --out /tmp/o --dry-run", "DL-DRY", 60)
        assert "DL-DRY 0" in out, out[-800:]
        assert "Would run: archinstall" in out
        serial = vm.serial.text()  # everything the guest wrote to ttyS0, as in serial.log
    assert PASSWORD not in serial
