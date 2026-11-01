# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""UI smoke test of seclegion-wifi under a private gtk4-broadwayd on a fake NM.Client (the pattern of
test_sysmon_ui.py): never the live Wayland/X display, never the real NetworkManager. Skips when
broadwayd or the system python3 with GTK4, libadwaita and libnm is missing."""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
WIFI = os.path.join(os.path.dirname(HERE), "..", "desktop", "wifi", "seclegion_wifi")


def _free_display(run):
    return next(n for n in range(40, 90) if not os.path.exists(os.path.join(run, f"broadway{n}.socket")))


def test_wifi_ui_smoke_under_broadway(tmp_path):
    broadwayd, py = shutil.which("gtk4-broadwayd"), "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    probe_imports = "import gi; gi.require_version('Gtk','4.0'); gi.require_version('NM','1.0')"
    if subprocess.run([py, "-c", probe_imports], capture_output=True).returncode:
        pytest.skip("gi GTK4 or libnm not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display(str(run))
    env = {k: v for k, v in os.environ.items()
           if k not in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}",
               HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"))
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "wifi_ui_probe.py")], env=env,
                           capture_output=True, text=True, timeout=60)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    print(json.dumps(got), file=sys.stderr)
    assert got["theme"] is True
    assert got["rows"] == [["Home", "WPA2, Connected, 70%"], ["Attic", "WPA3, 60%"], ["Cafe", "Open, 50%"],
                           ["Corp", "Enterprise, 40%"], ["Neighbour", "WPA2, 35%"],
                           ["Office", "WPA2, Saved, 20%"]]
    assert got["current"] == ["Home", "Connected, signal 70%", True]
    assert got["radio"] is True and got["scan_on_open"] == 1
    assert got["forget_buttons"] == ["Home", "Office"]
    # open: added with no security setting; saved: the most recently used profile is activated
    assert got["open_and_saved"] == [["add", "Cafe", "Cafe", None, None, True, "/ap/cafe", {}],
                                     ["activate", "Office", 9, True, "/ap/office"]]
    assert got["corp"][1] == [] and "802.1X" in got["corp"][0]
    assert got["psk_dialog"] == ["Join Neighbour", False, True]
    assert got["sae_dialog"] == [False, True]
    assert got["added"] == [["add", "Neighbour", "Neighbour", "wpa-psk", "12345678", True, "/ap/nb", {}],
                            ["add", "Attic", "Attic", "sae", "s", True, "/ap/attic", {}]]
    assert got["connecting"] == "Connecting to Attic"
    assert got["failed"] == ["Could not join Attic: the password was not accepted.", "Not connected"]
    assert got["disconnect_forget"] == [["disconnect"], ["delete", "Home", 5]]
    assert got["denied"] == "You are not allowed to change Wi-Fi settings here."
    assert got["generic"] == "Could not join Cafe."
    assert got["hidden_open"] == ["Connect to a hidden network…", "Connect to a hidden network", 1,
                                  True, False]
    assert got["hidden_validation"] == [
        [False, "Enter the network name."], [False, "A WPA password has 8 to 63 characters."],
        [False, "A network name is at most 32 bytes long."], [True, ""]]
    assert got["hidden_psk"] == [[["add", "Ghost", "Ghost", "wpa-psk", "12345678", True, None, {}]],
                                 [True], True]
    assert got["hidden_open_security"] == [False, False]
    assert got["hidden_open_ready"] is True
    assert got["hidden_open_join"] == [[["add", "Ghost2", "Ghost2", None, None, True, None, {}]], [True]]
    # a failed join says one plain sentence: neither NetworkManager's message nor the password
    assert got["hidden_failed_toast"] == ["Could not join Ghost3.", False]
    assert got["hidden_cancel"] == [True, 2]  # cancelling joins nothing: the two joins since the clear
    assert got["radio_off"] == [[["set", "/org/freedesktop/NetworkManager", "org.freedesktop.NetworkManager",
                                  "WirelessEnabled", False]], False, 0, "Wi-Fi is off.", False]


def test_second_launch_presents_the_running_window(tmp_path):
    """One instance: a second `seclegion-wifi` (a second click on the bar module) is forwarded to the
    running panel over D-Bus and presents its window; it builds no window of its own. Runs on a private
    session bus and a private Broadway display, with the NetworkManager client faked out."""
    broadwayd, py = shutil.which("gtk4-broadwayd"), "/usr/bin/python3"
    runner = shutil.which("dbus-run-session")
    if not broadwayd or not runner or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd, dbus-run-session or system python3 not available")
    probe_imports = "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')"
    if subprocess.run([py, "-c", probe_imports], capture_output=True).returncode:
        pytest.skip("gi GTK4 or libadwaita not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display(str(run))
    env = {k: v for k, v in os.environ.items()
           if k not in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}",
               HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"))
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([runner, "--", py, os.path.join(HERE, "wifi_single_probe.py"), "primary"],
                           env=env, capture_output=True, text=True, timeout=60)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["second_rcs"] == [0, 0], got  # forwarded to the primary; none built a window (exit 3)
    assert got["windows"] == 1 and got["same_window"] is True, got
    assert got["presented"] == 3, got  # the first launch, then one present per forwarded launch


def test_package_never_runs_a_command():
    """The panel talks to NetworkManager through libnm only: no nmcli, no subprocess, no shell."""
    for base, _dirs, files in os.walk(WIFI):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(base, f)) as fh:
                    text = fh.read()
                for word in ("nmcli", "subprocess", "os.system", "Popen", "GLib.spawn"):
                    assert word not in text, (f, word)
