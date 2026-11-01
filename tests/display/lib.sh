#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Second-output helpers for the display tests, on top of tests/ws/nested.sh: every hyprctl call
# goes through nested_hyprctl (the nested instance's pinned signature, never the live session).
#
#   out_create            -> OUT_NAME (the new monitor), OUT_FORM (headless|wayland); 1 if neither works
#   ws_monitor N          -> the monitor name of workspace N ("" if it does not exist)
#   ws_list               -> "id@monitor ..." for every workspace
#   ws_move N MON [FORMS] -> 0 if workspace N ended up on MON; MOVE_FORM = the form that did it
#
# Move forms, in the order the spike tries them: lua (the one seclegion-displayd uses),
# lua-active (focus N, then move the active workspace), legacy (the hyprlang dispatcher).

# shellcheck source=tests/ws/nested.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../ws" && pwd)/nested.sh"

OUT_NAME="" OUT_FORM="" MOVE_FORM=""

monitor_names() {
    nested_hyprctl monitors -j | python3 -c '
import json, sys
print(*[m["name"] for m in json.load(sys.stdin)])'
}

out_create() {
    local before after form n
    before=" $(monitor_names) "
    for form in headless wayland; do
        nested_hyprctl output create "$form" > /dev/null 2>&1 || continue
        for _ in $(seq 1 25); do
            after="$(monitor_names)"
            for n in $after; do
                case "$before" in *" $n "*) ;; *) OUT_NAME="$n" OUT_FORM="$form"; return 0 ;; esac
            done
            sleep 0.2
        done
    done
    return 1
}

ws_monitor() {
    nested_hyprctl workspaces -j | python3 -c '
import json, sys
print(next((w["monitor"] for w in json.load(sys.stdin) if str(w["id"]) == sys.argv[1]), ""))' "$1"
}

ws_list() {
    nested_hyprctl workspaces -j | python3 -c '
import json, sys
ws = sorted(json.load(sys.stdin), key=lambda w: w["id"])
print(" ".join("%s@%s" % (w["id"], w["monitor"]) for w in ws))'
}

ws_move() {
    local n="$1" mon="$2" form
    for form in ${3:-lua lua-active legacy}; do
        case "$form" in
            lua)
                nested_hyprctl dispatch "hl.dsp.workspace.move({ workspace = \"$n\", monitor = \"$mon\" })" ;;
            lua-active)
                nested_hyprctl dispatch "hl.dsp.focus({ workspace = \"$n\" })"
                nested_hyprctl dispatch "hl.dsp.workspace.move({ monitor = \"$mon\" })" ;;
            legacy) nested_hyprctl dispatch "moveworkspacetomonitor $n $mon" ;;
        esac > /dev/null 2>&1
        for _ in 1 2 3 4 5; do
            [ "$(ws_monitor "$n")" = "$mon" ] && { MOVE_FORM="$form"; return 0; }
            sleep 0.1
        done
    done
    return 1
}
