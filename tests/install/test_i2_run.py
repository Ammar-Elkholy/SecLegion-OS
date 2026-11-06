# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""I2: seclegion-install unit checks (pure) and the full VM install (@iso)."""
import functools
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))

import evidence  # noqa: E402
from tests.lib import bootgate, devloop  # noqa: E402
from tests.lib.qemu import QemuVM  # noqa: E402

PASSWORD = "test-pass-1"
LUKS_PASSPHRASE = "test-luks-2"
MIB = 1 << 20
DISK_BYTES = 60 << 30
ESP_START, ESP_MIB = 1, 100
NTFS_START, NTFS_MIB = 101, 32
DATA_START, DATA_MIB = 101, 64  # partition mode: a data partition that must survive
LINUX_FS = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"


def load_install():
    path = os.path.join(REPO, "installer", "installd", "seclegion-install")
    loader = importlib.machinery.SourceFileLoader("seclegion_install", path)
    spec = importlib.util.spec_from_loader("seclegion_install", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_install_argv_is_offline_and_silent():
    argv = load_install().archinstall_argv("/run/x")
    for flag in ("--silent", "--offline", "--skip-ntp", "--skip-wkd"):
        assert flag in argv
    assert "/run/x/user_credentials.json" in argv


def test_install_offline_conf_is_signed_and_cache_only():
    import post
    m = load_install()
    post.check_pacman_conf(m.OFFLINE_CONF)
    assert "http" not in m.OFFLINE_CONF


def test_post_argv_scrubs_the_tmpdir():
    argv = load_install().post_argv("/run/x")
    assert argv[argv.index("--creds-dir") + 1] == "/run/x" and "/mnt" in argv


def test_install_hints_file_only_passes_opt_in_tiers():
    m = load_install()
    got = m.opt_in_hints({"gaming": True, "virt": False, "dev": True, "username": "root"})
    assert got == {"gaming": True}
    assert m.opt_in_hints({"virt": "yes"}) == {} and m.opt_in_hints([1]) == {}


def test_install_hints_flag_reaches_post_hints(tmp_path, monkeypatch):
    m = load_install()
    seen = {}
    monkeypatch.setattr(m.c, "build_config", lambda a, f: ({}, {}))
    monkeypatch.setattr(m.c, "write", lambda cfg, cr, tmp, hints: seen.setdefault("hints", hints))
    monkeypatch.setattr(m.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "run"))
    monkeypatch.setattr(m, "LIVE_CONF", str(tmp_path / "pacman.conf"))
    monkeypatch.setattr(m, "ensure_keyring", lambda: None)
    monkeypatch.setattr(m, "run", lambda argv: None)
    (tmp_path / "pacman.conf").write_text("[options]\n")
    (tmp_path / "run").mkdir()
    answers = {"disk": "/dev/disk/by-id/x", "username": "ammar", "password": "p", "confirm": "X",
               "mode": "erase", "luks": False, "timezone": "UTC"}
    (tmp_path / "a.json").write_text(json.dumps(answers))
    (tmp_path / "f.json").write_text("{}")
    (tmp_path / "h.json").write_text(json.dumps({"virt": True, "dev": True}))
    assert m.main(["--answers", str(tmp_path / "a.json"), "--facts", str(tmp_path / "f.json"),
                   "--hints", str(tmp_path / "h.json")]) == 0
    assert seen["hints"]["virt"] is True and "dev" not in seen["hints"]


def make_windows_like_disk(path, scratch):
    """Raw GPT image file with an ESP (fat32) and a clean NTFS partition; returns (start, size) bytes
    of the NTFS partition. Image files only: sfdisk, mkfs.fat, mkntfs and dd conv=notrunc."""
    for tool in ("sfdisk", "mkfs.fat", "mkntfs"):
        if not shutil.which(tool):
            pytest.skip(f"NOT RUN: {tool} missing (ntfs-3g / dosfstools / util-linux)")
    with open(path, "wb") as fh:
        fh.truncate(DISK_BYTES)
    script = (f"label: gpt\nstart={ESP_START * 2048}, size={ESP_MIB * 2048}, "
              "type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n"
              f"start={NTFS_START * 2048}, size={NTFS_MIB * 2048}, "
              "type=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7\n")
    subprocess.run(["sfdisk", "--quiet", path], input=script.encode(), check=True)  # noqa: S603,S607
    for name, start, mib, mk in (("esp", ESP_START, ESP_MIB, ["mkfs.fat", "-F", "32"]),
                                 ("ntfs", NTFS_START, NTFS_MIB, ["mkntfs", "-F", "-f", "-Q"])):
        part = os.path.join(scratch, name + ".img")
        with open(part, "wb") as fh:
            fh.truncate(mib * MIB)
        subprocess.run([*mk, part], check=True, capture_output=True)  # noqa: S603
        if name == "esp" and shutil.which("mcopy"):  # stub bootmgfw.efi: the Windows entry needs one
            stub = os.path.join(scratch, "bootmgfw.efi")
            with open(stub, "wb") as fh:
                fh.write(b"MZ-stub")
            for argv in (["mmd", "-i", part, "::EFI", "::EFI/Microsoft", "::EFI/Microsoft/Boot"],
                         ["mcopy", "-i", part, stub, "::EFI/Microsoft/Boot/bootmgfw.efi"]):
                subprocess.run(argv, check=True, capture_output=True)  # noqa: S603
        subprocess.run(["dd", f"if={part}", f"of={path}", "bs=1M", f"seek={start}", "conv=notrunc",  # noqa: S603,S607
                        "status=none"], check=True)
        os.remove(part)
    return NTFS_START * MIB, NTFS_MIB * MIB


def make_partitioned_disk(path, scratch):
    """Raw GPT image: ESP (fat32), an ext4 data partition and a large Linux partition (no filesystem) to
    replace. Returns the (start, size) byte ranges that must stay unchanged: the ESP and the data."""
    for tool in ("sfdisk", "mkfs.fat", "mkfs.ext4"):
        if not shutil.which(tool):
            pytest.skip(f"NOT RUN: {tool} missing (dosfstools / e2fsprogs / util-linux)")
    with open(path, "wb") as fh:
        fh.truncate(DISK_BYTES)
    rest = DATA_START + DATA_MIB
    script = (f"label: gpt\nstart={ESP_START * 2048}, size={ESP_MIB * 2048}, "
              "type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n"
              f"start={DATA_START * 2048}, size={DATA_MIB * 2048}, type={LINUX_FS}\n"
              f"start={rest * 2048}, type={LINUX_FS}\n")
    subprocess.run(["sfdisk", "--quiet", path], input=script.encode(), check=True)  # noqa: S603,S607
    for name, start, mib, mk in (("esp", ESP_START, ESP_MIB, ["mkfs.fat", "-F", "32"]),
                                 ("data", DATA_START, DATA_MIB, ["mkfs.ext4", "-q", "-F", "-L", "DATA"])):
        part = os.path.join(scratch, name + ".img")
        with open(part, "wb") as fh:
            fh.truncate(mib * MIB)
        subprocess.run([*mk, part], check=True, capture_output=True)  # noqa: S603
        subprocess.run(["dd", f"if={part}", f"of={path}", "bs=1M", f"seek={start}", "conv=notrunc",  # noqa: S603,S607
                        "status=none"], check=True)
        os.remove(part)
    return [(ESP_START * MIB, ESP_MIB * MIB), (DATA_START * MIB, DATA_MIB * MIB)]


def sha256_range(path, start, size):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        fh.seek(start)
        left = size
        while left:
            chunk = fh.read(min(left, 4 << 20))
            if not chunk:
                break
            h.update(chunk)
            left -= len(chunk)
    return h.hexdigest()


class InstallRun:
    """One real install + installed boot. `log` is the evidence serial.log; `error` the failed assertion."""

    def __init__(self):
        self.sections, self.command, self.ntfs_sha, self.error = [], "", "", None
        self.scratch = None  # keep=True: caller owns and deletes this dir
        self.t_start = self.t_greeter = None  # time.monotonic(): first QEMU launch, installed greeter shown
        self.screenshot = None  # the installed-boot greeter screendump (kept under out/evidence)

    def add(self, phase, text):
        self.sections.append(f"[phase {phase}]\n{text.strip()}\n")

    @property
    def log(self):
        return "\n".join(self.sections)


@functools.cache
def run_install(mode, keyboard_extra=(), keep=False):
    """Run (once per mode, even when several gates read it) the install and boot; failures are recorded.

    keep=True: install only, then leave the scratch dir (run.scratch) with the installed target disk for
    the caller to boot and delete; no installed-boot phase here."""
    return fresh_install(mode, keyboard_extra, keep)


def fresh_install(mode, keyboard_extra=(), keep=False):
    """The uncached install: a caller that measures time must start its own run."""
    run = InstallRun()
    try:
        _install_and_boot(mode, run, keyboard_extra, keep)
    except AssertionError as exc:
        run.error = str(exc) or "assertion failed"
    except Exception as exc:  # noqa: BLE001 - a harness error must still leave the transcript and a reason
        run.error = f"{type(exc).__name__}: {exc}"
    return run


def install_and_boot(mode):
    run = run_install(mode)
    assert run.error is None, run.error
    return run


def _install_and_boot(mode, run, keyboard_extra=(), keep=False):
    iso = bootgate.find_iso()
    if not iso or not os.path.isfile(iso):
        pytest.skip("NOT RUN: no ISO (set SECLEGION_ISO)")
    answers = {"disk": devloop.TARGET_BY_ID, "mode": mode, "luks": False, "username": "tester",
               "password": PASSWORD, "hostname": "seclegion", "confirm": "QEMU HARDDISK",
               "timezone": "UTC"}
    if keyboard_extra:
        answers["keyboard_extra"] = list(keyboard_extra)
    if mode == "erase-luks":
        answers.update(luks=True, luks_passphrase=LUKS_PASSPHRASE)
    if mode == "partition":  # the third partition of make_partitioned_disk; placeholders filled in the guest
        answers.update(partition="XPARTX", confirm="XNAMEX")  # typable placeholders
    secrets = [PASSWORD] + ([LUKS_PASSPHRASE] if mode == "erase-luks" else [])
    root = devloop.MOUNT
    os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="i2-", dir=devloop.SCRATCH_ROOT)
    with open(os.path.join(REPO, "iso", "packages", "live.list")) as fh:
        live_list = fh.read()
    keep_scratch = False
    run.t_start = time.monotonic()
    extra = {"dev/answers.json": json.dumps(answers), "dev/live.list": live_list}
    try:
        target_image, ntfs, kept = None, None, []
        if mode == "partition":
            target_image = os.path.join(scratch, "target.img")
            kept = make_partitioned_disk(target_image, scratch)
            kept_before = [sha256_range(target_image, *r) for r in kept]
        if mode == "alongside":
            target_image = os.path.join(scratch, "target.img")
            ntfs = make_windows_like_disk(target_image, scratch)
            before = sha256_range(target_image, *ntfs)
            esp_before = sha256_range(target_image, ESP_START * MIB, ESP_MIB * MIB)
        with devloop.devloop_vm(iso, extra_files=extra, mem=4096, scratch=scratch,
                                target_image=target_image) as vm:
            run.command = evidence.repo_relative(vm.command, REPO)
            run.add("install-command", run.command)
            answers_path = f"{root}/dev/answers.json"
            if mode == "partition":  # the partition's kernel name is only known inside the guest
                answers_path = "/tmp/answers.json"  # the installer image is read-only
                out = devloop.run(
                    vm, f"p=$(readlink -f {devloop.TARGET_BY_ID}-part3); n=$(basename $p); "
                        f"sed -e 's|XPARTX|'$p'|' -e 's|XNAMEX|'$n'|' "
                        f"{root}/dev/answers.json > {answers_path}; "
                        f"test $(grep -c -e XPARTX -e XNAMEX {answers_path}) = 0 "
                        f"&& grep -q /dev/sd {answers_path}", "DL-PART", 60)
                run.add("partition", out)
                assert "DL-PART 0" in out, out[-600:]
            out = devloop.run(
                vm, f"SECLEGION_POST_SKIP_MISSING=1 python {root}/installd/seclegion-install "
                    f"--answers {answers_path} --dev --force-install-mode",
                "DL-INSTALL", 1800)
            if os.environ.get("SL_I2_LOG"):  # the whole install transcript, for debugging a failed run
                with open(os.environ["SL_I2_LOG"], "w") as fh:
                    fh.write(out)
            run.add("install", out)
            assert "SECLEGION-INSTALL-OK" in out and "DL-INSTALL 0" in out, out[-1500:]
            install_log = out
            out = devloop.run(vm, "find /mnt -name user_credentials.json | wc -l; "
                                  "arch-chroot /mnt pacman -Q seclegion-desktop; "
                                  "readlink /mnt/etc/systemd/system/sshd.service; "
                                  "ls -ln /mnt/home/tester/.config/hypr/hyprland.lua",  # no %: QMP types it
                              "DL-CHECK", 120)
            run.add("check", out)
            lines = out.splitlines()
            assert "0" in lines and "seclegion-desktop " in out and "/dev/null" in out, out[-600:]
            # the SecLegion Hyprland config reached the user (not Hyprland's autogenerated one), owned by them
            assert re.search(r"^-\S+ +\d+ +1000 +1000 .*/hypr/hyprland\.lua$", out, re.M), out[-600:]
            # the target-clean checker on the real installed tree, not only on fixtures
            out = devloop.run(vm, f"python {root}/installd/target_check.py --root /mnt "
                                  f"--live-list {root}/dev/live.list", "DL-TARGET", 120)
            run.add("target-check", out)
            assert "DL-TARGET 0" in out, out[-1500:]
            if mode == "alongside" and shutil.which("mcopy"):
                # the Windows entry on SecLegion's own ESP (/boot); the Windows ESP itself is hashed below
                out = devloop.run(vm, "cat /mnt/boot/loader/entries/windows.conf; "
                                      "ls /mnt/boot/EFI/seclegion", "DL-WINBOOT", 60)
                run.add("windows-entry", out)
                for want in ("title   Windows 11", "shellx64.efi", "windows.nsh"):
                    assert want in out, out[-600:]
            devloop.run(vm, "sync; umount -R /mnt", "DL-UMOUNT", 120)
            serial = vm.serial.text()
        for secret in secrets:
            assert secret not in serial and secret not in install_log
        if mode == "alongside":
            assert sha256_range(target_image, *ntfs) == before, "the Windows NTFS partition changed"
            assert sha256_range(target_image, ESP_START * MIB, ESP_MIB * MIB) == esp_before, \
                "the Windows ESP changed"
            run.ntfs_sha = before
            run.add("ntfs", f"NTFS-SHA256-UNCHANGED {before}")  # only after the comparison passed
        if mode == "partition":
            after = [sha256_range(target_image, *r) for r in kept]
            assert after == kept_before, "the ESP or the data partition changed"
            run.add("kept", f"PARTS-SHA256-UNCHANGED {kept_before[1]}")  # only after the comparison passed
        target = target_image or os.path.join(scratch, "target.qcow2")
        boot_dir = os.path.join(scratch, "boot")
        os.makedirs(boot_dir)
        shutil.copy(os.path.join(scratch, "vm", "OVMF_VARS.fd"), boot_dir)
        if keep:
            run.scratch, keep_scratch = scratch, True
            return
        evidence_dir = os.path.join(REPO, "out", "evidence")
        os.makedirs(evidence_dir, exist_ok=True)
        with QemuVM(iso, boot_dir, net="none", memory_mb=4096, disks=[(target, devloop.TARGET_SERIAL)],
                    boot="disk", reuse_vars=True) as vm2:
            if mode == "erase-luks":
                vm2.serial.wait_for(r"Enter passphrase for /dev/", 300)
                time.sleep(3)
                vm2.serial.send(LUKS_PASSPHRASE + "\n")  # the initramfs reads /dev/console = ttyS0
            vm2.serial.wait_for(r"Started .*(greetd|[Gg]reeter)", 300)  # unit Description, not its name
            time.sleep(20)
            vm2.screendump("installed.png")
            name = "i2-installed.png" if mode == "erase" else f"i3-{mode}-installed.png"
            run.screenshot = os.path.join(evidence_dir, name)
            shutil.copy(os.path.join(boot_dir, "installed.png"), run.screenshot)
            run.t_greeter = time.monotonic()
            text = vm2.serial.text()
        run.add("installed-boot", text)
        assert "Failed to start" not in text, text[-800:]
        assert "Arch Linux" not in text and "SecLegion OS" in text, text[-800:]  # /etc/os-release is ours
        for secret in secrets:
            assert secret not in text
    finally:
        if not keep_scratch:
            shutil.rmtree(scratch, ignore_errors=True)


@pytest.mark.iso
def test_i2_run():
    gate_m4("M4-erase", "erase")


def finish_gate(test_id, expected, body):
    """run_gate, then fail the test on a FAIL and skip on NOT RUN (never a silent pass)."""
    status, actual = bootgate.run_gate(test_id, expected, body)
    if status == "NOT RUN":
        pytest.skip(f"NOT RUN: {actual}")
    assert status == "PASS", actual


def gate_m4(test_id, mode, expected=None):
    """Evidence row for one install mode: the shared transcript + installed boot is the serial.log."""

    def body(result_dir, iso):
        run = run_install(mode)
        with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
            out.write(run.log)
        assert run.error is None, run.error
        return f"install {mode} OK, installed disk booted to the greeter", run.command, "n/a"

    finish_gate(test_id, expected or f"a real {mode} install succeeds, the target is clean and boots",
                body)
