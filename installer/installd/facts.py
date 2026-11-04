# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Gather the facts JSON the configurator validates against (see configurator.py).

Parsing is pure (unit tested with fixtures); gather() runs the real commands and only
works on the live ISO. Used by `seclegion-configure --gather-facts`.
"""

import json
import os
import subprocess

import release
import winguide

LSBLK = ["lsblk", "-J", "-b", "-O"]
BY_ID_DIR = "/dev/disk/by-id"
BOOT_MOUNT = "/run/archiso/bootmnt"


def parent_disk(lsblk, devpath):
    """Path of the whole disk that contains `devpath` (itself if it is a disk), else None."""

    def walk(node):
        if node.get("path") == devpath:
            return True
        return any(walk(child) for child in node.get("children") or [])

    for disk in lsblk.get("blockdevices", []):
        if walk(disk):
            return disk["path"]
    return None


def parse_by_id(pairs):
    """[(link_path, resolved_target)] -> {link_path: target}, partition links dropped."""
    return {link: target for link, target in pairs if "-part" not in os.path.basename(link)}


def build_facts(lsblk, by_id_pairs, root_source, boot_source, install_mode, dev_build):
    return {
        "install_mode": bool(install_mode),
        "dev_build": bool(dev_build),
        "boot_medium": parent_disk(lsblk, boot_source) if boot_source else None,
        "root_disk": parent_disk(lsblk, root_source) if root_source else None,
        "by_id": parse_by_id(by_id_pairs),
        "lsblk": lsblk,
    }


def probe_partitions(lsblk, probe=winguide.probe):
    """{partition path: winguide result} for every NTFS/BitLocker partition (read-only)."""
    out = {}
    for disk in lsblk.get("blockdevices", []):
        for p in disk.get("children") or []:
            if (p.get("fstype") or "").lower() in ("ntfs", "bitlocker") and p.get("path"):
                try:
                    out[p["path"]] = probe(p["path"])
                except OSError:
                    out[p["path"]] = "unreadable"
    return out


def _out(argv):
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603
    except (OSError, subprocess.CalledProcessError):
        return ""


def detect_install_mode(cmdline, target_state):
    """True iff the kernel cmdline asks for install mode AND seclegion-install.target is up.

    "activating" counts: with no network the target's multi-user.target dependencies keep it activating
    while the kiosk (and this GUI) is already running."""
    return "seclegion.mode=install" in cmdline.split() and target_state in ("active", "activating")


def _read_cmdline():
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def gather(install_mode=None, dev_build=None):
    """Live gathering. install_mode None = /proc/cmdline says seclegion.mode=install and systemd reports
    seclegion-install.target active or activating (detect_install_mode).

    dev_build None = DEV unless release mode (release.py); release mode always reports dev_build False."""
    rel = release.is_release()
    dev_build = (not rel) if dev_build is None else (bool(dev_build) and not rel)
    lsblk = json.loads(subprocess.run(LSBLK, check=True, capture_output=True, text=True).stdout)  # noqa: S603
    pairs = []
    if os.path.isdir(BY_ID_DIR):
        pairs = [
            (os.path.join(BY_ID_DIR, n), os.path.realpath(os.path.join(BY_ID_DIR, n)))
            for n in sorted(os.listdir(BY_ID_DIR))
        ]
    if install_mode is None:
        install_mode = detect_install_mode(
            _read_cmdline(), _out(["systemctl", "is-active", "seclegion-install.target"])
        )
    facts = build_facts(
        lsblk,
        pairs,
        _out(["findmnt", "-no", "SOURCE", "/"]),
        _out(["findmnt", "-no", "SOURCE", BOOT_MOUNT]),
        install_mode,
        dev_build,
    )
    facts["probes"] = probe_partitions(lsblk)
    return facts


if __name__ == "__main__":
    import sys

    json.dump(
        gather(install_mode=True if "--force-install-mode" in sys.argv[1:] else None), sys.stdout, indent=1
    )
