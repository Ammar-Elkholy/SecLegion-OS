# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-barcheck: one PASS and one FAIL path per bar row, SKIP without root, exit codes, no writes."""

import io
import json

import pytest
from conftest import PKG  # noqa: F401  (puts the package on sys.path)
from seclegion_barcheck import barcheck as bc

ENGINE = bc.ENGINE
WPCTL = """PipeWire 'pipewire-0'
Audio
 ├─ Devices:
 │      50. Built-in Audio
 ├─ Sinks:
 │  *   51. Speaker [vol: 0.4]
 ├─ Sources:
 │  *   52. Mic [vol: 1.0]
 └─ Streams:
Video
 ├─ Devices:
"""
BOOTCTL = "Boot loader: systemd-boot\nCurrent Entry:\n  type: Boot Loader Specification Type #2 (.efi)\n"
LSBLK_LUKS = {"blockdevices": [{"fstype": "crypto_LUKS", "children": [{"fstype": "btrfs"}]}]}
LSBLK_PLAIN = {"blockdevices": [{"fstype": "btrfs"}]}
VULKAN = "GPU0:\n deviceName = AMD 780M\nGPU1:\n deviceName = RTX 4060\n"
NMCLI = ("nmcli", "-t", "-f", "TYPE,STATE", "dev")
NVSUSPEND = ("systemctl", "is-enabled", "nvidia-suspend.service")
LSBLK = ("lsblk", "-J", "-f")


def good_runner(overrides=None):
    table = {
        ("bootctl", "status"): (0, BOOTCTL),
        ("nvidia-smi", "-L"): (0, "GPU 0: RTX 4060"),
        ("vulkaninfo", "--summary"): (0, VULKAN),
        NMCLI: (0, "wifi:connected\nethernet:unavailable"),
        ("wpctl", "status"): (0, WPCTL),
        NVSUSPEND: (0, "enabled"),
        ("powerprofilesctl", "get"): (0, "balanced"),
        LSBLK: (0, json.dumps(LSBLK_LUKS)),
        ("snapper", "--version"): (0, "snapper 0.11"),
        ("firefox", "--version"): (0, "Mozilla Firefox 130"),
        ("git", "--version"): (0, "git version 2.45"),
        ("ssh", "-V"): (0, "OpenSSH_9"),
        ("gpg", "--version"): (0, "gpg 2.4"),
        ("id", "-nG"): (0, f"wheel {ENGINE}"),
        ("systemctl", "is-enabled", f"{ENGINE}.service"): (0, "enabled"),
        (ENGINE, "info"): (0, "Server: ok"),
        ("claude", "--version"): (0, "2.1.302"),
        ("make", "--version"): (0, "GNU Make"),
        ("python3", "--version"): (0, "Python 3.12"),
        ("gcc", "--version"): (0, "gcc"),
        ("patch", "--version"): (0, "patch"),
        ("fakeroot", "--version"): (0, "fakeroot"),
        ("pkgconf", "--version"): (0, "2"),
        ("socat", "-V"): (0, "socat 1.8"),
        ("pacman", "-Q", "seclegion-virt"): (0, "seclegion-virt 1"),
        ("qemu-system-x86_64", "--version"): (0, "QEMU 9"),
    }
    table.update(overrides or {})
    calls = []

    def run(argv, timeout=8):
        calls.append(tuple(argv))
        hit = table.get(tuple(argv))
        return None if hit is None else bc.Result(*hit)

    run.calls = calls
    return run


@pytest.fixture
def tree(tmp_path):
    def w(rel, text):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    for addr, vendor, rt in (("0000:00:01.0", "0x1002", "active"), ("0000:01:00.0", "0x10de", "suspended")):
        w(f"sys/bus/pci/devices/{addr}/class", "0x030000\n")
        w(f"sys/bus/pci/devices/{addr}/vendor", vendor + "\n")
        w(f"sys/bus/pci/devices/{addr}/power/runtime_status", rt + "\n")
    (tmp_path / "sys/firmware/efi").mkdir(parents=True)
    (tmp_path / "sys/class/bluetooth/hci0").mkdir(parents=True)
    w("dev/video0", "")
    w("sys/power/mem_sleep", "[s2idle]\n")
    w("proc/driver/nvidia/params", "PreserveVideoMemoryAllocations: 1\n")
    w("proc/cmdline", "root=/dev/sda2 quiet\n")
    w("etc/pacman.conf", "[core]\nInclude = /etc/pacman.d/mirrorlist\n")
    return tmp_path


def make_live(tree):
    (tree / "run/archiso").mkdir(parents=True)


def lines(tree, run=None, euid=1000):
    return bc.run_all(bc.Ctx(tree, run or good_runner(), euid))


def status(out, row, check):
    got = [ln.status for ln in out if ln.row == row and ln.check == check]
    assert len(got) == 1, (row, check, got)
    return got[0]


def statuses(out, row, checks):
    return [status(out, row, c) for c in checks]


def test_all_good_has_no_fail_and_every_row(tree):
    out = lines(tree)
    assert not [ln for ln in out if ln.status == "FAIL"], out
    assert {f"B{i}" for i in range(1, 14)} <= {ln.row for ln in out}


def test_b1(tree):
    assert status(lines(tree), "B1", "bootloader") == "PASS"
    out = lines(tree, good_runner({("bootctl", "status"): (0, "Boot loader: GRUB")}))
    assert status(out, "B1", "bootloader") == "FAIL"
    out = lines(tree, good_runner({("bootctl", "status"): (1, "Failed to read")}))
    assert status(out, "B1", "bootloader") == "SKIP"  # as a user: needs root
    out = lines(tree, good_runner({("bootctl", "status"): (1, "")}), euid=0)
    assert status(out, "B1", "bootloader") == "FAIL"
    make_live(tree)
    assert status(lines(tree), "B1", "bootloader") == "PASS"  # live mode


def test_b2(tree):
    out = lines(tree)
    assert statuses(out, "B2", ("gpus", "nvidia-smi", "dgpu-runtime", "vulkaninfo")) == ["PASS"] * 4
    (tree / "sys/bus/pci/devices/0000:01:00.0/power/runtime_status").write_text("active\n")
    out = lines(tree, good_runner({("vulkaninfo", "--summary"): (0, "GPU0:\n deviceName = AMD\n"),
                                   ("nvidia-smi", "-L"): (9, "failed")}))
    assert statuses(out, "B2", ("dgpu-runtime", "vulkaninfo", "nvidia-smi")) == ["FAIL"] * 3


def test_b2_dgpu_state_read_before_nvidia_smi_wakes_it(tree):
    rt = tree / "sys/bus/pci/devices/0000:01:00.0/power/runtime_status"
    base = good_runner()

    def waking(argv, timeout=8):
        if argv[0] in ("nvidia-smi", "vulkaninfo"):
            rt.write_text("active\n")  # a client wakes the dGPU
        return base(argv, timeout)

    assert status(lines(tree, waking), "B2", "dgpu-runtime") == "PASS"


def test_b2_discrete_mode_skips_dgpu_runtime(tree):
    (tree / "sys/bus/pci/devices/0000:01:00.0/boot_vga").write_text("1\n")
    (tree / "sys/bus/pci/devices/0000:01:00.0/power/runtime_status").write_text("active\n")
    assert status(lines(tree), "B2", "dgpu-runtime") == "SKIP"


def test_b2_single_gpu_fails_and_no_vulkan_skips(tree):
    (tree / "sys/bus/pci/devices/0000:01:00.0/vendor").write_text("0x8086\n")
    out = lines(tree, good_runner({("vulkaninfo", "--summary"): None}))
    assert statuses(out, "B2", ("gpus", "nvidia-smi", "vulkaninfo")) == ["FAIL", "SKIP", "SKIP"]


def test_b3(tree):
    out = lines(tree)
    assert statuses(out, "B3", ("wifi", "bluetooth")) == ["PASS", "PASS"]
    (tree / "sys/class/bluetooth/hci0").rmdir()
    out = lines(tree, good_runner({NMCLI: (0, "ethernet:up")}))
    assert statuses(out, "B3", ("wifi", "bluetooth")) == ["FAIL", "FAIL"]


def test_b4(tree):
    assert statuses(lines(tree), "B4", ("wpctl", "webcam")) == ["PASS", "PASS"]
    (tree / "dev/video0").unlink()
    out = lines(tree, good_runner({("wpctl", "status"): (0, "Audio\n ├─ Sinks:\n")}))
    assert statuses(out, "B4", ("wpctl", "webcam")) == ["FAIL", "FAIL"]


B5 = ("mem_sleep", "nvidia-suspend", "preserve-vram", "powerprofilesctl")


def test_b5(tree):
    assert statuses(lines(tree), "B5", B5) == ["PASS"] * 4
    (tree / "sys/power/mem_sleep").write_text("deep\n")
    (tree / "proc/driver/nvidia/params").write_text("PreserveVideoMemoryAllocations: 0\n")
    out = lines(tree, good_runner({NVSUSPEND: (1, "disabled"), ("powerprofilesctl", "get"): None}))
    assert statuses(out, "B5", B5) == ["FAIL"] * 4


def test_b5_params_unreadable_as_user_is_skip(tree, monkeypatch):
    real = bc.Ctx.read

    def read(self, rel):
        return "perm" if rel.endswith("nvidia/params") else real(self, rel)

    monkeypatch.setattr(bc.Ctx, "read", read)
    assert status(lines(tree), "B5", "preserve-vram") == "SKIP"


def test_b6(tree):
    assert status(lines(tree), "B6", "luks") == "PASS"
    plain = good_runner({LSBLK: (0, json.dumps(LSBLK_PLAIN))})
    assert status(lines(tree, plain), "B6", "luks") == "FAIL"
    make_live(tree)
    assert status(lines(tree, plain), "B6", "luks") == "SKIP"


def test_b7(tree):
    assert status(lines(tree), "B7", "snapper") == "PASS"
    assert status(lines(tree, good_runner({("snapper", "--version"): None})), "B7", "snapper") == "SKIP"
    out = lines(tree, good_runner({("snapper", "--version"): (2, "broken")}))
    assert status(out, "B7", "snapper") == "FAIL"


def test_b8(tree):
    assert status(lines(tree), "B8", "pacman-conf") == "PASS"
    (tree / "etc/pacman.conf").write_text("[seclegion]\nServer = file:///var/lib/seclegion/repo\n")
    out = lines(tree)
    assert status(out, "B8", "pacman-conf") == "FAIL"
    assert "known gap B8" in [ln.detail for ln in out if ln.check == "pacman-conf"][0]
    make_live(tree)
    assert status(lines(tree), "B8", "pacman-conf") == "SKIP"


ROWS = (("B9", "firefox"), ("B10", "git"), ("B10", "ssh"), ("B10", "gpg"), ("B12", "claude"))


def test_b9_b10_b12(tree):
    out = lines(tree)
    assert [status(out, r, c) for r, c in ROWS] == ["PASS"] * 5
    gone = {("firefox", "--version"): None, ("git", "--version"): None, ("ssh", "-V"): None,
            ("gpg", "--version"): (2, "x"), ("claude", "--version"): None}
    out = lines(tree, good_runner(gone))
    assert [status(out, r, c) for r, c in ROWS] == ["FAIL"] * 5


def test_b11(tree):
    assert statuses(lines(tree), "B11", ("group", "service", "daemon")) == ["PASS"] * 3
    out = lines(tree, good_runner({("id", "-nG"): (0, "wheel"), (ENGINE, "info"): (1, "permission denied"),
                                   ("systemctl", "is-enabled", f"{ENGINE}.service"): (1, "disabled")}))
    assert statuses(out, "B11", ("group", "service", "daemon")) == ["FAIL"] * 3
    make_live(tree)
    assert statuses(lines(tree), "B11", ("group", "service")) == ["SKIP", "SKIP"]


B13 = ("make", "python", "base-devel", "socat", "qemu")


def test_b13(tree):
    assert statuses(lines(tree), "B13", B13) == ["PASS"] * 5
    out = lines(tree, good_runner({("make", "--version"): None, ("socat", "-V"): None,
                                   ("fakeroot", "--version"): None,
                                   ("qemu-system-x86_64", "--version"): None}))
    assert statuses(out, "B13", ("make", "base-devel", "socat", "qemu")) == ["FAIL"] * 4
    out = lines(tree, good_runner({("pacman", "-Q", "seclegion-virt"): (1, "not found")}))
    assert status(out, "B13", "qemu") == "SKIP"


def test_manual_rows_say_how(tree):
    manual = [ln for ln in lines(tree) if ln.detail.startswith("manual: ")]
    assert {ln.row for ln in manual} >= {"B2", "B3", "B4", "B5", "B6", "B11"}
    assert all(ln.status == "SKIP" for ln in manual)


def run_main(tree, argv, run=None, euid=1000):
    buf = io.StringIO()
    rc = bc.main(argv, run=run or good_runner(), root=str(tree), euid=euid, stdout=buf)
    return rc, buf.getvalue()


def test_exit_codes_and_format(tree):
    rc, text = run_main(tree, [])
    assert rc == 0
    rows = text.splitlines()
    assert all(r.split(" ", 1)[0] in ("PASS", "FAIL", "SKIP", "SUMMARY:") for r in rows)
    assert " — " in rows[0] and rows[-1].startswith("SUMMARY: ") and " 0 FAIL" in rows[-1]
    rc, text = run_main(tree, [], good_runner({("git", "--version"): None}))
    assert rc == 1 and "FAIL B10 git" in text


def test_no_writes_without_o_and_force_rules(tree, tmp_path_factory):
    before = sorted(tree.rglob("*"))
    run_main(tree, [])
    assert sorted(tree.rglob("*")) == before
    out = tmp_path_factory.mktemp("out") / "report.txt"
    rc, text = run_main(tree, ["-o", str(out)])
    assert rc == 0 and out.read_text() == text
    out.write_text("keep")
    run = good_runner()
    rc, text = run_main(tree, ["-o", str(out)], run)
    assert rc == 2 and out.read_text() == "keep" and text == "" and run.calls == []
    rc, _ = run_main(tree, ["-o", str(out), "--force"])
    assert rc == 0 and out.read_text() != "keep"


def test_only_read_only_commands_run(tree):
    run = good_runner()
    lines(tree, run)
    banned = {"suspend", "connect", "pair", "set", "hello-world", "run", "enable", "start"}
    assert not [c for c in run.calls if banned & set(c)]
