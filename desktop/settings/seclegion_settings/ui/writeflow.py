# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The write path of a settings row and the plain words it shows (issue 18). Pure Python, no gi.

Settings acts; it never hands the user a command to run. A privileged row's write goes through
`registry.write` (pkexec asks for the administrator password) on a worker thread from `offthread`;
the row shows a busy state meanwhile, and on any failure it re-reads the stored value, so the
control goes back to what is really set. Toasts are plain sentences: a message that would show a
command line is replaced by a short one, and the full error goes to the row's Details.
"""

from __future__ import annotations

import re

from ..backend import registry
from ..backend.env import AuthCancelled, CommandFailed, NotAuthorized, Refused, SettingError
from . import offthread

ASKS = "asks for the administrator password"
NOT_YET = "Settings can't change this yet"
BUSY = "Applying. Enter the administrator password if asked."
ACTION_DONE = {"appearance.reset": "Reset to SecLegion Dark. Applies now."}
CHIP_TIPS = {
    "root": "A system setting: changing it " + ASKS,
    "live": "Applies at once, no logout needed",
    "reboot": "Applies after the next boot",
}
# Text that reads like a command line. Such a message never reaches a toast.
COMMAND = re.compile(r"\bsudo\b|\bpkexec\b|seclegion-|\bsystemctl\b|`|\$ ")


def changeable(s: registry.Setting) -> bool:
    """False for a privileged row the system helper has no writer for yet."""
    return not s.privileged or registry.root_ready(s)


def privilege(s: registry.Setting) -> str:
    """The "needs privilege" line of Details."""
    if not s.privileged:
        return "no"
    return f"yes: {ASKS}" if changeable(s) else f"yes: {NOT_YET}"


def subtitle(s: registry.Setting, st: registry.Row) -> str:
    """The row's subtitle for its read state."""
    if not st.visible:
        return st.reason
    if st.error:
        return "Unavailable"
    return s.description if changeable(s) else NOT_YET


def failure(s: registry.Setting, e: BaseException) -> str:
    """The toast for a failed write. Auth errors first: they are Refused subclasses."""
    if isinstance(e, AuthCancelled):
        return f"{s.label}: not changed. The password was not entered."
    if isinstance(e, NotAuthorized):
        return f"{s.label}: not changed. This account may not change system settings."
    if isinstance(e, Refused) and not changeable(s):
        return f"{s.label}: not changed. {NOT_YET}."
    if isinstance(e, OSError):
        where = f" ({e.filename})" if e.filename else ""
        msg = f"{s.label}: {e.strerror or e}{where}"
    else:
        msg = str(e)
    # A failed user command names the command first ("nmcli ...: exit 1"); the root helper's
    # failures start with the label. Either way a command never reaches the toast.
    named = isinstance(e, CommandFailed) and not msg.startswith(f"{s.label}:")
    if named or COMMAND.search(msg):
        return f"{s.label}: not changed. The error is in Details."
    return msg


class WriteFlow:
    """One write per row at a time; the latest request runs when the current one ends.

    The row supplies `s`, `host` (toast, saved, rows), `ctx`, `raw`, `refresh()` and `set_busy()`.
    """

    _inflight = False  # a write is running on the worker thread
    _queued: tuple[str, bool] | None = None
    last_error = ""  # the full text of the last failure, shown in Details

    def apply(self, raw: str, undo: bool = False) -> None:
        """Write `raw` through the backend on a worker thread; the outcome lands in `_written` on
        the main loop. A privileged row blocks there on the password prompt, never on the UI."""
        if self._inflight:
            self._queued = (raw, undo)
            return
        previous = self.raw
        if raw == previous and self.s.kind != "action":
            return
        self._inflight = True
        if self.s.privileged:
            self.set_busy(True)
        ctx, setting = self.ctx, self.s
        offthread.run_async(
            lambda: registry.write(setting, ctx, raw),
            lambda res, err: self._written(raw, previous, undo, res, err),
        )

    def _written(self, raw: str, previous, undo: bool, res, err) -> None:
        """Main loop: the worker's write finished (res) or failed (err)."""
        self._inflight = False
        if self.s.privileged:
            self.set_busy(False)
        queued, self._queued = self._queued, None
        if err is not None:
            self._write_failed(err)
        else:
            self.last_error = ""
            self.refresh()
            if self.s.page == "appearance":  # a theme change moves the sibling rows too
                for other in self.host.rows.values():
                    if other is not self and other.s.page == "appearance":
                        other.refresh()
            if self.s.kind == "action":
                self.host.toast(ACTION_DONE.get(self.s.id, f"{self.s.label}: done."))
            else:
                self.host.saved(self, res, previous, undone=undo)
        if queued is not None:
            self.apply(*queued)

    def _write_failed(self, e: BaseException) -> None:
        if not isinstance(e, (SettingError, OSError)):
            raise e
        self.last_error = str(e)
        self.host.toast(failure(self.s, e))
        self.refresh()  # re-read: the control shows the stored value again

