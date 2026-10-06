#!/bin/bash
export GRIMBLAST_EDITOR="swappy"
DIR="$HOME/Pictures/Screenshots"
mkdir -p "$DIR"
export XDG_SCREENSHOTS_DIR="$DIR"

mode="${1:-area}"

case "$mode" in
    "area"|"snip")
        grimblast --notify copysave area
        ;;
    "edit"|"swappy")
        grimblast --notify edit area
        ;;
    "active"|"window")
        grimblast --notify copysave active
        ;;
    "screen"|"full")
        grimblast --notify copysave screen
        ;;
    *)
        grimblast --notify copysave area
        ;;
esac
