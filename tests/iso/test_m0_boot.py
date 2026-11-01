# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M0 gate: the stock releng placeholder ISO boots in the harness.

Oracle is the serial console. OVMF mirrors systemd-boot's menu onto serial (ANSI-drawn;
matched after escapes are stripped), which shows the archiso UEFI entry; the placeholder
profile's UEFI entries carry `console=ttyS0,115200 console=tty0` (iso/profile/PLACEHOLDER.md),
so a getty on ttyS0 then prints the login prompt. The kernel's "Command line:" line is
info-level and hidden on serial by the console loglevel, so it is not an oracle.
The screendump and optional OCR only confirm. Every run writes a new directory
evidence/M0-boot/<iso-sha256>/<UTC-timestamp>/ (result.json, serial.log, screen.png), whether
the boot passed or failed (a failed run also saves a screendump when QEMU is still up); an
existing result is never overwritten. The commit is recorded `-dirty` when the tree is not
clean, and tools/verify-evidence rejects a dirty PASS, so run `make vm` on a clean checkout.
If there is no ISO the test is skipped and no PASS is ever recorded.

SL_BOOT_LOGIN_RE and SL_BOOT_TIMEOUT override the login pattern and its timeout (seconds),
e.g. to prove that a wrong expectation fails and records FAIL evidence. Such a run records its
own patterns, which differ from the canonical ones, so it can never verify as PASS.
"""

import glob
import os
import platform

import pytest

import evidence
from tests.lib import ocr
from tests.lib.ovmf import OvmfNotFound
from tests.lib.qemu import QemuVM, kvm_usable
from tests.lib.qmp import QmpError

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_ID = "M0-boot"
# systemd-boot's archiso UEFI entry title, then the ttyS0 getty's prompt (or autologin shell).
# The canonical patterns live in tools/lib/evidence.py: verify-evidence rejects a PASS whose
# recorded patterns differ, so an SL_BOOT_LOGIN_RE run can never verify as PASS.
BOOT_ENTRY, DEFAULT_LOGIN = evidence.CANONICAL_SERIAL_PATTERNS[TEST_ID]
LOGIN = os.environ.get("SL_BOOT_LOGIN_RE") or DEFAULT_LOGIN
MENU_TIMEOUT = 120
BOOT_TIMEOUT = int(os.environ.get("SL_BOOT_TIMEOUT") or 600)


def find_iso():
    explicit = os.environ.get("SECLEGION_ISO")
    if explicit:
        return explicit
    isos = sorted(glob.glob(os.path.join(REPO, "out", "*.iso")), key=os.path.getmtime)
    return isos[-1] if isos else None


def commit_id():
    return evidence.git_commit_id(REPO)


@pytest.mark.iso
def test_stock_releng_iso_boots_to_login():
    iso = find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO (run `make iso`, or set SECLEGION_ISO)")
    iso_sha = evidence.sha256_file(iso)
    commit = commit_id()  # before the run dir exists; the code under test is what matters
    result_dir, started = evidence.new_result_dir(os.path.join(REPO, "evidence"), TEST_ID, iso_sha)

    status, actual, ocr_status, command = "FAIL", "", "", "n/a"
    try:
        with QemuVM(iso, result_dir) as vm:  # net="none": console-only test, see build_command
            command = evidence.repo_relative(vm.command, REPO)
            try:
                vm.serial.wait_for(BOOT_ENTRY, MENU_TIMEOUT)  # menu timeout 15s, then the kernel
                vm.serial.wait_for(LOGIN, BOOT_TIMEOUT)
            except AssertionError:
                try:
                    vm.screendump("screen.png")  # FAIL evidence: what the display showed
                except (QmpError, OSError):
                    pass  # QEMU already gone (SerialClosed); serial.log still records the run
                raise
            shot = vm.screendump("screen.png")
            ocr_status = ocr.ocr_image(shot).status
        status, actual = "PASS", ("serial showed the archiso UEFI boot entry in the systemd-boot "
                                  "menu, then a login prompt; screendump written")
    except OvmfNotFound as exc:
        status, actual = "NOT RUN", str(exc)
    except AssertionError as exc:  # WaitTimeout / SerialClosed carry the console tail
        actual = str(exc)[:800]
    finally:
        names = [n for n in ("serial.log", "screen.png")
                 if status != "NOT RUN" and os.path.isfile(os.path.join(result_dir, n))]
        evidence.write_result(os.path.join(REPO, "evidence"), {
            "test_id": TEST_ID, "status": status, "class": "AUTO", "commit": commit,
            "iso_sha256": iso_sha,
            "env": {"host": platform.system() + " " + platform.release(), "kvm": kvm_usable(),
                    "ocr": ocr_status or "n/a"},
            "command": command,
            "expected": f"serial matches /{BOOT_ENTRY}/ then /{LOGIN}/ within "
                        f"{BOOT_TIMEOUT}s; screendump taken",
            "serial_patterns": [BOOT_ENTRY, LOGIN],  # re-applied in order by verify-evidence
            "actual": actual, "exit_code": 0 if status == "PASS" else 1,
            "timestamp": started,
        }, names)
    if status == "NOT RUN":
        pytest.skip(f"NOT RUN: {actual}")
    assert status == "PASS", actual
