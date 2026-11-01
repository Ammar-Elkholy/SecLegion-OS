# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""D2 / G41, VM half: the installed system's greeter (greetd + regreet) really works.

One real install (keyboard_extra = ara) and one boot of the installed disk. State is read through a
serial getty (dev installs add console=ttyS0), keys go to the graphical greeter on tty1 through QMP.

regreet always shows a Session row (there is no option to hide it): the greeter screen is asserted to
list Hyprland and nothing else is possible, since exactly one session file exists (test_d2_static.py).
The password field only appears after Enter (regreet asks greetd for the secret first).
us/ara: Alt+Shift toggles the greeter's xkb group; the same keys typed after the toggle are not the
password (login fails), typed after toggling back they are (login works).

Evidence row M6-greeter (-k greeter, the VM test): the serial.log is the install transcript, then the
installed boot's serial. The G41-*-RC<n> probes print through the serial shell (split marker: the echo
cannot match). The toggle is checked by login behaviour, not by OCR; "no session selector" is NOT asserted
(the Session row is expected, see above): the row records that behaviour, not an absent selector.
"""
import hashlib
import os
import re
import shutil
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tests", "install"))

from test_i2_run import PASSWORD, finish_gate, run_install  # noqa: E402

from tests.lib import bootgate, devloop  # noqa: E402
from tests.lib.qemu import QemuVM  # noqa: E402

REQUIRE_OCR = os.environ.get("SL_REQUIRE_OCR") == "1"
WRONG = "wrong-pass-9"
KEY_DELAY = 0.05


class Guest:
    def __init__(self, vm, workdir):
        self.vm, self.workdir, self.ocr_ran = vm, workdir, False

    def screen(self, name):
        """Screendump + OCR text (lowercase) or None when tesseract is unavailable."""
        path = bootgate.take_screen(self.vm, name + ".png")
        assert path, "no screendump"
        status, text = bootgate.ocr_status_of(path)
        if status != "OK":
            assert not REQUIRE_OCR, f"SL_REQUIRE_OCR=1 but OCR did not run: {status}"
            return path, None
        self.ocr_ran = True
        return path, text.lower()

    def serial_login(self):
        self.vm.serial.send("\n")
        self.vm.serial.wait_for(r"login: ", 60)
        self.vm.serial.send("tester\n")
        self.vm.serial.wait_for(r"Password: ", 30)
        self.vm.serial.send(PASSWORD + "\n")  # the getty does not echo it
        self.vm.serial.wait_for(r"\[tester@\S+ ~\]\$ ", 60)

    def probe(self, cmd, marker="PR-RC"):
        """Run `cmd` in the serial shell, return its exit status (split marker: the echo can't match)."""
        start = len(self.vm.serial.text())
        head, tail = marker[:3], marker[3:]
        self.vm.serial.send(f"{cmd}; echo {head}''{tail}$?\n")
        self.vm.serial.wait_for(re.escape(marker) + r"\d+", 30)
        return int(re.findall(re.escape(marker) + r"(\d+)", self.vm.serial.text()[start:])[-1])

    def hyprland_running(self, marker="PR-RC"):
        return self.probe("pgrep -u tester -x Hyprland > /dev/null", marker) == 0

    def type_keys(self, text):
        self.vm.qmp.type_text(text, delay=KEY_DELAY)

    def start_auth(self):
        """Enter on the start screen: regreet asks greetd, the password prompt appears."""
        self.vm.qmp.send_key("ret")
        time.sleep(4)

    def attempt(self, keys, toggle=False):
        self.start_auth()
        if toggle:
            self.vm.qmp.send_key("alt", "shift")
            time.sleep(1)
        self.type_keys(keys)
        self.vm.qmp.send_key("ret")


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def greeter_scenario(vm, boot_dir, result_dir):
    """Boot to the greeter, then the G41 steps; each probe prints a G41-<step>-RC<n> marker on the serial."""
    g = Guest(vm, boot_dir)
    vm.serial.wait_for(r"Started .*(greetd|[Gg]reeter)", 300)
    time.sleep(20)
    g.serial_login()
    assert not g.hyprland_running("G41-BEFORE-RC"), "Hyprland already running before any greeter login"
    assert g.probe("ls /etc/greetd/sessions | grep -qx hyprland.desktop "
                   "&& test $(ls /etc/greetd/sessions | wc -l) = 1", "G41-SESSIONFILE-RC") == 0

    # 1: the start screen names the user and lists the single session; Enter shows the password prompt
    start_png, text = g.screen("start")
    if text is not None:
        for word in ("tester", "session", "hyprland"):
            assert word in text, f"start screen lacks {word!r}: {text!r}"
    start_hash = sha(start_png)
    g.start_auth()
    prompt_png, text = g.screen("prompt")
    shutil.copy(prompt_png, os.path.join(result_dir, "screen.png"))
    if text is not None:
        assert "password" in text and "tester" in text, text

    # 2: a wrong password does not start a session, the greeter is still there
    g.type_keys(WRONG)
    vm.qmp.send_key("ret")
    time.sleep(10)
    assert not g.hyprland_running("G41-WRONG-RC"), "Hyprland started after a wrong password"
    _, text = g.screen("after-wrong")
    if text is not None:
        assert "session" in text and "tester" in text and "welcome to hyprland" not in text, text

    # 4: the greeter's us/ara toggle: the right keys on the ara group are the wrong password
    g.attempt(PASSWORD, toggle=True)
    time.sleep(10)
    assert not g.hyprland_running("G41-ARA-RC"), "Alt+Shift did not switch to ara (password accepted)"

    # 3: toggled back to us, the correct password starts Hyprland
    g.attempt(PASSWORD, toggle=True)
    deadline = time.monotonic() + 60
    while not g.hyprland_running("G41-RIGHT-RC"):
        assert time.monotonic() < deadline, "no Hyprland for tester 60 s after the right password"
        time.sleep(3)
    time.sleep(10)
    after_png, text = g.screen("after-login")
    assert sha(after_png) != start_hash, "screen unchanged after login"
    if text is not None:
        assert "session:" not in text, text
    assert g.ocr_ran, "OCR did not run: the greeter screens were not checked"
    vm.serial.send("echo G41-OCR''-OK\n")  # only after every screen assertion held
    vm.serial.wait_for(r"G41-OCR-OK", 30)


@pytest.mark.iso
def test_greeter_vm():
    if not shutil.which("tesseract"):
        pytest.skip("NOT RUN: tesseract missing (G41 checks the greeter screens by OCR)")

    def body(result_dir, iso):
        run = run_install("erase", ("ara",), True)
        scratch = run.scratch
        booted = ""
        try:
            assert run.error is None, run.error
            target = os.path.join(scratch, "target.qcow2")
            boot_dir = os.path.join(scratch, "boot")
            with QemuVM(iso, boot_dir, net="none", memory_mb=4096, disks=[(target, devloop.TARGET_SERIAL)],
                        boot="disk", reuse_vars=True) as vm:
                command = bootgate.evidence.repo_relative(vm.command, REPO)
                try:
                    greeter_scenario(vm, boot_dir, result_dir)
                finally:
                    booted = vm.serial.text()
            assert PASSWORD not in booted and WRONG not in booted
            return "wrong and ara-group passwords start nothing, the right one starts Hyprland", command, "OK"
        finally:
            with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                out.write(f"{run.log}\n[phase installed-boot]\n{booted}\n")
            if scratch:
                shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("M6-greeter", "the installed greeter prompts for the user's password, exactly one session "
                "file (Hyprland) exists, a wrong password and the ara-group keys start nothing, the right "
                "one starts Hyprland (the Session row is shown: open owner decision)", body)
