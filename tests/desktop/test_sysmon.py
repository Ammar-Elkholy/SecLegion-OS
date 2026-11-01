# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-sysmon data layer on fake sysfs trees and a fake psutil (no GTK, no psutil needed).

The NVIDIA tests put a fake nvidia-smi on PATH that leaves a marker file when it runs, so "no process"
is checked by the absence of the marker, not by trusting the code path.
"""
import os
import signal
import sys
from collections import namedtuple
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop", "sysmon"))
from seclegion_sysmon import data, gpu, procs  # noqa: E402

SMI_OUT = "37, 1024, 8192, 51, 22.40"


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


@pytest.fixture
def tree(tmp_path):
    drm, psu, bin_ = tmp_path / "drm", tmp_path / "psu", tmp_path / "bin"
    bin_.mkdir()
    marker = tmp_path / "smi-ran"
    smi = bin_ / "nvidia-smi"
    smi.write_text(f"#!/bin/sh\necho \"$@\" >> '{marker}'\necho '{SMI_OUT}'\n")
    smi.chmod(0o755)
    env = {"SL_DRM_ROOT": str(drm), "SL_PSU_ROOT": str(psu), "PATH": str(bin_)}  # never the host nvidia-smi
    return SimpleNamespace(drm=drm, psu=psu, bin=bin_, marker=marker, env=env, smi=smi)


def nvidia(t, status, card="card0", slot="0000:01:00.0"):
    dev = t.drm / card / "device"
    put(dev / "vendor", "0x10de")
    put(dev / "power" / "runtime_status", status)
    put(dev / "uevent", f"DRIVER=nvidia\nPCI_SLOT_NAME={slot}")
    put(t.drm / f"{card}-HDMI-A-1" / "status", "connected")  # a connector entry: not a card


def supply(t, name, kind, **attrs):
    put(t.psu / name / "type", kind)
    for k, v in attrs.items():
        put(t.psu / name / k, str(v))


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_gpu_nvidia_suspended_no_process(tree):
    nvidia(tree, "suspended")
    supply(tree, "ADP0", "Mains", online=1)
    [g] = gpu.GpuReader(tree.env).read(query=True)
    assert (g.card, g.vendor, g.note) == ("card0", "NVIDIA", "dGPU sleeping")
    assert g.busy is None and g.temp is None
    assert not tree.marker.exists(), "nvidia-smi ran against a sleeping dGPU"


def test_gpu_nvidia_battery_no_query(tree):
    nvidia(tree, "active")
    supply(tree, "BAT0", "Battery", status="Discharging", capacity=70)
    supply(tree, "ADP0", "Mains", online=0)
    [g] = gpu.GpuReader(tree.env).read(query=True)
    assert g.note == "dGPU on" and g.busy is None
    assert not tree.marker.exists(), "nvidia-smi ran on battery"


def test_gpu_nvidia_active_on_ac_queries_its_slot_at_most_every_2s(tree):
    nvidia(tree, "active")
    supply(tree, "BAT0", "Battery", status="Charging", capacity=70)
    clock = Clock()
    r = gpu.GpuReader(tree.env, clock=clock)
    [g] = r.read(query=True)
    assert (g.busy, g.temp, g.power_w) == (37, 51.0, 22.4)
    assert (g.vram_used, g.vram_total) == (1024 * 2**20, 8192 * 2**20)
    calls = tree.marker.read_text().splitlines()
    assert calls == ["-i 0000:01:00.0 --query-gpu=" + gpu.QUERY + " --format=csv,noheader,nounits"]
    clock.t += 1.0
    assert r.read(query=True)[0].busy == 37  # cached
    assert len(tree.marker.read_text().splitlines()) == 1
    clock.t += 1.5
    r.read(query=True)
    assert len(tree.marker.read_text().splitlines()) == 2
    r.read(query=False)  # GPU page hidden
    assert len(tree.marker.read_text().splitlines()) == 2


def test_gpu_nvidia_without_nvidia_smi_shows_the_card(tree):
    nvidia(tree, "active")
    tree.smi.unlink()
    [g] = gpu.GpuReader(tree.env).read(query=True)
    assert g.vendor == "NVIDIA" and g.busy is None and g.note == "nvidia-smi not installed"


def test_gpu_amd(tree):
    dev = tree.drm / "card1" / "device"
    put(dev / "vendor", "0x1002")
    put(dev / "power" / "runtime_status", "unsupported")
    put(dev / "gpu_busy_percent", "42")
    put(dev / "mem_info_vram_used", str(512 * 2**20))
    put(dev / "mem_info_vram_total", str(2 * 2**30))
    put(dev / "hwmon" / "hwmon5" / "temp1_input", "48000")
    put(dev / "hwmon" / "hwmon5" / "power1_input", "9500000")
    put(tree.drm / "card1-eDP-1" / "status", "connected")
    put(tree.drm / "card2" / "device" / "vendor", "0x8086")
    gs = gpu.GpuReader(tree.env).read(query=True)
    assert [(g.card, g.vendor) for g in gs] == [("card1", "AMD"), ("card2", "Intel")]
    a = gs[0]
    assert (a.busy, a.vram_used, a.vram_total, a.temp, a.power_w) == (42, 512 * 2**20, 2 * 2**30, 48.0, 9.5)
    put(dev / "power" / "runtime_status", "suspended")
    a = gpu.GpuReader(tree.env).read()[0]
    assert a.note == "dGPU sleeping" and a.busy is None


NIC = namedtuple("NIC", "bytes_sent bytes_recv")
IFS = namedtuple("IFS", "isup")
CT = namedtuple("CT", "user nice system idle iowait irq softirq steal guest guest_nice")


class FakePs:
    def __init__(self):
        self.nics = {"lo": NIC(0, 0), "wlan0": NIC(0, 0), "docker0": NIC(0, 0)}
        self.cpu = CT(10, 0, 10, 80, 0, 0, 0, 0, 0, 0)

    def net_io_counters(self, pernic=False):
        return dict(self.nics)

    def net_if_stats(self):
        return {"lo": IFS(True), "wlan0": IFS(True), "docker0": IFS(False)}

    def cpu_times(self, percpu=False):
        return [self.cpu, self.cpu] if percpu else self.cpu

    def getloadavg(self):
        return (0.5, 0.4, 0.3)

    def cpu_freq(self):
        return SimpleNamespace(current=2400.0, max=4800.0)

    def virtual_memory(self):
        return SimpleNamespace(total=16 * 2**30, available=12 * 2**30, percent=25.0)

    def swap_memory(self):
        return SimpleNamespace(total=8 * 2**30, used=0)

    def disk_partitions(self, all=False):
        return []

    def disk_io_counters(self, perdisk=False):
        return {}


def test_net_bits(tmp_path):
    ps, clock = FakePs(), Clock()
    s = data.Sampler(ps=ps, env={"SL_SYS_ROOT": str(tmp_path)}, clock=clock)
    first = s.sample()
    assert [(n.name, n.down_bps, n.up_bps) for n in first.nets] == [("wlan0", 0.0, 0.0)]  # lo, down if
    ps.nics["wlan0"] = NIC(bytes_sent=250, bytes_recv=1_250_000)
    ps.cpu = CT(20, 0, 20, 140, 0, 0, 0, 0, 0, 0)
    clock.t += 2.0
    snap = s.sample()
    [n] = snap.nets
    assert n.down_bps == 5_000_000 and n.up_bps == 1000  # bytes * 8 / 2 s
    assert (data.fmt_bits(n.down_bps), data.fmt_bits(n.up_bps)) == ("5.0 Mb/s", "1.0 Kb/s")
    assert [data.fmt_bits(v) for v in (0, 999, 12_500, 940e6, 1.25e9)] == \
        ["0 b/s", "999 b/s", "12.5 Kb/s", "940 Mb/s", "1.2 Gb/s"]
    assert snap.cpu.total == pytest.approx(25.0)  # 20 busy of 80 s
    assert snap.mem.used == 4 * 2**30


def test_power_and_temps(tmp_path):
    t = SimpleNamespace(psu=tmp_path / "power_supply")
    supply(t, "BAT0", "Battery", status="Discharging", capacity=64)
    supply(t, "hidpp_battery_0", "Battery", status="Discharging", capacity=10, scope="Device")
    supply(t, "ADP0", "Mains", online=0)
    p = data.read_power(t.psu)
    assert [(b.name, b.capacity, b.status) for b in p.batteries] == [("BAT0", 64, "Discharging")]
    assert p.ac_online is False and p.on_battery
    hw = tmp_path / "hwmon"
    put(hw / "hwmon0" / "name", "k10temp")
    put(hw / "hwmon0" / "temp1_input", "61250")
    put(hw / "hwmon0" / "temp1_label", "Tctl")
    put(hw / "hwmon1" / "name", "amdgpu")
    put(hw / "hwmon1" / "temp1_input", "50000")
    put(hw / "hwmon1" / "device" / "power" / "runtime_status", "suspended")
    assert [(x.label, x.celsius) for x in data.read_temps(hw)] == [("k10temp Tctl", 61.25)]


class FakeProc:
    def __init__(self, table, pid):
        if pid not in table:
            raise FakePsProcs.NoSuchProcess(pid)
        self.pid, self.table = pid, table

    def uids(self):
        return self.table[self.pid]

    def send_signal(self, sig):
        FakePsProcs.sent.append((self.pid, sig))


UIDS = namedtuple("UIDS", "real effective saved")


class FakePsProcs:
    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    sent: list = []
    table = {100: UIDS(1000, 1000, 1000), 1: UIDS(0, 0, 0), 200: UIDS(1000, 0, 0)}

    def Process(self, pid):  # noqa: N802 (psutil's name)
        return FakeProc(self.table, pid)


def test_proc_kill_own_only():
    ps = FakePsProcs()
    FakePsProcs.sent = []
    procs.send(100, signal.SIGTERM, ps=ps, uid=1000)
    procs.send(100, signal.SIGKILL, ps=ps, uid=1000)
    assert FakePsProcs.sent == [(100, signal.SIGTERM), (100, signal.SIGKILL)]
    for pid in (1, 200):  # another user's; a setuid program
        with pytest.raises(procs.Refused):
            procs.send(pid, signal.SIGKILL, ps=ps, uid=1000)
    with pytest.raises(procs.Refused, match="already exited"):
        procs.send(999, signal.SIGTERM, ps=ps, uid=1000)
    with pytest.raises(procs.Refused):
        procs.send(100, signal.SIGHUP, ps=ps, uid=1000)
    assert FakePsProcs.sent == [(100, signal.SIGTERM), (100, signal.SIGKILL)]
    assert procs.is_own(UIDS(1000, 1000, 1000), 1000) and not procs.is_own(UIDS(0, 0, 0), 1000)


def test_history_keeps_60_samples():
    h = data.History()
    for i in range(100):
        h.push(i)
    assert len(h.values) == 60 and h.values[0] == 40 and h.peak() == 99
