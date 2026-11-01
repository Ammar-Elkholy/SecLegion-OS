#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Spike (G0 of the display menu, issue 14): which runtime form enables, mirrors, un-mirrors and
# positions a monitor in Lua mode, with no file written? In a NESTED Hyprland (catch-all rule scale
# 1.5, like the owner's `output = ""` rule) with a second output, each step sends one
#   hyprctl eval 'hl.monitor({ output = "N", <fields> })'
# and checks `monitors all -j`. Prints "SPIKE ok <form>" (exit 0) or "SPIKE fail <step>" (exit 1);
# exit 77 if no nested Hyprland or no second output. Diagnostics on stderr.
# Findings (Hyprland 0.56.2, 2026-10-31):
#   * the FIRST runtime rule for an output replaces the catch-all rule: fields left out take
#     Hyprland's defaults (mode preferred, position auto, scale AUTO - 2 for a 1080p headless, not
#     the catch-all's 1.5). So the menu always sends the output's current `mode` and `scale`.
#   * later runtime rules for the same output MERGE: a field left out keeps its value, so
#     `disabled = false` must be sent to enable (a rule without it keeps `disabled = true`), and
#     `mirror = ""` to stop mirroring (a rule without it keeps mirroring).
#   * a bad field is an error (`hyprctl eval` exit 7, "unknown field"); disabling every output
#     makes Hyprland add a FALLBACK monitor.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/display/lib.sh
. "$here/lib.sh"
trap nested_stop EXIT
extra="$NESTED_DIR/spike-monitor-apply.lua"
mkdir -p -- "$NESTED_DIR"
echo 'hl.monitor({ output = "", mode = "1280x720", position = "auto", scale = 1.5 })' > "$extra"
nested_start "$extra" || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
first="$(monitor_names)"
first="${first%% *}"
out_create || { echo "UNVERIFIED: no second output in the nested Hyprland" >&2; exit 77; }

# "<disabled> <mirrorOf name or none> <x> <y> <scale>" of one monitor, from `monitors all -j`
mon() {
    nested_hyprctl monitors all -j | python3 -c '
import json, sys
ms = json.load(sys.stdin)
ids = {str(m["id"]): m["name"] for m in ms}
m = next((m for m in ms if m["name"] == sys.argv[1]), None)
if m is None:
    print("absent")
else:
    mirror = ids.get(str(m.get("mirrorOf")), "none")
    print("disabled" if m.get("disabled") else "enabled", mirror, m["x"], m["y"], m["scale"])' "$1"
}

# step NAME FIELDS PYCOND: send the rule, wait until PYCOND (over d, mirror, x, y, scale) holds
step() {
    local name="$1" fields="$2" cond="$3" s=""
    reply="$(nested_hyprctl eval "hl.monitor({ output = \"$OUT_NAME\", $fields })" 2>&1)"
    for _ in $(seq 1 15); do
        s="$(mon "$OUT_NAME")"
        if python3 -c '
import sys
d, mirror, x, y, scale = sys.argv[1].split()
x, y, scale = int(x), int(y), float(scale)
sys.exit(0 if eval(sys.argv[2]) else 1)' "$s" "$cond" 2> /dev/null; then
            echo "$name: ok ($fields -> $s)" >&2
            return 0
        fi
        sleep 0.1
    done
    echo "$name: FAILED ($fields -> ${reply:-<no reply>}; state $s)" >&2
    echo "SPIKE fail $name"
    exit 1
}

echo "first $first, second $OUT_NAME ($OUT_FORM): $(mon "$OUT_NAME")" >&2
read -r _ _ _ _ cfg_scale <<< "$(mon "$OUT_NAME")"
mode="$(nested_hyprctl monitors all -j | python3 -c '
import json, sys
m = next(m for m in json.load(sys.stdin) if m["name"] == sys.argv[1])
print("%dx%d@%.2f" % (m["width"], m["height"], m["refreshRate"]))' "$OUT_NAME")"
nested_hyprctl eval "hl.monitor({ output = \"$OUT_NAME\", mirror = \"\" })" > /dev/null 2>&1
sleep 0.5
echo "first rule without scale: $(mon "$OUT_NAME") (catch-all scale $cfg_scale)" >&2
step disable  'disabled = true'                       'd == "disabled"'
step enable   "disabled = false, mode = \"$mode\", scale = $cfg_scale" \
    "d == \"enabled\" and scale == $cfg_scale"
step mirror   "disabled = false, mirror = \"$first\"" "d == \"enabled\" and mirror == \"$first\""
step unmirror 'disabled = false, mirror = ""'         'd == "enabled" and mirror == "none"'
step position 'position = "0x900"'                    'd == "enabled" and (x, y) == (0, 900)'
step auto     'position = "auto"'                     'd == "enabled" and (x, y) != (0, 900)'
echo "SPIKE ok eval hl.monitor({ output, disabled, mode, scale, mirror = \"<name>\"|\"\", position })"
