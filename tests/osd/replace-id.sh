#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G2: five volume-key presses in a row replace one popup. The owner's
# ae-osd.sh runs unchanged,
# with a stub wpctl (no real volume is touched) and the committed dunstify
# shim first on PATH; a logging wrapper (SL_DUNSTIFY_REAL) adds `-p` and
# records the id each press got (informational: swaync gives a replacing
# notification a NEW id and drops the old one, so "one id" is measured as
# "one notification left", from `swaync-client -c`).
#
# Host-safe: swaync runs on a PRIVATE session bus (dbus-run-session), so it can
# not take org.freedesktop.Notifications from the live daemon, and draws into a
# NESTED Hyprland (tests/ws/nested.sh). Control: with the real dunstify and no
# shim five notifications pile up (swaync ignores the dunst stack tag).
# Prints "replace-id-stable"; exit 1 on failure, 77 if it cannot run here.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

if [ "${1:-}" != inner ]; then
    command -v dbus-run-session > /dev/null || { echo "UNVERIFIED: no dbus-run-session" >&2; exit 77; }
    exec dbus-run-session -- bash "${BASH_SOURCE[0]}" inner
fi

# shellcheck source=tests/ws/nested.sh
. "$repo/tests/ws/nested.sh"
AE_OSD="${AE_OSD:-$HOME/.config/hypr/scripts/ae-osd.sh}"
[ -f "$AE_OSD" ] || { echo "UNVERIFIED: no ae-osd.sh at $AE_OSD (set AE_OSD)" >&2; exit 77; }
work="$NESTED_DIR/replace-id"
rm -rf -- "$work"
mkdir -p -- "$work/bin" "$work/shim"
SWAYNC_PID=""
cleanup() {
    [ -z "$SWAYNC_PID" ] || kill -TERM "$SWAYNC_PID" 2> /dev/null || true
    nested_stop
}
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# stub wpctl: a fixed volume, no change to the real sound server
cat > "$work/bin/wpctl" <<'EOF'
#!/bin/sh
case "$1" in get-volume) echo "Volume: 0.45" ;; esac
EOF
# logging wrapper around the real dunstify: -p prints the notification id
cat > "$work/real" <<EOF
#!/bin/sh
id="\$(/usr/bin/dunstify -p "\$@")" || exit \$?
echo "\$id" >> "\$SL_IDLOG"
EOF
chmod +x "$work/bin/wpctl" "$work/real"
ln -s "$repo/desktop/osd/dunstify" "$work/shim/dunstify"

wl_sockets() {   # names of the Wayland sockets in the runtime dir, one per line
    local d
    for d in "$XDG_RUNTIME_DIR"/wayland-*; do
        case "$d" in *.lock) ;; *) [ ! -S "$d" ] || printf '%s\n' "${d##*/}" ;; esac
    done
}
before="$(wl_sockets)"
nested_start || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
nested_display=""
for d in $(wl_sockets); do
    case $'\n'"$before"$'\n' in *$'\n'"$d"$'\n'*) ;; *) nested_display="$d" ;; esac
done
[ -n "$nested_display" ] || fail "no wayland socket of the nested compositor found"

mkdir -p -- "$work/cfg"
cp -- "$repo/desktop/swaync/config.json" "$repo/desktop/swaync/style.css" "$work/cfg/"
WAYLAND_DISPLAY="$nested_display" swaync -c "$work/cfg/config.json" -s "$work/cfg/style.css" > "$work/swaync.log" 2>&1 &
SWAYNC_PID=$!
owner=""
for i in $(seq 1 50); do
    owner="$(busctl --address="$DBUS_SESSION_BUS_ADDRESS" status org.freedesktop.Notifications 2> /dev/null | sed -n 's/^PID=//p')"
    [ -n "$owner" ] && break
    sleep 0.2
done
[ "$owner" = "$SWAYNC_PID" ] || { tail -n 5 "$work/swaync.log" >&2; fail "private-bus owner is '$owner', not our swaync $SWAYNC_PID"; }
[ "$DBUS_SESSION_BUS_ADDRESS" != "unix:path=/run/user/$(id -u)/bus" ] || fail "not on a private bus"

presses() {   # DIR-WITH-dunstify IDLOG -> five vol-up presses; ids recorded in IDLOG
    : > "$2"
    local n
    for n in 1 2 3 4 5; do
        PATH="$1:$work/bin:$PATH" SL_IDLOG="$2" SL_DUNSTIFY_REAL="$work/real" bash "$AE_OSD" vol-up \
            || fail "ae-osd.sh vol-up press $n exited $?"
    done
}

count() { swaync-client -c 2> /dev/null; echo; }   # notifications swaync holds now

# control: the real dunstify straight through (named dunstify in its own dir)
mkdir -p -- "$work/plain"
ln -sf "$work/real" "$work/plain/dunstify"
swaync-client -C > /dev/null 2>&1
[ "$(count)" = 0 ] || fail "swaync is not empty at the start"
presses "$work/plain" "$work/ids-plain"
[ "$(count)" = 5 ] || fail "control: want 5 notifications without the shim, got $(count): the test proves nothing"

swaync-client -C > /dev/null 2>&1
[ "$(count)" = 0 ] || fail "could not clear swaync"
presses "$work/shim" "$work/ids-shim"
[ "$(wc -l < "$work/ids-shim")" = 5 ] || fail "want 5 dunstify calls, got $(wc -l < "$work/ids-shim")"
[ "$(count)" = 1 ] || fail "with the shim want 1 notification after 5 presses, got $(count) (ids: $(tr '\n' ' ' < "$work/ids-shim"))"
echo replace-id-stable
