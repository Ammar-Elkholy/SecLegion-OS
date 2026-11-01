#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G2 (plan r12 K1): Super+Alt+R enters the `resize` submap, its keys resize the window,
# and Return / Escape leave. Run in a NESTED Hyprland (tests/ws/nested.sh); keys cannot be
# injected there, so each step runs the dispatcher the bind calls (lib.sh press/dsp_of).
#
# Hyprland 0.56.2 Lua facts this relies on, checked in the nested compositor:
#   * submap API: hl.define_submap("name", function() hl.bind(...) end) defines it,
#     hl.dsp.submap("name") enters it, hl.dsp.submap("reset") leaves it,
#     hl.get_current_submap() reads it (an empty string outside a submap).
#     `binds -j` lists a submap's binds with "submap": "name".
#   * resize args: hl.dsp.window.resize({ x = dx, y = dy, relative = true }) changes the
#     active window by dx, dy (a floating window keeps its centre, so it moves by half);
#     resize({ x = w, y = h }) sets an absolute size; hl.dsp.window.center() centres a
#     floating window. Both warn and do nothing on a maximised window.
#   * monitor size: hl.get_active_monitor() has width, height, scale, x, y, reserved.
#   * border options: general:resize_on_border, general:extend_border_grab_area and
#     general:hover_icon_on_border all exist (tests/keys/border-opt.sh).
# Prints "submap-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1

submap_now() { nested_hyprctl repl 'return "[" .. hl.get_current_submap() .. "]"' 2>&1; }
geom() {   # -> "W H X Y FLOATING" of the client
    nested_hyprctl clients -j | python3 -c '
import json, sys
c = json.load(sys.stdin)[0]
print(c["size"][0], c["size"][1], c["at"][0], c["at"][1], c["floating"])'
}
expect() {   # LABEL WANT_W WANT_H  (after the last step; tolerance 1 px)
    local w h
    read -r w h _ < <(geom)
    [ "$((w - $2))" -ge -1 ] && [ "$((w - $2))" -le 1 ] && [ "$((h - $3))" -ge -1 ] && [ "$((h - $3))" -le 1 ] \
        || { echo "$1: size ${w}x${h}, want $2x$3" >&2; exit 1; }
}

open_client || exit 1
# test setup, not a bind: un-maximise the client and give it a known floating size
nested_hyprctl dispatch 'hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })' > /dev/null

[ "$(submap_now)" = "[]" ] || { echo "not outside a submap at the start: $(submap_now)" >&2; exit 1; }
press "SUPER + ALT + R"
[ "$(submap_now)" = "[resize]" ] || { echo "Super+Alt+R did not enter resize: $(submap_now)" >&2; exit 1; }

press "f"   # float it
read -r _ _ _ _ fl < <(geom)
[ "$fl" = True ] || { echo "F did not float the window" >&2; exit 1; }
nested_hyprctl dispatch 'hl.dsp.window.resize({ x = 400, y = 300 })' > /dev/null
press "c"
expect "start" 400 300

press "right";        expect "right" 440 300
press "l";            expect "l" 480 300
press "left";         expect "left" 440 300
press "h";            expect "h" 400 300
press "down";         expect "down" 400 340
press "j";            expect "j" 400 380
press "up";           expect "up" 400 340
press "k";            expect "k" 400 300
press "SHIFT + right"; expect "shift+right" 410 300
press "SHIFT + left";  expect "shift+left" 400 300
press "SHIFT + down";  expect "shift+down" 400 310
press "SHIFT + up";    expect "shift+up" 400 300
press "CTRL + right";  expect "ctrl+right" 600 300
press "CTRL + left";   expect "ctrl+left" 400 300
press "CTRL + down";   expect "ctrl+down" 400 500
press "CTRL + up";     expect "ctrl+up" 400 300
press "equal";         expect "equal" 440 340
press "minus";         expect "minus" 400 300

# C centres: move it off-centre first (setup), then the bind brings it back
nested_hyprctl dispatch 'hl.dsp.window.move({ x = 5, y = 7 })' > /dev/null
press "c"
mon="$(nested_hyprctl monitors -j)"
read -r w h x y _ < <(geom)
MON="$mon" python3 -c '
import os, json, sys
m = json.loads(os.environ["MON"])[0]
w, h, x, y = map(int, sys.argv[1:5])
cx, cy = x + w / 2, y + h / 2
sys.exit(0 if abs(cx - (m["x"] + m["width"] / 2)) <= 2 and abs(cy - (m["y"] + m["height"] / 2)) <= 2 else "C did not centre: " + str((cx, cy)))' "$w" "$h" "$x" "$y" || exit 1

press "Return"
[ "$(submap_now)" = "[]" ] || { echo "Return did not leave the submap: $(submap_now)" >&2; exit 1; }
press "SUPER + ALT + R"
[ "$(submap_now)" = "[resize]" ] || { echo "re-enter failed: $(submap_now)" >&2; exit 1; }
press "Escape"
[ "$(submap_now)" = "[]" ] || { echo "Escape did not leave the submap: $(submap_now)" >&2; exit 1; }
echo submap-ok
