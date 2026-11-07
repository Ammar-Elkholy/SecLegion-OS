# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Shrink an existing partition (root, before archinstall): filesystem first, partition table second.

The filesystem is shrunk before the GPT entry, so a failure in between leaves a filesystem smaller than
its partition, which is harmless. ntfsresize runs a dry run first; nothing is written if it refuses.
ntfsresize gets a single --force: that skips the interactive "Are you sure" prompt but does NOT override
a dirty / hibernated volume (that needs --force twice), which must stay a refusal.
"""
import subprocess

import configurator as c

KIB = 1 << 10


def _disk_of(part):
    pk = part.get("pkname") or ""
    return pk if pk.startswith("/") else "/dev/" + pk


def plan_commands(part, new_size, sector, disk=None):
    """argv list (in order) that shrinks lsblk partition node `part` to new_size bytes. Pure.

    The first command of an ntfs plan is the dry run; the sgdisk call comes after the filesystem step."""
    dev = part["path"]
    fs = (part.get("fstype") or "").lower()
    disk = disk or _disk_of(part)
    if fs == "ntfs":
        fs_cmds = [["ntfsresize", "--no-action", "--force", "--size", str(new_size), dev],
                   ["ntfsresize", "--force", "--size", str(new_size), dev]]
    elif fs == "ext4":
        fs_cmds = [["e2fsck", "-f", "-y", dev], ["resize2fs", dev, f"{new_size // KIB}K"]]
    else:
        raise c.Refusal("shrink_bad_partition", f"cannot shrink a {fs or 'unknown'} filesystem")
    n, start = int(part["partn"]), int(part["start"])
    end = start + new_size // sector - 1
    sg = ["sgdisk", f"--delete={n}", f"--new={n}:{start}:{end}"]
    if part.get("parttype"):
        sg.append(f"--typecode={n}:{part['parttype']}")
    if part.get("partuuid"):
        sg.append(f"--partition-guid={n}:{part['partuuid']}")
    if part.get("partlabel"):
        sg.append(f"--change-name={n}:{part['partlabel']}")
    sg.append(disk)
    return fs_cmds + [sg, ["partprobe", disk], ["udevadm", "settle"]]


def _useful_line(res):
    lines = [x.strip() for x in f"{res.stderr or ''}\n{res.stdout or ''}".splitlines() if x.strip()]
    for line in lines:
        if "error" in line.lower() or "fail" in line.lower() or "refus" in line.lower():
            return line
    return lines[-1] if lines else f"exit status {res.returncode}"


def apply(answers, facts, run=subprocess.run):
    """Validate, then shrink answers.shrink to answers.shrink_size. Raises c.Refusal; never half-writes
    on a refusal of the dry run / validation."""
    c.validate(answers, facts)  # root re-judges everything, including the Windows probes
    disk = c.find_disk(answers, facts)
    part = next(p for p in disk["children"] if p.get("path") == answers.shrink)
    cmds = plan_commands(part, answers.shrink_size, c._sec(disk), disk=disk["path"])
    for i, argv in enumerate(cmds):
        res = run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        ok = res.returncode == 0 or (argv[0] == "e2fsck" and res.returncode == 1)  # 1: errors fixed
        if ok:
            continue
        before_table = argv[0] != "sgdisk" and not any(x[0] == "sgdisk" for x in cmds[:i])
        raise c.Refusal("shrink_fs_refused" if before_table else "shrink_table_failed", _useful_line(res))
