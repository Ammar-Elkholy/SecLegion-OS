#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G1 (plan r12 P2): helper windows float and open centred. In a NESTED Hyprland (never the
# live session: every hyprctl call is nested_hyprctl) with the committed seclegion-host.lua
# loaded, a window whose class is pavucontrol, blueman-manager, nm-connection-editor or
# org.seclegion.Settings opens floating and centred on the monitor,
# and a window of any other class (plain kitty, a lookalike) stays tiled.
# Windows are kitty terminals started with --class; they die with the compositor and by pid.
# Prints "rules-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
PIDS=""
cleanup() {
    local p
    for p in $PIDS; do kill -0 "$p" 2>/dev/null && kill -TERM "$p" 2>/dev/null; done
    keys_cleanup
}
trap cleanup EXIT
keys_start none

e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "configerrors: $e" >&2; exit 1; }

open_class() {   # CLASS -> opens a kitty window of that class; prints nothing, records its pid
    local cls="$1" i pid=""
    nested_hyprctl dispatch "hl.dsp.exec_cmd(\"kitty --config NONE -o remember_window_size=no -o initial_window_width=400 -o initial_window_height=300 --class $cls sh -c 'sleep 120'\")" > /dev/null
    for i in $(seq 1 75); do
        pid="$(nested_hyprctl clients -j | python3 -c '
import json, sys
print(next((c["pid"] for c in json.load(sys.stdin) if c["class"] == sys.argv[1]), ""))' "$cls")"
        [ -z "$pid" ] || break
        sleep 0.2
    done
    [ -n "$pid" ] || { echo "no window of class $cls appeared" >&2; return 1; }
    PIDS="$PIDS $pid"
    sleep 0.3
}

check_once() {   # CLASS WANT   (WANT: float | float:WxH | tiled)
    local mon
    mon="$(nested_hyprctl monitors -j)"
    nested_hyprctl clients -j | MON="$mon" python3 -c '
import json, os, sys
cls, want = sys.argv[1:3]
m = json.loads(os.environ["MON"])[0]
c = next((c for c in json.load(sys.stdin) if c["class"] == cls), None)
if c is None:
    sys.exit(cls + ": no such window")
if want == "tiled":
    sys.exit(0 if not c["floating"] else cls + ": floating, want tiled")
if not c["floating"]:
    sys.exit(cls + ": tiled, want floating")
if any(m["reserved"]):
    sys.exit("the nested monitor has reserved areas; this test compares with the whole monitor")
mw, mh = m["width"] / m["scale"], m["height"] / m["scale"]
w, h = c["size"]
if ":" in want:
    ww, hh = map(int, want.split(":")[1].split("x"))
    if abs(w - ww) > 1 or abs(h - hh) > 1:
        sys.exit("%s: size %dx%d, want %dx%d" % (cls, w, h, ww, hh))
cx, cy = c["at"][0] + w / 2, c["at"][1] + h / 2
if abs(cx - (m["x"] + mw / 2)) > 2 or abs(cy - (m["y"] + mh / 2)) > 2:
    sys.exit("%s: centre (%s, %s), want (%s, %s)" % (cls, cx, cy, m["x"] + mw / 2, m["y"] + mh / 2))' "$1" "$2" || return 1
}

check() {   # the compositor applies a rule's size after the first configure: poll up to 4 s
    local i
    for i in $(seq 1 20); do
        check_once "$1" "$2" 2> "$NESTED_DIR/winrules.err" && return 0
        sleep 0.2
    done
    cat "$NESTED_DIR/winrules.err" >&2
    exit 1
}

# negatives first: they stay tiled (a tiled window never moves the others, so the order only matters for geometry)
open_class kitty || exit 1
check kitty tiled
open_class pavucontrol-extra || exit 1       # a lookalike: the rule is anchored
check pavucontrol-extra tiled
open_class org.pulseaudio.pavucontrol || exit 1
check org.pulseaudio.pavucontrol float
open_class blueman-manager || exit 1
check blueman-manager float
open_class nm-connection-editor || exit 1
check nm-connection-editor float
open_class org.seclegion.Settings || exit 1
check org.seclegion.Settings float
check kitty tiled
echo rules-ok
