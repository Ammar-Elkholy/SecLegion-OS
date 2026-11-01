#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G6: what `seclegion-host apply keys` verify relies on, in a NESTED Hyprland.
#   1. `hyprctl reload` re-runs seclegion-keys.lua from disk (Hyprland builds a
#      new Lua state per reload, so no package.loaded clearing is needed).
#   2. A keys file that stops early (no Lua error) leaves configerrors empty but
#      loads none of its binds: only the bind count (every ^hl.bind( line live,
#      by its "seclegion-keys:" description) catches it.
#   3. A runtime error inside the file (hl.bnd) also leaves no bind live.
# Prints "broken-file-detected"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT

live() { nested_hyprctl binds -j | python3 -c 'import json,sys; print(sum(b["description"].startswith("seclegion-keys:") for b in json.load(sys.stdin)))'; }
want() { grep -c '^[[:space:]]*hl\.bind(' "$NESTED_DIR/seclegion-keys.lua"; }
reload() { nested_hyprctl reload > /dev/null && sleep 1; }

keys_start
ours_loaded || exit 1

sed -i '/code:19/d' "$NESTED_DIR/seclegion-keys.lua"
reload
[ "$(live)" = "$(want)" ] || { echo "reload did not re-run the edited file: $(live) live, file has $(want)" >&2; exit 1; }
echo reload-reruns-module

n="$(want)"
sed -i '1a do return end' "$NESTED_DIR/seclegion-keys.lua"
reload
e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "early return: configerrors not empty: $e" >&2; exit 1; }
[ "$(live)" = 0 ] || { echo "early return: $(live) binds live" >&2; exit 1; }
[ "$(live)" != "$n" ] || { echo "bind count check would pass" >&2; exit 1; }

sed -i -e '2d' -e 's/^\([[:space:]]*\)hl\.bind(/\1hl.bnd(/' "$NESTED_DIR/seclegion-keys.lua"
reload
[ "$(live)" = 0 ] || { echo "hl.bnd: $(live) binds live" >&2; exit 1; }
e="$(nested_hyprctl configerrors)"
echo "hl.bnd: configerrors ${e:+not }empty"
echo broken-file-detected
