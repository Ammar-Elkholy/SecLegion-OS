# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G74: Settings writes run off the UI thread, and their errors still reach the UI callback.

Headless: `offthread.run_async` takes a scheduler, so a fake main loop stands in for GLib.idle_add.
"""

import os
import queue
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop", "settings"))
from seclegion_settings.ui import offthread  # noqa: E402


class FakeLoop:
    """Collects what the worker posts; `tick()` runs one pending item like a main-loop iteration."""

    def __init__(self):
        self.q = queue.Queue()
        self.thread_ids = []

    def post(self, fn):
        self.q.put(fn)

    def tick(self, timeout):
        fn = self.q.get(timeout=timeout)
        self.thread_ids.append(threading.get_ident())
        fn()


def test_ui_thread_slow_writer_does_not_block_the_main_loop():
    loop, got = FakeLoop(), []

    def slow_writer():
        time.sleep(2)
        return "written"

    t0 = time.monotonic()
    offthread.run_async(slow_writer, lambda res, err: got.append((res, err)), schedule=loop.post)
    assert time.monotonic() - t0 < 0.5  # returned at once: the caller (main loop) is free
    assert got == []  # and the callback has not fired yet
    t1 = time.monotonic()
    ticked = 0
    while time.monotonic() - t1 < 0.5:  # the loop keeps ticking while the write sleeps
        ticked += 1
        time.sleep(0.01)
    assert ticked > 10 and got == []
    loop.tick(timeout=5)  # later, the result is marshalled onto the loop thread
    assert got == [("written", None)]
    assert loop.thread_ids == [threading.get_ident()]


def test_ui_thread_error_surfaces_to_the_callback():
    loop, got = FakeLoop(), []

    def failing_writer():
        raise OSError(13, "Permission denied", "/etc/x")

    offthread.run_async(failing_writer, lambda res, err: got.append((res, err)), schedule=loop.post)
    loop.tick(timeout=5)
    ((res, err),) = got
    assert res is None and isinstance(err, OSError) and err.filename == "/etc/x"


def test_ui_thread_work_runs_on_a_worker_thread():
    loop, ran_on = FakeLoop(), []
    offthread.run_async(lambda: ran_on.append(threading.get_ident()), lambda r, e: None, schedule=loop.post)
    loop.tick(timeout=5)
    assert ran_on and ran_on[0] != threading.get_ident()


def test_ui_thread_rows_apply_goes_through_run_async():
    """The only UI call of registry.write for a real write is wrapped (static guard). Since issue 18
    the write path of a row lives in ui/writeflow.py (GTK-free); rows.py only dry-runs."""
    ui = os.path.join(ROOT, "desktop/settings/seclegion_settings/ui")
    flow = open(os.path.join(ui, "writeflow.py")).read()
    rows = open(os.path.join(ui, "rows.py")).read()
    assert "offthread.run_async(" in flow and "res = registry.write(" not in flow
    assert "class SettingRow(WriteFlow)" in rows and "registry.write(self.s, self.ctx" not in rows
