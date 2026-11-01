# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer dev loop: boot the checkpoint ISO once, mount the repo's installer/ from a read-only
image, and run commands in the rescue root shell, without rebuilding the ISO.

The installer image is an ext4 file built with `mkfs.ext4 -d` (no root). The guest sees it as a
QEMU scsi disk with serial SLINST, the blank target disk as serial SLTARGET (by-id
scsi-0QEMU_QEMU_HARDDISK_SLTARGET). Commands are typed through QMP, output is read from ttyS0.
Keep typed commands to the characters QMP type_text knows (no quotes other than ', no braces).
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import time

from tests.lib import bootgate
from tests.lib.bootgate import MODE_TIMEOUT, REPO, choose, wait_for_menu
from tests.lib.qemu import QemuVM, create_blank_disk

KEY_DELAY = 0.03  # seconds between typed keys: a burst into the busy guest console loses keys
SCRATCH_ROOT = "/var/tmp/seclegion-build/vm"
MOUNT = "/run/seclegion-installer"
TARGET_SERIAL = "SLTARGET"
INSTALLER_SERIAL = "SLINST"
TARGET_BY_ID = "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_" + TARGET_SERIAL
INSTALLER_BY_ID = "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_" + INSTALLER_SERIAL


def build_installer_image(installer_dir, image, extra_files=None, slack_mb=16):
    """ext4 image of `installer_dir` (plus extra_files {relpath: text}), no root needed."""
    if not shutil.which("mkfs.ext4"):
        raise RuntimeError("mkfs.ext4 not found (e2fsprogs)")
    stage = tempfile.mkdtemp(prefix="installer-stage-", dir=os.path.dirname(image))
    try:
        shutil.copytree(
            installer_dir, stage, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True
        )
        for rel, text in (extra_files or {}).items():
            path = os.path.join(stage, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(stage) for n in ns)
        mb = max(8, size // (1 << 20) + slack_mb)
        subprocess.run(
            ["mkfs.ext4", "-q", "-F", "-d", stage, image, f"{mb}M"],  # noqa: S603,S607
            check=True,
            stdout=subprocess.DEVNULL,
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return image


def type_line(vm, text):
    vm.qmp.type_text(text + "\n", delay=KEY_DELAY)


def run(vm, cmd, marker, timeout=60, to_serial=True):
    """Type `cmd` in the rescue shell with output to ttyS0, then echo `marker` and wait for it.

    Returns the serial text from before this call to the marker line. The marker is typed after
    the command's own output, so the caller can match on it. The marker is built from two parts so
    the typed echo of the command line itself cannot satisfy the wait.
    """
    start = len(vm.serial.text())
    head, tail = marker[: len(marker) // 2], marker[len(marker) // 2 :]
    redirect = " > /dev/ttyS0 2>&1" if to_serial else ""
    type_line(vm, f"( {cmd} ){redirect}; echo {head}''{tail} $? > /dev/ttyS0")
    vm.serial.wait_for(re.escape(marker) + r" \d+", timeout)
    return vm.serial.text()[start:]


def wait_for_shell(vm, timeout=180):
    """Keys typed before the autologin shell exists are lost: retry until it answers."""
    deadline = time.monotonic() + timeout
    time.sleep(30)  # keys typed while the autologin getty starts can wedge it (seen in about half of boots)
    while True:
        vm.qmp.send_key("ctrl", "c")
        type_line(vm, "echo DL-SHELL''-READY > /dev/ttyS0")
        try:
            vm.serial.wait_for(r"DL-SHELL-READY", 5)
            return
        except AssertionError:
            assert time.monotonic() < deadline, "no root shell answered on tty1"


@contextlib.contextmanager
def devloop_vm(
    iso=None, installer_dir=None, extra_files=None, net="none", mem=4096, target_size="60G", scratch=None,
    target_image=None,
):
    """Boot the ISO to the rescue shell with the installer image mounted at MOUNT.

    target_image: an existing image file (qcow2 or raw) to use as the target disk instead of a blank
    one (e.g. one that already has a GPT and a Windows-like NTFS partition).
    Yields the running QemuVM. Scratch lives under SCRATCH_ROOT and is removed on exit.
    """
    iso = iso or bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        raise FileNotFoundError("no ISO (set SECLEGION_ISO)")
    installer_dir = installer_dir or os.path.join(REPO, "installer")
    os.makedirs(SCRATCH_ROOT, exist_ok=True)
    keep = scratch is not None  # caller owns (and deletes) a scratch dir it passed in
    scratch = scratch or tempfile.mkdtemp(prefix="devloop-", dir=SCRATCH_ROOT)
    try:
        target = target_image or create_blank_disk(os.path.join(scratch, "target.qcow2"), target_size)
        image = build_installer_image(installer_dir, os.path.join(scratch, "installer.img"), extra_files)
        with QemuVM(
            iso,
            os.path.join(scratch, "vm"),
            net=net,
            memory_mb=mem,
            disks=[(target, TARGET_SERIAL)],
            ro_images=[(image, INSTALLER_SERIAL)],
            keep_vars=keep,  # a caller-owned scratch keeps OVMF_VARS (the installed system's boot entry)
        ) as vm:
            wait_for_menu(vm)
            choose(vm, bootgate.ENTRY_RESCUE)
            vm.serial.wait_for(r"SECLEGION-MODE=rescue", MODE_TIMEOUT)
            wait_for_shell(vm)
            out = run(vm, f"mkdir -p {MOUNT} && mount -o ro {INSTALLER_BY_ID} {MOUNT}", "DL-MOUNTED", 60)
            assert re.search(r"DL-MOUNTED 0", out), f"installer image did not mount: {out[-400:]}"
            yield vm
    finally:
        if not keep:
            shutil.rmtree(scratch, ignore_errors=True)
