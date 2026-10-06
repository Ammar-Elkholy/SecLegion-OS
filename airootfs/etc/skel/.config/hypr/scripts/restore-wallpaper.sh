#!/usr/bin/env bash
# ==============================================================================
# restore-wallpaper.sh — Restore active wallpaper on session login
# ==============================================================================

wallpaper=$(cat "$HOME/.cache/current_wallpaper" 2>/dev/null)
type=$(cat "$HOME/.cache/current_wallpaper_type" 2>/dev/null)

[[ -z "$wallpaper" || ! -f "$wallpaper" ]] && exit 0

if [[ "$type" == "video" ]]; then
    if command -v mpvpaper &>/dev/null; then
        pkill -x hyprpaper 2>/dev/null
        sleep 0.2
        nohup mpvpaper -o "no-audio loop hwdec=auto vo=gpu --profile=fast" "*" "$wallpaper" >/dev/null 2>&1 &
    elif [[ -f "$HOME/.cache/wallpaper_frame.png" ]]; then
        awww img "$HOME/.cache/wallpaper_frame.png" --transition-type none
    fi
elif [[ "$type" == "gif" ]]; then
    pkill -x mpvpaper 2>/dev/null
    awww img "$wallpaper" --transition-type none
else
    pkill -x mpvpaper 2>/dev/null
    awww img "$wallpaper" --transition-type none
fi
