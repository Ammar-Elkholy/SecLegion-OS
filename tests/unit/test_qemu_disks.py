# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""QemuVM extra disks / read-only images / boot / mem options (devloop support). No QEMU needed."""
import pytest

from tests.lib import qemu


def test_disks_become_scsi_hd_with_serials_and_ro_images_are_readonly():
    cmd = qemu.build_command("/i", "/c", "/v", 5, 6, "/s", disks=[("/w/t.qcow2", "SLTARGET")],
                             ro_images=[("/w/inst.img", "SLINST")], boot="disk")
    joined = " ".join(cmd)
    assert "file=/w/t.qcow2,if=none,id=d1,format=qcow2" in joined
    assert "scsi-hd,drive=d1,bus=scsi0.0,serial=SLTARGET,bootindex=0" in joined
    assert "file=/w/inst.img,if=none,id=d2,format=raw,readonly=on" in joined
    assert "serial=SLINST" in joined and "bootindex" not in joined.split("SLINST")[1]
    with pytest.raises(ValueError):
        qemu.build_command("/i", "/c", "/v", 5, 6, "/s", boot="net")


def test_defaults_add_no_extra_drives():
    cmd = qemu.build_command("/i", "/c", "/v", 5, 6, "/s")
    assert not any("scsi-hd" in a or "bootindex" in a for a in cmd)


@pytest.mark.parametrize("key", ["disks", "ro_images"])
def test_qemuvm_refuses_dev_paths_in_disks(key, tmp_path):
    image = tmp_path / "ok.iso"
    image.write_bytes(b"x")
    with pytest.raises(qemu.DevicePathRefused):
        qemu.QemuVM(str(image), tmp_path, **{key: ["/dev/sda"]})
    with pytest.raises(qemu.DevicePathRefused):
        qemu.QemuVM(str(image), tmp_path, **{key: [("/dev/../dev/nvme0n1", "X")]})
    assert qemu.QemuVM(str(image), tmp_path, **{key: [str(tmp_path / "t.qcow2")]}).iso == str(image)


def test_create_blank_disk_refuses_dev():
    with pytest.raises(qemu.DevicePathRefused):
        qemu.create_blank_disk("/dev/shm/x.qcow2")


def test_mem_is_an_alias_for_memory_mb(tmp_path):
    image = tmp_path / "ok.iso"
    image.write_bytes(b"x")
    assert qemu.QemuVM(str(image), tmp_path, mem=2048).options["memory_mb"] == 2048
