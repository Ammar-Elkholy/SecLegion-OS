# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run a backend write in a worker thread and marshal the outcome back to the GTK main loop.

Pure Python: GLib is imported only when the default scheduler runs, so tests drive this module with
a fake scheduler and no display. `run_async(work, done)` returns at once; `done(result, error)` runs
on the main loop (through `GLib.idle_add`) with exactly one of the two set. Every exception raised by
`work` reaches `done` as `error`: nothing is swallowed and nothing is raised in the worker.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

# Tests that drive widgets and then read the result straight away set this True: `work` and `done`
# then run inline on the caller's thread. Production code never sets it.
synchronous = False


def glib_schedule(fn: Callable[[], None]) -> None:
    """Queue `fn` on the GLib main loop once; thread-safe."""
    from gi.repository import GLib

    def once() -> bool:
        fn()
        return False  # GLib.SOURCE_REMOVE

    GLib.idle_add(once)


def run_async(
    work: Callable[[], Any],
    done: Callable[[Any, BaseException | None], None],
    schedule: Callable[[Callable[[], None]], None] | None = None,
) -> threading.Thread | None:
    """Call `work()` off the calling thread, then `done(result, error)` on the main loop."""

    def call() -> tuple[Any, BaseException | None]:
        try:
            return work(), None
        except BaseException as e:  # reported to `done`, never lost in the worker
            return None, e

    if synchronous:
        result, error = call()
        done(result, error)
        return None
    post = schedule or glib_schedule

    def worker() -> None:
        result, error = call()
        post(lambda: done(result, error))

    t = threading.Thread(target=worker, name="seclegion-settings-write", daemon=True)
    t.start()
    return t
