# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M4-shrink (VM): install alongside by shrinking a Windows-like NTFS partition that fills the disk.

The guest builds the disk (GPT, one NTFS partition, one file), the installer shrinks the filesystem and the
GPT entry, installs into the freed gap, and afterwards the NTFS must still be consistent with the file intact.
Typed through QMP: no double quote, hash, braces, at sign, bang or percent in any guest command.
"""
import json
import os
import re
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))

from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import bootgate, devloop  # noqa: E402

GIB = 1 << 30
NEW_SIZE = 45 * GIB  # the NTFS partition after the shrink; the disk is 100 GiB, so ~55 GiB is freed
PART = devloop.TARGET_BY_ID + "-part1"
SHA = r"([0-9a-f]{64})  /run/w/data\.bin"


def _shrink_install(result_dir):
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO (set SECLEGION_ISO)")
    answers = {"disk": devloop.TARGET_BY_ID, "mode": "alongside", "luks": False, "username": "tester",
               "password": PASSWORD, "hostname": "seclegion", "confirm": "QEMU HARDDISK",
               "timezone": "UTC", "shrink": "XPARTX", "shrink_size": NEW_SIZE}
    root = devloop.MOUNT
    os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="shrink-", dir=devloop.SCRATCH_ROOT)
    with open(os.path.join(REPO, "iso", "packages", "live.list")) as fh:
        live_list = fh.read()
    extra = {"dev/answers.json": json.dumps(answers), "dev/live.list": live_list}
    log = []
    try:
        with devloop.devloop_vm(iso, extra_files=extra, mem=4096, scratch=scratch,
                                target_size="100G") as vm:
            log.append(evidence.repo_relative(vm.command, REPO))
            cmds = [
                ("DL-GPT", f"sgdisk -n 1:2048:0 -t 1:0700 -c 1:Windows {devloop.TARGET_BY_ID}; "
                           f"partprobe {devloop.TARGET_BY_ID}; udevadm settle; test -b {PART}", 120),
                ("DL-NTFS", f"mkntfs -F -Q -L Windows {PART} && mkdir -p /run/w && ntfs-3g {PART} /run/w "
                            f"&& dd if=/dev/urandom of=/run/w/data.bin bs=1M count=64 status=none "
                            f"&& sync && sha256sum /run/w/data.bin && umount /run/w", 300),
            ]
            outs = {}
            for marker, cmd, timeout in cmds:
                outs[marker] = devloop.run(vm, cmd, marker, timeout)
                log.append(outs[marker])
                assert f"{marker} 0" in outs[marker], outs[marker][-600:]
            before = re.search(SHA, outs["DL-NTFS"])
            assert before, outs["DL-NTFS"][-600:]
            out = devloop.run(
                vm, f"p=$(readlink -f {PART}); sed -e 's|XPARTX|'$p'|' {root}/dev/answers.json "
                    f"> /tmp/answers.json; grep -c /dev/sd /tmp/answers.json", "DL-ANS", 60)
            log.append(out)
            assert "DL-ANS 0" in out, out[-600:]
            out = devloop.run(
                vm, f"SECLEGION_POST_SKIP_MISSING=1 python {root}/installd/seclegion-install "
                    f"--answers /tmp/answers.json --dev --force-install-mode", "DL-INSTALL", 2400)
            log.append(out)
            assert "SECLEGION-INSTALL-OK" in out and "DL-INSTALL 0" in out, out[-1500:]
            out = devloop.run(
                vm, f"ntfsresize --check {PART}; echo CHECK-RC $?; ntfsfix -n {PART}; echo FIX-RC $?; "
                    f"lsblk -b -n -o SIZE -d {PART}; sgdisk -i 1 {devloop.TARGET_BY_ID}; "
                    f"ntfs-3g -o ro {PART} /run/w && sha256sum /run/w/data.bin; umount /run/w",
                "DL-NTFSCHK", 300)
            log.append(out)
            assert re.search(r"^CHECK-RC 0$", out, re.M) and re.search(r"^FIX-RC 0$", out, re.M), out[-900:]
            assert re.search(rf"^{NEW_SIZE}$", out, re.M), out[-900:]  # the partition really is smaller
            assert "Partition name: 'Windows'" in out, out[-900:]
            after = re.search(SHA, out)
            assert after and after.group(1) == before.group(1), "the file on the shrunk NTFS changed"
            out = devloop.run(vm, f"python {root}/installd/target_check.py --root /mnt "
                                  f"--live-list {root}/dev/live.list", "DL-TARGET", 120)
            log.append(out)
            assert "DL-TARGET 0" in out, out[-1500:]
            devloop.run(vm, "sync; umount -R /mnt", "DL-UMOUNT", 120)
            serial = vm.serial.text()
        assert PASSWORD not in serial
        log.append(f"NTFS-FILE-SHA256-UNCHANGED {before.group(1)}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(log))
    return log[0]


@pytest.mark.iso
def test_m4_shrink():
    def body(result_dir, iso):
        command = _shrink_install(result_dir)
        return "shrunk the NTFS to 45 GiB, installed alongside, NTFS clean, file hash unchanged", \
            command, "n/a"

    finish_gate("M4-shrink", "alongside install by shrinking the NTFS partition succeeds, the NTFS stays "
                             "consistent with its file intact and the target is clean", body)
