# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M7a / G58 (VM): the post-step defaults of an installed system: ufw deny-in, sshd off, a baseline snapshot.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py). The guest
prints one M7A-* line per passed check; the evidence row M7a-defaults checks them in order.
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
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))

import post  # noqa: E402
from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import Shell, installed_vm  # noqa: E402

BASELINE = "seclegion-baseline"  # pkgs/seclegion-firstboot/seclegion-firstboot: BASELINE


def defaults_session(vm):
    sh = Shell(vm, "M7ARC")
    sh.login()
    sh.sudo_prime()
    deadline = time.monotonic() + 120  # firstboot creates the baseline snapshot
    while sh.run("test -e /var/lib/seclegion/firstboot.done")[0] != 0:
        assert time.monotonic() < deadline, "firstboot never finished"
        time.sleep(3)

    rc, out = sh.run("sudo -n ufw status verbose")
    assert rc == 0, out
    assert re.search(r"^Status: active$", out, re.M), out
    assert re.search(r"^Default: deny \(incoming\)", out, re.M), out
    rc, out = sh.run("systemctl is-active ufw.service")  # ufw status alone says active from ufw.conf
    assert rc == 0 and re.search(r"^active$", out, re.M), out
    sh.say("M7A-UFW deny-incoming")

    # post.py masks exactly these units (symlinks to /dev/null); none of the running ones is active
    units = post.SSHD_MASKED
    rc, out = sh.run("readlink " + " ".join(f"/etc/systemd/system/{u}" for u in units))
    assert rc == 0 and re.findall(r"^\S+$", out, re.M) == ["/dev/null"] * len(units), out
    running = [u for u in units if "@" not in u]  # a template has no active state
    rc, out = sh.run("systemctl is-active " + " ".join(running))
    assert rc != 0 and re.findall(r"^\w+$", out, re.M) == ["inactive"] * len(running), out
    sh.say("M7A-SSHD masked inactive")

    rc, out = sh.run("sudo -n snapper -c root list --columns number,description")
    assert rc == 0, out
    hit = re.search(rf"^\s*(\d+)\s*[|\u2502]\s*{re.escape(BASELINE)}\s*$", out, re.M)  # UTF-8 table
    assert hit, f"no {BASELINE} snapshot: {out}"
    sh.say(f"M7A-BASELINE {hit.group(1)}")
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_m7a_defaults():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m7a-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    defaults_session(vm)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return "ufw deny-incoming, sshd masked and inactive, baseline snapshot present", command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("M7a-defaults", "the post-step defaults: ufw deny-in, sshd inactive, and a "
                f"`{BASELINE}` snapshot present", body)
