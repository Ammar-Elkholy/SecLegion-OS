#!/usr/bin/env bash
# Move focused window from special:magic back to the active workspace of the current monitor
active_ws=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .activeWorkspace.name' 2>/dev/null)
if [[ -z "$active_ws" || "$active_ws" == "null" ]]; then
    active_ws="1"
fi

hyprctl dispatch "hl.dsp.window.move({ workspace = '$active_ws' })"

if command -v dunstify &>/dev/null; then
    dunstify -a "AE_ARCH" -r 9993 -u low -t 1500 "📤 Window Restored" "Returned to Workspace <b>$active_ws</b>"
elif command -v notify-send &>/dev/null; then
    notify-send -a "AE_ARCH" -r 9993 -u low -t 1500 "📤 Window Restored" "Returned to Workspace <b>$active_ws</b>"
fi
