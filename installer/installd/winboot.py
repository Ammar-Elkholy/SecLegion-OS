# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Windows entry for SecLegion's own systemd-boot menu (alongside installs only; DAILY-DRIVER.md gap 7).

systemd-boot loads EFI binaries only from its own ESP, and the Windows ESP is never written (nothing is
copied from EFI/Microsoft: that goes stale on Windows updates). So the entry starts the UEFI shell from
SecLegion's ESP with a script that runs \\EFI\\Microsoft\\Boot\\bootmgfw.efi from whichever FSn: holds it.

Why the script scans for the file and does not match the Windows ESP's PARTUUID: the UEFI shell prints the
GPT GUID in `map` but has no substring match or parser for it, and a full device path cannot be known
from Linux. The scan is safe because SecLegion's ESP never contains EFI/Microsoft. The only miss is a
machine with two Windows ESPs (first one in firmware order wins; F12 starts the other). The PARTUUID is
recorded in the script for the failure message. Tested in QEMU/OVMF behind real systemd-boot.
"""

import json
import os
import re
import subprocess
import tempfile

SHELL_PKG = "edk2-shell"
SHELL_SRC = "usr/share/edk2-shell/x64/Shell.efi"  # in the target, from the package
ESP_DIR = "boot/EFI/seclegion"  # SecLegion's ESP is /boot
SHELL_DST = f"{ESP_DIR}/shellx64.efi"
SCRIPT_DST = f"{ESP_DIR}/windows.nsh"
ENTRY_DST = "boot/loader/entries/windows.conf"
TITLE = "Windows 11"
BOOTMGR = "EFI/Microsoft/Boot/bootmgfw.efi"
ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
_UUID = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")

SCRIPT = """@echo -off
# seclegion-post (alongside install): start the Windows Boot Manager, read-only on the Windows ESP.
# Windows ESP PARTUUID at install time: {partuuid}
echo SecLegion: looking for the Windows Boot Manager
for %n run (0 15)
  if exist fs%n:\\EFI\\Microsoft\\Boot\\bootmgfw.efi then
    echo SecLegion: starting Windows from fs%n:
    fs%n:\\EFI\\Microsoft\\Boot\\bootmgfw.efi
    exit /b
  endif
endfor
echo SecLegion: Windows Boot Manager not found (ESP PARTUUID {partuuid}).
echo SecLegion: use the firmware boot menu (F12).
stall 5000000
"""
ENTRY = """title   {title}
efi     /EFI/seclegion/shellx64.efi
options -nostartup \\EFI\\seclegion\\windows.nsh
"""


def script(partuuid):
    if not _UUID.fullmatch(partuuid):
        raise ValueError(f"bad PARTUUID {partuuid!r}")
    return SCRIPT.format(partuuid=partuuid.lower())


def entry():
    return ENTRY.format(title=TITLE)


def candidates(lsblk):
    """Unmounted vfat EFI System partitions of every disk: [(device path, PARTUUID)]. Without a NAME
    column `lsblk -J` lists partitions flat, next to their disk, so every level is checked."""
    out = []

    def walk(nodes):
        for ch in nodes or []:
            mounted = [m for m in (ch.get("mountpoints") or [ch.get("mountpoint")]) if m]
            if ((ch.get("parttype") or "").lower() == ESP_GUID and (ch.get("fstype") or "") == "vfat"
                    and ch.get("partuuid") and not mounted):
                out.append((ch["path"], ch["partuuid"]))
            walk(ch.get("children"))

    walk(lsblk.get("blockdevices"))
    return out


def _run(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout  # noqa: S603


def has_bootmgr(dev, run=_run, mkdtemp=tempfile.mkdtemp):
    """Mount `dev` read-only (no exec/dev/suid), look for bootmgfw.efi, unmount. Never writes."""
    mnt = mkdtemp(prefix="seclegion-winesp-", dir="/run")
    try:
        run(["mount", "-o", "ro,nodev,noexec,nosuid", dev, mnt])
    except (OSError, subprocess.CalledProcessError):
        os.rmdir(mnt)
        return False
    try:
        return os.path.isfile(os.path.join(mnt, BOOTMGR)) or _icase(mnt, BOOTMGR)
    finally:
        run(["umount", mnt])
        os.rmdir(mnt)


def _icase(root, rel):
    cur = root
    for part in rel.split("/"):
        hit = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
        if hit is None:
            return False
        cur = os.path.join(cur, hit)
    return os.path.isfile(cur)


def find_windows_esp(run=_run, probe=has_bootmgr):
    """(device, PARTUUID, count) of the Windows ESP, or None. Read-only: lsblk and a ro mount."""
    lsblk = json.loads(run(["lsblk", "-J", "-b", "-o", "PATH,TYPE,FSTYPE,PARTTYPE,PARTUUID,MOUNTPOINTS"]))
    found = [(d, u) for d, u in candidates(lsblk) if probe(d)]
    return (*found[0], len(found)) if found else None
