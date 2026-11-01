# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Boot an ISO under QEMU + OVMF as the invoking user, with serial + QMP channels.

Both channels are pre-connected socketpairs handed to QEMU as inherited fds, so
there is no socket-path race and nothing to poll for.
"""

import os
import shutil
import socket
import subprocess

from tests.lib.ovmf import find_ovmf, fresh_vars
from tests.lib.qmp import QmpClient
from tests.lib.serial import SerialCapture

NET_MODES = ("none", "user")


class DevicePathRefused(ValueError):
    """The harness boots image files only; a /dev path (a physical disk or USB stick) is refused."""


def refuse_device_path(path, image=True):
    """Raise DevicePathRefused for /dev/*, a symlink resolving there, or (image=True) a non-regular file.

    Checked on the literal path, its realpath and its file type, so neither `/dev/sda`,
    `/dev/../dev/sda`, a symlink to a device, nor a block/character device node gets through.
    """
    literal = os.path.normpath(os.path.abspath(path))
    real = os.path.realpath(path)
    for candidate in (literal, real):
        if candidate == "/dev" or candidate.startswith("/dev/"):
            raise DevicePathRefused(f"refusing {path!r}: the harness never touches /dev "
                                    "(image files only)")
    if image and os.path.exists(real) and not os.path.isfile(real):
        raise DevicePathRefused(f"refusing {path!r}: not a regular image file")
    return real


def create_blank_disk(path, size="60G"):
    """Create a sparse qcow2 at `path` (never under /dev) with qemu-img; returns the path."""
    refuse_device_path(path, image=False)
    subprocess.run(["qemu-img", "create", "-f", "qcow2", path, size],  # noqa: S603,S607 - fixed argv
                   check=True, stdout=subprocess.DEVNULL)
    return path


def _disk_args(disks, ro_images, boot, first_id):
    """Extra scsi-hd devices on the existing virtio-scsi bus. Entries are path or (path, serial).

    scsi-hd reports vendor QEMU / model QEMU HARDDISK, so they show under /dev/disk/by-id as
    scsi-0QEMU_QEMU_HARDDISK_<serial>, which the DEV-build installer accepts as a QEMU disk.
    """
    args = []
    entries = [(d, False) for d in disks] + [(d, True) for d in ro_images]
    for n, (entry, readonly) in enumerate(entries):
        path, serial = entry if isinstance(entry, (tuple, list)) else (entry, f"SLDISK{n}")
        fmt = "qcow2" if str(path).endswith(".qcow2") else "raw"
        drive = f"d{first_id + n}"
        spec = f"file={path},if=none,id={drive},format={fmt}" + (",readonly=on" if readonly else "")
        dev = f"scsi-hd,drive={drive},bus=scsi0.0,serial={serial}"
        if boot == "disk" and n == 0 and not readonly:
            dev += ",bootindex=0"
        args += ["-drive", spec, "-device", dev]
    return args


def kvm_usable():
    return os.access("/dev/kvm", os.R_OK | os.W_OK)


def build_command(iso, ovmf_code, vars_copy, serial_fd, qmp_fd, serial_log,
                  memory_mb=4096, cpus=2, vga="std", kvm=True, qemu="qemu-system-x86_64",
                  net="none", no_reboot=True, credentials=(), disks=(), ro_images=(), boot="cdrom"):
    """Pure command builder (unit-tested). Secure Boot off, headless.

    net: "none" (default) gives the guest no NIC at all. The M0 boot test only needs the
    console, so no network keeps the run deterministic, offline and unable to reach the
    host's LAN. "user" adds QEMU user-mode (SLIRP) NAT for tests that need outbound
    access (package mirrors, install tests); opt in per test.
    credentials: (name, value) pairs handed to the guest as SMBIOS OEM strings, which systemd
    imports as system credentials (the M2 self test reads `seclegion.selftest`). Never a secret.
    disks / ro_images: extra writable / read-only image files (see _disk_args). boot="cdrom"
    (default) boots the ISO; boot="disk" makes the first disk the boot device.
    no_reboot=True ends QEMU at a guest reset (a crash or reboot ends the run). The firmware-setup
    test needs False: GRUB's `fwsetup` sets OsIndications and resets, and OVMF then shows its menu.
    """
    if net not in NET_MODES:
        raise ValueError(f"net must be one of {NET_MODES}, not {net!r}")
    if boot not in ("cdrom", "disk"):
        raise ValueError(f"boot must be 'cdrom' or 'disk', not {boot!r}")
    accel = "kvm" if kvm else "tcg"
    return [
        qemu, "-name", "seclegion-harness", "-machine", f"q35,accel={accel}",
        "-cpu", "host" if kvm else "max", "-smp", str(cpus), "-m", str(memory_mb),
        "-display", "none", "-vga", vga, "-nic", net,
        *(["-no-reboot"] if no_reboot else []),
        "-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
        "-drive", f"if=pflash,format=raw,file={vars_copy}",
        # CD-ROM on virtio-scsi, not the q35 default (ICH9 AHCI): on this host's QEMU 11.1 +
        # KVM, OVMF intermittently spins forever polling AHCI port 0 PxCMD before BdsDxe,
        # so the boot never reaches the menu (about half of runs; 0 of 6 on virtio-scsi).
        "-drive", f"file={iso},if=none,id=cd0,media=cdrom,readonly=on",
        "-device", "virtio-scsi-pci,id=scsi0", "-device",
        "scsi-cd,drive=cd0,bus=scsi0.0" + (",bootindex=0" if boot == "cdrom" and disks else ""),
        *_disk_args(disks, ro_images, boot, 1),
        "-chardev", f"socket,id=ser0,fd={serial_fd},logfile={serial_log}",
        "-serial", "chardev:ser0",
        "-chardev", f"socket,id=qmp0,fd={qmp_fd}",
        "-mon", "chardev=qmp0,mode=control",
        *[arg for name, value in credentials
          for arg in ("-smbios", f"type=11,value=io.systemd.credential:{name}={value}")],
    ]


class QemuVM:
    """Context manager: `with QemuVM(iso, workdir) as vm: vm.serial.wait_for(...)`."""

    def __init__(self, iso, workdir, **options):
        refuse_device_path(iso)
        refuse_device_path(workdir, image=False)
        for entry in (*options.get("disks", ()), *options.get("ro_images", ())):
            refuse_device_path(entry[0] if isinstance(entry, (tuple, list)) else entry)
        if "mem" in options:
            options["memory_mb"] = options.pop("mem")
        self.iso = os.path.abspath(iso)
        self.workdir = os.path.abspath(workdir)
        self.options = options
        self.serial_log = os.path.join(self.workdir, "serial.log")
        self.command = None
        self.serial = None
        self.qmp = None
        self._proc = None
        self._stderr = None
        self._vars_copy = None
        self._keep_vars = bool(options.pop("keep_vars", False))  # caller boots the installed disk next

    def start(self):
        if not shutil.which("qemu-system-x86_64"):
            raise RuntimeError("qemu-system-x86_64 not found on PATH")
        os.makedirs(self.workdir, exist_ok=True)
        code, vars_template = find_ovmf()  # raises OvmfNotFound: never assume it exists
        vars_path = os.path.join(self.workdir, "OVMF_VARS.fd")
        if self.options.pop("reuse_vars", False) and os.path.exists(vars_path):
            vars_copy = vars_path  # keeps the boot entries an earlier run wrote (installed-system boot)
        else:
            vars_copy = fresh_vars(vars_template, vars_path)
        self._vars_copy = vars_copy
        serial_host, serial_vm = socket.socketpair()
        qmp_host, qmp_vm = socket.socketpair()
        self.command = build_command(
            self.iso, code, vars_copy, serial_vm.fileno(), qmp_vm.fileno(), self.serial_log,
            kvm=self.options.pop("kvm", kvm_usable()), **self.options,
        )
        # stderr goes to a file, not a PIPE nobody reads (a full pipe would stall QEMU).
        self._stderr = open(os.path.join(self.workdir, "qemu.stderr"), "wb")  # noqa: SIM115
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, runs as the invoking user
                self.command, pass_fds=(serial_vm.fileno(), qmp_vm.fileno()),
                stdout=subprocess.DEVNULL, stderr=self._stderr,
            )
            serial_vm.close()
            qmp_vm.close()
            self.serial = SerialCapture(serial_host).start()
            self.qmp = QmpClient(qmp_host)
            self.qmp.handshake()
        except BaseException:  # incl. KeyboardInterrupt: never leave a running VM behind
            serial_vm.close()
            qmp_vm.close()
            self.stop(force=True)  # handshake never completed: do not wait on QMP to quit
            serial_host.close()
            qmp_host.close()
            raise
        return self

    def screendump(self, name="screen.png"):
        return self.qmp.screendump(os.path.join(self.workdir, name))

    def stop(self, force=False):
        if self._proc is not None:
            try:
                if not force:
                    if self.qmp:
                        self.qmp.quit()
                    self._proc.wait(timeout=15)
            except Exception:
                force = True
            if force:
                self._proc.kill()
                self._proc.wait()
            self._proc = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None
        if self._vars_copy and os.path.isfile(self._vars_copy) and not self._keep_vars:
            os.remove(self._vars_copy)  # per-run scratch (EDK2 template copy), not evidence
        self._vars_copy = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
