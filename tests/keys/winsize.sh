#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G3 (plan r12 K1): Super+Ctrl+1/2/3 float a tiled window and give it 50 / 70 / 90 % of the
# monitor, centred.   usage: winsize.sh [50|70|90]   (default 70)
# In a NESTED Hyprland with the committed host + keys files a kitty window is tiled; the
# bind is a Lua function (keys cannot be injected), so the test checks the bind is
# registered with Super+Ctrl and then calls the function it runs,
# require("seclegion-keys").winsize(PCT), in the compositor's own Lua state.
# Prints "size-ok center-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
pct="${1:-70}"
case "$pct" in 50 | 70 | 90) ;; *) echo "usage: winsize.sh 50|70|90" >&2; exit 2 ;; esac
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1

# the bind: Super+Ctrl (modmask 64+4), carried by ours
nested_hyprctl binds -j | python3 -c '
import json, sys
pct = sys.argv[1]
want = "seclegion-keys: window " + pct + " % of the monitor, centred"
hit = [b for b in json.load(sys.stdin) if b["modmask"] == 68 and b["description"] == want]
sys.exit(0 if len(hit) == 1 else "want one Super+Ctrl bind for " + pct + " %, found " + str(len(hit)))' "$pct" || exit 1

open_client || exit 1
nested_hyprctl dispatch 'hl.dsp.window.float({ action = "disable" })' > /dev/null   # make sure it is tiled
nested_hyprctl clients -j | python3 -c '
import json, sys
sys.exit(0 if not json.load(sys.stdin)[0]["floating"] else "client is floating before the call")' || exit 1

out="$(nested_hyprctl repl "require('seclegion-keys').winsize($pct)" 2>&1)"
case "$out" in *rror*) echo "winsize($pct): $out" >&2; exit 1 ;; esac
sleep 0.3

mon="$(nested_hyprctl monitors -j)"
nested_hyprctl clients -j | MON="$mon" python3 -c '
import json, os, sys
pct = int(sys.argv[1])
m = json.loads(os.environ["MON"])[0]
c = json.load(sys.stdin)[0]
if not c["floating"]:
    sys.exit("the window is still tiled")
if any(m["reserved"]):
    sys.exit("the nested monitor has reserved areas; this test compares with the whole monitor")
mw, mh = m["width"] / m["scale"], m["height"] / m["scale"]
w, h = round(mw * pct / 100), round(mh * pct / 100)
sw, sh = c["size"]
if abs(sw - w) > 1 or abs(sh - h) > 1:
    sys.exit("size %dx%d, want %dx%d (%d %% of %dx%d)" % (sw, sh, w, h, pct, mw, mh))
print("size-ok", end=" ")
cx, cy = c["at"][0] + sw / 2, c["at"][1] + sh / 2
if abs(cx - (m["x"] + mw / 2)) > 2 or abs(cy - (m["y"] + mh / 2)) > 2:
    sys.exit("centre (%s, %s), want (%s, %s)" % (cx, cy, m["x"] + mw / 2, m["y"] + mh / 2))
print("center-ok")' "$pct" || exit 1
