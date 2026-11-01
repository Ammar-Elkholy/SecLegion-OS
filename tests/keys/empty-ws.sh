#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G3: Super+. (code:60) focuses the first empty workspace. In a NESTED
# Hyprland with seclegion-host.lua + seclegion-keys.lua loaded, a window sits
# on workspace 1; running the bind's dispatcher (keys cannot be injected into
# the nested compositor) must land on the lowest workspace id with no windows.
# Prints "empty-ws-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1

open_client || exit 1
[ "$(active)" = 1 ] && [ "$(ws_of "$KEYS_CLIENT")" = 1 ] || { echo "client not on workspace 1" >&2; exit 1; }
press "SUPER + code:60"
got="$(active)"
[ "$got" = 2 ] || { echo "Super+. from a busy workspace 1 gave $got, want 2 (the first empty one)" >&2; exit 1; }
[ "$(ws_of "$KEYS_CLIENT")" = 1 ] || { echo "the window moved" >&2; exit 1; }
press "SUPER + code:60"
[ "$(active)" = 2 ] || { echo "Super+. on an empty workspace left it ($(active))" >&2; exit 1; }
echo empty-ws-ok
