# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The live session is the SecLegion desktop (static content; the VM gate is M2-live-desktop).

ISO #11 booted stock Hyprland: the prebuilt live home never got /etc/skel, and greetd ran plain
`Hyprland`, so no uwsm session units (waybar, swaync, polkit agent) started.
"""

import os
import re
import tomllib

from tests.unit.conftest import REPO

PROFILE = os.path.join(REPO, "iso", "profile")
AIROOTFS = os.path.join(PROFILE, "airootfs")
BIN = os.path.join(AIROOTFS, "usr", "local", "bin")
WRAPPER = os.path.join(BIN, "seclegion-live-session")
HYPR = os.path.join(AIROOTFS, "home", "seclegion-live", ".config", "hypr")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def code_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_greetd_live_initial_session_is_the_wrapper():
    cfg = tomllib.loads(read(AIROOTFS, "etc", "greetd", "config.toml"))
    assert cfg["initial_session"]["command"] == "/usr/local/bin/seclegion-live-session"
    assert cfg["initial_session"]["user"] == "seclegion-live"


def test_wrapper_fills_the_home_without_overwriting_then_starts_hyprland_through_uwsm():
    lines = code_lines(read(WRAPPER))
    assert read(WRAPPER).startswith("#!/bin/sh\n")
    assert lines == ['cp -a -n /etc/skel/. "$HOME"/', "exec uwsm start -- hyprland.desktop"]
    assert os.access(WRAPPER, os.X_OK)  # -n: the live hypridle.conf and user.lua stay


def test_profiledef_permissions_for_the_session_files():
    perms = dict(re.findall(r'\["(/[^"]+)"\]="([^"]+)"', read(PROFILE, "profiledef.sh")))
    assert perms["/usr/local/bin/seclegion-live-session"] == "0:0:755"
    assert perms["/usr/local/bin/hyprlock"] == "0:0:755"
    assert perms["/home/seclegion-live/.config/hypr/user.lua"] == "1000:1000:640"
    assert perms["/home/seclegion-live/.config/hypr/hypridle.conf"] == "1000:1000:640"


def test_the_prebuilt_live_home_does_not_shadow_the_skel_desktop_config():
    # skel's hyprland.lua must arrive via the wrapper; a prebuilt copy would go stale
    assert sorted(os.listdir(HYPR)) == ["hypridle.conf", "user.lua"]


def test_live_session_cannot_lock():
    assert 'hl.unbind, "SUPER + L"' in read(HYPR, "user.lua")
    assert code_lines(read(BIN, "hyprlock"))[-1] == "exit 1"
    assert os.access(os.path.join(BIN, "hyprlock"), os.X_OK)
    idle = "\n".join(code_lines(read(HYPR, "hypridle.conf")))
    assert not re.search(r"lock_cmd|before_sleep_cmd|hyprlock|loginctl", idle)
