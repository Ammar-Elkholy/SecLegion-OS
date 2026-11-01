# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Shared pieces of the M1 VM gates: ISO lookup, GRUB menu keys, and one evidence record per gate.

Keys go to the guest through QMP (the firmware keyboard), the oracle is the serial console.
The ISO is only ever a file; QemuVM refuses /dev paths.
"""

import glob
import os
import platform
import time

import evidence
from tests.lib import ocr
from tests.lib.ovmf import OvmfNotFound
from tests.lib.qemu import kvm_usable
from tests.lib.qmp import QmpError

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MENU_TIMEOUT = 120  # firmware to the first GRUB menu on serial
MODE_TIMEOUT = int(os.environ.get("SL_BOOT_TIMEOUT") or 600)
# Menu positions (top level, 0 based): the order grub.cfg draws them in.
ENTRY_INSTALL, ENTRY_LIVE, ENTRY_RESCUE, ENTRY_MEMTEST, ENTRY_FIRMWARE, ENTRY_SAFE = range(6)


def find_iso():
    explicit = os.environ.get("SECLEGION_ISO")
    if explicit:
        return explicit
    isos = sorted(glob.glob(os.path.join(REPO, "out", "*.iso")), key=os.path.getmtime)
    return isos[-1] if isos else None


KEY_SETTLE = 1.0  # seconds


def wait_for_menu(vm):
    """Block until GRUB has drawn its menu on serial; returns time.monotonic() of that moment."""
    vm.serial.wait_for(r"Install SecLegion OS", MENU_TIMEOUT)
    return time.monotonic()


def press(vm, *keys):
    for key in keys:
        vm.qmp.send_key(key)


def choose(vm, index, submenu_item=None):
    """From the open GRUB menu, move down `index` entries and press Enter.

    submenu_item (0 based) additionally opens the Safe Graphics submenu and picks that item.
    """
    press(vm, *["down"] * index)
    time.sleep(KEY_SETTLE)  # GRUB redraws over serial after each move; an Enter sent mid-redraw was lost
    press(vm, "ret")
    if submenu_item is not None:
        vm.serial.wait_for(r"Install \(safe graphics\)", 30)
        press(vm, *["down"] * submenu_item)
        time.sleep(KEY_SETTLE)
        press(vm, "ret")


def take_screen(vm, name="screen.png"):
    try:
        return vm.screendump(name)
    except (QmpError, OSError):
        return None  # QEMU already gone; serial.log still records the run


def ocr_status_of(path):
    """(status, text) of OCR on a screendump. status is "n/a", "OK" or a "SKIPPED/FAILED: ..." string."""
    if not path:
        return "n/a", ""
    result = ocr.ocr_image(path)
    return result.status, result.text


def run_gate(test_id, expected, body, serial_name="serial.log", extra_artifacts=()):
    """Run `body(result_dir)` and write one evidence record, PASS or FAIL, never overwriting.

    body returns (actual, command, ocr_status) and raises AssertionError on a failed gate.
    Returns (status, actual); the caller skips on "NOT RUN".
    """
    iso = find_iso()
    if not iso or not os.path.isfile(iso):
        return "NOT RUN", "no ISO (run `make iso`, or set SECLEGION_ISO)"
    iso_sha = evidence.sha256_file(iso)
    commit = evidence.git_commit_id(REPO)  # before the run dir exists: the code under test
    result_dir, started = evidence.new_result_dir(os.path.join(REPO, "evidence"), test_id, iso_sha)
    status, actual, ocr_status, command = "FAIL", "", "", "n/a"
    try:
        actual, command, ocr_status = body(result_dir, iso)
        status = "PASS"
    except OvmfNotFound as exc:
        status, actual = "NOT RUN", str(exc)
    except AssertionError as exc:
        actual = str(exc)[:800]
    except Exception as exc:  # noqa: BLE001 - still FAIL, but with the reason recorded (was an empty actual)
        actual = f"{type(exc).__name__}: {exc}"[:800]
    finally:
        names = [n for n in (serial_name, "screen.png", *extra_artifacts)
                 if status != "NOT RUN" and os.path.isfile(os.path.join(result_dir, n))]
        evidence.write_result(os.path.join(REPO, "evidence"), {
            "test_id": test_id, "status": status, "class": "AUTO", "commit": commit,
            "iso_sha256": iso_sha,
            "env": {"host": platform.system() + " " + platform.release(), "kvm": kvm_usable(),
                    "ocr": ocr_status or "n/a"},
            "command": command, "expected": expected,
            "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
            "actual": actual, "exit_code": 0 if status == "PASS" else 1,
            "timestamp": started,
        }, names)
    return status, actual


def boot_default(vm_class, iso, workdir):
    """Boot the default entry with no input; return (serial text, screendump path or None, command).

    Waits for the menu, the install marker and the login prompt, then takes one screendump.
    """
    with vm_class(iso, workdir) as vm:
        command = evidence.repo_relative(vm.command, REPO)
        wait_for_menu(vm)
        vm.serial.wait_for(r"SECLEGION-MODE=install", MODE_TIMEOUT)
        vm.serial.wait_for(r"seclegion login:", MODE_TIMEOUT)
        shot = take_screen(vm)
        return vm.serial.text(), shot, command
