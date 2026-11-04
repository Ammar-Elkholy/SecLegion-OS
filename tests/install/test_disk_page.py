# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Disk page (D4): one card per disk, erase / free space / replace-a-partition, the DiskMap segments,
and the partition-mode confirmation. Pure page tests on facts_partitions.json; the render runs under
Broadway only (skipped, never faked, when it is not available)."""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(ROOT, "installer", "installd"))
import configurator as c  # noqa: E402
import diskmap  # noqa: E402
from model import Model  # noqa: E402

NVME = "/dev/nvme0n1"
MODEL_NAME = "WD Blue SN580 1TB"
GIB = 1 << 30


@pytest.fixture
def facts():
    with open(os.path.join(HERE, "fixtures", "facts_partitions.json")) as f:
        return json.load(f)


def disk_of(facts):
    return facts["lsblk"]["blockdevices"][0]


def pmodel(facts, partition="/dev/nvme0n1p5"):
    m = Model(facts)
    p = m.pages["disk"]
    p.set_disk(NVME)
    if partition:
        p.set_partition(partition)
    return m


def fill_user(m):
    u = m.pages["user"]
    u.set_username("ammar")
    u.set_password("pw-1")
    u.set_confirm("pw-1")


# ---- partition rows ----------------------------------------------------------

def test_disk_page_rows_only_p5_is_selectable(facts):
    rows = pmodel(facts).pages["disk"].partition_rows(NVME)
    assert [r["path"] for r in rows] == [f"/dev/nvme0n1p{n}" for n in range(1, 7)]
    assert [r["code"] for r in rows] == ["part_is_esp", "part_is_windows", "part_is_windows",
                                          "part_is_windows", None, "part_too_small"]
    assert [r["selectable"] for r in rows] == [False, False, False, False, True, False]
    assert all(r["reason"] for r in rows if not r["selectable"])
    assert all(r["reason"] is None for r in rows if r["selectable"])


def test_disk_page_windows_reason_points_to_disk_management_then_free_space(facts):
    rows = pmodel(facts).pages["disk"].partition_rows(NVME)
    text = rows[2]["reason"]
    assert "Windows" in text and "Disk Management" in text and "free space" in text
    assert "Use free space" in text
    assert "EFI" in rows[0]["reason"] and "20 GiB" in rows[5]["reason"]


def test_disk_page_every_partition_refusal_code_has_a_sentence():
    from pages.p3_disk import PART_REASON
    for code in ("part_mounted", "part_is_esp", "part_is_windows", "part_unknown", "part_too_small"):
        assert PART_REASON[code].endswith(".")


def test_disk_page_unidentified_partition_is_not_selectable(facts):
    p5 = disk_of(facts)["children"][4]
    p5["fstype"] = None
    p5["parttype"] = None
    rows = pmodel(facts, None).pages["disk"].partition_rows(NVME)
    assert rows[4]["code"] == "part_unknown" and not rows[4]["selectable"]


def test_disk_page_mounted_partition_is_not_selectable(facts):
    disk_of(facts)["children"][4]["mountpoints"] = ["/run/media/x"]
    rows = pmodel(facts, None).pages["disk"].partition_rows(NVME)
    assert rows[4]["code"] == "part_mounted" and not rows[4]["selectable"]


# ---- page state --------------------------------------------------------------

def test_disk_page_partition_mode_fragment_and_next(facts):
    m = Model(facts)
    p = m.pages["disk"]
    p.set_disk(NVME)
    assert p.fragment() == {"disk": NVME, "mode": "erase", "luks": True}  # no partition key outside it
    p.set_partition("/dev/nvme0n1p5")
    assert p.mode == "partition" and p.can_next() and p.error() is None
    assert p.fragment() == {"disk": NVME, "mode": "partition", "luks": False,
                            "partition": "/dev/nvme0n1p5"}
    p.set_mode("alongside")
    assert "partition" not in p.fragment()


def test_disk_page_partition_mode_blocks_next_until_a_partition_is_picked(facts):
    p = Model(facts).pages["disk"]
    p.set_disk(NVME)
    p.set_mode("partition")
    assert not p.can_next() and "partition" in p.error().lower()


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6])
def test_disk_page_refused_pick_returns_the_refusal_sentence(facts, n):
    p = pmodel(facts, f"/dev/nvme0n1p{n}").pages["disk"]
    row = p.partition_rows(NVME)[n - 1]
    assert not p.can_next() and p.error() == row["reason"]


def test_disk_page_picking_another_disk_clears_the_partition(facts):
    other = copy.deepcopy(disk_of(facts))
    other.update(name="nvme1n1", path="/dev/nvme1n1")
    facts["lsblk"]["blockdevices"].append(other)
    p = pmodel(facts).pages["disk"]
    p.set_disk("/dev/nvme1n1")
    assert p.partition is None and p.mode == "erase"


def test_disk_page_windows_findings_block_partition_mode_with_guidance(facts):
    facts["probes"]["/dev/nvme0n1p3"] = "hibernated"
    p = pmodel(facts).pages["disk"]
    assert not p.can_next() and "fast startup" in p.error().lower()
    assert p.guide() and any("Fast Startup" in s for s in p.guide())
    facts["probes"]["/dev/nvme0n1p3"] = "bitlocker"
    assert not p.can_next() and p.guide()


def test_disk_page_partition_mode_skips_the_alongside_pages(facts):
    m = pmodel(facts)
    keys = [q.key for q in m.visible()]
    assert "alongside" not in keys and "manual" not in keys
    assert keys[:3] == ["welcome", "language", "disk"]


def test_disk_page_unavailable_disk_gets_plain_words(facts):
    facts["boot_medium"] = NVME
    d = Model(facts).pages["disk"].disks()[0]
    assert d["problem"] and d["reason"] and "installer started from" in d["reason"]
    assert d["model"] == MODEL_NAME and d["size"] == 1000204886016


def test_disk_page_free_space_option(facts):
    p = pmodel(facts, None).pages["disk"]
    opt = p.free_option(NVME)  # the fixture has a ~320 GiB free tail
    assert opt["selectable"] is True and opt["reason"] is None
    assert len(opt["gaps"]) == 1 and opt["gaps"][0][1] > 300 * GIB
    disk_of(facts)["size"] = 640 * GIB  # the tail shrinks under 40 GiB
    opt = p.free_option(NVME)
    assert opt["selectable"] is False and "40 GiB" in opt["reason"] and not opt["gaps"]


def test_disk_page_erase_option_unavailable_for_a_tiny_disk(facts):
    disk_of(facts)["size"] = 15 * GIB
    d = Model(facts).pages["disk"].disks()[0]
    assert d["code"] == "disk_too_small" and d["reason"]


# ---- validate agreement ------------------------------------------------------

def test_disk_page_merged_answers_pass_validate_in_partition_mode(facts):
    m = pmodel(facts)
    fill_user(m)
    r = m.pages["review"]
    assert r.expected() == "nvme0n1p5"
    assert not r.can_next() and "nvme0n1p5" in r.error()
    for wrong in (MODEL_NAME, "/dev/nvme0n1p5", "nvme0n1p6", ""):
        r.set_typed(wrong)
        assert not r.can_next(), wrong
    r.set_typed("nvme0n1p5")
    ans = m.answers()
    assert ans["mode"] == "partition" and ans["partition"] == "/dev/nvme0n1p5"
    assert ans["confirm"] == "nvme0n1p5"
    ans.update(timezone="UTC")
    c.validate(c.Answers.from_dict(ans), facts, defer_unreadable=True)
    assert r.can_next() and r.error() is None


def test_disk_page_review_still_asks_for_the_model_in_erase_mode(facts):
    m = pmodel(facts, None)
    fill_user(m)
    assert m.pages["review"].expected() == MODEL_NAME
    m.pages["disk"].set_mode("alongside")
    assert m.pages["review"].expected() == MODEL_NAME


def test_disk_page_review_has_no_expected_name_without_a_partition(facts):
    m = pmodel(facts, None)
    fill_user(m)
    m.pages["disk"].set_mode("partition")
    assert m.pages["review"].expected() is None


# ---- diskmap segments --------------------------------------------------------

def test_diskmap_segments_cover_the_disk_end_to_end_without_overlap(facts):
    disk = disk_of(facts)
    segs = diskmap.segments(disk)
    assert segs[0]["start"] == 0
    pos = 0
    for s in segs:
        assert s["start"] == pos and s["size"] > 0
        pos += s["size"]
    assert pos == int(disk["size"])
    assert {s["kind"] for s in segs} <= {"part", "free"}
    assert any(s["kind"] == "free" for s in segs)  # the leading pad, the gaps and the tail
    parts = [s for s in segs if s["kind"] == "part"]
    assert [s["name"] for s in parts] == [f"nvme0n1p{n}" for n in range(1, 7)]
    assert parts[2]["fstype"] == "ntfs" and parts[4]["size"] == 214748364800


def test_diskmap_segments_include_a_big_free_tail(facts):
    disk = disk_of(facts)
    disk["size"] = 2000 * GIB
    segs = diskmap.segments(disk)
    assert segs[-1]["kind"] == "free" and segs[-1]["size"] > 700 * GIB
    assert sum(s["size"] for s in segs) == 2000 * GIB


def test_diskmap_segments_of_an_empty_disk_is_one_free_segment():
    segs = diskmap.segments({"size": 100 * GIB, "children": []})
    assert segs == [{"name": "free", "path": None, "start": 0, "size": 100 * GIB, "fstype": None,
                     "kind": "free", "role": "free"}]


def test_diskmap_colors_come_from_the_tokens_never_hardcoded():
    pal = diskmap.palette()
    toml = open(os.path.join(ROOT, "desktop", "theme", "tokens.toml")).read().upper()
    assert all(v.upper().strip("#") in toml for v in pal.values())
    assert pal["esp"] != pal["windows"] != pal["linux"]
    src = open(os.path.join(ROOT, "installer", "ui", "gtk", "diskmap.py")).read()
    assert not re.search(r"#[0-9A-Fa-f]{6}\b", src)


def test_diskmap_roles_by_filesystem(facts):
    roles = [s["role"] for s in diskmap.segments(disk_of(facts)) if s["kind"] == "part"]
    assert roles == ["esp", "windows_system", "windows", "windows_system", "linux", "linux"]
    assert set(roles) <= set(diskmap.palette())


def test_human_sizes():
    assert diskmap.human(200 * GIB) == "200 GiB"
    assert diskmap.human(1 << 40) == "1.0 TiB"
    assert diskmap.human(272629760) == "260 MiB"


# ---- Broadway render ---------------------------------------------------------

def _free_display():
    run = os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")
    for n in range(90, 120):
        if not os.path.exists(os.path.join(run, f"broadway{n}.socket")):
            return n
    return 90


def test_disk_page_renders_under_broadway(tmp_path):
    broadwayd = shutil.which("gtk4-broadwayd")
    py = "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi, cairo; gi.require_version('Gtk','4.0');"
                       "gi.require_version('Adw','1')"], capture_output=True).returncode:
        pytest.skip("gi GTK4/libadwaita/cairo not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display()
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}")
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "gui_disk_probe.py")], env=env,
                           capture_output=True, text=True, timeout=90)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["disks"] == 1 and got["maps"] >= 1
    assert got["row_sensitive"] == {
        "/dev/nvme0n1p1": False, "/dev/nvme0n1p2": False, "/dev/nvme0n1p3": False,
        "/dev/nvme0n1p4": False, "/dev/nvme0n1p5": True, "/dev/nvme0n1p6": False}
    assert got["picked"] == "/dev/nvme0n1p5" and got["fragment"]["mode"] == "partition"
    assert got["narrow_ok"]
