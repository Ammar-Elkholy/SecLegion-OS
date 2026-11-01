#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Spike: can a NESTED Hyprland get a second output, and which dispatch moves a workspace onto it?
# Creates the output (headless, else wayland), moves workspace 7 to it, removes the output.
# Prints "SPIKE ok <create-form> <move-form>" or "SPIKE no-output" (exit 0 for both); exit 1 if
# the output exists but no move form works; exit 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/display/lib.sh
. "$here/lib.sh"
trap nested_stop EXIT
nested_start || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }

out_create || { echo "SPIKE no-output"; exit 0; }
nested_hyprctl dispatch 'hl.dsp.focus({ workspace = "7" })' > /dev/null
echo "before move: $(ws_list)" >&2
ws_move 7 "$OUT_NAME" || { echo "no move form put workspace 7 on $OUT_NAME: $(ws_list)" >&2; exit 1; }
echo "after move ($MOVE_FORM): $(ws_list)" >&2
nested_hyprctl output remove "$OUT_NAME" > /dev/null
sleep 0.5
echo "after remove: $(ws_list)" >&2
echo "SPIKE ok $OUT_FORM $MOVE_FORM"
