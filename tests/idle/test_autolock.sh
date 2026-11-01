#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# desktop/idle/seclegion-autolock against a fake HOME (SL_HOME) and a stub systemctl:
# no real unit, inhibitor or hypridle is touched. Prints "autolock-ok" when all cases pass.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="$SRC/desktop/idle/seclegion-autolock"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# fresh world: $H fake home, $B stub bin, $L the stub's call log
world() {
    H="$WORK/$1/home" B="$WORK/$1/bin" L="$WORK/$1/calls.log"
    mkdir -p "$H/.config/hypr" "$B"
    : > "$L"
    printf 'general {\n\tlock_cmd = pidof hyprlock || hyprlock\n}\nlistener {\n\ttimeout = 300\n\ton-timeout = loginctl lock-session\n}\n' \
        > "$H/.config/hypr/hypridle.conf"
    OWNER0="$(sha256sum < "$H/.config/hypr/hypridle.conf")"
    # systemctl --user VERB ...: record it; is-active succeeds only for units named in $SL_ACTIVE
    cat > "$B/systemctl" <<'EOS'
#!/bin/sh
echo "$*" >> "$STUB_LOG"
[ "$1" = --user ] || exit 2
shift
case "$1" in
    is-active) for u in $STUB_ACTIVE; do [ "$u" = "$2" ] && exit 0; done; exit 3 ;;
    enable | disable | restart) [ -z "${STUB_FAIL:-}" ] || { echo "stub: failing" >&2; exit 1; } ;;
esac
exit 0
EOS
    chmod +x "$B/systemctl"
}
units() {   # install the two unit files as `seclegion-host apply idle` would
    mkdir -p "$H/.config/systemd/user"
    cp "$SRC/desktop/idle/seclegion-idle-inhibit.service" "$SRC/desktop/idle/seclegion-idle.service" "$H/.config/systemd/user/"
}
run() {
    SL_HOME="$H" PATH="$B:$PATH" STUB_LOG="$L" STUB_ACTIVE="${STUB_ACTIVE:-}" STUB_FAIL="${STUB_FAIL:-}" "$TOOL" "$@"
}
owner_untouched() { [ "$(sha256sum < "$H/.config/hypr/hypridle.conf")" = "$OWNER0" ] || fail "the owner's hypridle.conf changed"; }

# a bad value is refused: exit 2, "not one of", nothing run, no state written (G4)
world bad
out="$(run set 5s 2>&1)"; rc=$?
[ "$rc" = 2 ] || fail "set 5s: exit $rc, want 2"
grep -q "not one of" <<< "$out" || fail "set 5s: no 'not one of' in: $out"
[ ! -s "$L" ] || fail "set 5s ran systemctl: $(cat "$L")"
[ ! -e "$H/.config/seclegion/autolock" ] || fail "set 5s wrote the state file"
for v in "" 15 15M "never " 0 '15m;x' '../x'; do
    run set "$v" > /dev/null 2>&1; [ $? = 2 ] || fail "set '$v' not refused with 2"
done
run set > /dev/null 2>&1; [ $? = 2 ] || fail "set without a value not refused with 2"
run frob > /dev/null 2>&1; [ $? = 2 ] || fail "unknown command not refused with 2"
[ "$(run status 2>/dev/null)" = default ] || fail "status after refusals is not default"

# status with no state file, and a hand-edited bad state file, both read default
world st
[ "$(run status 2>/dev/null)" = default ] || fail "empty status"
mkdir -p "$H/.config/seclegion"; echo "bogus" > "$H/.config/seclegion/autolock"
[ "$(run status 2>/dev/null)" = default ] || fail "bogus state file not read as default"

# without the units installed, anything but default is refused and nothing runs
world nounits
run set never > /dev/null 2>&1; [ $? = 3 ] || fail "set never without units: want exit 3"
[ ! -e "$H/.config/seclegion/autolock" ] || fail "state written although the units are missing"
run set default > /dev/null 2>&1 || fail "set default must work without the units"
[ "$(run status 2>/dev/null)" = default ] || fail "default without units"

# never: the inhibitor is enabled and started, our hypridle is stopped, state is recorded
world never
units
[ "$(run set never)" = never ] || fail "set never output"
[ "$(run status 2>/dev/null)" = never ] || fail "status after never"
grep -qx -- '--user enable --now seclegion-idle-inhibit.service' "$L" || fail "inhibitor not started: $(cat "$L")"
grep -qx -- '--user disable --now seclegion-idle.service' "$L" || fail "hypridle unit not stopped: $(cat "$L")"
[ ! -e "$H/.local/share/seclegion/host/idle/hypridle.conf" ] || fail "never wrote a hypridle conf"
owner_untouched

# a delay: conf from the template, inhibitor started before our hypridle is (re)started
for pair in 15m:900 30m:1800 60m:3600; do
    world "d${pair%%:*}"
    units
    [ "$(run set "${pair%%:*}")" = "${pair%%:*}" ] || fail "set ${pair%%:*} output"
    conf="$H/.local/share/seclegion/host/idle/hypridle.conf"
    grep -qx "    timeout = ${pair##*:}" "$conf" || fail "${pair%%:*}: no 'timeout = ${pair##*:}' in $(cat "$conf")"
    grep -qx '    ignore_systemd_inhibit = true' "$conf" && grep -qx '    ignore_dbus_inhibit = true' "$conf" \
        && grep -qx '    ignore_wayland_inhibit = false' "$conf" || fail "${pair%%:*}: general block"
    grep -qx '    on-timeout = loginctl lock-session' "$conf" || fail "${pair%%:*}: on-timeout"
    ! grep -q '@TIMEOUT@' "$conf" || fail "${pair%%:*}: placeholder left in the conf"
    a="$(grep -n -- 'enable --now seclegion-idle-inhibit.service' "$L" | head -n1 | cut -d: -f1)"
    b="$(grep -n -- 'restart seclegion-idle.service' "$L" | head -n1 | cut -d: -f1)"
    [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ] || fail "${pair%%:*}: inhibitor not before the restart: $(cat "$L")"
    [ "$(run status 2>/dev/null)" = "${pair%%:*}" ] || fail "status after ${pair%%:*}"
    owner_untouched
done

# switching back to default stops both units and clears the effect
world back
units
run set 30m > /dev/null || fail "set 30m"
: > "$L"
run set default > /dev/null || fail "set default"
grep -qx -- '--user disable --now seclegion-idle.service' "$L" && grep -qx -- '--user disable --now seclegion-idle-inhibit.service' "$L" \
    || fail "default did not stop both units: $(cat "$L")"
[ "$(run status 2>/dev/null)" = default ] || fail "status after default"
owner_untouched

# a failing systemctl: nothing is recorded as set
world fails
units
STUB_FAIL=1 run set never > /dev/null 2>&1; [ $? = 5 ] || fail "systemctl failure: want exit 5"
[ "$(run status 2>/dev/null)" = default ] || fail "state recorded although systemctl failed"

# status warns (stderr only) when the state and the running units disagree
world warn
units
run set never > /dev/null || fail "set never"
out="$(STUB_ACTIVE="" run status 2>&1 >/dev/null)"
grep -q 'seclegion-idle-inhibit.service is not running' <<< "$out" || fail "no warning for a stopped inhibitor: $out"
out="$(STUB_ACTIVE="seclegion-idle-inhibit.service" run status 2>&1 >/dev/null)"
[ -z "$out" ] || fail "warning although the inhibitor runs: $out"

echo autolock-ok
