#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# tools/seclegion-host against a synthetic fake HOME, a fake /proc and PATH
# stubs (tests/host/fake-host) for every live command: no real process, unit,
# bus or HOME is touched. Each case runs in its own fresh world.
set -uo pipefail
[ -z "${TRACE:-}" ] || set -x

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"   # a real fs: 0700/0600 must be honoured (the repo may be on NTFS)
trap 'rm -rf -- "$WORK"' EXIT
for v in $(env | sed -n 's/^\(GIT_[A-Za-z_]*\)=.*/\1/p'); do unset "$v"; done

fail() { echo "    FAIL: $*" >&2; exit 1; }
calls() { cat "$F/calls.log"; }
owner_comm() { local o; o="$(cat "$F/bus-owner" 2>/dev/null)"; [ -d "$F/proc/$o" ] && cat "$F/proc/$o/comm"; }
fp() {   # ~/.config entirely, plus every file and symlink under ~/.local except our backup state
    fp_config
    (cd "$H" && find .local \( -path .local/state/seclegion/host-backups -o -path .local/state/seclegion/host-pending \) \
        -prune -o ! -type d -printf '%y %m %p %l\n' 2>/dev/null | sort)
}
fp_config() { (cd "$H/.config" && find . -printf '%y %m %p %l\n' | sort; find . -type f -print0 | sort -z | xargs -0 sha256sum); }
sl() { "$R/tools/seclegion-host" "$@" > "$C/out.log" 2>&1; local rc=$?; cat "$C/out.log" >> "$C/all.log"; return $rc; }

# world AUTOSTART_STYLE: both (dunst + swaync lines) | dunst (dunst line only)
#   | dup (two swaync lines and no dunst: what the old host-apply left on the live host)
world() {
    C="$WORK/case-$1" H="$C/home" F="$C/fake" R="$C/repo"
    mkdir -p "$C/bin" "$C/run" "$F/proc" "$F/units" "$R/tools"
    cp -r "$SRC/desktop" "$R/"
    cp "$SRC/tools/seclegion-host" "$SRC/tools/host-lib.sh" "$SRC/tools/seclegion-theme" "$SRC/tools/seclegion-keys-lint" \
        "$SRC/tools/seclegion-set" "$SRC/tools/seclegion-settings" "$SRC/tools/seclegion-root-apply" "$SRC/tools/seclegion-theme-pick" "$SRC/tools/seclegion-doctor" "$R/tools/"
    for c in pgrep kill hyprctl busctl systemctl systemd-run swaync dunst waybar nm-applet; do
        printf '#!/bin/sh\nexec bash %q %s "$0" "$@"\n' "$SRC/tests/host/fake-host" "$c" > "$C/bin/$c"
        chmod +x "$C/bin/$c"
    done
    echo 5000000 > "$F/nextpid"
    : > "$F/calls.log"
    : > "$C/run/wayland-test"
    export SL_NMAPPLET_REAL="$C/bin/nm-applet"   # what the shim and a rollback run: the stub
    export SL_HOME="$H" HOME="$H" SL_PROC="$F/proc" SL_FAKE="$F" PATH="$C/bin:$BASE_PATH" \
        XDG_RUNTIME_DIR="$C/run" WAYLAND_DISPLAY=wayland-test HYPRLAND_INSTANCE_SIGNATURE=test \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent
    for c in pgrep kill hyprctl busctl systemctl systemd-run swaync dunst waybar nm-applet; do
        [ "$(type -P "$c")" = "$C/bin/$c" ] || fail "$c is not stubbed"
    done

    D="$H/.config/hyprland-dotfiles"
    mkdir -p "$D"/{hypr/modules,waybar,swaync} "$H/.config/dunst" "$H/.local" \
        "$H/.config/systemd/user/default.target.wants"   # the owner's real layout (waybar.service lives there)
    printf '%s\n' 'require("modules.autostart")' 'require("hyprland-border")' 'hl.config({})' > "$D/hypr/hyprland.lua"
    if [ "$2" = both ]; then
        printf '%s\n' 'hl.on("hyprland.start", function () ' '    hl.exec_cmd("dunst")' '    hl.exec_cmd("swaync")' 'end)' > "$D/hypr/modules/autostart.lua"
    elif [ "$2" = dup ]; then
        printf '%s\n' 'hl.on("hyprland.start", function () ' '    -- Notification daemon' '    hl.exec_cmd("swaync")' '' \
            '    -- Notification center' '    hl.exec_cmd("swaync")' '' '    hl.exec_cmd("hypridle")' 'end)' > "$D/hypr/modules/autostart.lua"
    else
        printf '%s\n' 'hl.on("hyprland.start", function () ' '    hl.exec_cmd("dunst")' 'end)' > "$D/hypr/modules/autostart.lua"
    fi
    chmod 640 "$D/hypr/modules/autostart.lua"
    # the owner's lock screen: a regular file, dark field and no font_color, no trailing newline, mode 640
    printf 'input-field {\n    inner_color = rgba(5, 15, 14, 0.8)\n    text_color = rgba(255,255,255,0.9)\n}' > "$D/hypr/hyprlock.conf"
    chmod 640 "$D/hypr/hyprlock.conf"
    echo 'old waybar config' > "$D/waybar/config.jsonc"
    echo 'old swaync config' > "$D/swaync/config.json"
    echo 'old dunst' > "$H/.config/dunst/dunstrc"
    ln -s "$D/hypr" "$H/.config/hypr"
    ln -s "$D/waybar" "$H/.config/waybar"
    ln -s "$D/swaync" "$H/.config/swaync"
    [[ "$D" == "$WORK"/* ]] || fail "dotfiles repo outside the test dir"
    git -C "$D" init -q && git -C "$D" add -A \
        && git -C "$D" -c user.name=t -c user.email=t@t commit -qm init || fail "git init"
    echo '-- local edit' >> "$D/hypr/hyprland.lua"
    echo untracked > "$D/untracked.txt"

    # live session: dunst owns Notifications (started as "dunst"), a stray swaync, waybar service
    local p
    p="$(spawn dunst dunst)"; echo "$p" > "$F/bus-owner"
    spawn swaync swaync > /dev/null
    spawn waybar waybar > /dev/null
    echo active > "$F/units/waybar"
    spawn nm-applet nm-applet --indicator > /dev/null   # the owner's autostart line
    BK="$H/.local/state/seclegion/host-backups"
}
spawn() {
    local pid; pid="$(cat "$F/nextpid")"; echo $((pid + 1)) > "$F/nextpid"
    mkdir "$F/proc/$pid"; echo "$1" > "$F/proc/$pid/comm"; shift; printf '%s\0' "$@" > "$F/proc/$pid/cmdline"; echo "$pid"
}
swaync_lines() { grep -cE '^[[:space:]]*hl\.exec_cmd\("swaync"\)[[:space:]]*$' "$H/.config/hypr/modules/autostart.lua"; }
last_id() { (cd "$BK" && ls -1d 2*Z-* | tail -n1); }

case_apply_refused_rollback() {
    world a both
    local cfg0; cfg0="$(fp_config)"
    sl apply notifications || fail "apply notifications: $(cat "$C/out.log")"
    local id; id="$(last_id)"
    [ -f "$BK/baseline-0/rollback.sh" ] || fail "no baseline-0"
    [ "$(swaync_lines)" = 1 ] || fail "want exactly one swaync exec line, got $(swaync_lines)"
    grep -q 'exec_cmd("dunst")' "$H/.config/hypr/modules/autostart.lua" && fail "dunst line left"
    [ "$(readlink "$H/.config/swaync")" = "$H/.local/share/seclegion/host/notifications" ] || fail "swaync symlink"
    [ "$(owner_comm)" = swaync ] || fail "owner after apply: $(owner_comm)"
    [ -f "$F/units/seclegion-host-deadman.timer" ] || fail "dead-man not armed"
    grep -q -- '--on-active=120' "$F/calls.log" || fail "dead-man not 120 s"
    grep -qE "^kill -TERM 500000[01]" "$F/calls.log" || fail "dunst/swaync not stopped by pid"
    # backup shape
    for b in "$BK/$id" "$BK/baseline-0"; do
        [ "$(stat -c %a "$b")" = 700 ] || fail "$b not 0700"
        for f in manifest.json files.tar dotfiles.patch rollback.sh; do
            [ "$(stat -c %a "$b/$f")" = 600 ] || fail "$b/$f not 0600"
        done
    done
    [ "$(tar -tf "$BK/$id/files.tar" | sort | tr '\n' ' ')" = ".config/hypr/modules/autostart.lua .config/swaync " ] \
        || fail "files.tar holds: $(tar -tf "$BK/$id/files.tar" | tr '\n' ' ')"
    python3 - "$BK/$id/manifest.json" <<'PY' || fail "manifest"
import json, sys
m = json.load(open(sys.argv[1]))
assert m["notifications_owner"]["comm"] == "dunst" and m["notifications_owner"]["cmdline"] == ["dunst"], m
assert sorted(m["daemons"]) == ["dunst", "swaync"] and m["daemons"]["dunst"][0]["pid"] == 5000000, m
assert {p["kind"] for p in m["paths"]} == {"file", "symlink", "absent"}, m
assert "general:border_size" in m["hyprctl"], m
PY
    grep -q '^+-- local edit' "$BK/$id/dotfiles.patch" && grep -q 'untracked: untracked.txt' "$BK/$id/dotfiles.patch" \
        || fail "dotfiles.patch"

    sl apply waybar && fail "second apply was not refused"
    grep -q 'confirm or roll back the previous change first' "$C/out.log" || fail "refusal message: $(cat "$C/out.log")"
    [ "$(readlink "$H/.config/waybar")" = "$H/.config/hyprland-dotfiles/waybar" ] || fail "refused apply changed waybar"

    sl rollback || fail "rollback: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
    [ ! -e "$H/.local/share/seclegion/host/notifications" ] || fail "installed tree left behind"
    [ "$(owner_comm)" = dunst ] || fail "owner after rollback: $(owner_comm)"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "still pending"
    [ ! -f "$F/units/seclegion-host-deadman.timer" ] || fail "dead-man still armed"
}

case_reapply_rollback_last() {
    world b dunst
    sl apply notifications || fail "apply 1: $(cat "$C/out.log")"
    [ "$(swaync_lines)" = 1 ] || fail "want exactly one swaync exec line, got $(swaync_lines)"
    grep -q 'exec_cmd("dunst")' "$H/.config/hypr/modules/autostart.lua" && fail "dunst line left"
    sl confirm || fail "confirm: $(cat "$C/out.log")"
    local id1 tree1 tree pid_before
    id1="$(last_id)"
    [ -f "$BK/$id1/CONFIRMED" ] || fail "no CONFIRMED"
    tree() { (cd "$H/.local/share/seclegion/host/notifications" && find . -type f -print0 | sort -z | xargs -0 sha256sum); }
    tree1="$(tree)"
    echo '/* v2 */' >> "$R/desktop/swaync/style.css"
    sl apply notifications || fail "apply 2: $(cat "$C/out.log")"
    [ "$(last_id)" != "$id1" ] || fail "backup id collision"
    [ "$(tree)" != "$tree1" ] || fail "apply 2 installed the same tree"
    tar -tf "$BK/$(last_id)/files.tar" | grep -q '^.local/share/seclegion/host/notifications/style.css$' \
        || fail "previous installed tree not in files.tar"
    pid_before="$(cat "$F/bus-owner")"
    sl rollback --last || fail "rollback --last: $(cat "$C/out.log")"
    [ "$(tree)" = "$tree1" ] || fail "rollback --last did not restore the first apply's tree"
    [ "$(owner_comm)" = swaync ] || fail "no notification daemon after rollback (owner: '$(owner_comm)')"
    [ "$(cat "$F/bus-owner")" != "$pid_before" ] || fail "notification daemon not restarted"
    [ "$(swaync_lines)" = 1 ] || fail "autostart after rollback"
}

case_baseline_restarts_dunst() {
    world c both
    local all0; all0="$(fp)"
    sl apply notifications && sl confirm && sl apply waybar && sl confirm && sl apply border && sl confirm \
        || fail "apply chain: $(cat "$C/out.log")"
    grep -qx 'require("seclegion-host")' "$H/.config/hypr/hyprland.lua" || fail "require line"
    [ "$(diff "$H/.config/hypr/hyprland.lua" <(git -C "$H/.config/hyprland-dotfiles" show HEAD:hypr/hyprland.lua) | grep -c '^<')" = 2 ] \
        || fail "hyprland.lua: more than the require line changed"
    [ -f "$H/.config/hypr/seclegion-host.lua" ] || fail "seclegion-host.lua"
    grep -q "url(\"file://$H/.local/state/seclegion/theme/current/colors.css\")" "$H/.local/share/seclegion/host/waybar/style.css" \
        || fail "__HOME__ not rendered"
    : > "$F/calls.log"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ "$(owner_comm)" = dunst ] || fail "dunst not restored (owner: '$(owner_comm)')"
    grep -q "^systemd-run .*$C/bin/dunst\$" "$F/calls.log" || fail "dunst not started: $(calls)"
    grep -q '^systemctl --user restart waybar' "$F/calls.log" || fail "waybar not restarted"
    [ "$(fp)" = "$all0" ] || { diff <(echo "$all0") <(fp) >&2; fail "home differs after rollback to baseline-0"; }
    sl prune --keep 1 || fail "prune"
    [ -f "$BK/baseline-0/rollback.sh" ] || fail "prune removed baseline-0"
    [ "$(cd "$BK" && ls -1d 2*Z-* | wc -l)" = 1 ] || fail "prune kept $(ls "$BK")"
}

case_confirm_stop_fails() {
    world d both
    sl apply notifications || fail "apply: $(cat "$C/out.log")"
    local id; id="$(last_id)"
    touch "$F/stop-fails"
    sl confirm && fail "confirm succeeded although the timer could not be stopped"
    [ ! -e "$BK/$id/CONFIRMED" ] || fail "CONFIRMED written"
    [ -f "$H/.local/state/seclegion/host-pending" ] || fail "pending cleared"
    rm -f "$F/stop-fails"
    echo active > "$F/units/seclegion-host-deadman.service"
    sl confirm && fail "confirm succeeded while the dead-man service runs"
    [ ! -e "$BK/$id/CONFIRMED" ] || fail "CONFIRMED written while dead-man runs"
    rm -f "$F/units/seclegion-host-deadman.service"
    touch "$BK/$id/ROLLBACK_STARTED"   # a dead-man run that failed and was collected
    sl confirm && fail "confirm succeeded after a rollback had started"
    [ ! -e "$BK/$id/CONFIRMED" ] || fail "CONFIRMED written after a rollback had started"
    rm -f "$BK/$id/ROLLBACK_STARTED"
    sl confirm || fail "confirm: $(cat "$C/out.log")"
    [ -f "$BK/$id/CONFIRMED" ] || fail "CONFIRMED missing"
}

case_dup_swaync_collapsed() {
    world g dup
    local auto="$H/.config/hypr/modules/autostart.lua" orig a1
    orig="$(cat "$auto")"
    sl apply notifications || fail "apply: $(cat "$C/out.log")"
    [ "$(swaync_lines)" = 1 ] || fail "want exactly one swaync exec line, got $(swaync_lines)"
    [ "$(diff <(echo "$orig") "$auto" | grep -c '^[<>]')" = 1 ] || fail "more than one swaync line removed: $(diff <(echo "$orig") "$auto")"
    grep -q 'hl.exec_cmd("hypridle")' "$auto" || fail "other exec lines lost"
    [ "$(stat -c %a "$auto")" = 640 ] || fail "autostart mode changed"
    a1="$(sha256sum < "$auto")"
    sl confirm || fail "confirm: $(cat "$C/out.log")"
    sl apply notifications || fail "re-apply: $(cat "$C/out.log")"
    [ "$(sha256sum < "$auto")" = "$a1" ] || fail "re-apply edited autostart again"
    sl rollback --last || fail "rollback --last: $(cat "$C/out.log")"
    [ "$(swaync_lines)" = 1 ] || fail "rollback --last: want the first apply's single line"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ "$(cat "$auto")" = "$orig" ] || fail "baseline-0 did not restore the original autostart"
}

case_tar_failure_fatal() {
    world h both
    local cfg0; cfg0="$(fp_config)"
    printf '#!/bin/sh\necho "tar: simulated failure" >&2\nexit 2\n' > "$C/bin/tar"
    chmod +x "$C/bin/tar"
    sl apply notifications && fail "apply succeeded although tar failed"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed although tar failed"
    [ -z "$(ls -A "$BK" 2>/dev/null)" ] || fail "partial backup left: $(ls "$BK")"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "pending written"
    grep -qE '^(kill|systemd-run)' "$F/calls.log" && fail "daemons touched although tar failed: $(calls)"
    return 0
}

case_failed_verify_rolls_back() {
    world e both
    local cfg0; cfg0="$(fp_config)"
    echo 'error in seclegion-host.lua' > "$F/configerrors"
    sl apply border && fail "apply succeeded despite configerrors"
    grep -q 'rolling back' "$C/out.log" || fail "no immediate rollback: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after failed apply"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "failed apply left pending"
    [ ! -f "$F/units/seclegion-host-deadman.timer" ] || fail "failed apply left the dead-man armed"
}

case_tty_rollback() {
    world f both
    local cfg0; cfg0="$(fp_config)"
    sl apply notifications || fail "apply: $(cat "$C/out.log")"
    unset WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE
    rm -f "$C/run/wayland-test"
    : > "$F/calls.log"
    sl rollback --last || fail "tty rollback: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after TTY rollback"
    grep -q 'no Wayland session' "$C/out.log" || fail "no TTY notice"
    grep -qE '^(kill|systemd-run)' "$F/calls.log" && fail "TTY rollback touched daemons: $(calls)"
    return 0
}

case_signal_mid_apply_rolls_back() {
    world i both
    local cfg0; cfg0="$(fp_config)"
    # The swaync stub hangs up the tool while the notification daemon is being swapped.
    cat > "$C/bin/swaync" <<STUB
#!/bin/bash
# Hang up the outermost seclegion-host (subshells share its cmdline), once.
p=\$PPID top=
while [ "\$p" -gt 1 ]; do
    grep -qaF "$R/tools/seclegion-host" "/proc/\$p/cmdline" 2>/dev/null && top=\$p
    p=\$(awk '/^PPid:/{print \$2}' "/proc/\$p/status")
done
if [ -n "\$top" ] && [ ! -e "$F/hup-sent" ]; then : > "$F/hup-sent"; kill -HUP "\$top"; fi
exec bash $(printf %q "$SRC/tests/host/fake-host") swaync "\$0" "\$@"
STUB
    chmod +x "$C/bin/swaync"
    sl apply notifications && fail "apply survived SIGHUP"
    grep -q 'rolling back' "$C/out.log" || fail "no rollback on SIGHUP: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after interrupted apply"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "interrupted apply left pending"
}

case_waybar_unit_installed_and_removed() {
    world m both
    mkdir -p "$H/.config/systemd/user/default.target.wants"   # the owner's real layout
    local all0 u="$H/.config/systemd/user/seclegion-wsevents.service" b="$H/.local/share/seclegion/host"
    all0="$(fp_config)"
    sl apply waybar || fail "apply waybar: $(cat "$C/out.log")"
    [ -f "$u" ] && grep -q '^ExecStart=%h/.local/share/seclegion/host/bin/seclegion-wsevents$' "$u" || fail "unit file"
    [ -L "$H/.config/systemd/user/default.target.wants/seclegion-wsevents.service" ] || fail "unit not enabled"
    [ "$(cat "$F/units/seclegion-wsevents.service")" = active ] || fail "unit not started"
    for h in seclegion-ws seclegion-wsevents seclegion-vpn seclegion-sec seclegion-gpu seclegion-uptime seclegion-dnd seclegion-ai seclegion-sysmon seclegion-wifi; do
        [ "$(stat -c %a "$b/bin/$h")" = 755 ] || fail "$h not 755"
        [ ! -e "$b/waybar/$h" ] || fail "$h left in the waybar dir"
    done
    [ "$(ls "$b/bin" | tr '\n' ' ')" = "nm-applet python seclegion-ai seclegion-dnd seclegion-gpu seclegion-sec seclegion-sysmon seclegion-uptime seclegion-vpn seclegion-wifi seclegion-ws seclegion-wsevents " ] || fail "bin holds: $(ls "$b/bin")"
    [ -f "$b/bin/python/seclegion_sysmon/__init__.py" ] || fail "sysmon python tree not staged"
    [ ! -e "$b/bin/python/seclegion_sysmon/__pycache__" ] || fail "pycache staged"
    [ -f "$b/bin/python/seclegion_wifi/ui/window.py" ] || fail "wifi python tree not staged"
    [ ! -e "$b/bin/python/seclegion_wifi/__pycache__" ] || fail "wifi pycache staged"
    ls "$b"/waybar/*.in "$b"/waybar/*.service > /dev/null 2>&1 && fail "template or unit left in the installed waybar dir"
    [ "$(grep -c '"custom/ws[0-9]*": {' "$b/waybar/config.jsonc")" = 20 ] || fail "installed config lacks the 20 pills"
    grep -q 'systemctl --user daemon-reload' "$F/calls.log" || fail "no daemon-reload"
    grep -q 'systemctl --user enable --now seclegion-wsevents.service' "$F/calls.log" || fail "no enable --now"
    grep -q '^systemctl --user restart waybar' "$F/calls.log" || fail "waybar not restarted"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    [ ! -e "$u" ] && [ ! -L "$H/.config/systemd/user/default.target.wants/seclegion-wsevents.service" ] || fail "unit not removed"
    [ ! -e "$b/bin" ] || fail "host/bin left behind"
    [ ! -f "$F/units/seclegion-wsevents.service" ] || fail "unit still running after rollback"
    [ "$(fp_config)" = "$all0" ] || { diff <(echo "$all0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

case_waybar_unit_survives_rollback_to_previous_apply() {
    world n both
    mkdir -p "$H/.config/systemd/user/default.target.wants"
    local u="$H/.config/systemd/user/seclegion-wsevents.service" b="$H/.local/share/seclegion/host" h1
    sl apply waybar && sl confirm || fail "apply 1: $(cat "$C/out.log")"
    h1="$(sha256sum < "$b/bin/seclegion-wsevents")"
    echo '# v2' >> "$R/desktop/waybar/seclegion-wsevents"
    sl apply waybar || fail "apply 2: $(cat "$C/out.log")"
    [ "$(sha256sum < "$b/bin/seclegion-wsevents")" != "$h1" ] || fail "apply 2 did not install the new helper"
    : > "$F/calls.log"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    [ "$(sha256sum < "$b/bin/seclegion-wsevents")" = "$h1" ] || fail "helper not restored to apply 1"
    [ -f "$u" ] && [ -L "$H/.config/systemd/user/default.target.wants/seclegion-wsevents.service" ] || fail "unit lost by rollback to apply 1"
    [ "$(cat "$F/units/seclegion-wsevents.service")" = active ] || fail "unit not running again"
    grep -q 'systemctl --user daemon-reload' "$F/calls.log" || fail "no daemon-reload after rollback"
}

# an unreachable user manager (daemon-reload fails) must not abort the rollback
# after the files are restored: waybar is still restarted and ROLLED_BACK written
case_rollback_survives_daemon_reload_failure() {
    world o both
    local u="$H/.config/systemd/user/seclegion-wsevents.service" b="$H/.local/share/seclegion/host" id2 h1
    sl apply waybar && sl confirm || fail "apply 1: $(cat "$C/out.log")"
    h1="$(sha256sum < "$b/bin/seclegion-wsevents")"
    echo '# v2' >> "$R/desktop/waybar/seclegion-wsevents"
    sl apply waybar || fail "apply 2: $(cat "$C/out.log")"
    id2="$(last_id)"
    : > "$F/daemon-reload-fails"
    : > "$F/calls.log"
    sl rollback --last || fail "rollback aborted: $(cat "$C/out.log")"
    grep -q 'systemctl --user daemon-reload' "$F/calls.log" || fail "daemon-reload not attempted"
    grep -q 'warning: systemctl --user daemon-reload failed' "$C/out.log" || fail "no warning: $(cat "$C/out.log")"
    [ -f "$BK/$id2/ROLLED_BACK" ] || fail "ROLLED_BACK not written"
    grep -q '^systemctl --user restart waybar' "$F/calls.log" || fail "waybar not restarted"
    grep -q '^systemctl --user start seclegion-wsevents.service' "$F/calls.log" || fail "wsevents not started again"
    [ "$(sha256sum < "$b/bin/seclegion-wsevents")" = "$h1" ] && [ -f "$u" ] || fail "files not restored to apply 1"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "still pending"
}

case_rollback_survives_user_manager_down() {
    world p both
    local id2
    sl apply waybar && sl confirm || fail "apply 1: $(cat "$C/out.log")"
    echo '# v2' >> "$R/desktop/waybar/seclegion-wsevents"
    sl apply waybar || fail "apply 2: $(cat "$C/out.log")"
    id2="$(last_id)"
    : > "$F/manager-down"
    sl rollback --last || fail "rollback aborted: $(cat "$C/out.log")"
    grep -q 'warning: could not restart waybar' "$C/out.log" || fail "no restart warning: $(cat "$C/out.log")"
    [ -f "$BK/$id2/ROLLED_BACK" ] || fail "ROLLED_BACK not written"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "still pending"
}

case_lock_apply_rollback() {
    world j both
    local cfg0 orig_sha lock="$H/.config/hypr/hyprlock.conf" inst="$H/.local/share/seclegion/host/lock/hyprlock.conf"
    cfg0="$(fp_config)"
    orig_sha="$(sha256sum < "$H/.config/hyprland-dotfiles/hypr/hyprlock.conf")"
    [ ! -e "$H/.local/state/seclegion/theme/current" ] || fail "world already has a theme"

    # a misspelt key (the original bug: text_color is not an input-field key) is refused before any change
    sed -i 's/^    font_color = /    text_color = /' "$R/desktop/hypr/hyprlock.conf"
    sl apply lock && fail "apply accepted an input-field without font_color / with an unknown key"
    grep -q 'text_color' "$C/out.log" || fail "validator did not name the bad key: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed by a refused apply"
    [ -z "$(ls -1d "$BK"/2*Z-* 2>/dev/null)" ] || fail "refused apply left a backup: $(ls "$BK")"
    cp "$SRC/desktop/hypr/hyprlock.conf" "$R/desktop/hypr/hyprlock.conf"

    sl apply lock || fail "apply lock: $(cat "$C/out.log")"
    grep -q 'lock-source-ok' "$C/out.log" || fail "no lock-source-ok: $(cat "$C/out.log")"
    echo "    $(grep -o 'lock-source-ok' "$C/out.log")"
    [ -L "$lock" ] || fail "hyprlock.conf is not a symlink"
    [ "$(readlink "$lock")" = "$inst" ] || fail "symlink points at $(readlink "$lock")"
    [ "$(readlink -f "$lock")" = "$(readlink -f "$inst")" ] || fail "symlink does not resolve"
    cmp -s "$inst" "$SRC/desktop/hypr/hyprlock.conf" || fail "installed file differs from the repo"
    grep -qE '^[[:space:]]*font_color[[:space:]]*= \$sl_text$' "$lock" || fail "no font_color = \$sl_text"
    [ -f "$H/.local/state/seclegion/theme/current/hyprlock-colors.conf" ] || fail "default theme not seeded"
    grep -q '^\$sl_text = rgba(' "$H/.local/state/seclegion/theme/current/hyprlock-colors.conf" || fail "seeded theme lacks \$sl_text"
    [ -f "$F/units/seclegion-host-deadman.timer" ] || fail "dead-man not armed"
    grep -q -- '--on-active=120' "$F/calls.log" || fail "dead-man not 120 s"
    grep -q '^hyprctl reload' "$F/calls.log" && fail "lock must not reload Hyprland"
    grep -q hyprlock "$F/calls.log" && fail "hyprlock was run"
    [ "$(owner_comm)" = dunst ] || fail "lock touched the notification owner"

    sl rollback || fail "rollback: $(cat "$C/out.log")"
    [ ! -L "$lock" ] || fail "hyprlock.conf is still a symlink"
    [ "$(sha256sum < "$lock")" = "$orig_sha" ] || fail "hyprlock.conf is not byte-identical"
    [ "$(stat -c %a "$lock")" = 640 ] || fail "hyprlock.conf mode changed"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
    [ ! -e "$H/.local/share/seclegion/host/lock" ] || fail "installed lock tree left behind"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "still pending"
}

theme_cli() { XDG_STATE_HOME="$H/.local/state" "$R/tools/seclegion-theme" "$@"; }
theme_tree() { (cd "$H/.local/state/seclegion/theme/current" && find . -printf '%y %m %p %l %T@\n' | sort && find . -type f -print0 | sort -z | xargs -0 sha256sum); }

case_legacy_theme_dir_migrated() {
    world k both
    local cur="$H/.local/state/seclegion/theme/current" before
    # what the old host tool left: current/ a real directory holding only colors.css
    mkdir -p "$cur"
    printf '/* legacy seed */\n@define-color sl_bg #000000;' > "$cur/colors.css"
    chmod 640 "$cur/colors.css"
    touch -d '2020-01-02 03:04:05' "$cur/colors.css" "$cur"
    before="$(theme_tree)"
    theme_cli current > /dev/null 2>&1 && fail "the legacy dir should not count as an applied theme"

    sl apply lock || fail "apply lock: $(cat "$C/out.log")"
    [ -L "$cur" ] || fail "theme/current is not a symlink after apply"
    for f in hyprlock-colors.conf colors.css colors.json; do [ -s "$cur/$f" ] || fail "no $f under current"; done
    theme_cli current > "$C/theme.log" 2>&1 || fail "seclegion-theme current failed: $(cat "$C/theme.log")"
    theme_cli apply --no-hooks --mode default > "$C/theme.log" 2>&1 || fail "seclegion-theme apply failed: $(cat "$C/theme.log")"
    grep -q '^\$sl_text = rgba(' "$cur/hyprlock-colors.conf" || fail "no \$sl_text in the engine's lock colours"
    grep -q 'lock-source-ok' "$C/out.log" || fail "no lock-source-ok"
    python3 - "$BK/$(last_id)/manifest.json" <<'PY' || fail "manifest has no theme record"
import json, sys
t = json.load(open(sys.argv[1]))["theme"]
assert t["before"] == "moved" and len(t["created"]) == 1, t
PY
    [ "$(cat "$BK/$(last_id)/theme-current-legacy/colors.css")" = "$(printf '/* legacy seed */\n@define-color sl_bg #000000;')" ] \
        || fail "the old directory is not in the backup"

    sl rollback || fail "rollback: $(cat "$C/out.log")"
    [ -d "$cur" ] && [ ! -L "$cur" ] || fail "theme/current is not the real directory again"
    [ "$(theme_tree)" = "$before" ] || { diff <(echo "$before") <(theme_tree) >&2; fail "legacy theme dir differs after rollback"; }
    [ "$(ls -A "$H/.local/state/seclegion/theme" | tr '\n' ' ')" = "current " ] \
        || fail "theme dirs left behind: $(ls -A "$H/.local/state/seclegion/theme")"
}

case_theme_created_removed_on_rollback() {
    world l both
    local root="$H/.local/state/seclegion/theme" link1 n1
    [ ! -e "$root" ] || fail "world already has theme state"

    sl apply waybar || fail "apply waybar: $(cat "$C/out.log")"
    [ -L "$root/current" ] || fail "theme/current is not a symlink"
    theme_cli current > "$C/theme.log" 2>&1 || fail "seclegion-theme current failed: $(cat "$C/theme.log")"
    local id1; id1="$(last_id)"
    sl confirm || fail "confirm"
    link1="$(readlink "$root/current")" n1="$(ls -A "$root" | wc -l)"

    sl apply notifications || fail "apply notifications: $(cat "$C/out.log")"
    [ "$(readlink "$root/current")" = "$link1" ] && [ "$(ls -A "$root" | wc -l)" = "$n1" ] \
        || fail "a valid theme symlink was touched by the second apply"
    [ ! -e "$BK/$(last_id)/theme-undo" ] || fail "second apply recorded a theme change"
    sl rollback || fail "rollback 2: $(cat "$C/out.log")"
    [ "$(readlink "$root/current")" = "$link1" ] || fail "rolling back an apply that did not touch the theme removed it"

    sl rollback "$id1" || fail "rollback 1: $(cat "$C/out.log")"
    [ ! -e "$root" ] && [ ! -L "$root/current" ] || fail "theme state left behind: $(find "$root" 2>&1)"

    # baseline-0 undoes the theme change too
    sl apply waybar || fail "apply again: $(cat "$C/out.log")"
    [ -L "$root/current" ] || fail "theme/current is not a symlink (again)"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ ! -e "$root" ] || fail "baseline-0 left theme state: $(find "$root" 2>&1)"
}

# a fake ~/.themes with a Graphite-Mono-like gtk-4.0 and the owner's real layout around it
gtk_fixture() {
    mkdir -p "$H/.themes/Graphite-Mono/gtk-4.0/assets" "$H/.config/gtk-3.0" "$H/.config/qt6ct" "$H/.local/share"
    printf '@define-color accent_color #123456;\n' > "$H/.themes/Graphite-Mono/gtk-4.0/gtk.css"
    printf '@define-color accent_color #654321;\n' > "$H/.themes/Graphite-Mono/gtk-4.0/gtk-dark.css"
    echo svg > "$H/.themes/Graphite-Mono/gtk-4.0/assets/a.svg"; echo png > "$H/.themes/Graphite-Mono/gtk-4.0/thumbnail.png"
    ln -s "$H/.themes/Graphite-Mono/gtk-4.0" "$H/.config/gtk-4.0"
    printf '[Settings]\ngtk-theme-name=x\n' > "$H/.config/gtk-3.0/settings.ini"
    printf '[ColorScheme]\nactive_colors=#fff\n' > "$H/.config/qt6ct/colors.conf"
    printf '[Icons]\nTheme=Tela\n\n[General]\nTerminalApplication=kitty\n' > "$H/.config/kdeglobals"
}
themes_tree() { (cd "$H/.themes" && find . -printf '%y %m %p %l %T@\n' | sort; find . -type f -print0 | sort -z | xargs -0 sha256sum); }

case_gtk_apply_rollback() {
    world w both
    gtk_fixture
    local cfg0 th0 old g4="$H/.config/gtk-4.0" cur="$H/.local/state/seclegion/theme/current"
    cfg0="$(fp_config)" th0="$(themes_tree)" old="$(readlink "$g4")"
    # a gtk.css that is not ours is never replaced
    printf '/* mine */\n' > "$H/.config/gtk-3.0/gtk.css"
    sl apply gtk && fail "apply replaced a foreign gtk-3.0/gtk.css"
    grep -q 'not ours' "$C/out.log" || fail "refusal message: $(cat "$C/out.log")"
    [ -z "$(ls -1d "$BK"/2*Z-* 2>/dev/null)" ] && [ "$(cat "$H/.config/gtk-3.0/gtk.css")" = '/* mine */' ] || fail "refused apply changed something"
    rm "$H/.config/gtk-3.0/gtk.css"

    sl apply gtk || fail "apply gtk: $(cat "$C/out.log")"
    grep -q 'gtk-ok' "$C/out.log" || fail "no gtk-ok"
    [ -d "$g4" ] && [ ! -L "$g4" ] || fail "gtk-4.0 is not a real directory"
    [ "$(sed -n 's/^old_target=//p' "$g4/.seclegion-managed")" = "$old" ] || fail "old target not recorded"
    grep -qxF "@import url(\"file://$old/gtk.css\");" "$g4/gtk.css" || fail "gtk.css lacks the Graphite import: $(cat "$g4/gtk.css")"
    grep -qxF "@import url(\"file://$cur/gtk4.css\");" "$g4/gtk.css" || fail "gtk.css lacks our import"
    grep -qxF "@import url(\"file://$old/gtk-dark.css\");" "$g4/gtk-dark.css" || fail "gtk-dark.css lacks the Graphite import"
    [ "$(readlink "$g4/assets")" = "$old/assets" ] && [ "$(readlink "$g4/thumbnail.png")" = "$old/thumbnail.png" ] || fail "entries are not links into the old target"
    grep -qF 'seclegion-host:managed gtk3' "$H/.config/gtk-3.0/gtk.css" && grep -qF "file://$cur/gtk3.css" "$H/.config/gtk-3.0/gtk.css" || fail "gtk-3.0/gtk.css"
    [ "$(readlink "$H/.local/share/color-schemes/SecLegion.colors")" = "$cur/kde.colors" ] || fail "kde colours link"
    [ "$(readlink "$H/.config/qt6ct/colors/SecLegion.conf")" = "$cur/qt6ct.conf" ] || fail "qt6ct colours link"
    [ "$(cat "$H/.config/qt6ct/colors.conf")" = "$(printf '[ColorScheme]\nactive_colors=#fff')" ] || fail "qt6ct colors.conf touched"
    [ "$(cat "$H/.config/kdeglobals")" = "$(printf '[Icons]\nTheme=Tela\n\n[General]\nTerminalApplication=kitty\nColorScheme=SecLegion')" ] \
        || fail "kdeglobals: $(cat "$H/.config/kdeglobals")"
    [ "$(themes_tree)" = "$th0" ] || fail "something under ~/.themes changed during apply"
    grep -q 'next start' "$C/out.log" || fail "no 'next start' notice"
    # idempotent: a second apply keeps the first old target and the same files
    sl confirm || fail "confirm"
    sl apply gtk || fail "re-apply: $(cat "$C/out.log")"
    [ "$(sed -n 's/^old_target=//p' "$g4/.seclegion-managed")" = "$old" ] || fail "re-apply lost the old target"
    [ "$(grep -c '^ColorScheme=' "$H/.config/kdeglobals")" = 1 ] || fail "ColorScheme duplicated"
    sl rollback --last || fail "rollback 2: $(cat "$C/out.log")"
    [ -d "$g4" ] && [ ! -L "$g4" ] || fail "rolling back the re-apply lost the managed directory"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"

    [ -L "$g4" ] && [ "$(readlink "$g4")" = "$old" ] || fail "gtk-4.0 symlink not restored"
    echo "    gtk4-symlink-restored"
    [ "$(themes_tree)" = "$th0" ] || fail "~/.themes differs after apply + rollback"
    echo "    themes-untouched"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
    [ ! -e "$H/.local/share/color-schemes" ] || fail "color-schemes left behind"
}

case_gtk_refuses_themes_write() {
    world z both
    gtk_fixture
    # gtk-3.0 is a symlink into ~/.themes: writing gtk.css would write into it
    rm -rf "$H/.config/gtk-3.0"
    mkdir -p "$H/.themes/Graphite-Mono/gtk-3.0"
    ln -s "$H/.themes/Graphite-Mono/gtk-3.0" "$H/.config/gtk-3.0"
    local th0 cfg0; th0="$(themes_tree)" cfg0="$(fp_config)"
    sl apply gtk && fail "apply wrote through a symlink into ~/.themes"
    grep -q 'resolves into ~/.themes' "$C/out.log" || fail "refusal message: $(cat "$C/out.log")"
    [ "$(themes_tree)" = "$th0" ] || fail "~/.themes changed"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed by a refused apply"
}

case_gtk_old_theme_lacks_outputs() {
    world y both
    gtk_fixture
    local cfg0; cfg0="$(fp_config)"
    theme_cli reset --no-hooks > /dev/null 2>&1 || fail "theme reset"
    rm -f "$H/.local/state/seclegion/theme/current/gtk3.css"
    sl apply gtk && fail "apply gtk with a theme lacking gtk3.css"
    grep -q 'lacks gtk3.css' "$C/out.log" || fail "message: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed"
}

# L1: a qt6ct colour link left dangling (its theme dir was pruned) is reported, apply relinks it, the
# opt-in line names the owner's step and the kvantum style, a healthy link gets no warning, and a
# rollback puts the dangling link back
case_gtk_qt6ct_dangling() {
    world qt6dang both
    gtk_fixture
    local cfg0 lnk="$H/.config/qt6ct/colors/SecLegion.conf" cur="$H/.local/state/seclegion/theme/current"
    mkdir -p "$H/.config/qt6ct/colors"
    ln -s "$H/.local/state/seclegion/theme/gone/qt6ct.conf" "$lnk"
    [ -L "$lnk" ] && [ ! -e "$lnk" ] || fail "fixture link is not dangling"
    cfg0="$(fp_config)"
    sl apply gtk || fail "apply gtk: $(cat "$C/out.log")"
    grep -q "warning: qt6ct colour link $lnk is dangling" "$C/out.log" || fail "dangling link not reported: $(cat "$C/out.log")"
    grep -q 'qt6ct opt-in' "$C/out.log" && grep -q 'kvantum' "$C/out.log" || fail "no opt-in line: $(cat "$C/out.log")"
    [ "$(readlink "$lnk")" = "$cur/qt6ct.conf" ] && [ -s "$lnk" ] || fail "apply did not relink qt6ct"
    grep -q 'gtk-ok' "$C/out.log" || fail "no gtk-ok"
    [ "$(cat "$H/.config/qt6ct/colors.conf")" = "$(printf '[ColorScheme]\nactive_colors=#fff')" ] || fail "qt6ct colors.conf touched"
    sl confirm || fail "confirm"
    sl apply gtk || fail "re-apply: $(cat "$C/out.log")"
    grep -q 'is dangling' "$C/out.log" && fail "a healthy link was reported as dangling"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

fm_fixture() {
    mkdir -p "$H/.config/xfce4/xfconf/xfce-perchannel-xml" "$H/.config/yazi"
    printf '[Default Applications]\ninode/directory=org.kde.dolphin.desktop\ntext/html=brave-browser.desktop\n\n[Added Associations]\nx/y=z.desktop;' > "$H/.config/mimeapps.list"
    printf '<?xml version="1.1" encoding="UTF-8"?>\n\n<channel name="thunar" version="1.0">\n  <property name="last-view" type="string" value="ThunarIconView"/>\n</channel>\n' \
        > "$H/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml"
    printf 'MenuBar=Disabled\n\n[General]\nLockPanels=false\nShowStatusBar=false\nVersion=202\n\n[IconsMode]\nPreviewSize=128\n' > "$H/.config/dolphinrc"
    printf 'local mine = 1' > "$H/.config/yazi/init.lua"   # no trailing newline
    printf '# generated by seclegion-theme\n' > "$H/.config/yazi/theme.toml"
}

case_fm_apply_rollback() {
    world x both
    fm_fixture
    local cfg0 mime0 x="$H/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml" yz="$H/.config/yazi"
    cfg0="$(fp_config)" mime0="$(sha256sum < "$H/.config/mimeapps.list")"
    sl apply fm || fail "apply fm: $(cat "$C/out.log")"
    grep -q 'fm-ok' "$C/out.log" || fail "no fm-ok"
    grep -qx 'inode/directory=thunar.desktop' "$H/.config/mimeapps.list" || fail "mimeapps.list lacks inode/directory=thunar.desktop"
    echo "    mimeapps: $(grep '^inode/directory' "$H/.config/mimeapps.list")"
    [ "$(cat "$H/.config/mimeapps.list")" = "$(printf '[Default Applications]\ninode/directory=thunar.desktop\ntext/html=brave-browser.desktop\n\n[Added Associations]\nx/y=z.desktop;')" ] \
        || fail "mimeapps.list: more than the one key changed: $(cat "$H/.config/mimeapps.list")"
    grep -q 'name="last-view"' "$x" && [ "$(grep -c 'last-statusbar-visible' "$x")" = 1 ] && grep -q 'last-statusbar-visible" type="bool" value="true"' "$x" || fail "thunar.xml: $(cat "$x")"
    python3 -c 'import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])' "$x" || fail "thunar.xml no longer parses"
    grep -q 'running Thunar or xfconfd may overwrite' "$C/out.log" || fail "no xfconfd notice"
    [ "$(sed -n '/^\[General\]/,/^$/p' "$H/.config/dolphinrc" | tr '\n' ' ')" = '[General] LockPanels=false ShowStatusBar=FullWidth Version=202 ShowSpaceInfo=true  ' ] \
        || fail "dolphinrc [General]: $(cat "$H/.config/dolphinrc")"
    grep -qx 'MenuBar=Disabled' "$H/.config/dolphinrc" && grep -qx 'PreviewSize=128' "$H/.config/dolphinrc" || fail "dolphinrc other keys lost"
    cmp -s "$yz/plugins/seclegion-space.yazi/main.lua" "$SRC/desktop/fm/yazi/plugins/seclegion-space.yazi/main.lua" || fail "yazi plugin differs"
    [ "$(cat "$yz/init.lua")" = "$(printf 'local mine = 1\n-- seclegion-host: free space in the status bar (delete these two lines to disable)\nrequire("seclegion-space"):setup()')" ] \
        || fail "init.lua: $(cat "$yz/init.lua")"
    [ -f "$yz/theme.toml" ] || fail "yazi theme.toml lost"
    [ "$(cat "$yz/theme.toml")" = '# generated by seclegion-theme' ] || fail "yazi theme.toml touched"
    local h1; h1="$(fp_config)"
    sl confirm || fail confirm
    sl apply fm || fail "re-apply: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$h1" ] || { diff <(echo "$h1") <(fp_config) >&2; fail "re-apply changed files"; }
    grep -q '^hyprctl reload' "$F/calls.log" && fail "fm reloaded Hyprland"
    sl rollback baseline-0 || fail "rollback: $(cat "$C/out.log")"
    [ "$(sha256sum < "$H/.config/mimeapps.list")" = "$mime0" ] || fail "mimeapps.list not byte-identical after rollback"
    echo "    mimeapps-restored"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

case_fm_fresh_home_and_refusals() {
    world y2 both
    local cfg0 yz="$H/.config/yazi" x="$H/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml"
    cfg0="$(fp_config)"
    # a symlinked yazi dir (dotfiles repo) is refused before any change
    mkdir -p "$C/yazi-dotfiles"; ln -s "$C/yazi-dotfiles" "$yz"
    sl apply fm && fail "apply wrote through a symlinked yazi dir"
    grep -q 'is a symlink' "$C/out.log" || fail "message: $(cat "$C/out.log")"
    [ -z "$(ls -A "$C/yazi-dotfiles")" ] || fail "wrote into the symlink target"
    rm "$yz"
    sl apply fm || fail "apply on a fresh home: $(cat "$C/out.log")"
    [ "$(cat "$H/.config/mimeapps.list")" = "$(printf '[Default Applications]\ninode/directory=thunar.desktop')" ] || fail "mimeapps: $(cat "$H/.config/mimeapps.list")"
    cmp -s "$x" "$SRC/desktop/fm/thunar.xml" || fail "thunar.xml is not the repo copy"
    grep -qx 'ShowStatusBar=FullWidth' "$H/.config/dolphinrc" && grep -qx '\[General\]' "$H/.config/dolphinrc" || fail "dolphinrc"
    [ "$(grep -c seclegion-space "$yz/init.lua")" = 1 ] || fail "init.lua: $(cat "$yz/init.lua")"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

# settings: files only (no daemon, no theme state); the wrapper must run from the fake HOME
case_settings_apply_rollback() {
    world sett1 both
    local inst="$H/.local/share/seclegion/host/settings" bin="$H/.local/bin" app="$H/.local/share/applications/seclegion-settings.desktop"
    local cfg0 h1 f; cfg0="$(fp_config)"
    sl apply settings || fail "apply settings: $(cat "$C/out.log")"
    grep -q 'settings-ok' "$C/out.log" || fail "no settings-ok"
    for f in seclegion-set seclegion-settings seclegion-root-apply seclegion-theme; do [ -x "$inst/$f" ] || fail "$f not installed executable"; done
    [ "$(stat -c %a "$inst/seclegion-root-apply")" = 755 ] || fail "seclegion-root-apply is not 0755"
    [ -d "$inst/python/seclegion_settings" ] && [ -d "$inst/python/seclegion_theme" ] || fail "python packages missing"
    [ -z "$(find "$inst" -name __pycache__)" ] || fail "__pycache__ was installed"
    [ "$(head -n1 "$bin/seclegion-set")" = '#!/usr/bin/python3 -I' ] || fail "wrapper shebang"
    grep -qF "sys.path.insert(0, \"$inst/python\")" "$bin/seclegion-set" || fail "wrapper lacks the baked path"
    [ -x "$bin/seclegion-settings" ] || fail "seclegion-settings wrapper not executable"
    # the picker: a marked bash copy beside the seclegion-theme wrapper it runs
    [ -x "$bin/seclegion-theme-pick" ] && [ "$(head -n1 "$bin/seclegion-theme-pick")" = '#!/bin/bash' ] || fail "seclegion-theme-pick not installed executable"
    grep -qF 'seclegion-host:managed settings' "$bin/seclegion-theme-pick" || fail "picker lacks our marker"
    [ "$(sed 1,3d "$bin/seclegion-theme-pick" | sed 1d)" = "$(sed 1,3d "$SRC/tools/seclegion-theme-pick")" ] || fail "installed picker differs from the repo copy"
    [ -x "$bin/seclegion-theme" ] && grep -qF "sys.path.insert(0, \"$inst/python\")" "$bin/seclegion-theme" || fail "seclegion-theme wrapper missing or lacks the baked path"
    # the doctor: a marked executable copy of the repo tool
    [ -x "$bin/seclegion-doctor" ] && grep -qF 'seclegion-host:managed settings' "$bin/seclegion-doctor" || fail "seclegion-doctor missing, not executable or unmarked"
    [ "$(sed 4d "$bin/seclegion-doctor")" = "$(cat "$SRC/tools/seclegion-doctor")" ] || fail "installed doctor differs from the repo copy"
    grep -qx 'Categories=Settings;System;' "$app" && grep -qx "Exec=$bin/seclegion-settings" "$app" || fail "desktop entry: $(cat "$app")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed"
    grep -q '^hyprctl reload' "$F/calls.log" && fail "settings reloaded Hyprland"
    [ ! -e "$H/.local/state/seclegion/theme" ] || fail "settings touched the theme state"
    sl confirm || fail confirm
    h1="$(fp)"
    sl apply settings || fail "re-apply: $(cat "$C/out.log")"
    [ "$(fp)" = "$h1" ] || { diff <(echo "$h1") <(fp) >&2; fail "re-apply changed files"; }
    # the wrapper runs from the fake HOME with the host's environment cleared (-I writes __pycache__: last)
    (cd "$H" && env -i HOME="$H" PATH=/usr/bin:/bin "$bin/seclegion-set" --help > "$C/set-help.log" 2>&1) \
        || fail "seclegion-set --help failed: $(cat "$C/set-help.log")"
    # the installed theme CLI must find tokens.toml (it loads it before any subcommand)
    [ -f "$inst/python/tokens.toml" ] || fail "settings did not install python/tokens.toml"
    sl rollback baseline-0 || fail "rollback: $(cat "$C/out.log")"
    [ ! -e "$inst" ] && [ ! -e "$bin/seclegion-set" ] && [ ! -e "$bin/seclegion-settings" ] && [ ! -e "$app" ] \
        && [ ! -e "$bin/seclegion-theme-pick" ] && [ ! -e "$bin/seclegion-theme" ] && [ ! -e "$bin/seclegion-doctor" ] \
        || fail "rollback left settings files: $(cd "$H" && find .local -type f | grep -v host-backups)"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after rollback"
}

case_settings_refuses_foreign_files() {
    world sett2 both
    mkdir -p "$H/.local/bin"
    printf '#!/bin/sh\necho mine\n' > "$H/.local/bin/seclegion-set"
    sl apply settings && fail "apply replaced a file that is not ours"
    grep -q 'is not ours' "$C/out.log" || fail "message: $(cat "$C/out.log")"
    grep -q '^echo mine$' "$H/.local/bin/seclegion-set" || fail "foreign wrapper touched"
    [ ! -e "$H/.local/share/seclegion/host/settings" ] || fail "installed before the refusal"
}

# a picker of the owner's own is never replaced either
case_settings_refuses_foreign_picker() {
    world sett3 both
    mkdir -p "$H/.local/bin"
    printf '#!/bin/sh\necho mypick\n' > "$H/.local/bin/seclegion-theme-pick"
    sl apply settings && fail "apply replaced a picker that is not ours"
    grep -q 'is not ours' "$C/out.log" || fail "message: $(cat "$C/out.log")"
    grep -q '^echo mypick$' "$H/.local/bin/seclegion-theme-pick" || fail "foreign picker touched"
    [ ! -e "$H/.local/share/seclegion/host/settings" ] && [ ! -e "$H/.local/bin/seclegion-set" ] || fail "installed before the refusal"
}

# keys loads through the border's seclegion-host.lua: worlds for keys get border applied and
# confirmed first, and the owner's keybinds.lua (the committed snapshot)
nkeys() { grep -c '^[[:space:]]*hl\.bind(' "$SRC/desktop/hypr/seclegion-keys.lua"; }   # binds in the committed file, submap ones included

keys_world() {
    world "$1" both
    cp "$SRC/tests/keys/fixtures/owner-keybinds.lua" "$H/.config/hypr/modules/keybinds.lua"
    sl apply border && sl confirm || fail "apply border: $(cat "$C/out.log")"
    : > "$F/calls.log"
}

case_keys_apply_rollback() {
    keys_world q
    local cfg0 link="$H/.config/hypr/seclegion-keys.lua" inst="$H/.local/share/seclegion/host/keys/seclegion-keys.lua"
    grep -q '^local keys_ok, keys_err = pcall(require, "seclegion-keys")$' "$H/.config/hypr/seclegion-host.lua" \
        || fail "installed seclegion-host.lua lacks the guarded require"
    cfg0="$(fp_config)"
    sl apply keys || fail "apply keys: $(cat "$C/out.log")"
    grep -q 'keys: collisions=0' "$C/out.log" || fail "no lint verdict: $(cat "$C/out.log")"
    grep -q "keys: $(nkeys) binds live" "$C/out.log" || fail "no bind count: $(cat "$C/out.log")"
    [ "$(readlink "$link")" = "$inst" ] || fail "seclegion-keys.lua -> $(readlink "$link")"
    cmp -s "$inst" "$SRC/desktop/hypr/seclegion-keys.lua" || fail "installed keys differ from the repo"
    grep -q '^hyprctl binds -j' "$F/calls.log" || fail "live binds not read"
    grep -q '^hyprctl reload' "$F/calls.log" || fail "Hyprland not reloaded"
    grep -q '^hyprctl configerrors' "$F/calls.log" || fail "configerrors not checked"
    grep -qE '^hyprctl (dispatch|keyword)' "$F/calls.log" && fail "keys sent a dispatch/keyword"
    [ -f "$F/units/seclegion-host-deadman.timer" ] || fail "dead-man not armed"
    tar -tf "$BK/$(last_id)/files.tar" | grep -q . && fail "first keys apply backed up files: $(tar -tf "$BK/$(last_id)/files.tar")"
    : > "$F/calls.log"
    sl rollback || fail "rollback: $(cat "$C/out.log")"
    [ ! -e "$link" ] && [ ! -L "$link" ] || fail "seclegion-keys.lua left behind"
    [ ! -e "$H/.local/share/seclegion/host/keys" ] || fail "installed keys left behind"
    grep -q '^hyprctl reload' "$F/calls.log" || fail "rollback did not reload Hyprland"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "still pending"
}

case_keys_needs_border() {
    world r both
    cp "$SRC/tests/keys/fixtures/owner-keybinds.lua" "$H/.config/hypr/modules/keybinds.lua"
    local cfg0; cfg0="$(fp_config)"
    sl apply keys && fail "keys applied without border"
    grep -q 'Apply border first' "$C/out.log" || fail "no border hint: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed by a refused apply"
    [ ! -e "$BK" ] || fail "refused apply left backups: $(ls "$BK")"
}

case_keys_collision_refused() {
    keys_world s
    local cfg0; cfg0="$(fp_config)"
    # a live bind the owner's file does not show (Super+period, from elsewhere) takes our Super+.
    printf '[{"modmask": 64, "key": "period", "keycode": 0, "submap": "", "description": ""}]\n' > "$F/binds.json"
    sl apply keys && fail "keys applied over a live bind"
    grep -q 'collisions=1' "$C/out.log" || fail "lint verdict missing: $(cat "$C/out.log")"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config changed by a refused apply"
    grep -q '^hyprctl reload' "$F/calls.log" && fail "a refused apply reloaded Hyprland"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "refused apply left pending"
}

case_keys_configerrors_rolls_back() {
    keys_world t
    local cfg0; cfg0="$(fp_config)"
    echo 'seclegion-keys.lua:3: hl.bind: failed to parse key string' > "$F/configerrors"
    sl apply keys && fail "apply succeeded despite configerrors"
    grep -q 'rolling back' "$C/out.log" || fail "no immediate rollback: $(cat "$C/out.log")"
    [ ! -L "$H/.config/hypr/seclegion-keys.lua" ] || fail "seclegion-keys.lua left behind"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after failed apply"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "failed apply left pending"
    [ ! -f "$F/units/seclegion-host-deadman.timer" ] || fail "failed apply left the dead-man armed"
}

# baseline-0 taken by a tool that had no keys component (the owner's live one):
# the next apply merges keys into it, so rollback baseline-0 removes keys too,
# and a later border + keys + rollback --last still removes keys.
case_baseline_extended_with_keys() {
    world u both
    cp "$SRC/tests/keys/fixtures/owner-keybinds.lua" "$H/.config/hypr/modules/keybinds.lua"
    local cfg0 link="$H/.config/hypr/seclegion-keys.lua" inst="$H/.local/share/seclegion/host/keys"
    cfg0="$(fp_config)"
    sed -i 's/^COMPONENTS=(border notifications waybar lock keys gtk fm settings osd)$/COMPONENTS=(border notifications waybar lock)/' "$R/tools/seclegion-host"
    grep -qx 'COMPONENTS=(border notifications waybar lock)' "$R/tools/seclegion-host" || fail "could not drop keys, gtk, fm, settings and osd from the tool"
    sl apply border && sl confirm || fail "apply border (old tool): $(cat "$C/out.log")"
    grep -q 'seclegion-keys' "$BK/baseline-0/rollback.sh" "$BK/baseline-0/manifest.json" && fail "baseline-0 already covers keys"
    grep -q 'gtk-3.0/gtk.css\|thunar.xml\|seclegion-settings.desktop' "$BK/baseline-0/rollback.sh" "$BK/baseline-0/manifest.json" && fail "baseline-0 already covers gtk, fm or settings"
    cp "$SRC/tools/seclegion-host" "$R/tools/seclegion-host"
    sl apply keys || fail "apply keys: $(cat "$C/out.log")"
    grep -q 'baseline-0: now also covers keys' "$C/out.log" || fail "baseline-0 not extended: $(cat "$C/out.log")"
    grep -q 'gtk-3.0/gtk.css' "$BK/baseline-0/manifest.json" && grep -q 'thunar.xml' "$BK/baseline-0/manifest.json" && grep -q 'seclegion-settings.desktop' "$BK/baseline-0/manifest.json" \
        || fail "baseline-0 not extended with the gtk and fm paths: $(cat "$C/out.log")"
    sl confirm || fail "confirm keys: $(cat "$C/out.log")"
    [ -L "$link" ] || fail "keys not applied"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ ! -e "$link" ] && [ ! -L "$link" ] || fail "rollback baseline-0 left seclegion-keys.lua"
    [ ! -e "$inst" ] || fail "rollback baseline-0 left the installed keys"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback baseline-0"; }
    sl apply border && sl confirm || fail "re-apply border: $(cat "$C/out.log")"
    sl apply keys && sl confirm || fail "re-apply keys: $(cat "$C/out.log")"
    sl rollback --last || fail "rollback --last: $(cat "$C/out.log")"
    [ ! -e "$link" ] && [ ! -L "$link" ] || fail "rollback --last left seclegion-keys.lua"
    [ ! -e "$inst" ] || fail "rollback --last left the installed keys"
}

# a runtime error inside seclegion-keys.lua is swallowed by the pcall: configerrors
# stays empty but no bind of ours is live -> immediate rollback
case_keys_runtime_error_rolls_back() {
    keys_world v
    local cfg0; cfg0="$(fp_config)"
    : > "$F/keys-runtime-error"
    sl apply keys && fail "apply succeeded with no seclegion-keys bind live"
    grep -q "0 of the $(nkeys) seclegion-keys binds are live" "$C/out.log" || fail "no bind-count verdict: $(cat "$C/out.log")"
    grep -q 'rolling back' "$C/out.log" || fail "no immediate rollback: $(cat "$C/out.log")"
    [ ! -L "$H/.config/hypr/seclegion-keys.lua" ] || fail "seclegion-keys.lua left behind"
    [ "$(fp_config)" = "$cfg0" ] || fail "~/.config differs after failed apply"
    [ ! -e "$H/.local/state/seclegion/host-pending" ] || fail "failed apply left pending"
}

# osd: two symlinks in ~/.local/bin (the dunstify shim and seclegion-osd) into the installed tree
case_osd_apply_rollback() {
    world osd1 both
    local all0 bin="$H/.local/bin" inst="$H/.local/share/seclegion/host/osd" f
    all0="$(fp)"
    sl apply osd || fail "apply osd: $(cat "$C/out.log")"
    for f in dunstify seclegion-osd; do
        [ "$(readlink "$bin/$f")" = "$inst/$f" ] || fail "$f -> $(readlink "$bin/$f")"
        [ -x "$bin/$f" ] || fail "$f is not executable"
        cmp -s "$inst/$f" "$SRC/desktop/osd/$f" || fail "installed $f differs from the repo"
    done
    grep -q 'osd-shim-ok' "$C/out.log" || fail "no shim verdict: $(cat "$C/out.log")"
    grep -q 'WARNING: the border component' "$C/out.log" || fail "no hint that border (the PATH line) is missing: $(cat "$C/out.log")"
    grep -qE '^hyprctl (reload|dispatch|keyword)' "$F/calls.log" && fail "osd touched Hyprland"
    [ -f "$F/units/seclegion-host-deadman.timer" ] || fail "dead-man not armed"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    # G5: nothing left behind
    if [ -e "$bin/dunstify" ] || [ -L "$bin/dunstify" ]; then echo present > "$C/g5"; else echo absent > "$C/g5"; fi
    [ "$(cat "$C/g5")" = absent ] || fail "dunstify left behind"
    [ ! -e "$bin/seclegion-osd" ] && [ ! -L "$bin/seclegion-osd" ] || fail "seclegion-osd left behind"
    [ ! -e "$inst" ] || fail "installed osd left behind"
    # the shared logo stays after any apply (only baseline-0 removes it)
    [ "$(fp | grep -v seclegion-logo.png)" = "$(grep -v seclegion-logo.png <<< "$all0")" ] || { diff <(echo "$all0") <(fp) >&2; fail "home differs after rollback"; }
}

# a real file at ~/.local/bin/dunstify is the owner's (or the binary itself): never replaced
case_osd_refuses_real_file() {
    world osd2 both
    mkdir -p "$H/.local/bin"
    printf '#!/bin/sh\necho mine\n' > "$H/.local/bin/dunstify"
    chmod 755 "$H/.local/bin/dunstify"
    local all0; all0="$(fp)"
    sl apply osd && fail "osd applied over a real file"
    grep -q 'refusing to replace it' "$C/out.log" || fail "no refusal message: $(cat "$C/out.log")"
    [ "$(fp)" = "$all0" ] || fail "a refused apply changed the home"
    [ ! -e "$BK" ] || fail "refused apply left backups: $(ls "$BK")"
}

nm_argv() {   # argv of the one running nm-applet, space separated (empty: none running)
    local d out="" n=0
    for d in "$F"/proc/*/; do
        [ -d "$d" ] && [ "$(cat "$d/comm")" = nm-applet ] || continue
        out="$(tr '\0' ' ' < "$d/cmdline")"; n=$((n + 1))
    done
    [ "$n" -le 1 ] || fail "$n nm-applet processes"
    printf '%s' "$out"
}

# waybar: nm-applet restarted by pid through the shim (no --indicator, still running: the secret
# agent stays), and a rollback starts the recorded `nm-applet --indicator` again
case_waybar_nm_applet_shim() {
    world nm1 both
    local bin="$H/.local/bin" old
    old="$(pids_of_nm)"
    [ "$(nm_argv)" = "nm-applet --indicator " ] || fail "world: $(nm_argv)"
    sl apply waybar || fail "apply waybar: $(cat "$C/out.log")"
    [ "$(readlink "$bin/nm-applet")" = "$H/.local/share/seclegion/host/bin/nm-applet" ] || fail "nm-applet -> $(readlink "$bin/nm-applet")"
    grep -q "^kill -TERM $old" "$F/calls.log" || fail "the old nm-applet was not stopped by pid $old"
    # G2: running, from the real binary (here its stub), without --indicator
    [ "$(nm_argv)" = "$C/bin/nm-applet " ] || fail "after apply nm-applet runs as: $(nm_argv)"
    grep -q 'nm-applet-secret-agent-ok' "$C/out.log" || fail "no verdict: $(cat "$C/out.log")"
    sl confirm || fail "confirm"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    # G6: the recorded command is back, the shim is gone
    [ "$(nm_argv)" = "$C/bin/nm-applet --indicator " ] || fail "after rollback nm-applet runs as: $(nm_argv)"
    if [ -e "$bin/nm-applet" ] || [ -L "$bin/nm-applet" ]; then fail "shim left behind"; fi
}

pids_of_nm() { pgrep -x -u "$(id -u)" nm-applet; }

# baseline-0 undoes it too; and a real file at ~/.local/bin/nm-applet is never replaced
case_waybar_nm_applet_baseline_and_refusal() {
    world nm2 both
    sl apply waybar && sl confirm || fail "apply: $(cat "$C/out.log")"
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ "$(nm_argv)" = "$C/bin/nm-applet --indicator " ] || fail "baseline-0 left nm-applet as: $(nm_argv)"
    world nm3 both
    mkdir -p "$H/.local/bin"
    printf '#!/bin/sh\necho mine\n' > "$H/.local/bin/nm-applet"
    local all0; all0="$(fp)"
    sl apply waybar && fail "waybar applied over a real file"
    grep -q 'refusing to replace it' "$C/out.log" || fail "no refusal message: $(cat "$C/out.log")"
    [ "$(fp)" = "$all0" ] || fail "a refused apply changed the home"
    [ "$(nm_argv)" = "nm-applet --indicator " ] || fail "a refused apply touched nm-applet"
}

# nm-applet not running: apply starts nothing, rollback starts nothing
case_waybar_nm_applet_not_running() {
    world nm4 both
    rm -rf -- "${F:?}/proc/$(pids_of_nm)"
    sl apply waybar || fail "apply: $(cat "$C/out.log")"
    [ -z "$(nm_argv)" ] || fail "apply started nm-applet: $(nm_argv)"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    [ -z "$(nm_argv)" ] || fail "rollback started nm-applet: $(nm_argv)"
}

case_idle_apply_rollback() {
    world idle1 both
    local inst="$H/.local/share/seclegion/host/idle" bin="$H/.local/bin/seclegion-autolock" ud="$H/.config/systemd/user"
    local cfg0 st="$F/units"; cfg0="$(fp_config)"
    local inh=seclegion-idle-inhibit.service idl=seclegion-idle.service
    [ ! -e "$H/.config/seclegion" ] || fail "fixture already has ~/.config/seclegion"
    sl apply idle || fail "apply idle: $(cat "$C/out.log")"
    grep -q 'idle-ok (default)' "$C/out.log" || fail "no idle-ok (default)"
    [ -x "$inst/seclegion-autolock" ] && [ -f "$inst/hypridle.conf.in" ] || fail "idle files not installed"
    [ -f "$ud/$inh" ] && [ -f "$ud/$idl" ] || fail "units not installed"
    [ "$(readlink -f -- "$bin")" = "$(readlink -f -- "$inst/seclegion-autolock")" ] || fail "seclegion-autolock link"
    [ "$("$bin" status)" = default ] || fail "a fresh apply is not default"
    [ ! -f "$st/$inh" ] && [ ! -f "$st/$idl" ] || fail "default left a unit running"
    grep -q '^hyprctl reload' "$F/calls.log" && fail "idle reloaded Hyprland"
    # a delay: both units run, the conf is rendered
    "$bin" set 15m > /dev/null || fail "set 15m"
    [ "$(cat "$st/$inh")" = active ] && [ "$(cat "$st/$idl")" = active ] || fail "15m: units not both active"
    grep -qx '    timeout = 900' "$inst/hypridle.conf" || fail "15m: conf lacks timeout = 900"
    sl confirm || fail confirm
    # re-apply with a delay in force: the state is kept and the units come back up
    sl apply idle || fail "re-apply: $(cat "$C/out.log")"
    grep -q 'idle-ok (15m)' "$C/out.log" || fail "re-apply lost the state: $(cat "$C/out.log")"
    [ "$(cat "$st/$inh")" = active ] && [ "$(cat "$st/$idl")" = active ] || fail "re-apply: units not active"
    "$bin" set never > /dev/null || fail "set never"
    [ ! -f "$st/$idl" ] && [ "$(cat "$st/$inh")" = active ] || fail "never: wrong units"
    # rollback of the re-apply restores the 15m state it started from
    sl rollback --last || fail "rollback --last: $(cat "$C/out.log")"
    [ "$(cat "$st/$inh")" = active ] && [ "$(cat "$st/$idl")" = active ] || fail "rollback --last did not restore the running units"
    [ "$("$bin" status 2>/dev/null)" = 15m ] || fail "rollback --last did not restore the state file"
    # rollback to the baseline: gone, stopped, no residue
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ ! -f "$st/$inh" ] && [ ! -f "$st/$idl" ] || fail "units still active after rollback"
    [ ! -e "$ud/$inh" ] && [ ! -e "$ud/$idl" ] && [ ! -e "$ud/default.target.wants/$inh" ] && [ ! -e "$ud/default.target.wants/$idl" ] \
        || fail "unit files left: $(ls -R "$ud")"
    [ ! -e "$inst" ] && [ ! -e "$bin" ] || fail "idle files left"
    [ ! -e "$H/.config/seclegion" ] || fail "~/.config/seclegion left behind: $(ls -A "$H/.config/seclegion")"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

case_theme_auto_apply_rollback() {
    world ta1 both
    local inst="$H/.local/share/seclegion/host/theme-auto" ud="$H/.config/systemd/user" st="$F/units"
    local pu=seclegion-theme-sync.path su=seclegion-theme-sync.service sh cfg0
    mkdir -p "$D/hypr/scripts"
    printf '#!/bin/bash\necho owner wallpaper script\n' > "$D/hypr/scripts/restore-wallpaper.sh"
    sh="$(sha256sum "$D"/hypr/scripts/*wallpaper*.sh)"; cfg0="$(fp_config)"
    sl apply theme-auto || fail "apply theme-auto: $(cat "$C/out.log")"
    grep -q 'theme-auto-ok' "$C/out.log" || fail "no theme-auto-ok"
    [ -f "$ud/$pu" ] && [ -f "$ud/$su" ] && [ -L "$ud/default.target.wants/$pu" ] || fail "units not installed and enabled"
    [ "$(cat "$st/$pu")" = active ] || fail "path unit not started"
    [ ! -f "$st/$su" ] || fail "the service was started by apply"
    [ -x "$inst/seclegion-theme" ] && [ -f "$inst/python/seclegion_theme/auto.py" ] && [ -f "$inst/python/tokens.toml" ] \
        || fail "private seclegion-theme copy missing"
    [ "$(HOME="$H" XDG_STATE_HOME="$H/.local/state" python3 -I -B "$inst/seclegion-theme" auto status)" = off ] || fail "auto is not off by default"
    [ ! -e "$H/.local/state/seclegion/theme/auto" ] || fail "apply wrote the auto state"
    grep -q '^hyprctl' "$F/calls.log" && grep '^hyprctl' "$F/calls.log" | grep -qE 'reload|keyword|dispatch' && fail "theme-auto touched Hyprland"
    [ "$(sha256sum "$D"/hypr/scripts/*wallpaper*.sh)" = "$sh" ] || fail "owner wallpaper script changed"
    sl rollback --last || fail "rollback: $(cat "$C/out.log")"
    [ "$(ls "$ud" | grep -c seclegion-theme-sync)" = 0 ] || fail "unit left: $(ls -R "$ud")"
    [ ! -e "$ud/default.target.wants/$pu" ] && [ ! -f "$st/$pu" ] && [ ! -e "$inst" ] || fail "theme-auto files or state left"
    [ "$(sha256sum "$D"/hypr/scripts/*wallpaper*.sh)" = "$sh" ] || fail "owner wallpaper script changed by rollback"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
}

case_display_apply_rollback() {
    world dsp1 both
    local inst="$H/.local/share/seclegion/host/display" ud="$H/.config/systemd/user" st="$F/units"
    local u=seclegion-displayd.service cfg0 m; cfg0="$(fp_config)"
    sl apply display || fail "apply display: $(cat "$C/out.log")"
    grep -q 'display-ok' "$C/out.log" || fail "no display-ok"
    [ -f "$ud/$u" ] && [ -L "$ud/default.target.wants/$u" ] || fail "unit not installed and enabled"
    grep -qx 'ExecStart=%h/.local/share/seclegion/host/display/seclegion-displayd' "$ud/$u" || fail "unit ExecStart"
    [ "$(cat "$st/$u")" = active ] || fail "displayd not started"
    [ -x "$inst/seclegion-displayd" ] && [ ! -e "$inst/$u" ] && [ ! -e "$inst/.sl-units" ] || fail "daemon copy wrong"
    [ "$(readlink "$H/.local/bin/seclegion-display-menu")" = "$inst/seclegion-display-menu" ] \
        || fail "display menu not linked into ~/.local/bin"
    m="$(ls -1d "$H"/.local/state/seclegion/host-backups/*-display | tail -n1)/manifest.json"
    [ "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["displayd_service"])' "$m")" = inactive ] \
        || fail "manifest lacks displayd_service=inactive"
    grep '^hyprctl' "$F/calls.log" | grep -qE 'reload|keyword|dispatch' && fail "display touched Hyprland"
    sl confirm || fail confirm
    # re-apply: the running daemon is restarted on the new copy; rollback --last keeps it running
    : > "$F/calls.log"
    sl apply display || fail "re-apply: $(cat "$C/out.log")"
    grep -qx "systemctl --user restart $u" "$F/calls.log" || fail "re-apply did not restart $u"
    sl rollback --last || fail "rollback --last: $(cat "$C/out.log")"
    [ -f "$ud/$u" ] && [ -L "$ud/default.target.wants/$u" ] && [ "$(cat "$st/$u")" = active ] \
        || fail "rollback --last did not bring back the running unit of the first apply"
    # rollback to the baseline: disabled, stopped, no residue
    sl rollback baseline-0 || fail "rollback baseline-0: $(cat "$C/out.log")"
    [ ! -f "$st/$u" ] || fail "displayd still active after rollback"
    [ ! -e "$ud/$u" ] && [ ! -e "$ud/default.target.wants/$u" ] && [ ! -e "$inst" ] \
        && [ ! -L "$H/.local/bin/seclegion-display-menu" ] || fail "display files left"
    [ "$(fp_config)" = "$cfg0" ] || { diff <(echo "$cfg0") <(fp_config) >&2; fail "~/.config differs after rollback"; }
    # a unit of that name without our marker is the owner's: refused, nothing changed
    world dsp2 both
    printf '[Service]\nExecStart=/bin/true\n' > "$H/.config/systemd/user/$u"
    cfg0="$(fp)"
    sl apply display && fail "display applied over a foreign unit"
    grep -q 'refusing to replace it' "$C/out.log" || fail "no refusal message: $(cat "$C/out.log")"
    [ "$(fp)" = "$cfg0" ] || fail "a refused apply changed the home"
}

BASE_PATH="$PATH"
rc=0
cases=(case_apply_refused_rollback case_reapply_rollback_last case_baseline_restarts_dunst
       case_confirm_stop_fails case_dup_swaync_collapsed case_tar_failure_fatal
       case_failed_verify_rolls_back case_tty_rollback case_signal_mid_apply_rolls_back
       case_lock_apply_rollback case_legacy_theme_dir_migrated case_theme_created_removed_on_rollback
       case_waybar_unit_installed_and_removed case_waybar_unit_survives_rollback_to_previous_apply
       case_rollback_survives_daemon_reload_failure
       case_rollback_survives_user_manager_down
       case_gtk_apply_rollback case_gtk_refuses_themes_write case_gtk_old_theme_lacks_outputs case_gtk_qt6ct_dangling
       case_fm_apply_rollback case_fm_fresh_home_and_refusals
       case_settings_apply_rollback case_settings_refuses_foreign_files case_settings_refuses_foreign_picker
       case_keys_apply_rollback case_keys_needs_border case_keys_collision_refused
       case_keys_configerrors_rolls_back case_baseline_extended_with_keys
       case_keys_runtime_error_rolls_back case_osd_apply_rollback case_osd_refuses_real_file
       case_waybar_nm_applet_shim case_waybar_nm_applet_baseline_and_refusal case_waybar_nm_applet_not_running
       case_idle_apply_rollback case_theme_auto_apply_rollback case_display_apply_rollback)
[ $# -eq 0 ] || cases=("$@")   # run only the named cases
for t in "${cases[@]}"; do
    (set -e; "$t")   # not in an if: errexit must stay on inside the case
    if [ $? -eq 0 ]; then echo "PASS: $t"; else
        echo "FAIL: $t" >&2
        log="$(ls -1t "$WORK"/case-*/all.log 2>/dev/null | head -n1)"
        [ -z "$log" ] || { echo "--- tool output (tail) ---" >&2; tail -n 30 "$log" >&2; }
        rc=1
    fi
done
exit $rc
