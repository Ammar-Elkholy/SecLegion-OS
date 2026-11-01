# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import subprocess
import sys

from tests.unit.conftest import REPO, load_tool

cs = load_tool("check-space")
GIB = 1024**3

MOUNTINFO = """\
22 1 253:0 / / rw,relatime shared:1 - ext4 /dev/mapper/root rw
40 22 8:3 / /mnt/Dev_Lab rw,nosuid shared:2 - fuseblk /dev/sda3 rw,user_id=0
41 40 8:3 /x /mnt/Dev_Lab/with\\040space rw shared:3 - ext4 /dev/sdb1 rw
50 22 0:44 / /var/tmp rw shared:4 - tmpfs tmpfs rw
"""


def test_ext4_with_space_is_ok():
    assert cs.check("/var/lib/foo", 25, MOUNTINFO, 100 * GIB) == []


def test_fuseblk_refused_with_name_in_message():
    problems = cs.check("/mnt/Dev_Lab/build", 25, MOUNTINFO, 100 * GIB)
    assert len(problems) == 1 and "fuseblk" in problems[0]


def test_ntfs_names_refused():
    for fstype in ("ntfs", "ntfs3", "fuse.ntfs-3g"):
        info = f"1 0 8:1 / /data rw - {fstype} /dev/sda1 rw\n"
        assert cs.check("/data/x", 25, info, 100 * GIB), fstype


def test_low_space_refused():
    problems = cs.check("/home/u", 25, MOUNTINFO, 24 * GIB)
    assert len(problems) == 1 and "GiB free" in problems[0]


def test_exactly_min_space_ok():
    assert cs.check("/home/u", 25, MOUNTINFO, 25 * GIB) == []


def test_both_problems_reported():
    assert len(cs.check("/mnt/Dev_Lab", 25, MOUNTINFO, GIB)) == 2


def test_longest_mount_wins_and_escapes_decoded():
    assert cs.fstype_for("/mnt/Dev_Lab/with space/a", MOUNTINFO) == "ext4"
    assert cs.fstype_for("/mnt/Dev_Lab/other", MOUNTINFO) == "fuseblk"
    assert cs.fstype_for("/mnt/Dev_Lab_not", MOUNTINFO) == "ext4"  # prefix is not a path match


def test_nearest_existing_walks_up(tmp_path):
    assert cs.nearest_existing(str(tmp_path / "a" / "b")) == str(tmp_path)


def test_cli_refuses_fuseblk_on_this_host_if_present():
    # Real-host check: if /mnt/Dev_Lab is fuseblk the CLI must refuse it and say why.
    with open("/proc/self/mountinfo", encoding="utf-8") as handle:
        info = handle.read()
    if cs.fstype_for("/mnt/Dev_Lab", info) != "fuseblk":
        return
    proc = subprocess.run([sys.executable, REPO + "/tools/check-space", "/mnt/Dev_Lab"],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and "fuseblk" in proc.stderr


FORBIDDEN = "/mnt/Dev_Lab"


def test_path_under_dev_lab_is_refused_by_location():
    for path in (FORBIDDEN, FORBIDDEN + "/x/y", FORBIDDEN + "/not/created/yet"):
        problems = cs.forbidden_problems(path)
        assert len(problems) == 1 and FORBIDDEN in problems[0], path


def test_lookalike_and_other_paths_are_not_forbidden():
    for path in ("/mnt/Dev_Lab_not", "/mnt/Dev_Labx/a", "/var/tmp/seclegion-build", "/mnt"):
        assert cs.forbidden_problems(path) == [], path


def test_symlink_into_dev_lab_is_refused_by_realpath(tmp_path):
    link = tmp_path / "innocent"
    link.symlink_to(FORBIDDEN + "/some/dir")
    problems = cs.forbidden_problems(str(link / "build"))
    assert len(problems) == 1 and "resolves to" in problems[0]


def test_cli_refuses_a_symlink_into_dev_lab_whatever_the_filesystem(tmp_path):
    # The location rule must speak for itself, not lean on the fuseblk refusal.
    link = tmp_path / "innocent"
    link.symlink_to(FORBIDDEN + "/some/dir")
    proc = subprocess.run([sys.executable, REPO + "/tools/check-space", "--min-gib", "0", str(link)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and f"under {FORBIDDEN}" in proc.stderr
