# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import socket
import threading

import pytest

from tests.lib.serial import SerialCapture, SerialClosed, WaitTimeout


def pair():
    host, vm = socket.socketpair()
    return host, vm, SerialCapture(host).start()


def test_wait_for_sees_pattern_written_later():
    _host, vm, cap = pair()
    threading.Timer(0.05, lambda: vm.sendall(b"booting\r\nLogin: ")).start()
    assert cap.wait_for(r"Login: ", 5).group(0) == "Login: "


def test_ansi_and_cr_stripped():
    _host, vm, cap = pair()
    vm.sendall(b"\x1b[1;1H\x1b[32mOK\x1b[0m done\r\n")
    assert cap.wait_for(r"OK done", 5)


def test_private_csi_parameters_stripped():
    # OVMF's terminal emits ECMA-48 private parameters such as ESC [ = 3 h.
    _host, vm, cap = pair()
    vm.sendall(b"\x1b[=3h\x1b[8;056;240tmenu")
    assert cap.wait_for(r"^menu$", 5)


def test_osc_sequences_stripped_with_payload():
    # systemd's shell context (OSC 3008) wraps every command on the installed system's console.
    _host, vm, cap = pair()
    vm.sendall(b"\x1b]3008;start=ab;type=command;cwd=/home/t\x1b\\firefox.desktop\n"
               b"\x1b]0;title\x07M6SRC4:0\n")
    assert cap.wait_for(r"^firefox.desktop\nM6SRC4:0$", 5)


def test_cursor_orders_consecutive_waits():
    _host, vm, cap = pair()
    vm.sendall(b"B then A")
    cap.wait_for("A", 5)
    with pytest.raises(WaitTimeout):
        cap.wait_for("B", 0.2)  # B was before the cursor


def test_timeout_reports_tail():
    _host, vm, cap = pair()
    vm.sendall(b"something")
    with pytest.raises(WaitTimeout, match="something"):
        cap.wait_for("never", 0.2)


def test_closed_stream_fails_fast():
    _host, vm, cap = pair()
    vm.sendall(b"partial")
    vm.close()
    with pytest.raises(SerialClosed):
        cap.wait_for("never", 30)  # returns immediately, not after 30 s
    assert cap.closed and cap.raw() == b"partial"
