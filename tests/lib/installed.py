# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""A shared, cached "installed system" for the VM gates (one ~5 min erase install, many boots).

`installed_base(iso)` installs once per (ISO, installer/ content) and keeps the disk read-only
under BASE_ROOT. `installed_vm(...)` boots a throwaway qcow2 overlay on it, so a gate may change anything
and the base stays pristine. The base itself is never booted: firstboot runs in every overlay boot.
"""
import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

from tests.lib import devloop
from tests.lib.qemu import QemuVM

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
INSTALLER = os.path.join(REPO, "installer")  # devloop mounts all of it, not only installd
BASE_ROOT = os.path.join(devloop.SCRATCH_ROOT, "installed-base")
COMPLETE = "complete"  # written last: a key dir without it is a half-built base
KEY_RE = re.compile(r"[0-9a-f]{16}")
GREETER = r"Started .*(greetd|[Gg]reeter)"  # unit Description, not its name
PROMPT = r"\[tester@\S+ ~\]\$ "
_iso_sha = {}


def installer_hash(root=INSTALLER):
    """sha256 of every file under `root` (relative path + bytes): devloop mounts this checkout's installer."""
    digest = hashlib.sha256()
    for top, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(top, name)
            digest.update(os.path.relpath(path, root).encode() + b"\0")
            with open(path, "rb") as fh:
                digest.update(hashlib.sha256(fh.read()).digest())
    return digest.hexdigest()


def base_key(iso_sha, installd_sha):
    return hashlib.sha256((iso_sha + installd_sha).encode()).hexdigest()[:16]


def is_complete(key_dir):
    """Marker and disk both: a marker whose disk was deleted is a half-built base, rebuilt next run."""
    return all(os.path.isfile(os.path.join(key_dir, n)) for n in (COMPLETE, "target.qcow2"))


def prune_other_bases(keep_key, root=None):
    """Delete the other complete key dirs (the disk is tight: one base). Exact key-named dirs only."""
    root = root or BASE_ROOT
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if name != keep_key and KEY_RE.fullmatch(name) and os.path.isfile(os.path.join(path, COMPLETE)):
            shutil.rmtree(path)


def overlay_command(base, overlay):
    """qemu-img argv for a qcow2 overlay on `base` (absolute backing path: the overlay may live anywhere)."""
    return ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", os.path.abspath(base), overlay]


def installed_base(iso):
    """(base_qcow2, base_OVMF_VARS) of the installed system for `iso`; installs on a miss."""
    sha = _iso_sha.get(iso)
    if sha is None:
        sha = _iso_sha[iso] = _sha256_file(iso)
    key = base_key(sha, installer_hash())
    key_dir = os.path.join(BASE_ROOT, key)
    disk, nvram = os.path.join(key_dir, "target.qcow2"), os.path.join(key_dir, "OVMF_VARS.fd")
    if is_complete(key_dir):
        return disk, nvram
    if os.path.isdir(key_dir):
        shutil.rmtree(key_dir)  # a half-built base from an earlier failed run
    run = _i2_run().fresh_install("erase", (), True)
    scratch = run.scratch
    try:
        assert run.error is None, run.error
        os.makedirs(key_dir)
        shutil.move(os.path.join(scratch, "target.qcow2"), disk)
        shutil.move(os.path.join(scratch, "boot", "OVMF_VARS.fd"), nvram)
        os.chmod(disk, 0o444)
        os.chmod(nvram, 0o444)
        with open(os.path.join(key_dir, COMPLETE), "w") as fh:
            fh.write(f"iso {sha}\n")
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    prune_other_bases(key)
    return disk, nvram


def _i2_run():
    """tests/install/test_i2_run, imported lazily (it is test code, with the install fixtures)."""
    path = os.path.join(REPO, "tests", "install")
    if path not in sys.path:
        sys.path.insert(0, path)
    import test_i2_run  # noqa: PLC0415

    return test_i2_run


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextlib.contextmanager
def installed_vm(iso, scratch, memory_mb=4096, ro_images=(), no_reboot=False):
    """Boot a fresh overlay of the installed base to the greeter; the caller owns (and deletes) `scratch`."""
    base, base_vars = installed_base(iso)
    overlay = os.path.join(scratch, "overlay.qcow2")
    subprocess.run(overlay_command(base, overlay), check=True, stdout=subprocess.DEVNULL)  # noqa: S603
    boot_dir = os.path.join(scratch, "boot")
    os.makedirs(boot_dir, exist_ok=True)
    shutil.copyfile(base_vars, os.path.join(boot_dir, "OVMF_VARS.fd"))
    os.chmod(os.path.join(boot_dir, "OVMF_VARS.fd"), 0o644)  # the base copy is 0444
    with QemuVM(iso, boot_dir, net="none", memory_mb=memory_mb, disks=[(overlay, devloop.TARGET_SERIAL)],
                ro_images=list(ro_images), boot="disk", reuse_vars=True, no_reboot=no_reboot) as vm:
        vm.serial.wait_for(GREETER, 300)
        time.sleep(20)
        yield vm


SAY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 @._-]*")  # what Shell.say can type safely


class Shell:
    """The installed system's serial getty as user `tester` (password PASSWORD), one command at a time."""

    def __init__(self, vm, prefix="SLRC"):
        self.vm, self.prefix, self.n = vm, prefix, 0

    def login(self):
        s = self.vm.serial
        s.send("\n")
        s.wait_for(r"login: ", 120)
        s.send("tester\n")
        s.wait_for(r"Password: ", 30)
        s.send(_i2_run().PASSWORD + "\n")  # the getty does not echo it
        s.wait_for(PROMPT, 60)

    def sudo_prime(self):
        s = self.vm.serial
        s.send("sudo -k; sudo -v\n")
        s.wait_for(r"password for tester", 30)
        s.send(_i2_run().PASSWORD + "\n")  # sudo does not echo it
        s.wait_for(PROMPT, 30)

    def run(self, cmd, timeout=60):
        """(exit status, output) of `cmd`; the marker is split so the typed echo cannot match it."""
        self.n += 1
        mark = f"{self.prefix}{self.n}"
        typed = f"echo {mark[:3]}''{mark[3:]}:$?"
        self.vm.serial.send(f"{cmd}; {typed}\n")
        self.vm.serial.wait_for(re.escape(mark) + r":\d+", timeout)
        # Not an offset taken before sending: a prompt's escape sequence (systemd's OSC 3008) still arriving
        # at that moment is unstripped in text(), and stripped once complete, which shifted the offset.
        text = self.vm.serial.text()
        text = text[text.rfind(typed):] if typed in text else text
        rc = int(re.findall(re.escape(mark) + r":(\d+)", text)[-1])
        out = text.split("\n", 1)[1] if "\n" in text else text
        return rc, out[: out.rfind(mark[:3] + mark[3:] + ":")] if mark in out else out

    def say(self, line):
        """Print `line` on the serial console from the guest, split so the typed echo cannot match it.

        Plain words only (no quotes, `$`, `;`, `&`): it is typed into a shell."""
        assert SAY_RE.fullmatch(line), line
        rc, out = self.run(f"echo {line[:3]}''{line[3:]}")
        assert rc == 0, out

    def snaps(self):
        rc, out = self.run("sudo -n snapper -c root list --columns number,type")
        assert rc == 0, out
        rows = re.finditer(r"^\s*(\d+)\s*[|\u2502]\s*(\w[\w-]*)\s*$", out, re.M)  # ASCII or UTF-8 table
        return {int(m.group(1)): m.group(2) for m in rows}
