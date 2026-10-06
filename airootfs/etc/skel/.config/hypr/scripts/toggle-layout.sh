#!/bin/bash

# Switch layout on all keyboards
hyprctl switchxkblayout all next

# Query the new active layout
layout=$(hyprctl devices -j | jq -r '.keyboards[] | select(.main==true) | .active_keymap')

if [[ "$layout" =~ [Aa]rabic ]]; then
    notify-send -a "Keyboard" -r 9991 -u low -t 1200 "  Keyboard Layout" "<b>العربية (Arabic)</b>"
else
    notify-send -a "Keyboard" -r 9991 -u low -t 1200 "  Keyboard Layout" "<b>English (US)</b>"
fi
