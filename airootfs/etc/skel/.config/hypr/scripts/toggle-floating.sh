#!/bin/bash
win_info=$(hyprctl activewindow -j)
fullscreen_val=$(echo "$win_info" | jq -r '.fullscreen')
is_floating=$(echo "$win_info" | jq -r '.floating')

if [ "$fullscreen_val" != "0" ] && [ "$fullscreen_val" != "null" ]; then
    hyprctl dispatch 'hl.dsp.window.fullscreen()' 2>/dev/null
fi

hyprctl dispatch 'hl.dsp.window.float()' 2>/dev/null
hyprctl dispatch 'hl.dsp.window.center()' 2>/dev/null
