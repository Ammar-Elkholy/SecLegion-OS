#!/usr/bin/env bash
# ==============================================================================
# live-wallpaper-yazi.sh — AE_ARCH Live / Video Wallpaper Engine
# Supports GIF, WebP, MP4, WebM, MKV
# Uses mpvpaper if present; otherwise seamlessly falls back to awww + ffmpeg
# ==============================================================================

WALL_DIR="$HOME/Videos/LiveWallpapers"
mkdir -p "$WALL_DIR"
mkdir -p "$HOME/.cache/live_wallpapers"
cd "$WALL_DIR" || exit 1

# Check if directory has any wallpapers
count=$(find "$WALL_DIR" -maxdepth 1 -type f \( -name "*.gif" -o -name "*.webp" -o -name "*.mp4" -o -name "*.webm" -o -name "*.mkv" \) 2>/dev/null | wc -l)
if [[ "$count" -eq 0 ]]; then
    if command -v notify-send &>/dev/null; then
        notify-send -a "AE_ARCH Wallpaper" -r 9995 -u normal -t 4000 \
            "󰸉 No Live Wallpapers Found" \
            "Place your .mp4, .webm, or .gif files in <b>~/Videos/LiveWallpapers/</b>"
    fi
fi

rm -f /tmp/wallpaper.txt

# File picker: Yazi if in terminal, or Rofi picker fallback
if command -v yazi >/dev/null 2>&1 && [[ -t 0 ]]; then
    yazi --chooser-file /tmp/wallpaper.txt "$WALL_DIR"
else
    # GUI / Rofi picker fallback
    selected=$(find "$WALL_DIR" -maxdepth 1 -type f \( -name "*.gif" -o -name "*.webp" -o -name "*.mp4" -o -name "*.webm" -o -name "*.mkv" -o -name "*.png" -o -name "*.jpg" \) -exec basename {} \; | rofi -dmenu -p "󰸉 Select Live Wallpaper")
    if [[ -n "$selected" ]]; then
        echo "$WALL_DIR/$selected" > /tmp/wallpaper.txt
    fi
fi

if [[ -f /tmp/wallpaper.txt && -s /tmp/wallpaper.txt ]]; then
    wallpaper=$(realpath "$(cat /tmp/wallpaper.txt)")
    rm -f /tmp/wallpaper.txt

    ext="${wallpaper##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    wallpaper_frame="$HOME/.cache/wallpaper_frame.png"
    cached_live="$HOME/.cache/live_wallpapers/active_loop.gif"

    # Stop any conflicting wallpaper players
    pkill -x mpvpaper 2>/dev/null
    pkill -x hyprpaper 2>/dev/null

    if [[ "$ext" == "gif" || "$ext" == "webp" ]]; then
        # Native animated image support via awww
        awww img "$wallpaper" \
            --transition-type wipe \
            --transition-angle 45 \
            --transition-duration 2.0 \
            --transition-fps 60 \
            --transition-bezier 0.65,0.05,0.36,1

        # Extract frame for color generation
        if command -v ffmpeg &>/dev/null; then
            ffmpeg -y -i "$wallpaper" -vframes 1 "$wallpaper_frame" >/dev/null 2>&1 || cp "$wallpaper" "$wallpaper_frame"
        fi

        echo "$wallpaper" > "$HOME/.cache/current_wallpaper"
        echo "gif" > "$HOME/.cache/current_wallpaper_type"

        notify-send -a "AE_ARCH" -r 9995 -u low -t 2000 "󰸉 Live Wallpaper Active" "Playing animated loop via awww engine"

    elif [[ "$ext" == "mp4" || "$ext" == "webm" || "$ext" == "mkv" ]]; then
        # Video wallpaper
        if command -v ffmpeg &>/dev/null; then
            ffmpeg -y -i "$wallpaper" -vframes 1 "$wallpaper_frame" >/dev/null 2>&1
        fi

        if command -v mpvpaper &>/dev/null; then
            # Show smooth transition frame first
            if [[ -f "$wallpaper_frame" ]]; then
                awww img "$wallpaper_frame" --transition-type wipe --transition-duration 1.5
                sleep 1.6
            fi
            nohup mpvpaper -o "no-audio loop hwdec=auto vo=gpu --profile=fast" "*" "$wallpaper" >/dev/null 2>&1 &
            disown
            echo "$wallpaper" > "$HOME/.cache/current_wallpaper"
            echo "video" > "$HOME/.cache/current_wallpaper_type"
            notify-send -a "AE_ARCH" -r 9995 -u low -t 2000 "󰸉 Video Wallpaper Set" "Playing with hardware acceleration via mpvpaper"
        else
            # mpvpaper not installed: convert loop with ffmpeg into awww
            notify-send -a "AE_ARCH" -r 9995 -u normal -t 3000 "󰸉 Processing Video" "Converting video loop for awww engine..."
            ffmpeg -y -t 6 -i "$wallpaper" -vf "fps=30,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" "$cached_live" >/dev/null 2>&1
            if [[ -f "$cached_live" ]]; then
                awww img "$cached_live" --transition-type wipe --transition-duration 2.0
                echo "$cached_live" > "$HOME/.cache/current_wallpaper"
                echo "gif" > "$HOME/.cache/current_wallpaper_type"
                notify-send -a "AE_ARCH" -r 9995 -u normal -t 4000 "󰸉 Live Wallpaper Active" "Playing via awww. For native 60fps video decoding: yay -S mpvpaper"
            elif [[ -f "$wallpaper_frame" ]]; then
                awww img "$wallpaper_frame" --transition-type wipe --transition-duration 1.5
                notify-send -a "AE_ARCH" -r 9995 -u critical -t 5000 "󰸉 mpvpaper Needed" "To play full .mp4 videos directly, install: <b>yay -S mpvpaper</b>"
            fi
        fi
    else
        # Static image fallback
        awww img "$wallpaper" --transition-type wipe --transition-duration 2.0
        echo "$wallpaper" > "$HOME/.cache/current_wallpaper"
        echo "image" > "$HOME/.cache/current_wallpaper_type"
    fi

    # Optional color scheme sync
    if command -v wallust >/dev/null 2>&1 && [[ -f "$wallpaper_frame" ]]; then
        wallust run "$wallpaper_frame"
    fi

    # Reload notification center panel
    if pgrep -x swaync >/dev/null; then
        pkill -x swaync
        nohup swaync >/dev/null 2>&1 &
    fi
fi
