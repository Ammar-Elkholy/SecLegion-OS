# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Disk page B2: every disk shows its analysis (D1) and "install alongside: shrink a partition" with a
size slider (D2). Pure logic only; configurator.shrink_choices comes from a parallel branch, so a stub with
its documented shape stands in for it here."""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "installer", "installd"))

import configurator as c  # noqa: E402
from model import Model  # noqa: E402
from pages import p3_disk, p8_review  # noqa: E402

NVME = "/dev/nvme0n1"
P3 = "/dev/nvme0n1p3"
GIB = 1 << 30
MIB = 1 << 20


@pytest.fixture
def facts():
    with open(os.path.join(HERE, "fixtures", "facts_partitions.json")) as f:
        return json.load(f)


def _stub_choices(disk, facts):
    """The documented shape of configurator.shrink_choices: Windows p3 shrinkable (min 120 GiB)."""
    out = []
    for p in disk["children"]:
        win = p.get("fstype") == "ntfs" and p["parttype"] != p3_disk.RECOVERY_GUID
        out.append({"path": p["path"], "name": p["name"], "fstype": p.get("fstype"),
                    "label": p.get("label"), "size": int(p["size"]), "min_size": 120 * GIB,
                    "max_size": int(p["size"]),
                    "code": None if win else ("bitlocker" if p["path"] == "/dev/nvme0n1p4" else
                                              "shrink_too_small")})
    return out


@pytest.fixture
def shrink(monkeypatch):
    monkeypatch.setattr(c, "shrink_choices", _stub_choices, raising=False)


def page_of(facts):
    m = Model(facts)
    p = m.pages["disk"]
    p.set_disk(NVME)
    return m, p


# ---- D1: describe_partition and rows for refused disks ------------------------------------------

@pytest.mark.parametrize("part,what", [
    ({"fstype": "ntfs", "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"}, "Windows"),
    ({"fstype": "BitLocker"}, "Windows"),
    ({"fstype": "vfat", "parttype": c.ESP_GUID}, "EFI system"),
    ({"fstype": "ntfs", "parttype": "DE94BBA4-06D1-4D40-A16A-BFD50179D6AC"}, "Recovery"),
    ({"fstype": "ext4"}, "Linux"), ({"fstype": "btrfs"}, "Linux"), ({"fstype": "xfs"}, "Linux"),
    ({"fstype": "swap"}, "Swap"), ({"fstype": "crypto_LUKS"}, "Unknown"), ({}, "Unknown"),
])
def test_describe_partition_mapping(part, what):
    assert p3_disk.describe_partition(part) == what


def test_refused_disk_still_yields_its_partition_rows(facts):
    facts["install_mode"] = False
    _m, p = page_of(facts)
    assert p.disks()[0]["code"] == "not_install_mode"
    rows = p.analysis(NVME)
    parts = [r for r in rows if r["kind"] == "part"]
    assert [r["name"] for r in parts] == [f"nvme0n1p{i}" for i in range(1, 7)]
    assert [r["what"] for r in parts] == ["EFI system", "Unknown", "Windows", "Recovery", "Linux", "Linux"]
    free = [r for r in rows if r["kind"] == "free"]
    assert len(free) == 1 and free[0]["what"] == "Free space" and free[0]["size"] > 300 * GIB
    assert [r["start"] for r in rows] == sorted(r["start"] for r in rows)


def test_free_gaps_under_one_gib_are_not_rows():
    disk = {"size": 100 * GIB, "log-sec": 512, "children": [
        {"type": "part", "path": "/dev/x1", "name": "x1", "fstype": "ext4", "size": 99 * GIB + 512 * MIB,
         "start": 2048}]}
    assert [r["kind"] for r in p3_disk.analysis_rows(disk)] == ["part"]


# ---- D2: slider math and page state -----------------------------------------------------------

def test_shrink_hidden_without_configurator_support(facts, monkeypatch):
    monkeypatch.delattr(c, "shrink_choices")
    _m, p = page_of(facts)
    assert p.shrink_supported() is False and p.shrink_options(NVME) == []
    p.set_mode("alongside")
    assert "shrink" not in p.fragment()


def test_use_free_space_fragment_carries_shrink_none(facts, shrink):
    _m, p = page_of(facts)
    p.set_mode("alongside")
    f = p.fragment()
    assert f["mode"] == "alongside" and f["shrink"] is None and f["shrink_size"] is None


def test_shrink_reasons_are_plain_words():
    for code in ("shrink_mounted", "shrink_boot_medium", "shrink_too_small", "bitlocker",
                 "windows_hibernated", "shrink_bad_partition", "shrink_bad_size", "shrink_fs_refused"):
        assert p3_disk.REASONS[code]
    assert "Fast Startup" in p3_disk.REASONS["shrink_fs_refused"]
    assert "BitLocker" in p3_disk.REASONS["bitlocker"]


def test_shrink_options_list_refused_ones_with_reason(facts, shrink):
    _m, p = page_of(facts)
    byp = {o["path"]: o for o in p.shrink_options(NVME)}
    assert byp[P3]["selectable"] and byp[P3]["reason"] is None and byp[P3]["title"] == "Windows"
    assert not byp["/dev/nvme0n1p4"]["selectable"] and "BitLocker" in byp["/dev/nvme0n1p4"]["reason"]


def test_shrink_fragment_bytes_mib_aligned(facts, shrink):
    _m, p = page_of(facts)
    p.set_shrink_mode()
    assert p.shrink_path == P3 and p.mode == "alongside"
    size = 429496729600  # 400 GiB
    f = p.fragment()  # default: min(100 GiB, half) = 100 GiB for SecLegion
    assert f["mode"] == "alongside" and f["shrink"] == P3 and f["shrink_size"] == size - 100 * GIB
    p.set_shrink_space(150 * GIB)
    assert p.fragment()["shrink_size"] == size - 150 * GIB
    assert p.fragment()["shrink_size"] % MIB == 0
    assert p.shrink_summary() == "SecLegion: 150 GiB · Windows: 250 GiB left"


def test_shrink_space_is_clamped_to_the_bounds(facts, shrink):
    _m, p = page_of(facts)
    p.set_shrink_mode()
    p.set_shrink_space(1 * GIB)
    assert p.shrink_amount() == c.MIN_GAP
    p.set_shrink_space(900 * GIB)
    assert p.shrink_amount() == 280 * GIB  # 400 GiB - min_size 120 GiB
    assert p.fragment()["shrink_size"] == 120 * GIB


def test_unaligned_size_floors_to_mib():
    opt = {"size": 100 * GIB + 700 * 1024, "min_size": 10 * GIB}
    assert p3_disk.shrunk_size(opt, 40 * GIB) == (60 * GIB + 700 * 1024) // MIB * MIB


def test_shrink_state_survives_back_and_next_and_is_cleared_by_other_choices(facts, shrink):
    m, p = page_of(facts)
    p.set_shrink_mode()
    p.set_shrink_space(120 * GIB)
    for _ in range(3):
        m.next()  # welcome, language, time zone -> disk page (index 3)
    m.index = 3
    assert m.current.key == "disk" and m.can_next()
    assert "alongside" not in [x.key for x in m.visible()]
    m.next()
    m.back()
    assert (p.shrink_on, p.shrink_path, p.shrink_amount()) == (True, P3, 120 * GIB)
    p.set_mode("alongside")  # free space: the shrink choice is off, the keys say so
    assert p.fragment()["shrink"] is None and "alongside" in [x.key for x in m.visible()]
    p.set_shrink_mode()
    p.set_disk(NVME)  # same disk: kept
    assert p.shrink_on
    p.set_mode("erase")
    assert p.fragment().get("shrink") is None and not p.shrink_on


def test_shrink_without_a_choosable_partition_blocks_next(facts, shrink, monkeypatch):
    monkeypatch.setattr(c, "shrink_choices", lambda d, f: [dict(o, code="shrink_too_small")
                                                           for o in _stub_choices(d, f)])
    _m, p = page_of(facts)
    p.set_shrink_mode()
    assert p.shrink_path is None and p.error() and p.fragment()["shrink"] is None


# ---- review ----------------------------------------------------------------------------------

def test_review_line_names_the_shrink(facts, shrink):
    m, p = page_of(facts)
    p.set_shrink_mode()
    p.set_shrink_space(150 * GIB)
    review = m.pages["review"]
    assert review.shrink_line() == f"Shrink {P3} (Windows) from 400 GiB to 250 GiB"
    # Answers has no shrink field on this base (parallel branch): stub what needs it
    review.expected, review.disk_label = lambda: None, lambda: "disk"
    assert review.shrink_line() in [r[2] for r in p8_review.summary_rows(review)]
    p.set_mode("alongside")
    assert review.shrink_line() == ""


def test_real_shrink_choices_fragment_passes_validate(facts):
    """The page against the merged configurator: its fragment is a shrink the judge accepts."""
    _m, p = page_of(facts)
    p.set_shrink_mode()
    p.set_shrink_partition(P3)
    frag = p.fragment()
    assert frag["shrink"] == P3 and frag["shrink_size"] % MIB == 0
    disk = next(d for d in facts["lsblk"]["blockdevices"] if d["path"] == NVME)
    confirm = (disk.get("model") or disk.get("name")).strip()
    answers = c.Answers.from_dict(dict(frag, username="x", password="x", confirm=confirm))
    c.validate(answers, facts)
    c.build_config(answers, facts)
