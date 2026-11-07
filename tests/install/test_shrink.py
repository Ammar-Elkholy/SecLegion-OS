# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Install alongside by shrinking a partition: configurator judgement, plan and root-side apply (pure)."""
import copy
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import configurator as c  # noqa: E402
import shrink  # noqa: E402
from configurator import GIB, MIB, Answers, Refusal  # noqa: E402

SEC = 512
ESP = {"name": "vda1", "path": "/dev/vda1", "type": "part", "start": 2048, "size": 100 * MIB,
       "fstype": "vfat", "parttype": c.ESP_GUID, "mountpoints": [None]}
NTFS_START = 206848
WIN_TYPE = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"


def ntfs(size=200 * GIB, **kw):
    p = {"name": "vda2", "path": "/dev/vda2", "type": "part", "start": NTFS_START, "size": size,
         "fstype": "ntfs", "label": "Windows", "parttype": WIN_TYPE, "partn": 2,
         "partuuid": "11111111-2222-3333-4444-555555555555", "partlabel": "Basic data partition",
         "pkname": "vda", "mountpoints": [None]}
    p.update(kw)
    return p


def facts_for(parts, disk_size=None, **kw):
    end = max(int(p["start"]) * SEC + int(p["size"]) for p in parts)
    disk = {"name": "vda", "path": "/dev/vda", "type": "disk", "size": disk_size or end + GIB,
            "log-sec": SEC, "model": "QEMU HARDDISK", "vendor": "ATA", "pttype": "gpt",
            "mountpoints": [None], "children": parts}
    f = {"install_mode": True, "dev_build": True, "boot_medium": "/dev/sda", "root_disk": None,
         "by_id": {}, "probes": {"/dev/vda2": "clean"}, "lsblk": {"blockdevices": [disk]}}
    f.update(kw)
    return f


def ans(**kw):
    base = dict(disk="/dev/vda", username="u", password="p", timezone="UTC", mode="alongside",
                confirm="QEMU HARDDISK", shrink="/dev/vda2", shrink_size=100 * GIB)
    base.update(kw)
    return Answers(**base)


def disk_of(f):
    return f["lsblk"]["blockdevices"][0]


def refuse(code, a, f):
    with pytest.raises(Refusal) as e:
        c.validate(a, f)
    assert e.value.code == code


@pytest.fixture
def full():
    """200 GiB NTFS filling the disk (1 GiB of tail slack): no usable free gap."""
    return facts_for([ESP, ntfs()])


def test_choices_ntfs_200gib_shrinkable(full):
    (ch,) = c.shrink_choices(disk_of(full), full)  # the vfat ESP is not listed
    assert ch["path"] == "/dev/vda2" and ch["fstype"] == "ntfs" and ch["code"] is None
    assert ch["size"] == 200 * GIB and ch["max_size"] == 160 * GIB and ch["min_size"] == 20 * GIB
    assert ch["name"] == "vda2" and ch["label"] == "Windows"


def test_choices_codes():
    f = facts_for([ESP, ntfs(size=50 * GIB)])
    (ch,) = c.shrink_choices(disk_of(f), f)
    assert ch["code"] == "shrink_too_small" and ch["max_size"] < ch["min_size"]
    f = facts_for([ESP, ntfs(mountpoints=["/mnt/win"])])
    assert c.shrink_choices(disk_of(f), f)[0]["code"] == "shrink_mounted"
    f = facts_for([ESP, ntfs()], boot_medium="/dev/vda")
    assert c.shrink_choices(disk_of(f), f)[0]["code"] == "shrink_boot_medium"
    f = facts_for([ESP, ntfs()], probes={"/dev/vda2": "bitlocker"})
    assert c.shrink_choices(disk_of(f), f)[0]["code"] == "bitlocker"
    f = facts_for([ESP, ntfs()], probes={"/dev/vda2": "hibernated"})
    assert c.shrink_choices(disk_of(f), f)[0]["code"] == "windows_hibernated"
    f = facts_for([ESP, ntfs()], probes={"/dev/vda2": "unreadable"})
    assert c.shrink_choices(disk_of(f), f)[0]["code"] is None  # root re-checks


def test_validate_good_shrink_needs_no_existing_gap(full):
    refuse("gap_too_small", ans(shrink=None, shrink_size=None), full)
    c.validate(ans(), full)
    c.validate(ans(shrink_size=160 * GIB), full)
    c.validate(ans(shrink_size=c.MIN_KEEP), full)


@pytest.mark.parametrize("size", [c.MIN_KEEP - MIB, 160 * GIB + MIB, 100 * GIB + 512, 100 * GIB + 1])
def test_validate_bad_size(full, size):
    refuse("shrink_bad_size", ans(shrink_size=size), full)


def test_answers_shrink_rules():
    with pytest.raises(Refusal):
        ans(mode="erase")
    with pytest.raises(Refusal):
        ans(shrink_size=None)
    with pytest.raises(Refusal):
        ans(shrink=None)


def test_validate_refusals(full):
    refuse("shrink_bad_partition", ans(shrink="/dev/vda9"), full)
    refuse("shrink_bad_partition", ans(shrink="/dev/vda1"), full)  # vfat: not shrinkable
    other = copy.deepcopy(full)
    d2 = copy.deepcopy(disk_of(full))
    d2.update(name="vdb", path="/dev/vdb", children=[ntfs(name="vdb1", path="/dev/vdb1")])
    other["lsblk"]["blockdevices"].append(d2)
    other["probes"]["/dev/vdb1"] = "clean"
    refuse("shrink_bad_partition", ans(shrink="/dev/vdb1"), other)
    refuse("shrink_mounted", ans(), facts_for([ESP, ntfs(mountpoints=["/mnt/w"])]))
    refuse("bitlocker", ans(), facts_for([ESP, ntfs()], probes={"/dev/vda2": "bitlocker"}))
    refuse("windows_hibernated", ans(), facts_for([ESP, ntfs()], probes={"/dev/vda2": "hibernated"}))
    refuse("shrink_too_small", ans(shrink_size=20 * GIB), facts_for([ESP, ntfs(size=50 * GIB)]))
    refuse("boot_medium", ans(), facts_for([ESP, ntfs()], boot_medium="/dev/vda"))  # disk-level check first


def test_shrunk_disk_is_a_copy(full):
    d = disk_of(full)
    s = c.shrunk_disk(d, "/dev/vda2", 100 * GIB)
    assert d["children"][1]["size"] == 200 * GIB and s["children"][1]["size"] == 100 * GIB
    g = c.free_gaps(s)
    assert len(g) == 1 and g[0][1] >= 100 * GIB - 2 * MIB


def test_build_config_uses_the_freed_gap(full):
    cfg, _ = c.build_config(ans(), full)
    dm = cfg["disk_config"]["device_modifications"][0]
    assert dm["wipe"] is False
    existing = {p["dev_path"]: p for p in dm["partitions"] if p["dev_path"]}
    assert set(existing) == {"/dev/vda1", "/dev/vda2"}
    assert all(p["status"] == "existing" for p in existing.values())
    assert existing["/dev/vda2"]["size"]["value"] == 100 * GIB
    new_end = NTFS_START * SEC + 100 * GIB
    esp, root = [p for p in dm["partitions"] if p["status"] == "create"]
    lo = -(-new_end // MIB) * MIB
    assert esp["start"]["value"] * MIB == lo
    assert root["start"]["value"] * MIB == lo + c.ESP_SIZE
    assert root["start"]["value"] + root["size"]["value"] <= int(disk_of(full)["size"]) // MIB - 1


NTFS_PLAN = [
    ["ntfsresize", "--no-action", "--force", "--size", str(100 * GIB), "/dev/vda2"],
    ["ntfsresize", "--force", "--size", str(100 * GIB), "/dev/vda2"],
    ["sgdisk", "--delete=2", f"--new=2:{NTFS_START}:{NTFS_START + 100 * GIB // SEC - 1}",
     f"--typecode=2:{WIN_TYPE}", "--partition-guid=2:11111111-2222-3333-4444-555555555555",
     "--change-name=2:Basic data partition", "/dev/vda"],
    ["partprobe", "/dev/vda"],
    ["udevadm", "settle"],
]


def test_plan_ntfs_exact():
    assert shrink.plan_commands(ntfs(), 100 * GIB, SEC) == NTFS_PLAN


def test_plan_ext4_exact():
    p = ntfs(fstype="ext4", path="/dev/vda3", partn=3, partlabel=None,
             parttype="0fc63daf-8483-4772-8e79-3d69d8477de4", start=1000)
    got = shrink.plan_commands(p, 50 * GIB, SEC, disk="/dev/vda")
    assert got[:2] == [["e2fsck", "-f", "-y", "/dev/vda3"],
                       ["resize2fs", "/dev/vda3", f"{50 * GIB // 1024}K"]]
    assert got[2] == ["sgdisk", "--delete=3", f"--new=3:1000:{1000 + 50 * GIB // SEC - 1}",
                      "--typecode=3:0fc63daf-8483-4772-8e79-3d69d8477de4",
                      "--partition-guid=3:11111111-2222-3333-4444-555555555555", "/dev/vda"]
    assert got[3:] == [["partprobe", "/dev/vda"], ["udevadm", "settle"]]


def test_plan_orders_fs_before_table():
    plan = shrink.plan_commands(ntfs(), GIB, SEC)
    names = [a[0] + (a[1] if a[0] == "ntfsresize" else "") for a in plan]
    assert names.index("ntfsresize--no-action") < names.index("ntfsresize--force") < names.index("sgdisk")


class Runner:
    def __init__(self, fail_at=None, out="", rc=1):
        self.calls, self.fail_at, self.out, self.rc = [], fail_at, out, rc

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        bad = self.fail_at is not None and len(self.calls) - 1 == self.fail_at
        return subprocess.CompletedProcess(argv, self.rc if bad else 0, "", self.out if bad else "")


def test_apply_runs_the_plan(full):
    r = Runner()
    shrink.apply(ans(), full, run=r)
    assert r.calls == NTFS_PLAN


def test_apply_dry_run_refusal_writes_nothing(full):
    r = Runner(fail_at=0, out="ntfsresize v2022\nERROR(16): Windows is hibernated\n")
    with pytest.raises(Refusal) as e:
        shrink.apply(ans(), full, run=r)
    assert e.value.code == "shrink_fs_refused" and "hibernated" in e.value.message
    assert len(r.calls) == 1 and r.calls[0][1] == "--no-action"


def test_apply_fs_failure_leaves_table_alone(full):
    r = Runner(fail_at=1, out="boom")
    with pytest.raises(Refusal):
        shrink.apply(ans(), full, run=r)
    assert not any(a[0] == "sgdisk" for a in r.calls)


def test_apply_revalidates_before_any_command():
    r = Runner()
    f = facts_for([ESP, ntfs()], probes={"/dev/vda2": "hibernated"})
    with pytest.raises(Refusal):
        shrink.apply(ans(), f, run=r)
    assert r.calls == []
