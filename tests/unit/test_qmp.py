# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import json
import socket
import threading

import pytest

from tests.lib.qmp import QmpClient, QmpError


def fake_server(sock, replies):
    """Send the greeting, then answer each command with the next canned reply.

    A reply may be a list of messages (e.g. an event followed by the return).
    """
    seen = []

    def run():
        sock.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
        reader = sock.makefile("rb")
        for reply in replies:
            line = reader.readline()
            if not line:
                break
            seen.append(json.loads(line))
            for message in reply if isinstance(reply, list) else [reply]:
                sock.sendall(json.dumps(message).encode() + b"\n")

    threading.Thread(target=run, daemon=True).start()
    return seen


def client(replies):
    host, vm = socket.socketpair()
    seen = fake_server(vm, replies)
    qmp = QmpClient(host, timeout=5)
    qmp.handshake()
    return qmp, seen


def test_handshake_and_send_key():
    qmp, seen = client([{"return": {}}, {"return": {}}])
    qmp.send_key("ctrl", "alt", "f2")
    assert seen[0] == {"execute": "qmp_capabilities"}
    assert seen[1] == {"execute": "send-key", "arguments": {"keys": [
        {"type": "qcode", "data": "ctrl"}, {"type": "qcode", "data": "alt"},
        {"type": "qcode", "data": "f2"}]}}


def test_screendump_arguments():
    qmp, seen = client([{"return": {}}, {"return": {}}])
    qmp.screendump("/tmp/x.png")
    assert seen[1]["arguments"] == {"filename": "/tmp/x.png", "format": "png"}


def test_events_are_collected_not_returned():
    qmp, _ = client([{"return": {}}, [{"event": "STOP"}, {"return": {"ok": 1}}]])
    assert qmp.execute("query-status") == {"ok": 1}
    assert qmp.events == [{"event": "STOP"}]


def test_error_reply_raises():
    qmp, _ = client([{"return": {}}, {"error": {"class": "GenericError", "desc": "nope"}}])
    with pytest.raises(QmpError, match="nope"):
        qmp.execute("bogus")


def test_type_text_maps_shift_and_symbols():
    qmp, seen = client([{"return": {}}] * 5)
    qmp.type_text("a-B=")
    keys = [[k["data"] for k in s["arguments"]["keys"]] for s in seen[1:]]
    assert keys == [["a"], ["minus"], ["shift", "b"], ["equal"]]


def test_type_text_rejects_untypable():
    qmp, _ = client([{"return": {}}])
    with pytest.raises(ValueError):
        qmp.type_text("é")
