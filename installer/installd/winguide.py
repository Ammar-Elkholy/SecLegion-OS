# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Dual-boot guide detector (U3): classify a partition (device or image file), read-only.

Result is one of: "bitlocker", "hibernated", "clean", "not_ntfs".

Method (pure Python, no NTFS driver needed): the NTFS volume boot sector carries OEM id
"NTFS    " (BitLocker: "-FVE-FS-") at offset 3. For hibernation we parse MFT record 3
($Volume), attribute $VOLUME_INFORMATION (0x70) and test the VOLUME_IS_DIRTY flag (0x0001).
Windows leaves a volume dirty when it was hibernated / Fast-Startup-shut-down (ntfs-3g
refuses such volumes with "Windows is hibernated"), and also after an unclean shutdown;
both mean "do not shrink or touch it", so both map to the same refusal. ntfs-3g.probe was
evaluated and rejected: --readonly does not report hibernation (exit 0 on a volume with a
hiberfil.sys "HIBR" file), so it cannot back this check. Opens files "rb" only, never writes.
"""

import struct

BITLOCKER, HIBERNATED, CLEAN, NOT_NTFS = "bitlocker", "hibernated", "clean", "not_ntfs"
HIBERNATED_GUIDE = "shut Windows down fully: disable Fast Startup, or run `shutdown /s /t 0`"
VOLUME_IS_DIRTY = 0x0001


def _unfixup(rec, sector=512):
    """Apply NTFS update-sequence fixups to an MFT record; None if torn/invalid."""
    if rec[:4] != b"FILE":
        return None
    usa_off, usa_n = struct.unpack_from("<HH", rec, 4)
    rec = bytearray(rec)
    usn = rec[usa_off:usa_off + 2]
    for i in range(1, usa_n):
        end = i * sector
        if end > len(rec) or rec[end - 2:end] != usn:
            return None
        rec[end - 2:end] = rec[usa_off + 2 * i:usa_off + 2 * i + 2]
    return rec


def volume_flags_offset(f):
    """(absolute file offset of the $VOLUME_INFORMATION flags u16, flags) or None."""
    f.seek(0)
    boot = f.read(512)
    if len(boot) < 512:
        return None
    bps, spc = struct.unpack_from("<HB", boot, 0x0B)
    mft_lcn = struct.unpack_from("<Q", boot, 0x30)[0]
    cpr = struct.unpack_from("<b", boot, 0x40)[0]
    if not bps or not spc:
        return None
    rec_size = cpr * bps * spc if cpr > 0 else 1 << -cpr
    base = mft_lcn * bps * spc + 3 * rec_size
    f.seek(base)
    rec = _unfixup(f.read(rec_size), bps)
    if rec is None:
        return None
    pos = struct.unpack_from("<H", rec, 0x14)[0]
    while pos + 8 <= len(rec):
        atype, alen = struct.unpack_from("<II", rec, pos)
        if atype == 0xFFFFFFFF or alen == 0:
            return None
        if atype == 0x70 and rec[pos + 8] == 0:  # resident
            coff = struct.unpack_from("<H", rec, pos + 0x14)[0]
            flags_at = pos + coff + 10
            return base + flags_at, struct.unpack_from("<H", rec, flags_at)[0]
        pos += alen
    return None


def probe(path):
    """Classify `path` (partition device or image file). Read-only."""
    with open(path, "rb") as f:  # noqa: PTH123 - read-only on purpose
        oem = f.read(11)[3:11]
        if oem == b"-FVE-FS-":
            return BITLOCKER
        if oem != b"NTFS    ":
            return NOT_NTFS
        vol = volume_flags_offset(f)
    if vol and vol[1] & VOLUME_IS_DIRTY:
        return HIBERNATED
    return CLEAN


def refusal_for(result):
    """(code, message) for a probe result that blocks alongside installs, else None."""
    if result == BITLOCKER:
        return ("bitlocker", "a BitLocker volume is on this disk; suspend/decrypt BitLocker in Windows first")
    if result == HIBERNATED:
        return ("windows_hibernated", HIBERNATED_GUIDE)
    # fail closed: a Windows partition we cannot inspect is not safe to share a disk with
    if result == "unreadable":
        return ("windows_unreadable",
                "a Windows partition on this disk could not be checked for BitLocker or hibernation; "
                "boot Windows, shut it down fully, and try again")
    return None
