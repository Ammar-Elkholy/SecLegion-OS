#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G3: a program started by a Hyprland bind or autostart (hl.dsp.exec_cmd, the
# same path) finds ~/.local/bin first on PATH, so the `osd` shim is seen.
# Runs a NESTED Hyprland (tests/ws/nested.sh, never the live session) started
# with the live compositor's PATH, /usr/local/bin:/usr/bin, and a scratch HOME
# whose ~/.local/bin/dunstify is the shim from the repo. The committed
# desktop/hypr/seclegion-host.lua is loaded; then `hyprctl reload`.
# Checks, in the exec'd child (via /proc/<pid>/environ and `command -v`):
#   - control: without seclegion-host.lua the child has no ~/.local/bin on PATH
#   - with it: ~/.local/bin is first, and `command -v dunstify` is the shim
#   - after a reload: still first, and exactly once
# Prints "localbin-first"; exit 1 on failure, 77 if no nested Hyprland can start.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
# shellcheck source=tests/ws/nested.sh
. "$repo/tests/ws/nested.sh"
trap nested_stop EXIT

probe="$NESTED_DIR/path-probe"
rm -rf -- "$probe"
mkdir -p -- "$probe/home/.local/bin"
ln -s "$repo/desktop/osd/dunstify" "$probe/home/.local/bin/dunstify"
lb="$probe/home/.local/bin"
cat > "$probe/child.sh" <<EOF
#!/bin/sh
echo \$\$ > "$probe/pid.tmp"
command -v dunstify > "$probe/which" 2>/dev/null || : > "$probe/which"
mv "$probe/pid.tmp" "$probe/pid"
exec sleep 60
EOF
chmod +x "$probe/child.sh"

start() {   # [host] -> nested Hyprland with the live PATH and the scratch HOME
    local extra=""
    cp -- "$repo/desktop/hypr/seclegion-host.lua" "$NESTED_DIR/seclegion-host.lua"
    if [ "${1:-}" = host ]; then
        echo 'require("seclegion-host")' > "$NESTED_DIR/extra.lua"
        extra="$NESTED_DIR/extra.lua"
    fi
    PATH=/usr/local/bin:/usr/bin HOME="$probe/home" nested_start $extra \
        || { echo "UNVERIFIED: nested Hyprland did not start" >&2; exit 77; }
}

child_path() {   # exec the child through Hyprland; print its PATH (one entry per line)
    local i pid
    rm -f -- "$probe/pid" "$probe/which"
    nested_hyprctl dispatch "hl.dsp.exec_cmd(\"$probe/child.sh\")" > /dev/null
    for i in $(seq 1 50); do [ -s "$probe/pid" ] && break; sleep 0.2; done
    [ -s "$probe/pid" ] || { echo "the exec'd child never ran" >&2; return 1; }
    pid="$(cat "$probe/pid")"
    tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^PATH=//p' | tr ':' '\n'
    kill -TERM "$pid" 2>/dev/null || true   # the one process this probe started
}

# control: without our lua the child cannot see ~/.local/bin
start
p="$(child_path)" || exit 1
! grep -qxF "$lb" <<< "$p" || { echo "control: $lb on PATH without seclegion-host.lua" >&2; exit 1; }
nested_stop

start host
e="$(nested_hyprctl configerrors)"
[ -z "${e//[[:space:]]/}" ] || { echo "configerrors: $e" >&2; exit 1; }
p="$(child_path)" || exit 1
[ "$(head -n1 <<< "$p")" = "$lb" ] || { echo "PATH does not start with $lb: $(tr '\n' : <<< "$p")" >&2; exit 1; }
[ "$(cat "$probe/which")" = "$lb/dunstify" ] || { echo "dunstify resolves to '$(cat "$probe/which")'" >&2; exit 1; }

nested_hyprctl reload > /dev/null
sleep 1
p="$(child_path)" || exit 1
[ "$(head -n1 <<< "$p")" = "$lb" ] || { echo "after reload PATH starts with $(head -n1 <<< "$p")" >&2; exit 1; }
[ "$(grep -cxF "$lb" <<< "$p")" = 1 ] || { echo "after reload $lb is on PATH $(grep -cxF "$lb" <<< "$p") times" >&2; exit 1; }
[ "$(cat "$probe/which")" = "$lb/dunstify" ] || { echo "after reload dunstify resolves to '$(cat "$probe/which")'" >&2; exit 1; }
echo localbin-first
