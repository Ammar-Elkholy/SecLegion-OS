# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Every DRM card (SL_DRM_ROOT/card<N>), with the rules of desktop/waybar/seclegion-gpu. No GTK.

  AMD (0x1002)     gpu_busy_percent, mem_info_vram_*, hwmon temp1_input from sysfs; nothing is read
                   while the card is runtime-suspended.
  NVIDIA (0x10de)  runtime_status "suspended": "dGPU sleeping" and no child process (a query wakes it).
                   Awake on battery: "dGPU on", no query (a poll keeps it from runtime-suspending).
                   Awake on AC: one nvidia-smi query for its PCI slot, at most every MIN_QUERY_S.
                   No nvidia-smi on PATH: the card without stats.
  Others           the card without stats.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .data import drm_root, on_battery, psu_root, read, read_int

MIN_QUERY_S = 2.0
VENDORS = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}
# "unsupported": runtime PM is off for the device, so it never sleeps and a query cannot wake it.
AWAKE = ("active", "unsupported")
QUERY = "utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


@dataclass
class Gpu:
    card: str
    vendor: str
    slot: str = ""
    busy: int | None = None             # percent
    vram_used: int | None = None        # bytes
    vram_total: int | None = None
    temp: float | None = None           # degrees C
    power_w: float | None = None
    note: str = ""


def _slot(dev: Path) -> str:
    try:
        for line in (dev / "uevent").read_text().splitlines():
            k, _, v = line.partition("=")
            if k == "PCI_SLOT_NAME":
                return v.strip()
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def _num(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:  # "[N/A]", "[Not Supported]"
        return None


def parse_smi(line: str) -> dict:
    f = [x.strip() for x in line.strip().split(",")]
    if len(f) != 5:
        return {}
    busy, used, total, temp, power = (_num(x) for x in f)
    mib = 1024 * 1024
    return {"busy": None if busy is None else int(busy),
            "vram_used": None if used is None else int(used * mib),
            "vram_total": None if total is None else int(total * mib),
            "temp": temp, "power_w": power}


class GpuReader:
    """`read(query=True)` only while the GPU page is visible; `query=False` never starts a process."""

    def __init__(self, env=None, run=subprocess.run, clock=time.monotonic):
        import os
        self.env = os.environ if env is None else env
        self.run = run
        self.clock = clock
        self._cache: dict[str, tuple[float, dict]] = {}  # slot -> (time, parsed query)

    def cards(self) -> list[Path]:
        try:
            names = [p for p in drm_root(self.env).iterdir() if p.name[4:].isdigit() and p.name[:4] == "card"]
        except OSError:
            return []
        return sorted(names, key=lambda p: int(p.name[4:]))

    def read(self, query: bool = True) -> list[Gpu]:
        out = []
        for card in self.cards():
            dev = card / "device"
            vid = read(dev / "vendor") or ""
            g = Gpu(card.name, VENDORS.get(vid, f"vendor {vid or 'unknown'}"), _slot(dev))
            if vid == "0x1002":
                self._amd(g, dev)
            elif vid == "0x10de":
                self._nvidia(g, dev, query)
            else:
                g.note = "no statistics for this vendor"
            out.append(g)
        return out

    def _amd(self, g: Gpu, dev: Path) -> None:
        if read(dev / "power" / "runtime_status") == "suspended":
            g.note = "dGPU sleeping"
            return
        g.busy = read_int(dev / "gpu_busy_percent")
        g.vram_used = read_int(dev / "mem_info_vram_used")
        g.vram_total = read_int(dev / "mem_info_vram_total")
        for mon in sorted((dev / "hwmon").glob("hwmon*")):
            t = read_int(mon / "temp1_input")
            if t is not None:
                g.temp = t / 1000.0
            p = read_int(mon / "power1_average")
            if p is None:
                p = read_int(mon / "power1_input")
            if p is not None:
                g.power_w = p / 1e6
            break

    def _nvidia(self, g: Gpu, dev: Path, query: bool) -> None:
        st = read(dev / "power" / "runtime_status") or ""
        if st not in AWAKE:
            g.note = "dGPU sleeping" if st == "suspended" else f"dGPU {st or 'state unknown'}"
            return
        if on_battery(psu_root(self.env)):
            g.note = "dGPU on"
            return
        if not query:
            return
        smi = shutil.which("nvidia-smi", path=self.env.get("PATH", ""))
        if smi is None:
            g.note = "nvidia-smi not installed"
            return
        if not g.slot:
            g.note = "no PCI slot"
            return
        now = self.clock()
        hit = self._cache.get(g.slot)
        if hit is None or now - hit[0] >= MIN_QUERY_S:
            try:
                r = self.run([smi, "-i", g.slot, f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
                parsed = parse_smi(r.stdout.splitlines()[0]) if r.returncode == 0 and r.stdout else {}
            except (OSError, subprocess.TimeoutExpired):
                parsed = {}
            hit = (now, parsed)
            self._cache[g.slot] = hit
        if not hit[1]:
            g.note = "nvidia-smi gave no answer"
        for k, v in hit[1].items():
            setattr(g, k, v)
