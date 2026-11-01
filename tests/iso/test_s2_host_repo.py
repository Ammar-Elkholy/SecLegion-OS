# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Checkpoint A gate 19 (S2-host-repo): a VM installs a package from the signed repo served on the host.

The built repo directory is served by `python -m http.server` bound to 127.0.0.1; the guest (QEMU user-mode
net, host = 10.0.2.2) gets a throwaway pacman.conf with `SigLevel = Required DatabaseRequired` and installs
`hello` from it. The commands are typed into the rescue shell (tty1) through QMP; their output goes to
/dev/ttyS0, which is the oracle. Signatures must verify against the keyring already in the ISO.
"""

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import pytest

import evidence
from tests.lib import bootgate
from tests.lib.bootgate import MODE_TIMEOUT, REPO, choose, wait_for_menu
from tests.lib.qemu import QemuVM

PACKAGE = "hello"
HOST_IN_GUEST = "10.0.2.2"  # QEMU user-mode net: the host's loopback as seen from the guest
KEY_DELAY = 0.03  # seconds between typed keys: a burst into the busy guest console loses/garbles keys
CONF = "/tmp/s2.conf"  # inside the guest's RAM filesystem
REPO_DIRS = (os.path.join(REPO, "out", "repo", "seclegion"), "/var/tmp/seclegion-build/out/repo/seclegion")


def find_repo_dir():
    explicit = os.environ.get("SECLEGION_REPO_DIR")
    for path in [explicit] if explicit else REPO_DIRS:
        if path and os.path.isfile(os.path.join(path, "seclegion.db")):
            return path
    return None


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def to_tty(vm, command):
    """Type `command` into the rescue shell; its stdout/stderr land on the serial console."""
    vm.qmp.type_text(command + " > /dev/ttyS0 2>&1\n", delay=KEY_DELAY)


def when_ok(vm, command, marker):
    vm.qmp.type_text(f"{command} > /dev/ttyS0 2>&1 && echo {marker} > /dev/ttyS0\n", delay=KEY_DELAY)


def collect(vm, result_dir):
    """Keep the serial log and a screendump with the evidence, pass or fail."""
    bootgate.take_screen(vm)
    for name in ("serial.log", "screen.png"):
        if os.path.isfile(os.path.join(vm.workdir, name)):
            shutil.copy(os.path.join(vm.workdir, name), result_dir)


@pytest.mark.iso
def test_s2_host_repo_vm_installs_from_a_repo_served_on_the_host():
    repo_dir = find_repo_dir()
    if not repo_dir:
        pytest.skip("NOT RUN: no built repo (out/repo/seclegion; or set SECLEGION_REPO_DIR)")
    scratch_root = "/var/tmp/seclegion-build/vm"
    os.makedirs(scratch_root, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="s2-", dir=scratch_root)

    def body(result_dir, iso):
        port = free_port()
        server = subprocess.Popen(  # noqa: S603 - fixed argv, loopback only, stopped below by this handle
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", repo_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with contextlib.ExitStack() as stack:
                vm = stack.enter_context(QemuVM(iso, os.path.join(scratch, "vm"), net="user"))
                stack.callback(collect, vm, result_dir)  # runs first (LIFO), while the VM is still up
                command = evidence.repo_relative(vm.command, REPO)
                wait_for_menu(vm)
                choose(vm, bootgate.ENTRY_RESCUE)
                vm.serial.wait_for(r"SECLEGION-MODE=rescue", MODE_TIMEOUT)
                deadline = time.monotonic() + 180
                while True:  # keys typed before the autologin shell exists are lost: retry until it answers
                    # ctrl-c first: a half-lost line ("ho ...") gets zsh's correct prompt, which would take
                    # the next attempt's "e" as its answer and loop forever
                    vm.qmp.send_key("ctrl", "c")
                    time.sleep(0.5)
                    vm.qmp.type_text("echo S2-SHELL-READY > /dev/ttyS0\n", delay=KEY_DELAY)
                    try:
                        vm.serial.wait_for(r"S2-SHELL-READY", 5)
                        break
                    except AssertionError:
                        assert time.monotonic() < deadline, "no root shell answered on tty1"
                while True:  # the keyring must be initialised and populated before packages can verify
                    vm.qmp.type_text(
                        "echo S2-PI $(systemctl is-active pacman-init) > /dev/ttyS0\n", delay=KEY_DELAY
                    )
                    try:
                        vm.serial.wait_for(r"S2-PI active", 10)
                        break
                    except AssertionError:
                        assert time.monotonic() < deadline + 300, "pacman-init never became active"
                level = "SigLevel = Required DatabaseRequired"
                vm.qmp.type_text(
                    f"(echo '[options]'; echo '{level}'; echo '[seclegion]'; echo '{level}'; "
                    f"echo 'Server = http://{HOST_IN_GUEST}:{port}') > {CONF}\n",
                    delay=KEY_DELAY,
                )
                pacman = f"pacman --config {CONF}"
                when_ok(vm, f"{pacman} -Sy", "S2-REPO-SYNC-OK")
                vm.serial.wait_for(r"S2-REPO-SYNC-OK", 180)
                when_ok(vm, f"{pacman} -S --noconfirm {PACKAGE}", "S2-REPO-INSTALL-OK")
                vm.serial.wait_for(r"S2-REPO-INSTALL-OK", 180)
                vm.qmp.type_text(f"echo S2-REPO-QUERY $(pacman -Q {PACKAGE}) > /dev/ttyS0\n", delay=KEY_DELAY)
                vm.serial.wait_for(rf"S2-REPO-QUERY {PACKAGE} \d", 30)
            return (
                f"rescue shell synced [seclegion] from http://{HOST_IN_GUEST}:<port> "
                f"with SigLevel = Required "
                f"DatabaseRequired, installed {PACKAGE}, pacman -Q {PACKAGE} succeeds",
                command,
                "n/a",
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    try:
        status, actual = bootgate.run_gate(
            "S2-host-repo",
            "a VM installs a package from a signed repo served on the host, signatures required",
            body,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)  # the directory created above
    if status == "NOT RUN":
        pytest.skip(f"NOT RUN: {actual}")
    assert status == "PASS", actual
