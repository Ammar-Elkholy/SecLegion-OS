# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""VM gate: the installer GUI's facts on a copytoram install boot (the real-laptop failure of ISO #12).

ISO #12 showed every disk as "not_install_mode" on metal (systemctl is-active exits 3 while the target is
"activating") and would have offered the boot USB as a target once archiso unmounted bootmnt (copytoram).
This boots the Install entry with copytoram=y added in GRUB's edit mode, no NIC, two blank target disks, and
the selftest action `print-facts`, which runs `seclegion-installer-gui --print-facts` as the kiosk user
(runuser -u seclegion-installer) and prints the result as a gui_facts line on the serial console. (The kiosk
has no shell, so the selftest credential is the way to run a command in an install-mode guest.)

Checks: install_mode true; boot_medium is the ISO device (the harness attaches the ISO as a CD-ROM, so
/dev/sr<N>, not a real USB /dev/sda); both target disks have refusal null and 2 disks are listed.
Needs the selftest `print-facts` action and `--print-facts` from this branch in the ISO. Not run yet: no ISO
with them exists. NOT checked: the GRUB edit keystrokes (e, End, text, Ctrl-X) are unproven on this menu;
the test asserts copytoram shows in the kernel command line echoed on serial.
"""
import json
import os
import re
import shutil
import tempfile
import time

import pytest

import evidence
from tests.lib import bootgate
from tests.lib.bootgate import MODE_TIMEOUT, wait_for_menu
from tests.lib.qemu import QemuVM, create_blank_disk

PREFIX = "SECLEGION-SELFTEST "
DISK_SERIALS = ("SLFACT1", "SLFACT2")
EXTRA_ARG = " copytoram=y"


def edit_cmdline(vm, index, extra):
    """Open GRUB's editor on entry `index`, append `extra` to the linux line, boot with Ctrl-X."""
    bootgate.press(vm, *["down"] * index)
    time.sleep(bootgate.KEY_SETTLE)
    bootgate.press(vm, "e")
    time.sleep(2)
    bootgate.press(vm, "end")  # the cursor starts on the linux line (the first line of the entry)
    vm.qmp.type_text(extra, delay=0.03)
    time.sleep(bootgate.KEY_SETTLE)
    vm.qmp.send_key("ctrl", "x")


def gui_facts(serial_text):
    for line in evidence.ANSI_RE.sub("", serial_text).splitlines():
        if PREFIX in line:
            try:
                obj = json.loads(line.split(PREFIX, 1)[1])
            except ValueError:
                continue
            if obj.get("section") == "gui_facts":
                return obj
    return None


@pytest.mark.iso
def test_m2_kiosk_facts_copytoram_install_boot():
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("no ISO (set SECLEGION_ISO)")
    root = "/var/tmp/seclegion-build/vm"  # image files only live here
    os.makedirs(root, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="m2facts-", dir=root)
    try:
        disks = [(create_blank_disk(os.path.join(scratch, f"t{n}.qcow2"), "60G"), serial)
                 for n, serial in enumerate(DISK_SERIALS)]
        with QemuVM(iso, os.path.join(scratch, "vm"), net="none", disks=disks,
                    credentials=[("seclegion.selftest", "print-facts")]) as vm:
            wait_for_menu(vm)
            edit_cmdline(vm, bootgate.ENTRY_INSTALL, EXTRA_ARG)
            vm.serial.wait_for(r'SECLEGION-SELFTEST \{"section": "done"', MODE_TIMEOUT)
            text = vm.serial.text()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    assert "seclegion.mode=install" in text and "copytoram" in text, "edited cmdline not seen on serial"
    got = gui_facts(text)
    assert got and got["rc"] == 0 and got["facts"], f"no gui_facts line: {got}"
    facts = got["facts"]
    assert facts["install_mode"] is True, facts
    assert re.fullmatch(r"/dev/sr\d+", facts["boot_medium"] or ""), facts  # the ISO CD-ROM of the harness
    paths = [d["path"] for d in facts["disks"]]
    assert len(paths) == 2 and all(d["refusal"] is None for d in facts["disks"]), facts
    assert facts["boot_medium"] not in paths
