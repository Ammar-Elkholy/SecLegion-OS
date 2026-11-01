# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The system data behind the Overview page. No GTK.

Counters come from python-psutil (CPU, memory, disks, network); temperatures and power supplies are
read from sysfs. `Sampler.sample()` turns two readings into rates, so the first sample's rates are 0.
psutil is imported on first use and can be replaced (`ps=`), so tests run without it.

Roots (tests only): SL_SYS_ROOT (default /sys) is the base of class/hwmon and class/power_supply;
SL_PSU_ROOT overrides the power-supply directory, SL_HWMON_ROOT the hwmon one, SL_DRM_ROOT the DRM one.
"""
from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

HISTORY = 60  # samples kept for the graphs (one per refresh)


# -- roots and small readers -------------------------------------------------------------------
def sys_root(env) -> Path:
    return Path(env.get("SL_SYS_ROOT") or "/sys")


def psu_root(env) -> Path:
    return Path(env.get("SL_PSU_ROOT") or sys_root(env) / "class" / "power_supply")


def hwmon_root(env) -> Path:
    return Path(env.get("SL_HWMON_ROOT") or sys_root(env) / "class" / "hwmon")


def drm_root(env) -> Path:
    return Path(env.get("SL_DRM_ROOT") or sys_root(env) / "class" / "drm")


def read(path: Path) -> str | None:
    """The first line of a sysfs file, stripped; None when it is missing or unreadable."""
    try:
        with open(path) as f:
            return f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return None


def read_int(path: Path) -> int | None:
    v = read(path)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def psutil_module(ps=None):
    if ps is not None:
        return ps
    import psutil
    return psutil


# -- formatting ----------------------------------------------------------------------------------
def fmt_bits(bits_per_s: float) -> str:
    """A network rate in bits per second, decimal prefixes: 840 b/s, 12.5 Kb/s, 940 Mb/s, 1.2 Gb/s."""
    v = max(float(bits_per_s), 0.0)
    if v < 1000:
        return f"{v:.0f} b/s"
    for unit in ("Kb/s", "Mb/s", "Gb/s", "Tb/s"):
        v /= 1000
        if v < 1000 or unit == "Tb/s":
            return f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"
    raise AssertionError("unreachable")


def fmt_bytes(n: float) -> str:
    """A size in binary units: 512 B, 3.4 MiB, 15.2 GiB."""
    v = max(float(n), 0.0)
    if v < 1024:
        return f"{v:.0f} B"
    for unit in ("KiB", "MiB", "GiB", "TiB", "PiB"):
        v /= 1024
        if v < 1024 or unit == "PiB":
            return f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"
    raise AssertionError("unreachable")


def fmt_byte_rate(n: float) -> str:
    return fmt_bytes(n) + "/s"


# -- the samples ---------------------------------------------------------------------------------
@dataclass
class Cpu:
    total: float = 0.0                       # percent busy, all cores
    per_core: list[float] = field(default_factory=list)
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)
    freq_mhz: float | None = None
    freq_max_mhz: float | None = None


@dataclass
class Mem:
    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0


@dataclass
class Disk:
    device: str                              # kernel name (nvme0n1p2, dm-0)
    mounts: list[str]
    fstype: str
    total: int | None
    used: int | None
    percent: float | None
    read_bps: float = 0.0                    # bytes per second
    write_bps: float = 0.0


@dataclass
class Net:
    name: str
    down_bps: float                          # bits per second
    up_bps: float


@dataclass
class Temp:
    label: str
    celsius: float


@dataclass
class Battery:
    name: str
    capacity: int | None
    status: str


@dataclass
class Power:
    batteries: list[Battery] = field(default_factory=list)
    ac_online: bool | None = None            # None: no mains/USB supply reported
    on_battery: bool = False


@dataclass
class Snapshot:
    cpu: Cpu
    mem: Mem
    disks: list[Disk]
    nets: list[Net]
    temps: list[Temp]
    power: Power


def cpu_busy_idle(t) -> tuple[float, float]:
    """(total, idle) seconds from one psutil cpu_times tuple. guest time is already in user/nice."""
    total = sum(t) - getattr(t, "guest", 0.0) - getattr(t, "guest_nice", 0.0)
    return total, t.idle + getattr(t, "iowait", 0.0)


def busy_percent(before, after) -> float:
    t0, i0 = cpu_busy_idle(before)
    t1, i1 = cpu_busy_idle(after)
    dt = t1 - t0
    if dt <= 0:
        return 0.0
    return max(0.0, min(100.0, (dt - (i1 - i0)) / dt * 100.0))


def _rate(now: int, before: int | None, dt: float) -> float:
    if before is None or dt <= 0 or now < before:  # first sample, or the counter was reset
        return 0.0
    return (now - before) / dt


def on_battery(psu: Path) -> bool:
    """Any supply discharging: the rule desktop/waybar/seclegion-gpu uses."""
    try:
        supplies = sorted(psu.iterdir())
    except OSError:
        return False
    return any(read(s / "status") == "Discharging" for s in supplies)


def read_power(psu: Path) -> Power:
    p = Power(on_battery=on_battery(psu))
    try:
        supplies = sorted(psu.iterdir())
    except OSError:
        return p
    for s in supplies:
        kind = read(s / "type")
        if kind == "Battery":
            if read(s / "scope") == "Device":  # a mouse or headset, not the laptop's battery
                continue
            p.batteries.append(Battery(s.name, read_int(s / "capacity"), read(s / "status") or "Unknown"))
        elif kind in ("Mains", "USB", "USB_C", "USB_PD"):
            online = read_int(s / "online")
            if online is not None:
                p.ac_online = bool(online) or bool(p.ac_online)
    return p


def read_temps(hwmon: Path) -> list[Temp]:
    """Every temp*_input under the hwmon class. A sensor whose device is runtime-suspended is skipped:
    reading it could wake a sleeping dGPU."""
    out: list[Temp] = []
    try:
        mons = sorted(hwmon.iterdir(), key=lambda p: (len(p.name), p.name))
    except OSError:
        return out
    for mon in mons:
        if read(mon / "device" / "power" / "runtime_status") == "suspended":
            continue
        name = read(mon / "name") or mon.name
        try:
            inputs = sorted(mon.glob("temp*_input"), key=lambda p: (len(p.name), p.name))
        except OSError:
            continue
        for inp in inputs:
            milli = read_int(inp)
            if milli is None:
                continue
            label = read(inp.with_name(inp.name.replace("_input", "_label"))) or inp.name.split("_")[0]
            out.append(Temp(f"{name} {label}", milli / 1000.0))
    return out


class Sampler:
    """Holds the previous counters so that each `sample()` reports rates since the last one."""

    def __init__(self, ps=None, env=None, clock=time.monotonic):
        self._ps = ps
        self.env = os.environ if env is None else env
        self.clock = clock
        self._t: float | None = None
        self._cpu = None
        self._cores = None
        self._net: dict[str, tuple[int, int]] = {}
        self._disk: dict[str, tuple[int, int]] = {}

    @property
    def ps(self):
        self._ps = psutil_module(self._ps)
        return self._ps

    def sample(self) -> Snapshot:
        now = self.clock()
        dt = 0.0 if self._t is None else now - self._t
        self._t = now
        return Snapshot(self._sample_cpu(), self._sample_mem(), self._sample_disks(dt),
                        self._sample_nets(dt), read_temps(hwmon_root(self.env)),
                        read_power(psu_root(self.env)))

    def _sample_cpu(self) -> Cpu:
        ps = self.ps
        total, cores = ps.cpu_times(), ps.cpu_times(percpu=True)
        c = Cpu()
        if self._cpu is not None:
            c.total = busy_percent(self._cpu, total)
            c.per_core = [busy_percent(a, b) for a, b in zip(self._cores, cores, strict=False)]
        else:
            c.per_core = [0.0] * len(cores)
        self._cpu, self._cores = total, cores
        try:
            c.load = tuple(ps.getloadavg())
        except (AttributeError, OSError):
            c.load = os.getloadavg()
        try:
            f = ps.cpu_freq()
        except (AttributeError, OSError, NotImplementedError):
            f = None
        if f is not None:
            c.freq_mhz = f.current or None
            c.freq_max_mhz = f.max or None
        return c

    def _sample_mem(self) -> Mem:
        vm, sw = self.ps.virtual_memory(), self.ps.swap_memory()
        return Mem(vm.total, vm.total - vm.available, vm.available, vm.percent, sw.total, sw.used)

    def _sample_nets(self, dt: float) -> list[Net]:
        ps = self.ps
        counters = ps.net_io_counters(pernic=True) or {}
        try:
            stats = ps.net_if_stats()
        except OSError:
            stats = {}
        out, seen = [], {}
        for name in sorted(counters):
            c = counters[name]
            seen[name] = (c.bytes_recv, c.bytes_sent)
            if name == "lo" or (name in stats and not stats[name].isup):
                continue
            rx0, tx0 = self._net.get(name, (None, None))
            out.append(Net(name, _rate(c.bytes_recv, rx0, dt) * 8, _rate(c.bytes_sent, tx0, dt) * 8))
        self._net = seen
        return out

    def _sample_disks(self, dt: float) -> list[Disk]:
        ps = self.ps
        try:
            io = ps.disk_io_counters(perdisk=True) or {}
        except (OSError, RuntimeError):
            io = {}
        by_dev: dict[str, Disk] = {}
        for part in ps.disk_partitions(all=False):
            if not part.device.startswith("/dev/"):
                continue
            dev = os.path.basename(os.path.realpath(part.device))  # /dev/mapper/root -> dm-0
            if dev in by_dev:
                by_dev[dev].mounts.append(part.mountpoint)
                continue
            try:
                u = ps.disk_usage(part.mountpoint)
                total, used, pct = u.total, u.used, u.percent
            except OSError:
                total = used = pct = None
            by_dev[dev] = Disk(dev, [part.mountpoint], part.fstype, total, used, pct)
        seen = {}
        for dev, d in by_dev.items():
            c = io.get(dev)
            if c is None:
                continue
            seen[dev] = (c.read_bytes, c.write_bytes)
            r0, w0 = self._disk.get(dev, (None, None))
            d.read_bps, d.write_bps = _rate(c.read_bytes, r0, dt), _rate(c.write_bytes, w0, dt)
        self._disk = seen
        return list(by_dev.values())


class History:
    """The last HISTORY values of one series, oldest first."""

    def __init__(self, size: int = HISTORY):
        self.values: deque[float] = deque(maxlen=size)

    def push(self, v: float) -> None:
        self.values.append(float(v))

    def peak(self) -> float:
        return max(self.values, default=0.0)
