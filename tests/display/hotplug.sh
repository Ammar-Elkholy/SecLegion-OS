#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Unplug test in a NESTED Hyprland (loaded with desktop/hypr/seclegion-host.lua): a second output
# carries workspace 7 (one kitty window on it, so it is not destroyed as empty); the output is
# removed; workspace 7 must then be on the remaining monitor.
#   bash tests/display/hotplug.sh                  # with desktop/display/seclegion-displayd running
#   SL_NO_DAEMON=1 bash tests/display/hotplug.sh   # without it (the repro)
# Prints every workspace's monitor, then "PASS ws7-on-remaining" (exit 0) or "FAIL ws7-on-removed" /
# "FAIL ws7-<monitor or missing>" (exit 1). Exit 77 if no nested Hyprland or no second output.
# Finding (Hyprland 0.56.2, 2026-10-30): it PASSES without the daemon. Hyprland moves the removed
# output's workspaces itself (events: moveworkspace(v2) to the remaining monitor, then
# monitorremoved(v2)), for both headless and wayland outputs. The ghost case (a hybrid-GPU HDMI that
# Hyprland keeps after its connector says disconnected) cannot be made here; seclegion-displayd
# handles it (tests/display/test_displayd.py), and this test checks it leaves the normal path alone.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
# shellcheck source=tests/display/lib.sh
. "$here/lib.sh"
CLIENT_PID="" DAEMON_PID=""

cleanup() {
    if [ -n "$DAEMON_PID" ]; then kill -TERM "$DAEMON_PID" 2>/dev/null; wait "$DAEMON_PID" 2>/dev/null; fi
    nested_stop
    # the client dies with its compositor; make sure of it, by pid
    if [ -n "$CLIENT_PID" ] && kill -0 "$CLIENT_PID" 2>/dev/null; then
        kill -TERM "$CLIENT_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

nested_start "$repo/desktop/hypr/seclegion-host.lua" \
    || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
remaining="$(monitor_names)"
out_create || { echo "UNVERIFIED: no second output in the nested Hyprland" >&2; exit 77; }

nested_hyprctl dispatch 'hl.dsp.focus({ workspace = "7" })' > /dev/null
nested_hyprctl dispatch 'hl.dsp.exec_cmd("kitty --config NONE sh -c \"sleep 120\"")' > /dev/null
for _ in $(seq 1 75); do
    CLIENT_PID="$(nested_hyprctl clients -j | python3 -c '
import json, sys
print(next((c["pid"] for c in json.load(sys.stdin) if c["workspace"]["id"] == 7), ""))')"
    [ -z "$CLIENT_PID" ] || break
    sleep 0.2
done
[ -n "$CLIENT_PID" ] || { echo "no client window appeared on workspace 7" >&2; exit 1; }
ws_move 7 "$OUT_NAME" lua || { echo "workspace 7 did not move to $OUT_NAME: $(ws_list)" >&2; exit 1; }
echo "before remove: $(ws_list)"

daemon="$repo/desktop/display/seclegion-displayd"
if [ "${SL_NO_DAEMON:-}" != 1 ] && [ ! -e "$daemon" ]; then
    echo "daemon: absent ($daemon), running without it"
elif [ "${SL_NO_DAEMON:-}" != 1 ]; then
    log="$NESTED_DIR/displayd.log"
    HYPRLAND_INSTANCE_SIGNATURE="$NESTED_SIG" \
        SL_HYPRCTL="env HYPRLAND_INSTANCE_SIGNATURE=$NESTED_SIG hyprctl" \
        SL_SOCKET2="$XDG_RUNTIME_DIR/hypr/$NESTED_SIG/.socket2.sock" \
        SL_AWWW=true \
        python3 "$daemon" > "$log" 2>&1 &
    DAEMON_PID=$!
    for _ in $(seq 1 50); do grep -q 'listening' "$log" 2>/dev/null && break; sleep 0.1; done
    grep -q 'listening' "$log" || { echo "seclegion-displayd did not connect:" >&2; cat "$log" >&2; exit 1; }
fi

nested_hyprctl output remove "$OUT_NAME" > /dev/null
got=""
for _ in $(seq 1 30); do   # up to 3 s for the move
    got="$(ws_monitor 7)"
    [ "$got" = "$remaining" ] && break
    sleep 0.1
done
echo "after remove ($OUT_NAME gone, $remaining remains):"
nested_hyprctl workspaces -j | python3 -c '
import json, sys
for w in sorted(json.load(sys.stdin), key=lambda w: w["id"]):
    print("  workspace %s monitor=%s monitorID=%s windows=%s"
          % (w["id"], w["monitor"], w["monitorID"], w["windows"]))'
[ -z "$DAEMON_PID" ] || sed 's/^/  displayd: /' "$NESTED_DIR/displayd.log"

if [ "$got" = "$remaining" ]; then echo "PASS ws7-on-remaining"; exit 0; fi
if [ "$got" = "$OUT_NAME" ]; then echo "FAIL ws7-on-removed"; else echo "FAIL ws7-${got:-missing}"; fi
exit 1
