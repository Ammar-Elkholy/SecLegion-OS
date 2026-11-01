#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Shared by the tests/keys/*.sh behaviour tests. Starts a NESTED Hyprland
# (tests/ws/nested.sh, never the live session) whose config dir holds the
# committed desktop/hypr/seclegion-host.lua and seclegion-keys.lua and whose
# config only does require("seclegion-host"): the same guarded
# pcall(require, "seclegion-keys") path the host uses.
#
# Keys cannot be injected into the nested compositor, so a test runs the
# dispatcher a bind would call: dsp_of "SUPER + code:60" prints the dispatcher
# expression of that hl.bind line, verbatim from the committed file.
KEYS_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_REPO="$(cd "$KEYS_HERE/../.." && pwd)"
KEYS_FILE="$KEYS_REPO/desktop/hypr/seclegion-keys.lua"
KEYS_CLIENT="" KEYS_CLIENT_PID=""
# shellcheck source=tests/ws/nested.sh
. "$KEYS_REPO/tests/ws/nested.sh"

keys_cleanup() {
    nested_stop
    # the test client dies with its compositor; make sure of it, by pid
    if [ -n "$KEYS_CLIENT_PID" ] && kill -0 "$KEYS_CLIENT_PID" 2>/dev/null; then kill -TERM "$KEYS_CLIENT_PID" 2>/dev/null || true; fi
}

keys_start() {   # [none] -> nested Hyprland with host + keys loaded (none: no keys file); exit 77 if it cannot start
    mkdir -p -- "$NESTED_DIR"
    cp -- "$KEYS_REPO/desktop/hypr/seclegion-host.lua" "$NESTED_DIR/seclegion-host.lua"
    if [ "${1:-}" = none ]; then rm -f -- "$NESTED_DIR/seclegion-keys.lua"
    else cp -- "$KEYS_FILE" "$NESTED_DIR/seclegion-keys.lua"; fi
    echo 'require("seclegion-host")' > "$NESTED_DIR/extra.lua"
    nested_start "$NESTED_DIR/extra.lua" || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
}

dsp_of() {   # KEYS -> the dispatcher expression bound to KEYS in the keys file
    python3 - "$KEYS_FILE" "$1" <<'PY'
import re, sys
path, want = sys.argv[1:3]
pat = re.compile(r'^\s*hl\.bind\("([^"]+)",\s*(hl\.dsp\..*\)),\s*\{[^{}]*description = "[^"]*" \}\)\s*$')
hits = [m.group(2) for m in map(pat.match, open(path)) if m and m.group(1) == want]
if len(hits) != 1:
    sys.exit(f"dsp_of: {len(hits)} binds for {want!r} in {path}")
print(hits[0])
PY
}

press() {   # KEYS -> run its dispatcher in the nested instance; must answer ok
    local d out
    d="$(dsp_of "$1")" || exit 1
    out="$(nested_hyprctl dispatch "$d" 2>&1)"
    [ "$out" = ok ] || { echo "dispatch $d -> $out" >&2; exit 1; }
}

active() { nested_hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }

ours_loaded() {   # every hl.bind of the keys file is live (by description), and configerrors is empty
    local want got e
    e="$(nested_hyprctl configerrors)"
    [ -z "${e//[[:space:]]/}" ] || { echo "configerrors: $e" >&2; return 1; }
    want="$(grep -c '^[[:space:]]*hl\.bind(' "$KEYS_FILE")"
    got="$(nested_hyprctl binds -j | python3 -c 'import json,sys; print(sum(b["description"].startswith("seclegion-keys:") for b in json.load(sys.stdin)))')"
    [ "$got" = "$want" ] || { echo "want $want seclegion-keys binds, nested has $got" >&2; return 1; }
}

open_client() {   # one kitty window on the active workspace -> KEYS_CLIENT (address), KEYS_CLIENT_PID
    local i addr=""
    nested_hyprctl dispatch 'hl.dsp.exec_cmd("kitty --config NONE sh -c \"sleep 120\"")' > /dev/null
    for i in $(seq 1 75); do
        addr="$(nested_hyprctl clients -j | python3 -c 'import json,sys; c=json.load(sys.stdin); print(c[0]["address"] if c else "")')"
        [ -z "$addr" ] || break
        sleep 0.2
    done
    [ -n "$addr" ] || { echo "no client window appeared" >&2; return 1; }
    KEYS_CLIENT_PID="$(nested_hyprctl clients -j | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["pid"])')"
    KEYS_CLIENT="$addr"
}

ws_of() {   # ADDRESS -> workspace id of that window
    nested_hyprctl clients -j | python3 -c '
import json, sys
print(next(c["workspace"]["id"] for c in json.load(sys.stdin) if c["address"] == sys.argv[1]))' "$1"
}
