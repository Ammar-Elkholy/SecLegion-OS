# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-rescue rollback (V2): the script runs against stub binaries that record their argv. No root.

rollback needs --yes; without it the script prints its plan, runs no mutating command and exits 2."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "pkgs" / "seclegion-rescue" / "seclegion-rescue"

STUB = """#!/usr/bin/env bash
name=${0##*/}
echo "$name $*" >> "$STUB_LOG"
last=${*: -1}
case "$name" in
    id) echo "${STUB_UID:-0}" ;;
    findmnt) case "$*" in *SOURCE*) echo "/dev/vda3[/@]" ;; *FSTYPE*) echo "${STUB_FSTYPE:-btrfs}" ;; esac ;;
    mount)
        if [[ $* == *subvolid=5* ]]; then
            mkdir -p "$last/@"
            for n in $STUB_SNAPS; do mkdir -p "$last/@.snapshots/$n/snapshot"; done
        fi
        ;;
    btrfs) mkdir "$last" ;;
    mv)
        if [[ -n ${STUB_FAIL_MV_TO_AT:-} && $last == */@ && $1 == */@rollback-* ]]; then exit 1; fi
        exec "$REAL_MV" "$@"
        ;;
    arch-chroot)
        if [[ -n ${STUB_FAIL_CHROOT:-} && $* == *"$STUB_FAIL_CHROOT"* ]]; then exit 1; fi
        ;;
esac
exit 0
"""
STUBBED = ("id", "findmnt", "mount", "umount", "btrfs", "mv", "arch-chroot", "snapper", "bootctl")


def run_cli(tmp_path, *args, **env):
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name in STUBBED:
        f = stubs / name
        f.write_text(STUB)
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    rundir = tmp_path / "run"
    rundir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    log.write_text("")
    full = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "STUB_LOG": str(log),
        "REAL_MV": shutil.which("mv"),
        "SECLEGION_RESCUE_RUNDIR": str(rundir),
        "STUB_SNAPS": "1 2 3",
        **env,
    }
    r = subprocess.run([str(CLI), *args], capture_output=True, text=True, env=full)
    calls = [ln for ln in log.read_text().splitlines() if not ln.startswith(("id ", "findmnt "))]
    return r, calls, rundir


def index_of(calls, pattern):
    return next(i for i, c in enumerate(calls) if re.search(pattern, c))


def test_rollback_order_renames_never_deletes(tmp_path):
    r, calls, rundir = run_cli(tmp_path, "rollback", "--yes", "3")
    assert r.returncode == 0, r.stderr
    top = r"\S*/seclegion-rescue-top\.\w+"
    order = [
        rf"^mount -o subvolid=5 /dev/vda3 {top}$",
        rf"^btrfs subvolume snapshot {top}/@\.snapshots/3/snapshot {top}/@rollback-\d{{8}}T\d{{6}}Z$",
        rf"^mv {top}/@ {top}/@broken-\d{{8}}T\d{{6}}Z$",
        rf"^mv {top}/@rollback-\d{{8}}T\d{{6}}Z {top}/@$",
        r"^mount -o subvol=@ /dev/vda3 \S+/seclegion-rescue-new\.\w+$",
        r"^mount --bind /boot \S+/seclegion-rescue-new\.\w+/boot$",
        r"^arch-chroot \S+ sh -c .*vmlinuz-linux",
        r"^arch-chroot \S+ mkinitcpio -P$",
        r"^umount \S+/seclegion-rescue-new\.\w+/boot$",
        r"^umount \S+/seclegion-rescue-new\.\w+$",
        rf"^umount {top}$",
    ]
    idx = [index_of(calls, p) for p in order]
    assert idx == sorted(idx) and len(set(idx)) == len(idx), calls
    assert not any("delete" in c or c.startswith(("rm ", "rmdir ")) for c in calls)
    # the same timestamp in all three names; the old @ is kept under its new name, the snapshot is the new @
    stamps = set(re.findall(r"@(?:rollback|broken)-(\w+)", "\n".join(calls)))
    assert len(stamps) == 1
    topdir = next(rundir.glob("seclegion-rescue-top.*"))
    assert sorted(p.name for p in topdir.iterdir() if p.name.startswith("@") and p.name != "@.snapshots") == [
        "@",
        f"@broken-{stamps.pop()}",
    ]
    assert "reboot" in r.stdout.lower()


def test_rollback_refuses_non_root(tmp_path):
    r, calls, _ = run_cli(tmp_path, "rollback", "--yes", "3", STUB_UID="1000")
    assert r.returncode != 0 and "root" in r.stderr
    assert calls == []


def test_rollback_missing_snapshot_changes_nothing_and_unmounts(tmp_path):
    r, calls, _ = run_cli(tmp_path, "rollback", "--yes", "9")
    assert r.returncode != 0 and "no snapshot 9" in r.stderr
    assert [c.split()[0] for c in calls] == ["mount", "umount"]


def test_rollback_bad_arguments(tmp_path):
    for arg in ("abc", "0", "../3", "-1", "3 4"):
        r, calls, _ = run_cli(tmp_path, "rollback", "--yes", arg)
        assert r.returncode != 0 and calls == [], arg
    r, calls, _ = run_cli(tmp_path, "rollback", "--yes")
    assert r.returncode == 64 and calls == []


def test_rollback_not_btrfs(tmp_path):
    r, calls, _ = run_cli(tmp_path, "rollback", "--yes", "3", STUB_FSTYPE="ext4")
    assert r.returncode != 0 and "btrfs" in r.stderr and calls == []


def test_rollback_uki_failure_still_unmounts_and_keeps_the_old_root(tmp_path):
    r, calls, rundir = run_cli(tmp_path, "rollback", "--yes", "3", STUB_FAIL_CHROOT="mkinitcpio")
    assert r.returncode != 0 and "UKI was not rebuilt" in r.stderr
    umounts = [c for c in calls if c.startswith("umount ")]
    mounts = [c for c in calls if c.startswith("mount ")]
    assert len(umounts) == len(mounts) == 3
    assert [c.split()[-1] for c in umounts] == [c.split()[-1] for c in reversed(mounts)]
    topdir = next(rundir.glob("seclegion-rescue-top.*"))
    assert any(p.name.startswith("@broken-") for p in topdir.iterdir())


def test_rollback_failed_swap_puts_the_old_root_back(tmp_path):
    r, calls, rundir = run_cli(tmp_path, "rollback", "--yes", "3", STUB_FAIL_MV_TO_AT="1")
    assert r.returncode != 0 and "restored" in r.stderr
    assert re.search(r"^mv \S+/@broken-\w+ \S+/@$", calls[-2]), calls
    assert calls[-1].startswith("umount ")
    assert not any(c.startswith("arch-chroot") for c in calls)
    topdir = next(rundir.glob("seclegion-rescue-top.*"))
    assert (topdir / "@").is_dir() and not list(topdir.glob("@broken-*"))


def test_rollback_without_yes_prints_the_plan_and_changes_nothing(tmp_path):
    r, calls, _ = run_cli(tmp_path, "rollback", "3", STUB_UID="1000")
    assert r.returncode == 2 and "--yes" in r.stderr and "nothing was changed" in r.stderr
    assert calls == []
    for part in ("mount -o subvolid=5", "btrfs subvolume snapshot", "mv ", "mkinitcpio -P"):
        assert part in r.stdout
    assert r.stdout.index("mv ") < r.stdout.index("mkinitcpio -P")
    assert "delete" not in r.stdout


def test_status_and_list_snapshots_call_snapper(tmp_path):
    r, calls, _ = run_cli(tmp_path, "list-snapshots")
    assert r.returncode == 0 and calls == ["snapper -c root list"]
    r, calls, _ = run_cli(tmp_path, "status")
    assert r.returncode == 0 and calls == ["snapper list-configs", "bootctl list"]
    assert os.access(CLI, os.X_OK)
