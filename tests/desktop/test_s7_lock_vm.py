# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G46 (VM, installed base): while the screen is locked, synthetic input reaches no client.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py). The test logs
in as `tester` on the serial getty, then through the greeter over QMP. Everything about Hyprland runs INSIDE
the guest (`hyprctl -i 0`); hyprctl never runs on the host.

In the guest session a foot window runs `cat > /tmp/s7-typed`: it is the focused client and records every
key it receives. Checked: a control word typed over QMP reaches the file (unlocked, so the client takes
input); the shipped SUPER + L bind (QMP) starts hyprlock (the lock fires); a probe word typed over QMP
while locked is NOT in the file; the tester password typed over QMP unlocks (hyprlock exits); a second
control word reaches the file again. The serial.log is the installed boot's console; S7-* lines are printed
by the guest. Decision O4 stands: 1.0 ships the branded hyprlock screen and no screensaver.
NOT checked: a pre-lock overlay (there is none), the lock after an idle timeout (hypridle's timer), and
`loginctl lock-session` (from the serial getty it targets the ttyS0 session, not the Hyprland one).
seclegion-dotfiles ships ~/.config/hypr/hypridle.conf, which turns logind's Lock signal into hyprlock.
"""
import os
import re
import shutil
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "install"))

from test_d2_greeter_vm import Guest  # noqa: E402
from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import Shell, installed_vm  # noqa: E402

TYPED = "/tmp/s7-typed"
CONTROL_1, PROBE, CONTROL_2 = "controlone", "probeword", "controltwo"
CONTROL_TRIES = 3
FOOT_RE = "'class.: .foot.'"  # matches hyprctl's `"class": "foot"` without a nested quote in the guest shell
RECORDER = "/tmp/s7-recorder.sh"  # a script, so no quote has to survive the serial shell and the Lua string


def login_through_greeter(vm, sh):
    g = Guest(vm, "")
    assert not g.hyprland_running("S7BEFORE"), "Hyprland already running before the greeter login"
    g.start_auth()
    g.type_keys(PASSWORD)
    vm.qmp.send_key("ret")
    deadline = time.monotonic() + 90
    while not g.hyprland_running("S7WAIT"):
        assert time.monotonic() < deadline, "no Hyprland for tester 90 s after the greeter login"
        time.sleep(3)
    rc, out = sh.run("for i in $(seq 30); do hyprctl -i 0 version > /dev/null 2>&1 && break; sleep 2; done; "
                     "hyprctl -i 0 version | head -n 1", timeout=120)
    assert rc == 0 and re.search(r"Hyprland", out), out
    sh.say("S7-HYPRLAND started through the greeter and answers hyprctl")


def wait_for(sh, cmd, what, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        rc, out = sh.run(cmd)
        if rc == 0:
            return
        assert time.monotonic() < deadline, f"{what} did not happen within {seconds} s"
        time.sleep(1)


def typed_has(sh, word):
    rc, out = sh.run(f"grep -q -x {word} {TYPED}")
    return rc == 0


def type_line(vm, word):
    vm.qmp.type_text(word, delay=0.05)
    vm.qmp.send_key("ret")


def start_recorder(sh):
    rc, out = sh.run(f"rm -f {TYPED}")
    assert rc == 0, out
    rc, out = sh.run(f"printf '%s\\n' '#!/bin/sh' 'exec foot sh -c \"cat > {TYPED}\"' > {RECORDER} "
                     f"&& chmod +x {RECORDER}")
    assert rc == 0, out
    # Hyprland 0.55+ takes a Lua expression here: "dispatch exec foot" is a syntax error
    rc, out = hypr(sh, f'hl.dsp.exec_cmd("{RECORDER}")')
    assert rc == 0, out
    wait_for(sh, f"pgrep -u tester -x cat && test -e {TYPED}", "the recorder client starting")
    # the compositor lists the window (it is mapped), not only: the process started
    wait_for(sh, f"hyprctl -i 0 clients -j | grep -q {FOOT_RE}", "foot listed in the guest's clients", 30)
    focus_recorder(sh)


def hypr(sh, lua, timeout=30):
    """One Lua dispatch inside the guest (hyprctl never runs on the host); rc is not trusted."""
    return sh.run(f"hyprctl -i 0 dispatch '{lua}'", timeout=timeout)


def focus_recorder(sh):
    """Close the first-login welcome window if it is up, then focus foot and wait until it holds focus."""
    hypr(sh, 'hl.dsp.window.close({ window = "class:org.seclegion.Welcome" })')  # no-op without a window
    wait_for(sh, "! hyprctl -i 0 clients -j | grep -q org.seclegion.Welcome", "the welcome window going", 30)
    deadline = time.monotonic() + 30
    while True:
        hypr(sh, 'hl.dsp.focus({ window = "class:foot" })')
        rc, out = sh.run(f"hyprctl -i 0 activewindow -j | grep -q {FOOT_RE}")
        if rc == 0:
            return
        assert time.monotonic() < deadline, "the foot recorder did not take focus within 30 s"
        time.sleep(1)


def check_unlocked_input(sh, vm):
    start_recorder(sh)
    # Retried with focus re-taken: the keys can land before the window accepts input. The probe word
    # typed under the lock is never retried.
    for attempt in range(1, CONTROL_TRIES + 1):
        focus_recorder(sh)
        time.sleep(2)
        type_line(vm, CONTROL_1)
        try:
            wait_for(sh, f"grep -q -x {CONTROL_1} {TYPED}", "the first control word reaching the client", 8)
            break
        except AssertionError:
            assert attempt < CONTROL_TRIES, f"first control word never reached the client ({attempt} tries)"
    sh.say("S7-CONTROL a word typed over QMP reaches the focused client while unlocked")


def check_lock(sh, vm):
    rc, out = sh.run("pgrep -u tester -x hyprlock")
    assert rc != 0, ("hyprlock already running before the lock", out)
    vm.qmp.send_key("meta_l", "l")  # the shipped lock bind (hyprland.lua): SUPER + L runs hyprlock
    wait_for(sh, "pgrep -u tester -x hyprlock", "hyprlock starting after SUPER + L", 30)
    time.sleep(5)  # the lock surface is up
    sh.say("S7-LOCK SUPER L started hyprlock for tester")


def check_locked_input(sh, vm):
    type_line(vm, PROBE)
    time.sleep(5)
    rc, out = sh.run("pgrep -u tester -x hyprlock")
    assert rc == 0, ("hyprlock is gone after the probe", out)
    rc, out = sh.run(f"pgrep -u tester -x cat && test -e {TYPED} && ! grep -q {PROBE} {TYPED}")
    assert rc == 0, ("the probe word reached the client under the lock", out)
    assert typed_has(sh, CONTROL_1)
    sh.say("S7-LOCKED a word typed over QMP under the lock reached no client")


def check_unlock(sh, vm):
    type_line(vm, PASSWORD)
    wait_for(sh, "! pgrep -u tester -x hyprlock", "hyprlock exiting after the password", 30)
    sh.say("S7-UNLOCK the tester password typed over QMP ended hyprlock")
    time.sleep(3)
    type_line(vm, CONTROL_2)
    wait_for(sh, f"grep -q -x {CONTROL_2} {TYPED}", "the second control word reaching the client", 20)
    # the pattern stays a bracket class: the serial echo of this command must not hold the password
    rc, out = sh.run(f"! grep -q {PROBE} {TYPED} && ! grep -q 'pass-[1]' {TYPED}")
    assert rc == 0, ("the probe word or the password reached the client", out)
    sh.say("S7-AFTER a word typed over QMP reaches the client again after the unlock")


def save_failure_state(vm, sh, result_dir):
    """Keep the guest screen with the evidence, and print the compositor's windows into serial.log."""
    try:
        vm.qmp.screendump(os.path.join(result_dir, "screen.png"))
    except Exception:  # QEMU already gone: serial.log still records the run
        return
    try:
        sh.run("hyprctl -i 0 clients -j | grep -E 'class|title|focusHistoryID'; "
               "hyprctl -i 0 activewindow -j | grep class; "
               "pgrep -u tester -a 'hyprlock|cat|foot'", timeout=20)
    except Exception:
        pass


def lock_session(vm, result_dir):
    sh = Shell(vm, "S7RC")
    sh.login()
    login_through_greeter(vm, sh)
    try:
        check_unlocked_input(sh, vm)
        check_lock(sh, vm)
        check_locked_input(sh, vm)
        check_unlock(sh, vm)
    except BaseException:
        save_failure_state(vm, sh, result_dir)
        raise
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_s7_result():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="s7-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    lock_session(vm, result_dir)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return ("a QMP-typed word reaches a focused client unlocked, SUPER + L starts "
                    "hyprlock, a probe word typed under the lock reaches no client, the password unlocks "
                    "and a second word reaches the client"), command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("S7-result", "while the screen is locked synthetic input reaches no client and the lock "
                "fires: a client records QMP-typed words, a word typed under hyprlock is not recorded, "
                "and input works again after the unlock", body)
