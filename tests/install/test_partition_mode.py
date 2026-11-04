# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Partition mode: replace ONE existing partition, keep everything else (the owner's Legion layout)."""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import configurator as c  # noqa: E402
from configurator import Answers, Refusal, build_config, partition_choices  # noqa: E402

NVME = "/dev/nvme0n1"
MB = 1 << 20
GB = 1 << 30


@pytest.fixture
def legion_facts():
    with open(os.path.join(HERE, "fixtures", "facts_partitions.json")) as f:
        return json.load(f)


def disk(facts):
    return facts["lsblk"]["blockdevices"][0]


def part(facts, n):
    return next(p for p in disk(facts)["children"] if p["name"] == f"nvme0n1p{n}")


def ans(n=5, **kw):
    base = dict(disk=NVME, mode="partition", partition=f"/dev/nvme0n1p{n}",
                confirm=f"nvme0n1p{n}", username="u", password="p", timezone="UTC")
    base.update(kw)
    return Answers(**base)


def refuse(code, a, facts, **kw):
    with pytest.raises(Refusal) as e:
        c.validate(a, facts, **kw)
    assert e.value.code == code


def test_partition_mode_replaces_only_the_chosen_partition(legion_facts):
    cfg, _ = build_config(Answers(disk=NVME, mode="partition", partition="/dev/nvme0n1p5",
                                  confirm="nvme0n1p5", username="u", password="p"), legion_facts)
    dm = cfg["disk_config"]["device_modifications"][0]
    assert dm["wipe"] is False
    assert cfg["disk_config"]["config_type"] == "default_layout"
    status = {p["dev_path"]: p["status"] for p in dm["partitions"] if p["dev_path"]}
    assert status["/dev/nvme0n1p5"] == "delete"
    assert all(s == "existing" for d, s in status.items() if d != "/dev/nvme0n1p5")
    assert len(status) == 6
    new = [p for p in dm["partitions"] if p["status"] == "create"]
    p5 = part(legion_facts, 5)
    start = p5["start"] * 512
    end = start + p5["size"]
    lo = -(-start // MB) * MB  # aligned UP
    hi = end // MB * MB  # aligned DOWN
    assert lo > start and hi < end  # the fixture is off the MiB grid on both sides
    esp, root = new
    assert [esp["mountpoint"], esp["fs_type"], esp["flags"]] == ["/boot", "fat32", ["boot", "esp"]]
    assert esp["start"]["unit"] == "MiB" and esp["start"]["value"] * MB == lo
    assert esp["size"]["value"] * MB == c.ESP_SIZE
    assert root["start"]["value"] * MB == lo + c.ESP_SIZE
    assert root["start"]["value"] * MB + root["size"]["value"] * MB == hi
    assert hi == 615701 * MB and lo == 410902 * MB  # exact byte math, independent of the code
    assert root["size"]["value"] == 615701 - 410902 - 1024
    assert root["fs_type"] == "btrfs" and root["mount_options"] == ["compress=zstd"]
    assert [(v["name"], v["mountpoint"]) for v in root["btrfs"]] == c.SUBVOLS
    assert "disk_encryption" not in cfg["disk_config"]


def test_new_partitions_stay_inside_the_chosen_extent(legion_facts):
    cfg, _ = build_config(ans(), legion_facts)
    dm = cfg["disk_config"]["device_modifications"][0]
    p5 = part(legion_facts, 5)
    others = [p for p in dm["partitions"] if p["status"] == "existing"]
    for n in dm["partitions"]:
        if n["status"] != "create":
            continue
        s = n["start"]["value"] * MB
        e = s + n["size"]["value"] * MB
        assert p5["start"] * 512 <= s and e <= p5["start"] * 512 + p5["size"]
        for o in others:  # never touches a kept partition
            assert e <= o["start"]["value"] or s >= o["start"]["value"] + o["size"]["value"]


def test_kept_partitions_are_emitted_like_alongside(legion_facts):
    cfg, _ = build_config(ans(), legion_facts)
    dm = cfg["disk_config"]["device_modifications"][0]
    kept = {p["dev_path"]: p for p in dm["partitions"] if p["status"] == "existing"}
    assert kept["/dev/nvme0n1p1"]["flags"] == ["boot", "esp"]
    assert kept["/dev/nvme0n1p3"]["fs_type"] == "ntfs"
    assert all(p["mountpoint"] is None for p in kept.values())
    gone = next(p for p in dm["partitions"] if p["status"] == "delete")
    assert gone["dev_path"] == "/dev/nvme0n1p5" and gone["mountpoint"] is None


def test_partition_mode_with_luks_encrypts_only_the_new_root(legion_facts):
    cfg, creds = build_config(ans(luks=True, luks_passphrase="pass-phrase-9"), legion_facts)
    dm = cfg["disk_config"]["device_modifications"][0]
    root = next(p for p in dm["partitions"] if p["fs_type"] == "btrfs")
    assert cfg["disk_config"]["disk_encryption"]["partitions"] == [root["obj_id"]]
    assert creds["encryption_password"] == "pass-phrase-9"


def test_partition_mode_defaults_to_no_luks(legion_facts):
    a = ans()
    assert a.use_luks is False and a.effective_mode == "partition"


def test_post_hints_ask_for_the_windows_entry(legion_facts):
    assert c.post_hints(ans())["alongside"] is True


def test_summary_names_the_replaced_partition(legion_facts):
    cfg, _ = build_config(ans(), legion_facts)
    text = c.summary(cfg, ans())
    assert f"Disk:       {NVME} (replace /dev/nvme0n1p5)" in text
    assert "Mode:       partition" in text


def test_partition_choices_lists_all_six_and_only_p5_is_selectable(legion_facts):
    got = partition_choices(disk(legion_facts), legion_facts)
    assert [g[0] for g in got] == [f"/dev/nvme0n1p{n}" for n in range(1, 7)]
    assert [g[1] for g in got] == [int(p["size"]) for p in disk(legion_facts)["children"]]
    assert [g[2] for g in got] == ["part_is_esp", "part_is_windows", "part_is_windows",
                                   "part_is_windows", None, "part_too_small"]


# ---- one test per refusal code ----------------------------------------------

@pytest.mark.parametrize("n,code", [(1, "part_is_esp"), (2, "part_is_windows"),
                                    (3, "part_is_windows"), (4, "part_is_windows"),
                                    (6, "part_too_small")])
def test_refuse_unsuitable_partitions(legion_facts, n, code):
    refuse(code, ans(n), legion_facts)
    with pytest.raises(Refusal) as e:
        build_config(ans(n), legion_facts)
    assert e.value.code == code


def test_refuse_mounted_partition(legion_facts):
    part(legion_facts, 5)["mountpoints"] = ["/run/media/x"]
    refuse("part_mounted", ans(), legion_facts)


def test_refuse_partition_with_a_mounted_child(legion_facts):
    part(legion_facts, 5)["children"] = [{"name": "luks", "path": "/dev/mapper/luks", "type": "crypt",
                                          "mountpoints": ["/mnt"]}]
    refuse("part_mounted", ans(), legion_facts)


def test_refuse_another_mounted_partition_on_the_disk(legion_facts):
    part(legion_facts, 6)["mountpoints"] = ["/mnt/other"]
    refuse("mounted", ans(), legion_facts)


def test_refuse_unknown_filesystem_and_type(legion_facts):
    p = part(legion_facts, 5)
    p["fstype"] = None
    p["parttype"] = None
    refuse("part_unknown", ans(), legion_facts)
    p["parttype"] = ""
    refuse("part_unknown", ans(), legion_facts)


def test_unformatted_linux_partition_is_selectable(legion_facts):
    part(legion_facts, 5)["fstype"] = None  # parttype says Linux filesystem: fresh, nothing to lose
    c.validate(ans(), legion_facts)


def test_windows_type_is_compared_lowercase(legion_facts):
    part(legion_facts, 5)["parttype"] = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE"
    refuse("part_is_windows", ans(), legion_facts)
    part(legion_facts, 5)["parttype"] = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    refuse("part_is_esp", ans(), legion_facts)


def test_bitlocker_filesystem_is_windows(legion_facts):
    part(legion_facts, 5)["fstype"] = "BitLocker"
    assert partition_choices(disk(legion_facts), legion_facts)[4][2] == "part_is_windows"
    refuse("windows_unreadable", ans(), legion_facts)  # unprobed: the probe check fires first
    legion_facts["probes"]["/dev/nvme0n1p5"] = "clean"
    refuse("part_is_windows", ans(), legion_facts)


def test_refuse_partition_on_another_disk(legion_facts):
    other = copy.deepcopy(disk(legion_facts))
    other.update(name="nvme1n1", path="/dev/nvme1n1")
    for p in other["children"]:
        p["name"] = p["name"].replace("nvme0n1", "nvme1n1")
        p["path"] = p["path"].replace("nvme0n1", "nvme1n1")
    legion_facts["lsblk"]["blockdevices"].append(other)
    refuse("no_such_partition", ans(partition="/dev/nvme1n1p5", confirm="nvme1n1p5"), legion_facts)


def test_refuse_partition_that_does_not_exist(legion_facts):
    refuse("no_such_partition", ans(partition="/dev/nvme0n1p9", confirm="nvme0n1p9"), legion_facts)


def test_refuse_the_disk_itself_as_partition(legion_facts):
    refuse("no_such_partition", ans(partition=NVME, confirm="nvme0n1"), legion_facts)


def test_missing_partition_is_bad_partition():
    for missing in (None, ""):
        with pytest.raises(Refusal) as e:
            Answers(disk=NVME, mode="partition", partition=missing, username="u", password="p")
        assert e.value.code == "bad_partition"


@pytest.mark.parametrize("confirm", ["", "nvme0n1p6", "/dev/nvme0n1p5", "WD Blue SN580 1TB"])
def test_refuse_wrong_confirm(legion_facts, confirm):
    refuse("confirm_mismatch", ans(confirm=confirm), legion_facts)


def test_disk_model_does_not_confirm_partition_mode(legion_facts):
    with pytest.raises(Refusal) as e:
        build_config(ans(confirm="WD Blue SN580 1TB"), legion_facts)
    assert e.value.code == "confirm_mismatch"


# ---- disk-level checks stay in force ----------------------------------------

def test_disk_level_refusals_still_apply(legion_facts):
    f = copy.deepcopy(legion_facts)
    f["install_mode"] = False
    refuse("not_install_mode", ans(), f)
    f = copy.deepcopy(legion_facts)
    f["boot_medium"] = NVME
    refuse("boot_medium", ans(), f)
    f = copy.deepcopy(legion_facts)
    f["root_disk"] = NVME
    refuse("root_disk", ans(), f)
    f = copy.deepcopy(legion_facts)
    disk(f)["pttype"] = "dos"
    refuse("mbr_disk", ans(), f)
    f = copy.deepcopy(legion_facts)
    f["dev_build"] = True
    refuse("dev_build_real_disk", ans(), f)


def test_partition_mode_skips_the_disk_size_check(legion_facts):
    disk(legion_facts)["size"] = 15 * GB  # lsblk says small; only the chosen extent counts
    c.validate(ans(), legion_facts)


# ---- Windows probes behave as in alongside ----------------------------------

@pytest.mark.parametrize("probe,code", [("hibernated", "windows_hibernated"),
                                        ("bitlocker", "bitlocker"),
                                        ("unreadable", "windows_unreadable")])
def test_windows_probe_refuses_partition_mode(legion_facts, probe, code):
    legion_facts["probes"]["/dev/nvme0n1p3"] = probe
    refuse(code, ans(), legion_facts)
    with pytest.raises(Refusal) as e:
        build_config(ans(), legion_facts)
    assert e.value.code == code


def test_unprobed_ntfs_partition_fails_closed(legion_facts):
    legion_facts["probes"].pop("/dev/nvme0n1p4")
    refuse("windows_unreadable", ans(), legion_facts)


def test_defer_unreadable_is_honoured(legion_facts):
    legion_facts["probes"].pop("/dev/nvme0n1p4")
    c.validate(ans(), legion_facts, defer_unreadable=True)
    legion_facts["probes"]["/dev/nvme0n1p3"] = "hibernated"  # a real finding is never deferred
    refuse("windows_hibernated", ans(), legion_facts, defer_unreadable=True)
