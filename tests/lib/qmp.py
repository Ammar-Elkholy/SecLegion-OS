# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Minimal synchronous QMP client: send-key, screendump, arbitrary commands."""

import json
import time

# Characters typed by type_text -> QMP qcode (shift handled separately).
_QCODES = {" ": "spc", "-": "minus", "=": "equal", ",": "comma", ".": "dot", "/": "slash",
           "\n": "ret", "_": "minus", "+": "equal", ":": "semicolon", ";": "semicolon",
           "'": "apostrophe", ">": "dot", "&": "7", "|": "backslash", "$": "4", "?": "slash",
           "(": "9", ")": "0", "[": "bracket_left", "]": "bracket_right"}
_SHIFTED = set("_+:>&|$?()")


class QmpError(RuntimeError):
    pass


class QmpClient:
    def __init__(self, sock, timeout=30.0):
        self._sock = sock
        self._sock.settimeout(timeout)
        self._buf = b""
        self.events = []
        self.greeting = None

    def _read_message(self):
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(65536)
            except TimeoutError as exc:
                raise QmpError("timed out waiting for QMP reply") from exc
            if not chunk:
                raise QmpError("QMP connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line)

    def handshake(self):
        self.greeting = self._read_message()
        if "QMP" not in self.greeting:
            raise QmpError(f"unexpected QMP greeting: {self.greeting!r}")
        self.execute("qmp_capabilities")
        return self.greeting

    def execute(self, command, **arguments):
        message = {"execute": command}
        if arguments:
            message["arguments"] = arguments
        self._sock.sendall(json.dumps(message).encode() + b"\n")
        while True:
            reply = self._read_message()
            if "event" in reply:
                self.events.append(reply)
            elif "error" in reply:
                raise QmpError(f"{command}: {reply['error'].get('desc', reply['error'])}")
            elif "return" in reply:
                return reply["return"]

    def send_key(self, *qcodes):
        """Press the given qcodes together (e.g. 'ctrl', 'alt', 'f2'), then release."""
        self.execute("send-key", keys=[{"type": "qcode", "data": q} for q in qcodes])

    def type_text(self, text, delay=0.0):
        for char in text:
            if delay:
                time.sleep(delay)
            if char.isupper():
                self.send_key("shift", char.lower())
            elif char in _SHIFTED:
                self.send_key("shift", _QCODES[char])
            elif char in _QCODES:
                self.send_key(_QCODES[char])
            elif char.isalnum() and char.isascii():
                self.send_key(char)
            else:
                raise ValueError(f"type_text cannot type {char!r}")

    def screendump(self, path, fmt="png"):
        """Write the current display to `path` (QEMU writes the file itself)."""
        self.execute("screendump", filename=path, format=fmt)
        return path

    def quit(self):
        try:
            self.execute("quit")
        except QmpError:
            pass  # QEMU may close the socket before replying
