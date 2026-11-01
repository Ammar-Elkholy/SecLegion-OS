# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""M11 / G72 (VM): a snap-pac pair per pacman transaction, `seclegion-rescue rollback`, boots after.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py), booted with
a serial getty (user `tester`, sudo with the password typed at the prompt, which is not echoed). The repo
copy of seclegion-rescue comes in on a read-only image (the ISO's package is the old stub). The offline
transaction removes tesseract-data-ara (`pacman -Rdd`: the dependency check is not what is tested).
The guest prints one M11-* line per step; the evidence row M11-rollback checks them in order.
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

from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import GREETER, Shell, installed_vm  # noqa: E402

PKG = "tesseract-data-ara"
RESCUE_MNT = "/run/sl-rescue"


def rollback_session(vm):
    """The gate: a pacman transaction, its snap-pac pair, the rollback, the reboot. Prints a result line
    per step from the guest (tests/lib/installed.py Shell.say), which the evidence patterns check."""
    sh = Shell(vm, "M11RC")
    sh.login()
    sh.sudo_prime()
    # firstboot's baseline snapshot proves the snapper root config works; wait for it
    deadline = time.monotonic() + 120
    while sh.run("test -e /var/lib/seclegion/firstboot.done")[0] != 0:
        assert time.monotonic() < deadline, "firstboot never finished"
        time.sleep(3)
    before = sh.snaps()
    assert before, "no snapper root config / no snapshots"
    assert sh.run(f"pacman -Q {PKG}")[0] == 0

    # one offline transaction -> exactly one new pre/post pair
    rc, out = sh.run(f"sudo -n pacman -Rdd --noconfirm {PKG}", 180)
    assert rc == 0, out
    after = sh.snaps()
    new = {n: t for n, t in after.items() if n not in before}
    assert sorted(new.values()) == ["post", "pre"], (before, after)
    pre = next(n for n, t in new.items() if t == "pre")
    post = next(n for n, t in new.items() if t == "post")
    assert sh.run(f"pacman -Q {PKG}")[0] != 0
    sh.say(f"M11-PAIR pre {pre} post {post}")

    # the repo's seclegion-rescue from the read-only image
    rc, out = sh.run(f"sudo -n mkdir -p {RESCUE_MNT} && sudo -n mount -o ro "
                     f"{devloop.INSTALLER_BY_ID} {RESCUE_MNT}")
    assert rc == 0, out
    rc, out = sh.run(f"sudo -n bash {RESCUE_MNT}/seclegion-rescue rollback --yes {pre}", 300)
    assert rc == 0, out
    assert "Reboot now" in out and "@broken-" in out, out
    sh.say(f"M11-ROLLBACK to {pre}")
    vm.serial.send("sudo -n systemctl reboot\n")

    vm.serial.wait_for(GREETER, 400)  # after the reboot (cursor moved)
    time.sleep(20)
    sh.login()
    sh.sudo_prime()
    rc, out = sh.run(f"pacman -Q {PKG}")
    assert rc == 0, f"{PKG} is not back after the rollback: {out}"
    rc, out = sh.run("sudo -n btrfs subvolume list /")
    assert rc == 0 and re.search(r"path @broken-\d{8}T\d{6}Z$", out, re.M), out
    sh.say(f"M11-BACK {PKG} restored with @broken")
    assert "Failed to start" not in vm.serial.text()
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_m11_rollback_after_pacman_transaction_boots():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m11-", dir=devloop.SCRATCH_ROOT)
        try:
            image = devloop.build_installer_image(
                os.path.join(REPO, "pkgs", "seclegion-rescue"), os.path.join(scratch, "rescue.img"))
            with installed_vm(iso, scratch, ro_images=[(image, devloop.INSTALLER_SERIAL)]) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    rollback_session(vm)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return "snap-pac pair, rollback to the pre snapshot, booted to the greeter", command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("M11-rollback", "a snap-pac pair per pacman transaction, `seclegion-rescue rollback`, "
                "and the system boots afterwards", body)
