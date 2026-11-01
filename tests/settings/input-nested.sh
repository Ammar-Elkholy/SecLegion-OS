#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Plan r12 S2: a NESTED Hyprland with seclegion-host.lua loads ~/.config/seclegion/input.lua,
# which the Settings backend wrote into a temp HOME, and the options carry its values:
# input:repeat_rate, input:repeat_delay and the touchpad tap, natural scroll and dwt options.
# Negative: a broken input.lua leaves the keys loaded. Never touches the live session
# (tests/ws/nested.sh). Prints "input-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$repo/tests/keys/lib.sh"
mkdir -p -- "$repo/.build"
fakehome="$(mktemp -d "$repo/.build/input-home.XXXXXX")"
trap 'keys_cleanup; rm -rf -- "$fakehome"' EXIT

set_row() {   # ID VALUE: the real backend writes the file, into the fake home
    SL_HOME="$fakehome" HOME="$fakehome" python3 -I "$repo/tools/seclegion-set" set "$1" "$2" > /dev/null \
        || { echo "set $1 $2 failed" >&2; exit 1; }
}
set_row input.repeat_rate 47
set_row input.repeat_delay 333
set_row input.tap_to_click off
set_row input.natural_scroll on
set_row input.disable_while_typing off
[ -f "$fakehome/.config/seclegion/input.lua" ] || { echo "no input.lua written" >&2; exit 1; }

export HOME="$fakehome"
keys_start
e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "configerrors: $e" >&2; exit 1; }
want() {   # OPTION VALUE
    local out
    out="$(nested_hyprctl getoption "input:$1" 2>&1)"
    printf '%s\n' "$out" | grep -qx "[a-z]*: $2" || { echo "input:$1 is not $2: $out" >&2; exit 1; }
}
want repeat_rate 47
want repeat_delay 333
want touchpad:natural_scroll true
want touchpad:tap-to-click false
want touchpad:disable_while_typing false
ours_loaded || exit 1
nested_stop

# negative: a broken file must not take the host overlay (or the keys) down
printf 'hl.config({ input = {\n' > "$fakehome/.config/seclegion/input.lua"
keys_start
ours_loaded || { echo "a broken input.lua broke the host overlay" >&2; exit 1; }
echo input-ok
