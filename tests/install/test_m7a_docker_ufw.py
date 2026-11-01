# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M7a / D-DKR-1 (VM): the container engine under ufw: the DOCKER-USER chain hands new connections to ufw.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py). The guest
prints one M7A-DKR* line per passed check; the evidence row M7a-docker-ufw checks them in order.
No container is started (the installed system is offline): the rules and the service are checked.
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

from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import Shell, installed_vm  # noqa: E402

ENGINE = "dock" + "er"  # the same split as installer/installd/post.py
JUMP = "-A DOCKER-USER -j ufw-user-forward"
DROP = "-A DOCKER-USER -m conntrack --ctstate NEW -j DROP"


def order_ok(rules):
    """The ufw jump comes before the drop of new connections."""
    lines = [ln.strip() for ln in rules.splitlines()]
    return JUMP in lines and DROP in lines and lines.index(JUMP) < lines.index(DROP)


def docker_ufw_session(vm):
    sh = Shell(vm, "M7ADK")
    sh.login()
    sh.sudo_prime()
    deadline = time.monotonic() + 120  # firstboot, then the service is up
    while sh.run("test -e /var/lib/seclegion/firstboot.done")[0] != 0:
        assert time.monotonic() < deadline, "firstboot never finished"
        time.sleep(3)
    while sh.run(f"systemctl is-active {ENGINE}.service")[0] != 0:
        assert time.monotonic() < deadline, f"{ENGINE}.service never became active"
        time.sleep(3)

    rc, out = sh.run("sudo -n ufw status")
    assert rc == 0, out
    assert re.search(r"^Status: active$", out, re.M), out
    # ufw status reads ufw.conf: it says active even when ufw.service failed to restore the rules
    for unit in ("ufw", ENGINE):
        rc, out = sh.run(f"systemctl is-active {unit}.service")
        assert rc == 0 and re.search(r"^active$", out, re.M), (unit, out)
    sh.say("M7A-DKR ufw active and service active")

    rc, out = sh.run("sudo -n iptables -S DOCKER-USER")
    assert rc == 0, out
    assert order_ok(out), out
    sh.say("M7A-DKR4 ufw-user-forward before NEW drop")

    rc, out = sh.run("sudo -n ip6tables -S DOCKER-USER")  # our after6.rules block declares the chain
    if rc == 0:
        assert order_ok(out), out
        sh.say("M7A-DKR6 ufw-user-forward before NEW drop")
    else:
        sh.say("M7A-DKR6 chain absent")

    rc, out = sh.run(f"{ENGINE} info --format '{{{{.ServerVersion}}}}'")  # tester is in the group: no sudo
    assert rc == 0 and re.search(r"^\d+\.\d+", out, re.M), out
    sh.say("M7A-DKRINFO tester without sudo")
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_m7a_docker_ufw():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m7a-dk-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    docker_ufw_session(vm)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return "ufw active, DOCKER-USER hands new connections to ufw, docker info ok", command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("M7a-docker-ufw", "the container engine under ufw: DOCKER-USER sends new connections to ufw "
                "before dropping them, and the engine service answers the tester without sudo", body)
