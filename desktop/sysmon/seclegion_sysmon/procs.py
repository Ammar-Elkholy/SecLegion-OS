# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The process list and End/Kill for the user's own processes. No GTK.

A process is the user's own when its real and effective uid are both the user's uid: setuid programs
(effective root) and other users' processes are refused before any signal is sent.
"""
from __future__ import annotations

import os
import signal
from dataclasses import dataclass

from .data import psutil_module

ATTRS = ["pid", "name", "username", "uids", "cpu_percent", "memory_info"]


@dataclass
class Proc:
    pid: int
    name: str
    user: str
    cpu: float          # percent of one core (top's convention)
    rss: int            # bytes
    own: bool


class Refused(Exception):
    """The signal was not sent; the message says why."""


def is_own(uids, uid: int) -> bool:
    return uids is not None and uids.real == uid and uids.effective == uid


def list_procs(ps=None, uid: int | None = None) -> list[Proc]:
    ps = psutil_module(ps)
    uid = os.getuid() if uid is None else uid
    out = []
    for p in ps.process_iter(ATTRS):
        i = p.info
        mem = i.get("memory_info")
        out.append(Proc(i["pid"], i.get("name") or "?", i.get("username") or "?", i.get("cpu_percent") or 0.0,
                        mem.rss if mem is not None else 0, is_own(i.get("uids"), uid)))
    return out


def send(pid: int, sig: int, ps=None, uid: int | None = None) -> None:
    """SIGTERM (End process) or SIGKILL (Kill) to one of the user's own processes, else Refused."""
    if sig not in (signal.SIGTERM, signal.SIGKILL):
        raise Refused(f"signal {sig} is not End or Kill")
    ps = psutil_module(ps)
    uid = os.getuid() if uid is None else uid
    if pid == os.getpid():
        raise Refused("this is the system monitor itself")
    try:
        p = ps.Process(pid)
        if not is_own(p.uids(), uid):
            raise Refused(f"process {pid} belongs to another user")
        p.send_signal(sig)  # psutil checks the pid was not reused since Process() was made
    except ps.NoSuchProcess:
        raise Refused(f"process {pid} has already exited") from None
    except ps.AccessDenied:
        raise Refused(f"not allowed to signal process {pid}") from None
