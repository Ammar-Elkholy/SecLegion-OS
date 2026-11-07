# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-installer-gui --print-facts: the disk page's verdicts as JSON, without GTK."""

import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "ui", "seclegion-installer-gui")
GIB = 1 << 30


def sd(name, size, children=()):
    return {"name": name, "path": f"/dev/{name}", "type": "disk", "size": size, "log-sec": 512,
            "model": "Disk " + name, "pttype": "gpt", "mountpoints": [None], "children": list(children)}


def laptop(install_mode):
    esp = {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "type": "part", "start": 2048,
           "size": 512 << 20, "fstype": "vfat", "mountpoints": [None]}
    return {"install_mode": install_mode, "dev_build": False, "boot_medium": "/dev/sda", "root_disk": None,
            "by_id": {}, "probes": {},
            "lsblk": {"blockdevices": [sd("nvme0n1", 512 * GIB, [esp]), sd("nvme1n1", 256 * GIB),
                                       sd("sda", 32 * GIB)]}}


def printed(tmp_path, facts):
    f = tmp_path / "facts.json"
    f.write_text(json.dumps(copy.deepcopy(facts)))
    r = subprocess.run([sys.executable, GUI, "--print-facts", "--facts", str(f)],
                       capture_output=True, text=True, check=True, timeout=60)
    return json.loads(r.stdout)


def test_print_facts_install_mode_disks_and_boot_usb(tmp_path):
    got = printed(tmp_path, laptop(True))
    assert got["install_mode"] is True and got["boot_medium"] == "/dev/sda"
    by = {d["path"]: d for d in got["disks"]}
    assert by["/dev/nvme0n1"]["refusal"] is None and by["/dev/nvme1n1"]["refusal"] is None
    assert by["/dev/sda"]["refusal"] == "boot_medium"
    assert by["/dev/nvme0n1"]["partitions"] == ["/dev/nvme0n1p1"] and by["/dev/nvme1n1"]["partitions"] == []


def test_print_facts_outside_install_mode_refuses_every_disk(tmp_path):
    got = printed(tmp_path, laptop(False))
    assert got["install_mode"] is False
    assert {d["refusal"] for d in got["disks"]} <= {"not_install_mode", "boot_medium"}
    assert next(d for d in got["disks"] if d["path"] == "/dev/nvme0n1")["refusal"] == "not_install_mode"


def test_print_facts_does_not_import_gtk(tmp_path):
    f = tmp_path / "facts.json"
    f.write_text(json.dumps(laptop(True)))
    code = ("import sys,runpy;sys.argv=['g','--print-facts','--facts',sys.argv[1]];"
            f"\ntry: runpy.run_path({GUI!r}, run_name='__main__')\nexcept SystemExit: pass\n"
            "assert 'gi' not in sys.modules and 'app' not in sys.modules")
    subprocess.run([sys.executable, "-c", code, str(f)], capture_output=True, check=True, timeout=60)
