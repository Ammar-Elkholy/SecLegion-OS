#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# Start / stop a NESTED Hyprland (a window inside the running session) for
# workspace behaviour tests. It never talks to the live session: every hyprctl
# call goes through nested_hyprctl, which pins the instance signature of the
# nested compositor and refuses to run without one.
#
#   . tests/ws/nested.sh; nested_start [extra-lua-file]; nested_hyprctl ...; nested_stop
#
# State lives under <repo>/.build/ws (gitignored). Stops only the pid it started.

NESTED_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NESTED_DIR="$NESTED_REPO/.build/ws"
NESTED_SIG="" NESTED_PID=""

nested_start() {
    LIVE_SIG="${HYPRLAND_INSTANCE_SIGNATURE:-}"
    local extra="${1:-}" before d i
    mkdir -p -- "$NESTED_DIR"
    [ -n "${WAYLAND_DISPLAY:-}" ] || { echo "nested: no WAYLAND_DISPLAY (need a parent session)" >&2; return 1; }
    {
        echo 'hl.config({ misc = { disable_hyprland_logo = true, disable_splash_rendering = true } })'
        echo 'hl.monitor({ output = "", mode = "1280x720", position = "auto", scale = 1 })'
        [ -z "$extra" ] || cat -- "$extra"
    } > "$NESTED_DIR/hyprland.lua"
    before="$(ls "$XDG_RUNTIME_DIR/hypr" 2>/dev/null)"
    env -u HYPRLAND_INSTANCE_SIGNATURE Hyprland --config "$NESTED_DIR/hyprland.lua" \
        > "$NESTED_DIR/nested.log" 2>&1 &
    NESTED_PID=$!
    echo "$NESTED_PID" > "$NESTED_DIR/nested.pid"
    for i in $(seq 1 100); do
        kill -0 "$NESTED_PID" 2>/dev/null || { echo "nested: Hyprland exited:" >&2; tail -n 20 "$NESTED_DIR/nested.log" >&2; return 1; }
        for d in "$XDG_RUNTIME_DIR"/hypr/*/; do
            d="${d%/}"
            [ -d "$d" ] || continue
            case $'\n'"$before"$'\n' in *$'\n'"${d##*/}"$'\n'*) continue ;; esac
            if [ -S "$d/.socket.sock" ] && grep -qx "$NESTED_PID" "$d/hyprland.lock" 2>/dev/null; then
                NESTED_SIG="${d##*/}"
                break 2
            fi
        done
        sleep 0.2
    done
    [ -n "$NESTED_SIG" ] || { echo "nested: no instance signature appeared:" >&2; tail -n 20 "$NESTED_DIR/nested.log" >&2; nested_stop; return 1; }
    for i in $(seq 1 50); do
        nested_hyprctl monitors -j 2>/dev/null | grep -q '"name"' && return 0
        sleep 0.2
    done
    echo "nested: no monitor came up" >&2
    nested_stop
    return 1
}

nested_hyprctl() {
    [ -n "$NESTED_SIG" ] || { echo "nested_hyprctl: no nested instance (refusing to touch the live session)" >&2; return 1; }
    HYPRLAND_INSTANCE_SIGNATURE="$NESTED_SIG" hyprctl "$@"
}

nested_stop() {
    local i
    [ -z "$NESTED_PID" ] || kill -TERM "$NESTED_PID" 2>/dev/null || true
    for i in $(seq 1 50); do
        [ -z "$NESTED_PID" ] && break
        kill -0 "$NESTED_PID" 2>/dev/null || break
        sleep 0.1
    done
    [ -z "$NESTED_PID" ] || ! kill -0 "$NESTED_PID" 2>/dev/null || kill -KILL "$NESTED_PID" 2>/dev/null || true
    # Hyprland leaves its (log-only) runtime dir behind: remove the one we created
    if [ -n "$NESTED_SIG" ] && [ "$NESTED_SIG" != "${LIVE_SIG:-}" ]; then
        rm -rf -- "${XDG_RUNTIME_DIR:?}/hypr/${NESTED_SIG:?}"
    fi
    NESTED_PID="" NESTED_SIG=""
}
