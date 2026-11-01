#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G1 (plan r12 K1): the edge grab is set. In a NESTED Hyprland with seclegion-host.lua
# loaded, general:resize_on_border is true, general:extend_border_grab_area is 20 and
# general:hover_icon_on_border is true, and the config has no errors. The option names are
# the ones Hyprland 0.56.2 accepts (checked here: getoption answers "set: true" for each).
# Prints "border-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start

e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "configerrors: $e" >&2; exit 1; }

want() {   # OPTION VALUE
    local out
    out="$(nested_hyprctl getoption "general:$1" 2>&1)"
    printf '%s\n' "$out" | grep -qx "[a-z]*: $2" || { echo "general:$1 is not $2: $out" >&2; exit 1; }
    printf '%s\n' "$out" | grep -qx 'set: true' || { echo "general:$1 is not set by the config: $out" >&2; exit 1; }
}
want resize_on_border true
want extend_border_grab_area 20
want hover_icon_on_border true
echo border-ok
