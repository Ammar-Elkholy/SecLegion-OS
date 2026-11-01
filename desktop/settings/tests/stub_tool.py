# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Fake system tools for the tests. Invoked as `stub_tool.py NAME ARGS...` by the wrapper scripts
that `stubs.make_bin` writes into a PATH directory. State lives in $SL_STUB_STATE/state.json so a
write is visible to the next read (real round trips). Every state change is appended to
$SL_STUB_STATE/mutations.log; every call to calls.log.
"""
import json
import os
import sys

STATE_DIR = os.environ["SL_STUB_STATE"]
STATE = os.path.join(STATE_DIR, "state.json")

DEFAULTS = {
    "ppd": "balanced", "backlight": 50, "kbd": 0, "volume": 0.40, "mute": False, "mic_mute": False,
    "wifi": True, "rf_blocked": False, "bt": True, "dnd": False,
    "filemgr": "thunar.desktop", "browser": "firefox.desktop",
    "lid_unit": "disabled", "theme_mode": "default", "theme_contrast": "normal", "theme_accent": None,
    "theme_id": "seclegion-dark", "theme_auto": "off",
    "autolock": "default", "updates": 3, "failed_units": "", "configerrors": "",
    "sshd": "disabled", "sshd_active": False, "ufw": "disabled",
    "ss": ("State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
           "LISTEN 0      128          0.0.0.0:22        0.0.0.0:*\n"
           "LISTEN 0      128             [::]:22           [::]:*\n"
           "LISTEN 0      4096       127.0.0.1:631       0.0.0.0:*\n"
           "LISTEN 0      4096   127.0.0.53%lo:53        0.0.0.0:*\n"
           "LISTEN 0      511            [::1]:8080         [::]:*\n"),
}


def monitors(name):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "hyprctl", name)) as f:
        return json.load(f)


def load():
    try:
        with open(STATE) as f:
            st = {**DEFAULTS, **json.load(f)}
    except OSError:
        st = dict(DEFAULTS)
    st.setdefault("monitors", monitors("monitors-extend.json"))
    return st


def save(st, what):
    with open(STATE, "w") as f:
        json.dump(st, f)
    with open(os.path.join(STATE_DIR, "mutations.log"), "a") as f:
        f.write(what + "\n")


def say(text):
    print(text)


def main(argv):
    name, args = argv[0], argv[1:]
    with open(os.path.join(STATE_DIR, "calls.log"), "a") as f:
        f.write(json.dumps([name, *args]) + "\n")
    st = load()
    line = " ".join([name, *args])
    if name == "powerprofilesctl":
        if args[:1] == ["get"]:
            say(st["ppd"])
        elif args[:1] == ["set"]:
            st["ppd"] = args[1]
            save(st, line)
    elif name == "brightnessctl":
        a = list(args)
        dev = "kbd" if "-d" in a and "kbd" in a[a.index("-d") + 1] else "backlight"
        if "set" in a:
            st["kbd" if dev == "kbd" else "backlight"] = int(a[a.index("set") + 1].rstrip("%"))
            save(st, line)
        else:
            pct = st[dev if dev == "kbd" else "backlight"]
            if dev == "kbd":
                say(f"asus_kbd_backlight,leds,{pct},{pct}%,100")
            else:
                say(f"amdgpu_bl1,backlight,{pct * 255 // 100},{pct}%,255")
    elif name == "wpctl":
        key = "mic_mute" if "SOURCE" in line else "mute"
        if args[0] == "get-volume":
            say(f"Volume: {st['volume']:.2f}" + (" [MUTED]" if st[key] else ""))
        elif args[0] == "set-volume":
            st["volume"] = int(args[2].rstrip("%")) / 100
            save(st, line)
        elif args[0] == "set-mute":
            st[key] = args[2] == "1"
            save(st, line)
    elif name == "nmcli":
        if args[:2] == ["radio", "wifi"]:
            if len(args) == 2:
                say("enabled" if st["wifi"] else "disabled")
            else:
                st["wifi"] = args[2] == "on"
                save(st, line)
    elif name == "rfkill":
        if args[0] == "-n":
            say("\n".join(["blocked" if st["rf_blocked"] else "unblocked"] * 2))
        else:
            st["rf_blocked"] = args[0] == "block"
            save(st, line)
    elif name == "bluetoothctl":
        if args[0] == "show":
            say("Controller 00:11:22:33:44:55 (public)\n\tPowered: " + ("yes" if st["bt"] else "no"))
        elif args[0] == "power":
            st["bt"] = args[1] == "on"
            save(st, line)
        elif args[0] in ("devices", "paired-devices"):
            say("Device AA:BB:CC:DD:EE:01 Pixel Buds\nDevice AA:BB:CC:DD:EE:02 Keyboard K2")
    elif name == "swaync-client":
        if args[0] == "-D":
            sys.stdout.write("true" if st["dnd"] else "false")
        else:
            st["dnd"] = args[0] == "-dn"
            save(st, line)
    elif name == "xdg-mime":
        if args[0] == "query":
            say(st["filemgr"])
        elif args[0] == "default":
            st["filemgr"] = args[1]
            save(st, line)
    elif name == "xdg-settings":
        if args[0] == "get":
            say(st["browser"])
        elif args[0] == "set":
            st["browser"] = args[2]
            save(st, line)
    elif name == "upower":
        if args[0] == "-e":
            base = "/org/freedesktop/UPower/devices/"
            say(f"{base}battery_BAT0\n{base}line_power_ADP0")
        else:
            say("  state: discharging\n  time to empty: 3.2 hours\n  percentage: 82%")
    elif name == "hyprctl":
        if args[:1] == ["version"]:
            say("Hyprland 0.56.2 built from branch v0.56.2")
        elif args[:1] == ["configerrors"]:
            say(st["configerrors"])
        elif args == ["-j", "monitors", "all"]:
            say(json.dumps(st["monitors"]))
        else:
            save(st, line)  # hyprsunset temperature N / identity: record only
    elif name == "seclegion-theme":
        if args[0] == "current":
            say(json.dumps({"mode": st["theme_mode"], "requested_mode": st["theme_mode"],
                            "contrast": st["theme_contrast"],
                            "source": {"accent_override": st["theme_accent"]}}))
        elif args[0] == "list":
            say(json.dumps([{"id": i, "label": i, "accent": "#00ff88", "bg": "#050f0e",
                             "surface": "#0b1e1c", "text": "#e0fff4", "current": i == st["theme_id"]}
                            for i in ("seclegion-dark", "seclegion-teal", "seclegion-cyan")]))
        elif args[0] == "auto":
            if args[1] == "status":
                say(st["theme_auto"])
            else:
                st["theme_auto"] = args[1]
                save(st, line)
        elif args[0] == "reset":
            st["theme_mode"], st["theme_id"] = "default", "seclegion-dark"
            save(st, line)
        elif args[0] == "apply" and "--theme" in args:
            st["theme_id"] = args[args.index("--theme") + 1]
            save(st, line)
        elif args[0] == "apply":
            st["theme_mode"] = args[args.index("--mode") + 1]
            st["theme_contrast"] = args[args.index("--contrast") + 1]
            if "--accent" in args:
                st["theme_accent"] = args[args.index("--accent") + 1]
            save(st, line)
    elif name == "systemctl":
        a = [x for x in args if x != "--user"]
        if "--user" not in args and a[0] in ("is-enabled", "is-active") and len(a) > 1:
            key = a[1].removesuffix(".service")  # system units: sshd, ufw
            if a[0] == "is-active":
                on = bool(st.get(key + "_active"))
                say("active" if on else "inactive")
            else:
                on = st.get(key) == "enabled"
                say(st.get(key, "not-found"))
            return 0 if on else 1
        if "--user" not in args and a[0] in ("enable", "disable", "mask", "unmask") and "sshd.service" in a:
            if a[0] in ("enable", "disable"):  # a masked unit stays masked, as systemctl does
                if st["sshd"] != "masked":
                    st["sshd"], st["sshd_active"] = a[0] + "d", a[0] == "enable"
                else:
                    sys.stderr.write("stub systemctl: Unit sshd.service is masked.\n")
                    return 1
            else:
                st["sshd"] = "masked" if a[0] == "mask" else "disabled"
            save(st, line)
            return 0
        if a[0] == "is-enabled" or a[0] == "is-active":
            on = st["lid_unit"] == "enabled"
            say("enabled" if on else "disabled")
            return 0 if on else 1
        if a[0] in ("enable", "disable"):
            st["lid_unit"] = a[0] + "d"
            save(st, line)
        elif a[0] == "daemon-reload":
            save(st, line)
        elif a[0] == "restart":
            save(st, line)
        elif a[0] == "list-units":
            say(st["failed_units"])
    elif name == "seclegion-autolock":
        if args[0] == "status":
            say(st["autolock"])
        elif args[0] == "set":
            st["autolock"] = args[1]
            save(st, line)
            say(args[1])
    elif name == "df":
        say("Filesystem     1024-blocks      Used Available Capacity Mounted on\n"
            "/dev/nvme0n1p2   100000000  45000000  55000000      45% /\n"
            "/dev/nvme0n1p1     1048576    131072    917504      13% /boot")
    elif name == "gio":
        if args[:2] == ["trash", "--empty"]:
            home = os.environ.get("HOME", "")
            if not home or home != os.environ.get("SL_HOME"):  # only ever the test's fake home
                sys.stderr.write("stub gio: refusing a HOME that is not SL_HOME\n")
                return 1
            import shutil
            for sub in ("files", "info"):
                d = os.path.join(home, ".local", "share", "Trash", sub)
                if os.path.isdir(d):
                    shutil.rmtree(d)
                    os.makedirs(d)
            save(st, line)
    elif name == "checkupdates":
        if st["updates"] == 0:
            return 2
        say("\n".join(f"pkg{i} 1.0-1 -> 1.1-1" for i in range(st["updates"])))
    elif name == "wl-copy":
        with open(os.path.join(STATE_DIR, "clipboard.txt"), "w") as f:
            f.write(sys.stdin.read())
        save(st, line)
    elif name in ("blueman-manager", "xdg-terminal-exec"):
        save(st, line)
    elif name == "ss":
        say(st["ss"].rstrip("\n"))
    elif name == "seclegion-display-menu":
        st["monitors"] = monitors(f"monitors-{args[0]}.json")  # the layout that mode leaves
        save(st, line)
    elif name in ("sshd", "ufw", "timedatectl"):
        save(st, line)  # root tools: any call is recorded as a mutation
    elif name == "snapper":
        pass
    elif name == "hyprsunset" or name == "systemd-inhibit":
        pass
    else:
        sys.stderr.write(f"stub: unknown tool {name}\n")
        return 127
    return 0


sys.exit(main(sys.argv[1:]))
