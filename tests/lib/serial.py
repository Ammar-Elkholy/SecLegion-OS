# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Serial console capture with event-driven wait-for-pattern (no sleeps, no polling)."""

import re
import threading

ANSI_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\r")


class WaitTimeout(AssertionError):
    """The pattern did not appear in time; carries the tail of the console for diagnosis."""


class SerialClosed(AssertionError):
    """The serial stream ended (QEMU exited) before the pattern appeared."""


class SerialCapture:
    """Reads a connected socket on a thread, keeps the text, lets tests block on patterns.

    Matching runs on text with ANSI escapes and CR removed. Each successful wait
    advances a cursor, so consecutive waits must match in order.
    """

    def __init__(self, sock):
        self._sock = sock
        self._raw = bytearray()
        self._cond = threading.Condition()
        self._closed = False
        self._cursor = 0
        self._thread = threading.Thread(target=self._pump, name="serial-capture", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _pump(self):
        try:
            while True:
                chunk = self._sock.recv(65536)
                if not chunk:
                    break
                with self._cond:
                    self._raw += chunk
                    self._cond.notify_all()
        except OSError:
            pass
        finally:
            with self._cond:
                self._closed = True
                self._cond.notify_all()

    def send(self, text):
        """Type `text` into the guest's serial console (what /dev/console reads when ttyS0 is last)."""
        self._sock.sendall(text.encode())

    def text(self):
        """All text captured so far, escapes stripped."""
        with self._cond:
            return ANSI_RE.sub("", self._raw.decode("utf-8", "replace"))

    def raw(self):
        with self._cond:
            return bytes(self._raw)

    @property
    def closed(self):
        with self._cond:
            return self._closed

    def wait_for(self, pattern, timeout):
        """Block until `pattern` (regex str) matches text after the cursor; return the match.

        Raises WaitTimeout after `timeout` seconds, SerialClosed if the stream ends first.
        """
        regex = re.compile(pattern)
        found = {}

        def ready():
            text = ANSI_RE.sub("", self._raw.decode("utf-8", "replace"))
            match = regex.search(text, self._cursor)
            if match:
                found["match"] = match
                return True
            return self._closed

        with self._cond:
            satisfied = self._cond.wait_for(ready, timeout)
            if "match" in found:
                self._cursor = found["match"].end()
                return found["match"]
            tail = ANSI_RE.sub("", self._raw.decode("utf-8", "replace"))[-600:]
        if self._closed and satisfied:
            raise SerialClosed(f"serial closed before /{pattern}/ appeared; tail: {tail!r}")
        raise WaitTimeout(f"/{pattern}/ not seen within {timeout}s; tail: {tail!r}")
