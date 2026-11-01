# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M5 text-path gates: G47 (QEMU launch to the installed greeter under 900 s) and G49 (disk full).

G47: no selftest exists on an installed system, so "greeter" = the serial line for the greetd/greeter unit
on the installed-disk boot AND OCR of the greeter screendump showing the user name. The clock starts at the
first QEMU launch (the devloop VM) and stops after the greeter screendump of the installed boot.
G49: the configurator refuses a target under 20 GiB before anything is written: seclegion-install prints
one `refused:` line and exits 2, leaves no traceback, restores /etc/pacman.conf and removes the /run
credentials dir. The plan's G49 says "a full disk shows the error screen"; only the size refusal is checked.

Evidence rows: -k fast -> M5-fast, -k disk_full -> M5-diskfull (the serial.log is the install transcript plus,
for M5-fast, two M5-FAST lines written only after the elapsed and OCR assertions held).
"""
import json
import os
import re
import shutil
import tempfile

import pytest
from test_i2_run import PASSWORD, REPO, finish_gate, fresh_install

from tests.lib import bootgate, devloop
from tests.lib.qemu import kvm_usable

LIMIT_S = 900
SMALL_DISK = "3G"


@pytest.mark.iso
def test_m5_fast_install_under_900s():
    if not kvm_usable():
        pytest.skip("NOT RUN: KVM is not usable (the 900 s gate requires it)")
    if not shutil.which("tesseract"):
        pytest.skip("NOT RUN: tesseract missing (G47 requires the OCR of the greeter prompt)")

    def body(result_dir, iso):
        run = fresh_install("erase")  # never the cached run: only a run this test started is timed
        log = run.log
        try:
            assert run.error is None, run.error
            assert run.t_start is not None and run.t_greeter is not None
            elapsed = run.t_greeter - run.t_start
            print(f"elapsed_s={elapsed:.0f}")
            status, text = bootgate.ocr_status_of(run.screenshot)
            assert status == "OK", f"OCR did not run: {status}"
            assert "tester" in text.lower(), f"the greeter does not show the user name: {text!r}"
            assert elapsed < LIMIT_S, f"elapsed_s={elapsed:.0f} >= {LIMIT_S}"
            log += (f"\nM5-FAST elapsed_s={elapsed:.0f} limit_s={LIMIT_S}\n"
                    "M5-FAST ocr=OK greeter screen names tester\n")
        finally:
            with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                out.write(log)
            if run.screenshot and os.path.isfile(run.screenshot):
                shutil.copy(run.screenshot, os.path.join(result_dir, "screen.png"))
        return f"installed greeter after {elapsed:.0f} s (< {LIMIT_S}), OCR shows tester", run.command, "OK"

    finish_gate("M5-fast", f"from QEMU launch to the installed greeter in under {LIMIT_S} s (KVM, -nic "
                "none): the greeter unit started on the installed boot and OCR of the greeter shows the user",
                body)


@pytest.mark.iso
def test_m5_disk_full():
    def body(result_dir, iso):
        root = devloop.MOUNT
        answers = json.dumps({"disk": devloop.TARGET_BY_ID, "mode": "erase", "luks": False,
                              "username": "tester", "password": PASSWORD, "hostname": "seclegion",
                              "confirm": "QEMU HARDDISK", "timezone": "UTC"})
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m5-full-", dir=devloop.SCRATCH_ROOT)
        out = after = command = ""
        try:
            with open(os.path.join(REPO, "iso", "packages", "live.list")) as fh:
                live_list = fh.read()
            extra = {"dev/answers.json": answers, "dev/live.list": live_list}
            with devloop.devloop_vm(iso, extra_files=extra, mem=4096, scratch=scratch,
                                    target_size=SMALL_DISK) as vm:
                command = bootgate.evidence.repo_relative(vm.command, REPO)
                out = devloop.run(
                    vm, f"SECLEGION_POST_SKIP_MISSING=1 python {root}/installd/seclegion-install "
                        f"--answers {root}/dev/answers.json --dev --force-install-mode",
                    "DL-INSTALL", 1800)
                after = devloop.run(
                    vm, "grep -c seclegion-cache /etc/pacman.conf; "
                        "ls /etc | grep -c pacman.conf.seclegion-orig; ls /run | grep -c seclegion-install-",
                    "DL-AFTER", 60)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
            with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as log:
                log.write(f"[phase install]\n{out.strip()}\n\n[phase after]\n{after.strip()}\n")
        rc = re.search(r"DL-INSTALL (\d+)", out)
        # the configurator refuses a disk under 20 GiB before anything is written (exit 2, one line)
        assert rc and rc.group(1) == "2", out[-1500:]
        assert "SECLEGION-INSTALL-OK" not in out and "archinstall" not in out, out[-1500:]
        assert re.search(r"^refused: .*(disk_too_small|under 20 GiB)", out, re.M), out[-1500:]
        assert "Traceback" not in out, out[-2500:]
        assert PASSWORD not in out
        counts = re.findall(r"^(\d+)$", after, re.M)
        assert counts[:3] == ["0", "0", "0"], f"live pacman.conf not restored or creds dir left: {after}"
        print(f"disk_full: rc={rc.group(1)} refused before writing")
        return "a 3 GiB target is refused before any write (exit 2), nothing left behind", command, "n/a"

    finish_gate("M5-diskfull", "a too-small target is refused with one `refused:` line (exit 2), no "
                "archinstall run, no traceback, the live pacman.conf restored and no credentials dir left",
                body)
