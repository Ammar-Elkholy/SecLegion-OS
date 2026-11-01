#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G1: desktop/osd/dunstify rewrites the dunst stack tag to the swaync
# replace hint and leaves everything else alone; seclegion-osd uses its own
# tag, 2000 ms and low urgency. A fake "real" dunstify (SL_DUNSTIFY_REAL)
# records its argv, one argument per line.
# Prints "synchronous-tag-ok"; exit 1 on failure.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

printf '#!/bin/sh\nfor a in "$@"; do printf "%%s\\n" "$a"; done > "%s/argv"\n' "$work" > "$work/real"
chmod +x "$work/real"
export SL_DUNSTIFY_REAL="$work/real"
shim="$repo/desktop/osd/dunstify"
osd="$repo/desktop/osd/seclegion-osd"

check() {   # NAME EXPECTED-ARGV (newline separated) ARGS... -> run the shim, compare the recorded argv
    local name="$1" want="$2"
    shift 2
    rm -f "$work/argv"
    "$shim" "$@" || fail "$name: shim exited $?"
    [ "$(cat "$work/argv")" = "$want" ] || { diff <(printf '%s\n' "$want") "$work/argv" >&2; fail "$name: argv differs"; }
}

check separate $'-u\nlow\n-h\nstring:x-canonical-private-synchronous:ae-osd\n-h\nint:value:40\nTitle\nBody' \
    -u low -h string:x-dunst-stack-tag:ae-osd -h int:value:40 Title Body
check equals $'--hints=string:x-canonical-private-synchronous:x\nT' --hints=string:x-dunst-stack-tag:x T
check attached $'-hstring:x-canonical-private-synchronous:x\nT' -hstring:x-dunst-stack-tag:x T
# text that merely mentions the tag stays as given; spaces and empty arguments survive
check untouched $'-t\n2000\nsay string:x-dunst-stack-tag:y\n\na b' -t 2000 'say string:x-dunst-stack-tag:y' '' 'a b'
check noargs ''

# the shim never runs itself: with no override it execs /usr/bin/dunstify by absolute path
grep -q '/usr/bin/dunstify' "$shim" || fail "shim does not name /usr/bin/dunstify"
grep -qE '^exec "\$real"' "$shim" || fail "shim does not exec the real binary"

# seclegion-osd: own tag, 2000 ms, low urgency, int:value, label. It calls the
# sibling shim, so the recorded argv already has the tag rewritten.
rm -f "$work/argv"
"$osd" volume 55 Volume || fail "seclegion-osd exited $?"
want=$'--urgency=low\n--timeout=2000\n--appname=SecLegion\n--icon=audio-volume-high-symbolic\n-h\nstring:x-canonical-private-synchronous:seclegion-osd\n-h\nint:value:55\nVolume\n55%'
[ "$(cat "$work/argv")" = "$want" ] || { diff <(printf '%s\n' "$want") "$work/argv" >&2; fail "seclegion-osd argv differs"; }
"$osd" brightness 250 || fail "clamp run"
grep -qx 'int:value:100' "$work/argv" || fail "value 250 was not clamped to 100"
"$osd" volume abc 2> /dev/null && fail "non-numeric value accepted"
"$osd" volume 2> /dev/null && fail "missing value accepted"

echo synchronous-tag-ok
