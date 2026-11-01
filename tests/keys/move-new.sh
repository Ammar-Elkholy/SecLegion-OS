#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G4: Super+Shift+. moves the focused window to the first empty workspace and
# follows it; Super+Alt+. does the same silently (focus stays). Runs each
# bind's dispatcher in a NESTED Hyprland (keys cannot be injected into it).
# Prints "move-new-ok"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/keys/lib.sh
. "$here/lib.sh"
trap keys_cleanup EXIT
keys_start
ours_loaded || exit 1

open_client || exit 1
[ "$(ws_of "$KEYS_CLIENT")" = 1 ] || { echo "client not on workspace 1" >&2; exit 1; }
press "SUPER + SHIFT + code:60"
[ "$(ws_of "$KEYS_CLIENT")" = 2 ] || { echo "Super+Shift+. put the window on $(ws_of "$KEYS_CLIENT"), want 2" >&2; exit 1; }
[ "$(active)" = 2 ] || { echo "Super+Shift+. did not follow (active $(active))" >&2; exit 1; }

# workspace 1 is empty now: the silent move sends the window there and focus stays on 2
press "SUPER + ALT + code:60"
[ "$(ws_of "$KEYS_CLIENT")" = 1 ] || { echo "Super+Alt+. put the window on $(ws_of "$KEYS_CLIENT"), want 1" >&2; exit 1; }
[ "$(active)" = 2 ] || { echo "Super+Alt+. followed the window (active $(active)), want silent" >&2; exit 1; }
echo move-new-ok
