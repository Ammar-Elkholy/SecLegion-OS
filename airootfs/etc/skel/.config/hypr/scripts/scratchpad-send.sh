#!/usr/bin/env bash
# Move focused window into special:magic (scratchpad)
hyprctl dispatch "hl.dsp.window.move({ workspace = 'special:magic' })"

if command -v dunstify &>/dev/null; then
    dunstify -a "AE_ARCH" -r 9994 -u low -t 1500 "📥 Sent to Scratchpad" "Press <b>Super + S</b> to view, <b>Super + Z</b> to return"
elif command -v notify-send &>/dev/null; then
    notify-send -a "AE_ARCH" -r 9994 -u low -t 1500 "📥 Sent to Scratchpad" "Press <b>Super + S</b> to view, <b>Super + Z</b> to return"
fi
