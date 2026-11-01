# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G39 (VM, installed base): a user's ~/.config/hypr/user.lua really overrides a shipped bind.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py). The test logs
in as `tester` on the serial getty, writes ~/.config/hypr/user.lua (it unbinds the shipped SUPER + L, which
starts hyprlock, binds it to `touch /tmp/s6-user-bind`, and adds SUPER + F9 -> `touch /tmp/s6-new-bind`),
then logs in through the greeter over QMP. Everything about Hyprland is read INSIDE the guest through
`hyprctl -i 0` (the first instance under /run/user/$UID/hypr); hyprctl never runs on the host.

Checked: Hyprland starts for tester; `hyprctl binds -j` lists SUPER + L with the user's description and not
the shipped "lock the screen", plus the new SUPER + F9 and a shipped bind the user left alone (SUPER + D);
a real SUPER + L key press (QMP) creates the marker file and starts no hyprlock; SUPER + F9 creates the
second marker. The serial.log is the installed boot's console; the S6-* lines are printed by the guest.
NOT checked: user.lua with a syntax error (tests/desktop/test_d1_user_lua.py covers the loader off-VM).
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

SUPER = 64  # Hyprland modmask of SUPER
USER_LUA = (
    'hl.unbind("SUPER + L")',
    'hl.bind("SUPER + L", hl.dsp.exec_cmd("touch /tmp/s6-user-bind"), { description = "s6 override" })',
    'hl.bind("SUPER + F9", hl.dsp.exec_cmd("touch /tmp/s6-new-bind"), { description = "s6 new bind" })',
)
OVERRIDE_MARK, NEW_MARK = "/tmp/s6-user-bind", "/tmp/s6-new-bind"
# Prints one "BIND <modmask> <key> <description> <arg>" line per bind (spaces in fields become _).
LIST_BINDS = (
    "import json,subprocess as s; "
    "[print(\"BIND\", b[\"modmask\"], b[\"key\"], str(b.get(\"description\")).replace(\" \", \"_\"), "
    "str(b.get(\"arg\")).replace(\" \", \"_\")) "
    "for b in json.loads(s.check_output([\"hyprctl\", \"-i\", \"0\", \"binds\", \"-j\"]))]"
)


def binds(sh):
    rc, out = sh.run(f"python3 -I -c '{LIST_BINDS}'")
    assert rc == 0, out
    return re.findall(r"^BIND (\d+) (\S+) (\S+) (\S+)\s*$", out, re.M)


def write_user_lua(sh):
    sh.run("mkdir -p ~/.config/hypr && : > ~/.config/hypr/user.lua")
    for line in USER_LUA:
        assert "'" not in line
        rc, out = sh.run(f"printf '%s\\n' '{line}' >> ~/.config/hypr/user.lua")
        assert rc == 0, out
    rc, out = sh.run("cat ~/.config/hypr/user.lua")
    assert rc == 0 and all(line in out for line in USER_LUA), out
    sh.say("S6-USERLUA user.lua written in the home of tester")


def login_through_greeter(vm, sh):
    g = Guest(vm, "")
    assert not g.hyprland_running("S6BEFORE"), "Hyprland already running before the greeter login"
    g.start_auth()
    g.type_keys(PASSWORD)
    vm.qmp.send_key("ret")
    deadline = time.monotonic() + 90
    while not g.hyprland_running("S6WAIT"):
        assert time.monotonic() < deadline, "no Hyprland for tester 90 s after the greeter login"
        time.sleep(3)
    rc, out = sh.run("for i in $(seq 30); do hyprctl -i 0 version > /dev/null 2>&1 && break; sleep 2; done; "
                     "hyprctl -i 0 version | head -n 1", timeout=120)
    assert rc == 0 and re.search(r"Hyprland", out), out
    rc, out = sh.run("ls -d /run/user/$(id -u)/hypr/*/")
    assert rc == 0 and re.search(r"^/run/user/\d+/hypr/\S+/\s*$", out, re.M), out
    sh.say("S6-HYPRLAND started through the greeter and answers hyprctl")


def check_binds(sh):
    found = binds(sh)
    lock = [b for b in found if b[0] == str(SUPER) and b[1].lower() == "l"]
    assert [b[2] for b in lock] == ["s6_override"], ("SUPER + L is not the user's bind alone", lock)
    # a Lua bind's "arg" is an opaque id, not the command: the marker file in check_keys proves the command
    assert not [b for b in found if b[2] == "lock_the_screen"], found
    new = [b for b in found if b[0] == str(SUPER) and b[1].lower() == "f9"]
    assert [b[2] for b in new] == ["s6_new_bind"], new
    shipped = [b for b in found if b[0] == str(SUPER) and b[1].lower() == "d"]
    assert [b[2] for b in shipped] == ["launcher"], ("the shipped SUPER + D bind is gone", shipped)
    sh.say("S6-BINDS SUPER L maps to the user command and the new bind is present")


def press(sh, vm, key, marker):
    rc, out = sh.run(f"rm -f {marker}; ! test -e {marker}")
    assert rc == 0, out
    vm.qmp.send_key("meta_l", key)
    deadline = time.monotonic() + 20
    while True:
        rc, out = sh.run(f"test -e {marker}")
        if rc == 0:
            return
        assert time.monotonic() < deadline, f"{marker} did not appear after SUPER + {key}"
        time.sleep(1)


def check_keys(sh, vm):
    press(sh, vm, "l", OVERRIDE_MARK)
    rc, out = sh.run("pgrep -u tester -x hyprlock")
    assert rc != 0, ("the shipped hyprlock bind still fires", out)
    sh.say("S6-OVERRIDE SUPER L created the marker and started no hyprlock")
    press(sh, vm, "f9", NEW_MARK)
    sh.say("S6-NEWBIND SUPER F9 created the second marker")


def userlua_session(vm):
    sh = Shell(vm, "S6RC")
    sh.login()
    write_user_lua(sh)
    login_through_greeter(vm, sh)
    check_binds(sh)
    check_keys(sh, vm)
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_s6_userlua():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="s6-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    userlua_session(vm)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return ("user.lua written, Hyprland started through the greeter, SUPER + L rebound to the user "
                    "command and a new bind present in hyprctl binds, both keys fire by QMP"), command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("S6-userlua", "a user's ~/.config/hypr/user.lua is loaded last on the installed system: it "
                "replaces a shipped bind (SUPER + L) and adds one, hyprctl lists both, and pressing the keys "
                "runs the user's commands", body)
