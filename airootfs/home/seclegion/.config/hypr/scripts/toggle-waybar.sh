#!/bin/bash
if systemctl --user is-active --quiet waybar; then
    systemctl --user stop waybar
elif pgrep -x "waybar" > /dev/null; then
    pkill -x "waybar"
else
    systemctl --user start waybar
fi
