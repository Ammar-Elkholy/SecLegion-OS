#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G1: in a NESTED Hyprland (Lua config), the legacy dispatch string that
# waybar 0.15.0 sends ("workspace N") is rejected, and the Lua form works.
# Prints "lua-rejects-legacy" on success; exit 1 otherwise; exit 77 if no
# nested Hyprland can start (UNVERIFIED).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/ws/nested.sh
. "$here/nested.sh"
trap nested_stop EXIT
nested_start || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }

legacy="$(nested_hyprctl dispatch 'workspace 2' 2>&1)"
lua="$(nested_hyprctl dispatch 'hl.dsp.focus({ workspace = "2" })' 2>&1)"
active="$(nested_hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
if [[ "$legacy" == *"error"* ]] && [ "$lua" = ok ] && [ "$active" = 2 ]; then
    echo lua-rejects-legacy
else
    echo "legacy='$legacy' lua='$lua' active=$active" >&2
    exit 1
fi
