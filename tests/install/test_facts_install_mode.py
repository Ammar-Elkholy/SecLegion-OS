# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Install mode = cmdline token AND target active/activating (a laptop without network stays activating)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "installer", "installd"))
import facts  # noqa: E402

INSTALL = "BOOT_IMAGE=x seclegion.mode=install systemd.unit=seclegion-install.target"


@pytest.mark.parametrize(
    "cmdline,state,want",
    [
        (INSTALL, "activating", True),
        (INSTALL, "active", True),
        ("BOOT_IMAGE=x seclegion.mode=install", "inactive", False),
        ("BOOT_IMAGE=x seclegion.mode=live systemd.unit=seclegion-live.target", "active", False),
        ("BOOT_IMAGE=x seclegion.mode=install", "failed", False),
        ("BOOT_IMAGE=x xseclegion.mode=install", "active", False),
    ],
)
def test_detect_install_mode(cmdline, state, want):
    assert facts.detect_install_mode(cmdline, state) is want


class Done:
    def __init__(self, stdout="", rc=0):
        self.stdout, self.returncode = stdout, rc


def fake_runner(state, rc=3, lsblk=None):
    """systemctl answers `state` with exit code rc (is-active: 3 for anything but active); the rest is
    empty. rc only applies to the is-active style; `show` exits 0 in every state."""

    def run(argv, **kw):
        if argv[0] == "lsblk":
            return Done(json.dumps(lsblk or {"blockdevices": []}))
        if argv[:2] == ["systemctl", "is-active"]:
            return Done(state + "\n", rc)
        if argv[:2] == ["systemctl", "show"]:
            assert "ActiveState" in argv
            return Done(state + "\n", 0)
        return Done("", 1)

    return run


@pytest.mark.parametrize("state,want", [("activating", True), ("active", True),
                                        ("inactive", False), ("failed", False)])
def test_gather_install_mode_from_the_target_state(monkeypatch, state, want):
    monkeypatch.setattr(facts.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(facts, "_read_cmdline", lambda: INSTALL)
    assert facts.gather(run=fake_runner(state))["install_mode"] is want


def test_gather_install_mode_needs_the_cmdline_token(monkeypatch):
    monkeypatch.setattr(facts.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(facts, "_read_cmdline", lambda: "BOOT_IMAGE=x seclegion.mode=live")
    assert facts.gather(run=fake_runner("activating"))["install_mode"] is False


def test_out_keeps_stdout_of_a_nonzero_exit():
    assert facts._out(["x"], fake_runner("activating", rc=3)) == ""  # unknown argv: empty
    assert facts._out(["systemctl", "is-active", "t"], fake_runner("activating", rc=3)) == "activating"


# ---- boot medium after copytoram ---------------------------------------------------------------

ISO_UUID = "2026-11-01-10-20-30-00"
CMD = f"BOOT_IMAGE=/arch/boot/x86_64/vmlinuz-linux archisosearchuuid={ISO_UUID} copytoram=y"


def disk(name, size, children=(), uuid=None):
    d = {"name": name, "path": f"/dev/{name}", "type": "disk", "size": size, "uuid": uuid,
         "children": list(children)}
    return d


def part(name, uuid=None, fstype=None):
    return {"name": name, "path": f"/dev/{name}", "type": "part", "size": 1 << 30, "uuid": uuid,
            "fstype": fstype}


def laptop(usb):
    return {"blockdevices": [
        disk("nvme0n1", 512 << 30,
             [part("nvme0n1p1", "AAAA-1111", "vfat"), part("nvme0n1p3", "1234", "ntfs")]),
        disk("nvme1n1", 512 << 30),
        usb,
    ]}


USB_VARIANTS = {
    "on_disk": disk("sda", 32 << 30, uuid=ISO_UUID),
    "on_sda1": disk("sda", 32 << 30, [part("sda1", ISO_UUID, "iso9660"), part("sda2", "EFI-1", "vfat")]),
    "on_sda2": disk("sda", 32 << 30, [part("sda1", "XX", "vfat"), part("sda2", ISO_UUID, "iso9660")]),
}


@pytest.mark.parametrize("variant", sorted(USB_VARIANTS))
def test_boot_disk_from_cmdline(variant):
    assert facts.boot_disk_from_cmdline(laptop(USB_VARIANTS[variant]), CMD) == "/dev/sda"


@pytest.mark.parametrize("cmd", [
    f"archisodevice=UUID={ISO_UUID} x=1",
    f"img_dev=/dev/disk/by-uuid/{ISO_UUID}",
])
def test_boot_disk_from_other_cmdline_forms(cmd):
    assert facts.boot_disk_from_cmdline(laptop(USB_VARIANTS["on_sda2"]), cmd) == "/dev/sda"


def test_boot_disk_from_cmdline_none_without_a_match():
    lsblk = laptop(USB_VARIANTS["on_sda1"])
    assert facts.boot_disk_from_cmdline(lsblk, "quiet") is None
    assert facts.boot_disk_from_cmdline(lsblk, "archisosearchuuid=nope") is None


def test_gather_finds_the_boot_usb_without_bootmnt(monkeypatch):
    monkeypatch.setattr(facts.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(facts, "_read_cmdline", lambda: INSTALL + f" archisosearchuuid={ISO_UUID}")
    got = facts.gather(run=fake_runner("activating", lsblk=laptop(USB_VARIANTS["on_sda1"])))
    assert got["boot_medium"] == "/dev/sda" and got["install_mode"] is True
