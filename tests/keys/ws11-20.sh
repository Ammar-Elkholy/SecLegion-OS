#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G5: Super+Alt+1..0 (code:10..19) focus workspaces 11..20 and
# Super+Alt+Shift+1..0 move the focused window there; Super+Ctrl+Right/Left
# step to the next/previous workspace. Runs each bind's dispatcher in a NESTED
# Hyprland (keys cannot be injected into it).
# Prints "ws11-20-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1

# workspaces 1-5 are persistent (seclegion-host.lua): from 1, next is 2 and back is 1
press "SUPER + CONTROL + Right"
[ "$(active)" = 2 ] || { echo "Super+Ctrl+Right from 1 gave $(active)" >&2; exit 1; }
press "SUPER + CONTROL + Left"
[ "$(active)" = 1 ] || { echo "Super+Ctrl+Left from 2 gave $(active)" >&2; exit 1; }

for n in 1 2 3 4 5 6 7 8 9 10; do
    press "SUPER + ALT + code:$((n + 9))"
    [ "$(active)" = $((n + 10)) ] || { echo "Super+Alt+code:$((n + 9)) gave $(active), want $((n + 10))" >&2; exit 1; }
done

nested_hyprctl dispatch 'hl.dsp.focus({ workspace = 1 })' > /dev/null
open_client || exit 1
for n in 1 2 3 4 5 6 7 8 9 10; do
    press "SUPER + ALT + SHIFT + code:$((n + 9))"
    [ "$(ws_of "$KEYS_CLIENT")" = $((n + 10)) ] \
        || { echo "Super+Alt+Shift+code:$((n + 9)) put the window on $(ws_of "$KEYS_CLIENT"), want $((n + 10))" >&2; exit 1; }
done
echo ws11-20-ok
