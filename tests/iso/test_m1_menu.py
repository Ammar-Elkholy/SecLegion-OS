# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r13 J1c (G6 to G9): the SecLegion GRUB menu, booted for real in the VM harness.

Needs a built ISO (`make iso`, or SECLEGION_ISO) and QEMU/OVMF; without them each test is
skipped (NOT RUN), never recorded as a PASS. The oracle is the serial console: GRUB draws its menu
on serial, the stub seclegion-mode@<m>.service prints `SECLEGION-MODE=<m>` on ttyS0, and the
firmware and Memtest86+ draw on serial too. Keys go in through QMP. OCR of the screendump only
confirms (tesseract may be missing: the record says so in env.ocr); SL_REQUIRE_OCR=1 makes a
missing or failing OCR a test failure instead (the owner's final run).

Every test writes evidence/<id>/<iso-sha256>/<UTC>/ whether it passes or not. The ISO is only a
file: QemuVM refuses /dev paths.

  -k default          G6  M1-menu      six entries, no input, Install boots after >= 10 s
  -k modes            G7  M1-modes     each entry boots its own mode
  -k memtest_fwsetup  G8  M1-memtest, M1-fwsetup
  -k branding         G9  M1-branding  (tools/check-branding, plus its planted-string negative)
  -k theme_repro      G3  M1-theme-repro  (two `tools/docker-build.sh theme` runs; no ISO boot)
"""

import os
import re
import shutil
import subprocess
import sys
import time

import pytest

import evidence
from tests.lib import bootgate
from tests.lib.bootgate import MODE_TIMEOUT, REPO, choose, press, wait_for_menu
from tests.lib.qemu import QemuVM
from tests.lib.serial import WaitTimeout

CHECK_BRANDING = os.path.join(REPO, "tools", "check-branding")
REQUIRE_OCR = os.environ.get("SL_REQUIRE_OCR") == "1"
TIMER_FLOOR = 10  # the GRUB menu waits at least this long before booting the default
# How each Menu mode is reached: (top-level index, Safe Graphics submenu item or None).
ENTRY_KEYS = {"install": (bootgate.ENTRY_INSTALL, None), "live": (bootgate.ENTRY_LIVE, None),
              "rescue": (bootgate.ENTRY_RESCUE, None),
              "safe-install": (bootgate.ENTRY_SAFE, 0), "safe-live": (bootgate.ENTRY_SAFE, 1)}


def finish(status, actual):
    if status == "NOT RUN":
        pytest.skip(f"NOT RUN: {actual}")
    assert status == "PASS", actual


def read_log(workdir):
    with open(os.path.join(workdir, "serial.log"), encoding="utf-8", errors="replace") as handle:
        return handle.read()


def check_ocr(status, text, needle):
    """OCR confirms what serial already proved; a missing tesseract is recorded, not hidden."""
    if status == "OK":
        assert needle.lower() in text.lower(), f"OCR of the screendump lacks {needle!r}: {text[:200]!r}"
    elif REQUIRE_OCR:
        raise AssertionError(f"SL_REQUIRE_OCR=1 but OCR did not run: {status}")


@pytest.mark.iso
def test_m1_default_boots_install_after_the_timeout():
    def body(result_dir, iso):
        with QemuVM(iso, result_dir) as vm:  # no key is ever sent in this test
            command = evidence.repo_relative(vm.command, REPO)
            shown = wait_for_menu(vm)
            for pattern in evidence.CANONICAL_SERIAL_PATTERNS["M1-menu"][1:-1]:
                vm.serial.wait_for(pattern, 30)  # the other five entries, in menu order
            vm.serial.wait_for(r"SECLEGION-MODE=install", MODE_TIMEOUT)
            waited = time.monotonic() - shown
            vm.serial.wait_for(r"seclegion login:", MODE_TIMEOUT)
            shot = bootgate.take_screen(vm)
            assert waited >= TIMER_FLOOR, f"booted {waited:.1f}s after the menu, before the timeout"
            assert len(re.findall(r"SECLEGION-MODE=(\w+)", vm.serial.text())) >= 1
            ocr_status = bootgate.ocr_status_of(shot)[0]
        return (f"six entries drawn, no input, SECLEGION-MODE=install {waited:.1f}s after the "
                "menu appeared", command, ocr_status)

    finish(*bootgate.run_gate(
        "M1-menu", f"six titles on serial, then SECLEGION-MODE=install after >= {TIMER_FLOOR}s "
        "with no key pressed", body))


@pytest.mark.iso
def test_m1_modes_each_entry_boots_its_own_mode():
    def body(result_dir, iso):
        log, commands = [], []
        for entry, mode in evidence.M1_MODES:
            workdir = os.path.join(result_dir, f"boot-{entry}")
            try:
                with QemuVM(iso, workdir) as vm:
                    commands.append(evidence.repo_relative(vm.command, REPO))
                    wait_for_menu(vm)
                    index, item = ENTRY_KEYS[entry]
                    choose(vm, index, item)
                    vm.serial.wait_for(rf"SECLEGION-MODE={mode}", MODE_TIMEOUT)
                    time.sleep(3)  # a wrong target would have printed its own marker by now
                    seen = set(re.findall(r"SECLEGION-MODE=(\w+)", vm.serial.text()))
                    assert seen == {mode}, f"entry {entry}: markers {sorted(seen)}, wanted {mode}"
                    bootgate.take_screen(vm, "screen.png")
                    if os.path.isfile(os.path.join(workdir, "screen.png")):
                        shutil.copy(os.path.join(workdir, "screen.png"), result_dir)
            finally:
                if os.path.isfile(os.path.join(workdir, "serial.log")):
                    log.append(f"[entry {entry}]\n" + read_log(workdir) + "\n")
                shutil.rmtree(workdir, ignore_errors=True)  # per-boot scratch dir made above
                with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                    out.write("".join(log))
        return "each of install, live, rescue and both Safe Graphics entries booted its own mode", \
            commands[0] + "  (x5, one boot per entry)", "n/a"

    finish(*bootgate.run_gate(
        "M1-modes", "entries install, live, rescue, safe-install, safe-live print their own "
        "SECLEGION-MODE=<m>, chosen with QMP keys", body))


@pytest.mark.iso
def test_m1_memtest_fwsetup_memtest():
    def body(result_dir, iso):
        with QemuVM(iso, result_dir) as vm:
            command = evidence.repo_relative(vm.command, REPO)
            wait_for_menu(vm)
            choose(vm, bootgate.ENTRY_MEMTEST)
            # The entry's title was on serial already; the banner is Memtest86+'s own title bar.
            vm.serial.wait_for(evidence.M1_MEMTEST_BANNER, 60)
            time.sleep(5)  # let it draw one frame before the screendump
            shot = bootgate.take_screen(vm)
            status, text = bootgate.ocr_status_of(shot)
            # tesseract cannot read Memtest86+'s grey title bar ("Memtest86+ v8.10": dark text on grey,
            # read as "Memte§?86+"), so OCR confirms the stats panel; the exact banner is checked on serial.
            check_ocr(status, text, "CLK/Temp")
        return "Memtest86+ started and printed its title bar on serial", command, status

    finish(*bootgate.run_gate(
        "M1-memtest", "Memory Test boots Memtest86+: its banner is on serial", body))


@pytest.mark.iso
def test_m1_memtest_fwsetup_fwsetup():
    def body(result_dir, iso):
        # GRUB's `fwsetup` sets OsIndications and resets: the guest must be allowed to reboot.
        with QemuVM(iso, result_dir, no_reboot=False) as vm:
            command = evidence.repo_relative(vm.command, REPO)
            wait_for_menu(vm)
            vm.serial.wait_for(r"UEFI Firmware Settings", 30)
            choose(vm, bootgate.ENTRY_FIRMWARE)
            # GRUB sometimes drops the Enter (1 in ~6 runs, the menu stays drawn): press it again, at most
            # twice, only while nothing past the menu has appeared
            for attempt in range(3):
                try:
                    found = vm.serial.wait_for(r"Please select boot device|Device Manager", 20)
                    break
                except WaitTimeout:
                    if attempt == 2:
                        raise
                    press(vm, "ret")
            if found.group(0) != "Device Manager":  # OVMF's boot manager menu first
                time.sleep(2)
                press(vm, "ret")  # its first item is "EFI Firmware Setup"
                vm.serial.wait_for(r"Device Manager", 60)
            time.sleep(2)
            shot = bootgate.take_screen(vm)
            status, text = bootgate.ocr_status_of(shot)
            check_ocr(status, text, "Device Manager")
        return "UEFI Firmware Settings opened the firmware setup: Device Manager on serial", \
            command, status

    finish(*bootgate.run_gate(
        "M1-fwsetup", "UEFI Firmware Settings opens the firmware setup (Device Manager shown)",
        body))


@pytest.mark.iso
def test_m1_branding_boot_and_planted_string():
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO (run `make iso`, or set SECLEGION_ISO)")
    clean = subprocess.run([sys.executable, CHECK_BRANDING, "--evidence", iso],
                           capture_output=True, text=True, check=False)
    assert clean.stdout.strip() == "branding-ok", clean.stdout + clean.stderr
    planted = subprocess.run([sys.executable, CHECK_BRANDING, "--plant", "Arch Linux", iso],
                             capture_output=True, text=True, check=False)
    assert planted.returncode == 1 and planted.stdout.startswith("branding-FAIL"), planted.stdout


@pytest.mark.iso
def test_m1_theme_repro_two_theme_builds_are_identical():
    """G3: two `tools/docker-build.sh theme` runs with one SOURCE_DATE_EPOCH give equal sha files."""
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO to attach the record to (run `make iso`)")

    def body(result_dir, _iso):
        workdir = os.environ.get("SECLEGION_WORKDIR", "/var/tmp/seclegion-build")
        sums = os.path.join(workdir, "out", "grub-theme.sha256")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["SOURCE_DATE_EPOCH"] = "1700000000"
        lines, copies = [], []
        for run in ("a", "b"):
            proc = subprocess.run([os.path.join(REPO, "tools", "docker-build.sh"), "theme"],
                                  env=env, capture_output=True, text=True, check=False)
            assert proc.returncode == 0, f"theme build {run} failed: {proc.stderr[-400:]}"
            copy = os.path.join(result_dir, f"grub-theme.{run}.sha256")
            shutil.copy(sums, copy)
            copies.append(copy)
            lines.append(f"run {run}: {os.path.basename(sums)} sha256 "
                         f"{evidence.sha256_file(sums)}")
        same = open(copies[0], "rb").read() == open(copies[1], "rb").read()  # noqa: SIM115
        for copy in copies:
            os.remove(copy)
        if same:
            lines.append("theme-repro: identical")
        with open(os.path.join(result_dir, "theme.log"), "w", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
        assert same, "the two grub-theme.sha256 files differ"
        return "two theme builds, same SOURCE_DATE_EPOCH: identical grub-theme.sha256", \
            "tools/docker-build.sh theme (x2)", "n/a"

    finish(*bootgate.run_gate(
        "M1-theme-repro", "two theme builds with the same SOURCE_DATE_EPOCH: equal sha256 files",
        body, serial_name="theme.log"))
