#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G3: run the on-click command of custom/wsN, taken verbatim from the committed
# desktop/waybar/config.jsonc, against a NESTED Hyprland (loaded with our
# desktop/hypr/seclegion-host.lua) and print the resulting active workspace.
#   bash tests/ws/click.sh 3      -> active=3
# Also checks scroll (e+1 / e-1) and seclegion-ws on the nested instance, to stderr.
# Exit 1 on failure, 77 if no nested Hyprland can start (UNVERIFIED).
# SL_WS_CONFIG overrides the config file (used to show the check failing).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
cfg="${SL_WS_CONFIG:-$repo/desktop/waybar/config.jsonc}"
n="${1:?usage: click.sh N}"
# shellcheck source=tests/ws/nested.sh
. "$here/nested.sh"
trap nested_stop EXIT

field() {   # MODULE KEY -> the string value from the jsonc (whole-line // comments stripped)
    python3 - "$cfg" "$1" "$2" <<'PY'
import json, sys
text = "\n".join(l for l in open(sys.argv[1]) if not l.lstrip().startswith("//"))
print(json.loads(text)[sys.argv[2]][sys.argv[3]])
PY
}
active() { nested_hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }
run_cmd() { HYPRLAND_INSTANCE_SIGNATURE="$NESTED_SIG" sh -c "$1" > /dev/null; }

click="$(field "custom/ws$n" on-click)" || exit 1
up="$(field "custom/ws$n" on-scroll-up)" || exit 1
down="$(field "custom/ws$n" on-scroll-down)" || exit 1

nested_start "$repo/desktop/hypr/seclegion-host.lua" || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
[ -z "$(nested_hyprctl configerrors)" ] || { echo "configerrors: $(nested_hyprctl configerrors)" >&2; exit 1; }

run_cmd "$click"
got="$(active)"
echo "active=$got"
[ "$got" = "$n" ] || exit 1

# scroll: next, then previous (workspaces 1-5 are persistent, so n+1 exists for n < 5)
if [ "$n" -lt 5 ]; then
    run_cmd "$down"
    [ "$(active)" = "$((n + 1))" ] || { echo "scroll-down from $n gave $(active)" >&2; exit 1; }
    run_cmd "$up"
    [ "$(active)" = "$n" ] || { echo "scroll-up gave $(active)" >&2; exit 1; }
    echo "ok: scroll down/up" >&2
fi

# the pills read the same instance: the clicked one is active, an absent one is hidden
export SL_HYPRCTL="env HYPRLAND_INSTANCE_SIGNATURE=$NESTED_SIG hyprctl" SL_WS_URGENT=/nonexistent
out="$("$repo/desktop/waybar/seclegion-ws" "$n")"
[[ "$out" == *'"class":"active"'* ]] || { echo "seclegion-ws $n: $out" >&2; exit 1; }
out="$("$repo/desktop/waybar/seclegion-ws" 15)"
[[ "$out" == *'"class":"hidden"'* ]] || { echo "seclegion-ws 15: $out" >&2; exit 1; }
echo "ok: seclegion-ws active/hidden; persistent rules loaded" >&2
