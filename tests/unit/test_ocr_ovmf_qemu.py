# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import os
import subprocess

import pytest

from tests.lib import ocr, ovmf, qemu


def test_ocr_skips_explicitly_when_tesseract_missing(tmp_path):
    result = ocr.ocr_image(tmp_path / "x.png", tesseract="")
    assert result.skipped and result.status == "SKIPPED: tesseract missing"


def test_ocr_reports_failure_not_success(tmp_path):
    result = ocr.ocr_image(tmp_path / "x.png", tesseract="/bin/false")
    assert result.status.startswith("FAILED")


def test_find_ovmf_missing_is_reported_not_assumed():
    with pytest.raises(ovmf.OvmfNotFound, match="edk2-ovmf"):
        ovmf.find_ovmf(candidates=(("/nonexistent/CODE.fd", "/nonexistent/VARS.fd"),))


def test_find_ovmf_picks_first_complete_pair(tmp_path):
    code, vars_ = tmp_path / "C.fd", tmp_path / "V.fd"
    code.write_bytes(b"c")
    vars_.write_bytes(b"v")
    half = tmp_path / "only_code.fd"
    half.write_bytes(b"c")
    found = ovmf.find_ovmf(candidates=((str(half), str(tmp_path / "none")), (str(code), str(vars_))))
    assert found == (str(code), str(vars_))


def test_fresh_vars_is_an_independent_copy(tmp_path):
    template = tmp_path / "V.fd"
    template.write_bytes(b"pristine")
    a = ovmf.fresh_vars(str(template), str(tmp_path / "a.fd"))
    b = ovmf.fresh_vars(str(template), str(tmp_path / "b.fd"))
    with open(a, "ab") as handle:
        handle.write(b"-dirty")
    assert open(b, "rb").read() == b"pristine" and template.read_bytes() == b"pristine"
    assert oct(os.stat(a).st_mode & 0o777) == "0o600"


def test_qemu_command_is_unprivileged_headless_and_uses_vars_copy():
    cmd = qemu.build_command("/i.iso", "/c.fd", "/run/vars.fd", 5, 6, "/s.log", kvm=False)
    assert cmd[0] == "qemu-system-x86_64" and "sudo" not in cmd
    assert "if=pflash,format=raw,file=/run/vars.fd" in cmd  # writable per-run copy
    assert "if=pflash,format=raw,readonly=on,file=/c.fd" in cmd
    assert "none" in cmd and "accel=tcg" in " ".join(cmd)
    assert any(a.startswith("socket,id=ser0,fd=5") for a in cmd)
    assert qemu.build_command("/i", "/c", "/v", 5, 6, "/s", kvm=True)[4] == "q35,accel=kvm"


def test_iso_is_a_virtio_scsi_cdrom_not_on_ahci():
    # OVMF can hang forever polling the q35 AHCI port before BdsDxe (see build_command).
    cmd = qemu.build_command("/i.iso", "/c.fd", "/v.fd", 5, 6, "/s.log")
    drives = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-drive"]
    cdrom = [d for d in drives if d.startswith("file=/i.iso,")]
    assert cdrom == ["file=/i.iso,if=none,id=cd0,media=cdrom,readonly=on"]
    devices = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-device"]
    assert "virtio-scsi-pci,id=scsi0" in devices
    assert "scsi-cd,drive=cd0,bus=scsi0.0" in devices


def test_stop_removes_the_per_run_vars_copy(tmp_path):
    class _Exited:
        def wait(self, timeout=None):
            return 0

    vm = qemu.QemuVM("x.iso", str(tmp_path))
    vars_copy = tmp_path / "OVMF_VARS.fd"
    vars_copy.write_bytes(b"vars")
    vm._proc, vm._vars_copy = _Exited(), str(vars_copy)
    vm.stop()
    assert not vars_copy.exists()


def test_stop_keeps_the_vars_copy_when_asked(tmp_path):
    """I2 boots the installed disk next: the boot entry the installer wrote must survive stop()."""
    class _Exited:
        def wait(self, timeout=None):
            return 0

    vm = qemu.QemuVM("x.iso", str(tmp_path), keep_vars=True)
    vars_copy = tmp_path / "OVMF_VARS.fd"
    vars_copy.write_bytes(b"vars")
    vm._proc, vm._vars_copy = _Exited(), str(vars_copy)
    vm.stop()
    assert vars_copy.exists() and "keep_vars" not in vm.options


def test_net_defaults_to_none_and_user_mode_is_opt_in():
    default = qemu.build_command("/i", "/c", "/v", 5, 6, "/s")
    assert default[default.index("-nic") + 1] == "none"
    user = qemu.build_command("/i", "/c", "/v", 5, 6, "/s", net="user")
    assert user[user.index("-nic") + 1] == "user"
    with pytest.raises(ValueError, match="net must be"):
        qemu.build_command("/i", "/c", "/v", 5, 6, "/s", net="bridge")


class _FakePopen:
    instances = []

    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        self.killed = self.waited = False
        _FakePopen.instances.append(self)

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return -9


def _vm_with_fakes(monkeypatch, tmp_path, handshake):
    _FakePopen.instances = []
    code, template = tmp_path / "CODE.fd", tmp_path / "VARS.fd"
    code.write_bytes(b"c")
    template.write_bytes(b"v")
    monkeypatch.setattr(qemu.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(qemu, "find_ovmf", lambda: (str(code), str(template)))
    monkeypatch.setattr(qemu.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(qemu.QmpClient, "handshake", handshake)
    return qemu.QemuVM("x.iso", str(tmp_path / "run"), kvm=False)


@pytest.mark.parametrize("failure", [RuntimeError("QMP handshake timeout"),
                                     KeyboardInterrupt()])
def test_start_terminates_qemu_when_the_handshake_fails(monkeypatch, tmp_path, failure):
    def handshake(self):
        raise failure

    vm = _vm_with_fakes(monkeypatch, tmp_path, handshake)
    with pytest.raises(type(failure)):
        vm.start()
    (proc,) = _FakePopen.instances
    assert proc.killed and proc.waited  # no orphaned VM
    assert vm._proc is None
    assert not (tmp_path / "run" / "OVMF_VARS.fd").exists()  # scratch cleaned up too


def test_qemu_stderr_goes_to_a_file_not_an_unread_pipe(monkeypatch, tmp_path):
    def handshake(self):
        raise RuntimeError("stop here")

    vm = _vm_with_fakes(monkeypatch, tmp_path, handshake)
    with pytest.raises(RuntimeError):
        vm.start()
    kwargs = _FakePopen.instances[0].kwargs
    assert kwargs["stderr"] is not subprocess.PIPE
    assert kwargs["stderr"].name == str(tmp_path / "run" / "qemu.stderr")
    assert kwargs["stderr"].closed  # stop() closed it


@pytest.mark.parametrize("path", ["/dev/sda", "/dev/nvme0n1", "/dev/../dev/sdb", "/dev", "/dev/null"])
def test_harness_refuses_dev_paths(path, tmp_path):
    with pytest.raises(qemu.DevicePathRefused):
        qemu.refuse_device_path(path)
    with pytest.raises(qemu.DevicePathRefused):
        qemu.QemuVM(path, tmp_path)


def test_harness_refuses_symlink_into_dev_and_workdir_in_dev(tmp_path):
    link = tmp_path / "disk.img"
    link.symlink_to("/dev/null")
    with pytest.raises(qemu.DevicePathRefused):
        qemu.QemuVM(str(link), tmp_path)
    image = tmp_path / "ok.iso"
    image.write_bytes(b"x")
    with pytest.raises(qemu.DevicePathRefused):
        qemu.QemuVM(str(image), "/dev/shm/x")
    assert qemu.QemuVM(str(image), tmp_path).iso == str(image)  # a plain image file is accepted


def test_credentials_become_smbios_oem_strings_and_default_to_none():
    assert "-smbios" not in qemu.build_command("/i", "/c", "/v", 5, 6, "/s")
    cmd = qemu.build_command("/i", "/c", "/v", 5, 6, "/s", credentials=[("seclegion.selftest", "report")])
    assert cmd[cmd.index("-smbios") + 1] == "type=11,value=io.systemd.credential:seclegion.selftest=report"
