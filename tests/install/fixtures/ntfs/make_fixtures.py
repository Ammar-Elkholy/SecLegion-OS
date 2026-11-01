# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Generate NTFS test images (rootless, image files only, never a /dev node).

clean:      truncate + mkntfs -F -f -Q
hibernated: clean image whose $Volume VOLUME_IS_DIRTY flag is set (the state Windows leaves
            after hibernate / Fast Startup; what winguide detects). Patched in the image file only.
bitlocker:  SYNTHETIC 1 MiB file whose boot sector has OEM id "-FVE-FS-" at offset 3.
"""

import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "installer", "installd"))
import winguide  # noqa: E402


def clean(path, mib=32):
    with open(path, "wb") as f:
        f.truncate(mib << 20)
    subprocess.run(["mkntfs", "-F", "-f", "-Q", path], check=True, capture_output=True)  # noqa: S603, S607
    return path


def hibernated(path):
    clean(path)
    with open(path, "r+b") as f:
        off, flags = winguide.volume_flags_offset(f)
        f.seek(off)
        f.write(struct.pack("<H", flags | winguide.VOLUME_IS_DIRTY))
    return path


def bitlocker(path):
    boot = bytearray(512)
    boot[0:3] = b"\xeb\x58\x90"
    boot[3:11] = b"-FVE-FS-"
    boot[510:512] = b"\x55\xaa"
    with open(path, "wb") as f:
        f.write(boot)
        f.truncate(1 << 20)
    return path
