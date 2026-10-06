#!/bin/bash

cd "$HOME/Pictures/Wallpapers" || exit

rm -f /tmp/wallpaper.txt

if command -v yazi >/dev/null 2>&1; then
    yazi --chooser-file /tmp/wallpaper.txt
else
    selected=$(ls -1 "$HOME/Pictures/Wallpapers" | rofi -dmenu -p "󰸉 Select Wallpaper")
    if [ -n "$selected" ]; then
        echo "$HOME/Pictures/Wallpapers/$selected" > /tmp/wallpaper.txt
    fi
fi

if [ -f /tmp/wallpaper.txt ]; then
    wallpaper=$(realpath "$(cat /tmp/wallpaper.txt)")

    pkill -x mpvpaper 2>/dev/null

    awww img "$wallpaper" \
    --transition-type wipe \
    --transition-angle 45 \
    --transition-duration 2.5 \
    --transition-fps 60 \
    --transition-bezier 0.65,0.05,0.36,1

    if command -v wallust >/dev/null 2>&1; then
        wallust run "$wallpaper"
    fi

    pkill -x swaync 2>/dev/null
    swaync &

    echo "$wallpaper" > ~/.cache/current_wallpaper
    echo "image" > ~/.cache/current_wallpaper_type
    cp "$wallpaper" ~/.cache/wallpaper_frame.png

    rm -f /tmp/wallpaper.txt
fi
