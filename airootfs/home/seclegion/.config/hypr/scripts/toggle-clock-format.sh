#!/usr/bin/env bash
# SecLegion OS - Toggle Waybar Clock Format (12-hour AM/PM vs 24-hour)
CONFIG="$HOME/.config/waybar/config.jsonc"
[ -f "$CONFIG" ] || exit 0

if grep -q "%H:%M" "$CONFIG"; then
    sed -i 's/%H:%M/%I:%M %p/g' "$CONFIG"
    MODE="12-Hour (AM/PM)"
else
    sed -i 's/%I:%M %p/%H:%M/g' "$CONFIG"
    MODE="24-Hour"
fi

# Reload Waybar
pkill -SIGUSR2 waybar 2>/dev/null || (pkill waybar && hyprctl dispatch exec waybar >/dev/null 2>&1 &)

if command -v notify-send >/dev/null 2>&1; then
    notify-send -a "SecLegion OS" "Clock Format Toggled" "Active Format: $MODE" -i preferences-system-time
fi
