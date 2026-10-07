#!/usr/bin/env bash
# =============================================================================
# ae-osd.sh — AE-ARCH Branded On-Screen Display
# Neon green/cyan popups for: volume, brightness, media, system events
# Uses dunstify with category "ae-osd" so it appears in the OSD layer
# =============================================================================

OSD_APP="AE-OS"
ICON_LOGO="${HOME}/.config/hypr/icons/ae-logo.png"

# ─── helpers ──────────────────────────────────────────────────────────────────
notify_osd() {
    local title="$1"
    local body="$2"
    local icon="${3:-audio-volume-high-symbolic}"
    local value="${4:-}"   # 0-100 for progress bar

    local hints=(-h string:x-dunst-stack-tag:ae-osd)
    [[ -n "$value" ]] && hints+=(-h "int:value:${value}")

    # Use the SecLegion/AE logo if it exists, else fallback to symbolic icon
    [[ -f "$ICON_LOGO" ]] && icon="$ICON_LOGO"

    dunstify \
        --urgency=low \
        --timeout=2000 \
        --appname="$OSD_APP" \
        --icon="$icon" \
        "${hints[@]}" \
        "$title" "$body"
}

# ─── actions ──────────────────────────────────────────────────────────────────
case "$1" in

    vol-up)
        wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+
        VOL=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{printf "%d", $2*100}')
        notify_osd "  Volume" "${VOL}%" audio-volume-high-symbolic "$VOL"
        ;;

    vol-down)
        wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-
        VOL=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{printf "%d", $2*100}')
        notify_osd "  Volume" "${VOL}%" audio-volume-medium-symbolic "$VOL"
        ;;

    vol-mute)
        wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
        MUTED=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | grep -c MUTED)
        if [[ "$MUTED" -gt 0 ]]; then
            notify_osd "  Muted" "Audio silenced" audio-volume-muted-symbolic "0"
        else
            VOL=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{printf "%d", $2*100}')
            notify_osd "  Unmuted" "${VOL}%" audio-volume-high-symbolic "$VOL"
        fi
        ;;

    mic-mute)
        wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle
        MUTED=$(wpctl get-volume @DEFAULT_AUDIO_SOURCE@ | grep -c MUTED)
        if [[ "$MUTED" -gt 0 ]]; then
            notify_osd "  Mic Off" "Microphone muted" microphone-sensitivity-muted-symbolic "0"
        else
            notify_osd "  Mic On" "Microphone active" audio-input-microphone-symbolic "100"
        fi
        ;;

    bright-up)
        brightnessctl -e4 -n2 set 5%+
        BRIGHT=$(brightnessctl -m | awk -F, '{gsub(/%/,"",$4); print $4}')
        notify_osd "󰖨  Brightness" "${BRIGHT}%" display-brightness-symbolic "$BRIGHT"
        ;;

    bright-down)
        brightnessctl -e4 -n2 set 5%-
        BRIGHT=$(brightnessctl -m | awk -F, '{gsub(/%/,"",$4); print $4}')
        notify_osd "󰖩  Brightness" "${BRIGHT}%" display-brightness-symbolic "$BRIGHT"
        ;;

    media-play)
        playerctl play-pause
        STATUS=$(playerctl status 2>/dev/null || echo "Unknown")
        TITLE=$(playerctl metadata title 2>/dev/null | head -c 40 || echo "")
        if [[ "$STATUS" == "Playing" ]]; then
            notify_osd "  Playing" "$TITLE" media-playback-start-symbolic
        else
            notify_osd "  Paused" "$TITLE" media-playback-pause-symbolic
        fi
        ;;

    media-next)
        playerctl next
        sleep 0.3
        TITLE=$(playerctl metadata title 2>/dev/null | head -c 40 || echo "")
        notify_osd "  Next Track" "$TITLE" media-skip-forward-symbolic
        ;;

    media-prev)
        playerctl previous
        sleep 0.3
        TITLE=$(playerctl metadata title 2>/dev/null | head -c 40 || echo "")
        notify_osd "  Previous" "$TITLE" media-skip-backward-symbolic
        ;;

    scratchpad-show)
        notify_osd " Scratchpad" "Special workspace shown" preferences-desktop-display-symbolic
        ;;

    scratchpad-hide)
        notify_osd " Scratchpad" "Special workspace hidden" preferences-desktop-display-symbolic
        ;;

    lang-en)
        notify_osd "󰀫  Language" "Switched to English" preferences-desktop-locale-symbolic
        ;;

    lang-ar)
        notify_osd "󰀫  Language" "Switched to Arabic" preferences-desktop-locale-symbolic
        ;;

    lock)
        notify_osd "  Locking" "Screen locking..." system-lock-screen-symbolic
        sleep 0.5
        hyprlock
        ;;

    logout-menu)
        pkill -x wlogout || wlogout
        ;;

    waybar-toggle)
        ~/.config/hypr/scripts/toggle-waybar.sh
        notify_osd "  Waybar" "Bar toggled" view-grid-symbolic
        ;;

    screenshot-area)     ~/.config/hypr/scripts/screenshot.sh area ;;
    screenshot-edit)     ~/.config/hypr/scripts/screenshot.sh edit ;;
    screenshot-active)   ~/.config/hypr/scripts/screenshot.sh active ;;
    screenshot-screen)   ~/.config/hypr/scripts/screenshot.sh screen ;;

    *)
        echo "Usage: ae-osd.sh <action>"
        echo "  vol-up | vol-down | vol-mute | mic-mute"
        echo "  bright-up | bright-down"
        echo "  media-play | media-next | media-prev"
        echo "  scratchpad-show | scratchpad-hide"
        echo "  lang-en | lang-ar"
        echo "  lock | logout-menu | waybar-toggle"
        echo "  screenshot-area | screenshot-edit | screenshot-active | screenshot-screen"
        ;;
esac
