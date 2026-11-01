#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Spike: which Lua-mode hyprctl form disables a monitor at runtime? (seclegion-displayd step 2)
# In a NESTED Hyprland: create a second output, try each form, and check `monitors all` for it.
# Prints "SPIKE ok <form>" or "SPIKE none" (exit 0 for both); exit 77 if no nested Hyprland or no
# second output. Diagnostics (re-enable, does the disable outlive a remove + re-create) on stderr.
#   eval     hyprctl eval 'hl.monitor({ output = "N", disabled = true })'
#   dispatch hyprctl dispatch 'hl.monitor({ output = "N", disabled = true })'
#   keyword  hyprctl keyword monitor N,disable   (hyprlang)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/display/lib.sh
. "$here/lib.sh"
trap nested_stop EXIT
nested_start || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
out_create || { echo "UNVERIFIED: no second output in the nested Hyprland" >&2; exit 77; }

# "enabled" | "disabled" | "absent", from `monitors all`
mon_state() {
    nested_hyprctl monitors all -j | python3 -c '
import json, sys
m = next((m for m in json.load(sys.stdin) if m["name"] == sys.argv[1]), None)
print("absent" if m is None else ("disabled" if m.get("disabled") else "enabled"))' "$1"
}

mon_set() {   # form name on|off
    local form="$1" n="$2" off="true" kw="disable"
    [ "$3" = off ] || { off="false"; kw="preferred,auto,1"; }
    case "$form" in
        eval) nested_hyprctl eval "hl.monitor({ output = \"$n\", disabled = $off })" ;;
        dispatch) nested_hyprctl dispatch "hl.monitor({ output = \"$n\", disabled = $off })" ;;
        keyword) nested_hyprctl keyword monitor "$n,$kw" ;;
    esac
}

wait_state() {   # name want
    local s=""
    for _ in $(seq 1 10); do
        s="$(mon_state "$1")"
        [ "$s" = "$2" ] && return 0
        sleep 0.1
    done
    echo "  state of $1: $s" >&2
    return 1
}

echo "output $OUT_NAME ($OUT_FORM): $(mon_state "$OUT_NAME")" >&2
found=""
for form in eval dispatch keyword; do
    reply="$(mon_set "$form" "$OUT_NAME" off 2>&1)"
    echo "form $form -> ${reply:-<no reply>}" >&2
    if wait_state "$OUT_NAME" disabled || [ "$(mon_state "$OUT_NAME")" = absent ]; then
        found="$form"
        break
    fi
done
[ -n "$found" ] || { echo "SPIKE none"; exit 0; }

echo "workspaces after disable: $(ws_list)" >&2
reply="$(mon_set "$found" "$OUT_NAME" on 2>&1)"
if wait_state "$OUT_NAME" enabled; then echo "re-enable ($found): ok" >&2
else echo "re-enable ($found): FAILED (${reply:-<no reply>})" >&2; fi

# Does the disable outlive the output? Disable, remove, re-create under the same name.
mon_set "$found" "$OUT_NAME" off > /dev/null 2>&1
nested_hyprctl output remove "$OUT_NAME" > /dev/null 2>&1
sleep 0.3
if nested_hyprctl output create "$OUT_FORM" "$OUT_NAME" > /dev/null 2>&1 && sleep 0.5 \
    && [ "$(mon_state "$OUT_NAME")" != absent ]; then
    echo "re-created $OUT_NAME after a disable: $(mon_state "$OUT_NAME")" >&2
else
    echo "could not re-create $OUT_NAME under the same name (persistence not measured)" >&2
fi
echo "SPIKE ok $found"
