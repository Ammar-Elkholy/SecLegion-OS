# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Issue 18: Settings acts and never shows a command for the user to run. Display-free.

`test_no_commands_shown` collects every user-facing string: what each row shows for its read state
(all capabilities on, fake ctx), the toast for every kind of failure, and every string literal the
UI sources pass to a toast, title, subtitle, tooltip, label, button or dialog.
`test_privileged_write_offthread` drives the real write path (`writeflow.WriteFlow`) with a stub
pkexec that reports a dismissed password prompt.
"""
import ast
import queue
import re
import threading
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from seclegion_settings.backend import registry
from seclegion_settings.backend.env import (
    AuthCancelled,
    CommandFailed,
    InvalidValue,
    NotAuthorized,
    Refused,
    Unavailable,
)
from seclegion_settings.ui import offthread, pages, writeflow
from stubs import StubCase, snapshot

COMMAND = re.compile(r"sudo|pkexec|seclegion-|systemctl|`|\$ |copy (the )?command", re.I)
UI = Path(writeflow.__file__).parent
SINKS = {"toast", "set_title", "set_subtitle", "set_tooltip_text", "set_label", "set_description",
         "set_body", "set_heading", "set_button_label", "add_response", "Toast", "AlertDialog",
         "StatusPage", "Button", "Label", "_label", "_chip"}


def _strings(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def ui_literals():
    """(file:line, text) for every string a UI sink receives, and every public str constant."""
    for f in sorted(UI.glob("*.py")):
        tree = ast.parse(f.read_text(), str(f))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if fn in SINKS:
                    for a in [*n.args, *(k.value for k in n.keywords)]:
                        yield from ((f"{f.name}:{n.lineno}", s) for s in _strings(a))
            elif isinstance(n, ast.Assign) and tree.body.count(n):
                names = [t.id for t in n.targets if isinstance(t, ast.Name)]
                # text and tables of text; a Path or a compiled pattern is not text the user reads
                text = (ast.Constant, ast.Dict, ast.Set, ast.Tuple, ast.List, ast.JoinedStr)
                if names and not names[0].startswith("_") and isinstance(n.value, text):
                    yield from ((f"{f.name}:{n.lineno}", s) for s in _strings(n.value))


class NoCommands(StubCase):
    def test_no_commands_shown(self):
        ctx = self.ctx()
        shown = []
        for s in registry.SETTINGS:
            st = registry.row(s, ctx)
            self.assertTrue(st.visible, f"{s.id} hidden: {st.reason}")  # all capabilities on
            texts = [s.label, s.description, s.confirm or "", s.action_label or "",
                     writeflow.subtitle(s, st), writeflow.privilege(s), *s.choices,
                     *registry.CHOICE_LABELS.get(s.id, {}).values()]
            for e in (AuthCancelled(f"{s.label}: x"), NotAuthorized(f"{s.label}: x"),
                      Refused(f"{s.label}: x"), Unavailable(f"{s.id}: x"), InvalidValue(f"{s.id}: x"),
                      CommandFailed("sudo systemctl restart x: exit 1"),
                      CommandFailed(f"{s.label}: not changed; seclegion-root-apply: run as root: sudo"),
                      OSError(13, "Permission denied", "/etc/x")):
                texts.append(writeflow.failure(s, e))
            if s.privileged and not writeflow.changeable(s):  # the real refusal, before any prompt
                with self.assertRaises(Refused) as cm:
                    registry.write(s, ctx, s.choices[0] if s.choices else str(s.minimum or "on"))
                texts.append(writeflow.failure(s, cm.exception))
            shown += [(s.id, t) for t in texts]
        shown += [("page", p.label) for p in pages.PAGES]
        literals = list(ui_literals())
        self.assertGreater(len(literals), 50)  # the scan reached the toasts, labels and dialogs
        bad = [(where, t) for where, t in shown + literals if COMMAND.search(t)]
        self.assertEqual(bad, [])


class FakeLoop:
    def __init__(self):
        self.q = queue.Queue()

    def post(self, fn):
        self.q.put(fn)


class FakeHost:
    def __init__(self):
        self.toasts, self.saves, self.rows = [], [], {}

    def toast(self, title, undo=None):
        self.toasts.append(title)

    def saved(self, row, res, previous, undone=False):
        self.saves.append((res, previous))


class FakeRow(writeflow.WriteFlow):
    """The GTK row's hooks, recorded: refresh re-reads the stored value like SettingRow does."""

    def __init__(self, s, ctx):
        self.s, self.ctx, self.host = s, ctx, FakeHost()
        self.busy_log, self.refreshes = [], 0
        self.refresh()
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1
        self.raw = registry.row(self.s, self.ctx).value

    def set_busy(self, on):
        self.busy_log.append(on)


class PrivilegedWrite(StubCase):
    def pkexec(self, rc):
        p = self.tmp / "pkexec"
        p.write_text(f"#!/bin/sh\nexit {rc}\n")
        p.chmod(0o755)
        self.environ["SL_PKEXEC"] = str(p)

    def dispatch(self, row, raw):
        """Apply through the real offthread helper with a fake main loop; returns the worker's tid."""
        loop, seen, real = FakeLoop(), [], offthread.run_async

        def spy(work, done):
            seen.append(work)
            return real(lambda: (threading.get_ident(), work()), lambda r, e: done(r and r[1], e),
                        schedule=loop.post)

        offthread.run_async = spy
        self.addCleanup(setattr, offthread, "run_async", real)
        row.apply(raw)
        self.assertEqual(len(seen), 1)  # dispatched through offthread.run_async
        self.assertEqual(row.busy_log, [True])  # busy while the worker waits on the prompt
        loop.q.get(timeout=10)()
        return row

    def test_privileged_write_offthread(self):
        self.pkexec(126)  # the password prompt was dismissed
        before = (snapshot(self.etc), snapshot(self.home))
        row = FakeRow(registry.get("power.lid_battery"), self.ctx())
        stored = row.raw
        self.assertNotEqual(stored, "lock")
        self.dispatch(row, "lock")
        self.assertEqual(row.busy_log, [True, False])
        self.assertEqual(row.host.toasts,
                         ["Lid closed on battery: not changed. The password was not entered."])
        self.assertEqual(row.host.saves, [])
        self.assertEqual(row.refreshes, 1)  # re-read: the control goes back to the stored value
        self.assertEqual(row.raw, stored)
        self.assertIn("password", row.last_error)
        self.assertEqual((snapshot(self.etc), snapshot(self.home)), before)

    def test_privileged_write_success_saves(self):
        self.pkexec(0)
        row = self.dispatch(FakeRow(registry.get("power.charge_limit"), self.ctx()), "80")
        self.assertEqual(row.host.toasts, [])
        self.assertEqual(len(row.host.saves), 1)
        self.assertEqual(row.last_error, "")

    def test_theme_auto_runs_the_theme_tool_offthread(self):
        row = FakeRow(registry.get("appearance.auto"), self.ctx())
        loop = FakeLoop()
        real = offthread.run_async
        offthread.run_async = lambda w, d: real(w, d, schedule=loop.post)
        self.addCleanup(setattr, offthread, "run_async", real)
        row.apply("on")
        loop.q.get(timeout=10)()
        self.assertIn("seclegion-theme auto on", self.mutations())
        self.assertEqual(len(row.host.saves), 1)


if __name__ == "__main__":
    unittest.main()
