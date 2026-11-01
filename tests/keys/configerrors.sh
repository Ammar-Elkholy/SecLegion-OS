#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G6: a NESTED Hyprland that loads seclegion-host.lua, which pulls in
# seclegion-keys.lua through its guarded require, has no config errors and
# every seclegion-keys bind live. Then the same without seclegion-keys.lua
# (border applied, keys not): still no config errors, and no seclegion bind.
# Prints "configerrors-empty"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1
nested_stop

keys_start none
e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "without seclegion-keys.lua: configerrors: $e" >&2; exit 1; }
n="$(nested_hyprctl binds -j | python3 -c 'import json,sys; print(sum(b["description"].startswith("seclegion-keys:") for b in json.load(sys.stdin)))')"
[ "$n" = 0 ] || { echo "without seclegion-keys.lua: $n seclegion binds still live" >&2; exit 1; }
grep -q 'seclegion-keys not loaded' "$XDG_RUNTIME_DIR/hypr/$NESTED_SIG/hyprland.log" \
    || { echo "the guarded require logged nothing" >&2; exit 1; }
echo configerrors-empty
