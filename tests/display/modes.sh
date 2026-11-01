#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G3 of the display menu (issue 14), in a NESTED Hyprland: the window output stands in for the
# laptop screen (SL_DISPLAY_INTERNAL), a created headless output for the HDMI. Runs
# desktop/display/seclegion-display-menu MODE for laptop, extend, mirror, external, laptop, extend
# and checks `monitors all -j` and the workspaces after each. The menu's hyprctl is pinned to the
# nested instance (HYPRLAND_INSTANCE_SIGNATURE set to it; never the live session).
# Prints one line per mode, then "PASS modes" (exit 0) or "FAIL <mode>: <why>" (exit 1);
# exit 77 if no nested Hyprland or no second output.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
# shellcheck source=tests/display/lib.sh
. "$here/lib.sh"
trap nested_stop EXIT
extra="$NESTED_DIR/modes.lua"
mkdir -p -- "$NESTED_DIR"
echo 'hl.monitor({ output = "", mode = "1280x720", position = "auto", scale = 1.5 })' > "$extra"
nested_start "$extra" || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
inner="$(monitor_names)"
inner="${inner%% *}"
out_create || { echo "UNVERIFIED: no second output in the nested Hyprland" >&2; exit 77; }
ext="$OUT_NAME"
[ -n "$NESTED_SIG" ] || exit 1

# the scale each output has from the catch-all rule; every mode must keep it
scales() {
    nested_hyprctl monitors all -j | python3 -c '
import json, sys
print(" ".join("%s=%g" % (m["name"], m["scale"]) for m in json.load(sys.stdin)))'
}
want_scales="$(scales)"

menu() {
    HYPRLAND_INSTANCE_SIGNATURE="$NESTED_SIG" SL_HYPRCTL=hyprctl SL_DISPLAY_INTERNAL="$inner" \
        SL_LOCK="$NESTED_DIR/display-menu.lock" python3 "$repo/desktop/display/seclegion-display-menu" "$1"
}

# check MODE: the state `monitors all -j` + `workspaces -j` must show after MODE
check() {
    local mode="$1" why=""
    for _ in $(seq 1 20); do
        why="$(python3 - "$mode" "$inner" "$ext" "$want_scales" \
            "$(nested_hyprctl monitors all -j)" "$(nested_hyprctl workspaces -j)" <<'PY'
import json, sys
mode, inner, ext, want, mons, wss = sys.argv[1:]
ms = {m["name"]: m for m in json.loads(mons)}
ids = {str(m["id"]): m["name"] for m in ms.values()}
on = lambda n: n in ms and not ms[n]["disabled"]
mirror = lambda n: ids.get(str(ms[n].get("mirrorOf")), "none")
ws = {w["monitor"] for w in json.loads(wss) if w["id"] > 0}
expect = {
    "laptop": on(inner) and not on(ext) and ws <= {inner},
    "extend": on(inner) and on(ext) and mirror(ext) == "none" and mirror(inner) == "none",
    "mirror": on(inner) and on(ext) and mirror(ext) == inner and ws <= {inner},
    "external": on(ext) and not on(inner) and mirror(ext) == "none" and ws <= {ext},
}[mode]
scales = {n: "%g" % ms[n]["scale"] for n in (inner, ext)}
if not all(f"{n}={s}" in want.split() for n, s in scales.items()):
    expect = False
state = {n: (on(n), mirror(n), scales[n]) for n in (inner, ext)}
print("" if expect else f"state {state} workspaces on {sorted(ws)}")
PY
)"
        [ -z "$why" ] && return 0
        sleep 0.1
    done
    echo "FAIL $mode: $why"
    exit 1
}

nested_hyprctl dispatch 'hl.dsp.focus({ workspace = "5" })' > /dev/null
ws_move 5 "$ext" lua || { echo "FAIL setup: workspace 5 is not on $ext" ; exit 1; }
echo "internal $inner, external $ext ($OUT_FORM); scales $want_scales; workspaces $(ws_list)" >&2
for mode in laptop extend mirror external laptop extend; do
    menu "$mode" || { echo "FAIL $mode: the menu exited $?"; exit 1; }
    check "$mode"
    echo "ok $mode: $(ws_list)"
done
echo "PASS modes"
