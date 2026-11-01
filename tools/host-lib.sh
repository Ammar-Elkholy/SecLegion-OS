#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# shellcheck shell=bash disable=SC2034
# Shared code for tools/seclegion-host and every generated rollback.sh.
#
# seclegion-host sources this file; when it takes a backup it copies this file
# verbatim into <backup>/rollback.sh behind a header of baked variables, so a
# rollback never depends on the repo, /mnt, Wayland or Python.
#
# Every live action goes through a PATH command (pgrep, kill, busctl,
# systemctl, systemd-run, hyprctl) so tests can stub them; PROC is /proc on the
# host and a fake tree in tests. Callers set: PROG HOME_DIR STATE DEADMAN PROC.

log() { printf '%s: %s\n' "${PROG:-seclegion-host}" "$*"; }
err() { printf '%s: ERROR: %s\n' "${PROG:-seclegion-host}" "$*" >&2; }

# Reach the owner's session from anywhere (TTY, dead-man unit, terminal).
session_env() {
    local s d best=""
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
    if [ -z "${WAYLAND_DISPLAY:-}" ]; then
        for s in "$XDG_RUNTIME_DIR"/wayland-[0-9]*; do
            if [ -S "$s" ]; then export WAYLAND_DISPLAY="${s##*/}"; break; fi
        done
    fi
    if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
        for d in "$XDG_RUNTIME_DIR"/hypr/*/; do
            if [ -d "$d" ] && { [ -z "$best" ] || [ "$d" -nt "$best" ]; }; then best="$d"; fi
        done
        if [ -n "$best" ]; then best="${best%/}"; export HYPRLAND_INSTANCE_SIGNATURE="${best##*/}"; fi
    fi
    return 0
}
has_wayland() { [ -n "${WAYLAND_DISPLAY:-}" ] && [ -e "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; }
has_hyprland() { [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; }

# ---- processes (own uid only, exact names, by pid) -------------------------
pids_of() { pgrep -x -u "$(id -u)" "$1" || [ $? -eq 1 ]; }
alive() { kill -0 "$1" 2>/dev/null; }
proc_comm() { cat 2>/dev/null "$PROC/$1/comm" || true; }
# argv of a pid, one element per line (cmdline is NUL-separated)
proc_argv() { tr 2>/dev/null '\0' '\n' < "$PROC/$1/cmdline" || true; }

stop_pid() {
    local pid="$1" i
    kill -TERM "$pid" 2>/dev/null || return 0   # already gone
    for i in $(seq 1 50); do
        alive "$pid" || return 0
        sleep 0.1
    done
    err "pid $pid ($(proc_comm "$pid")) did not exit after SIGTERM"
    return 1
}

# Start a daemon in its own transient user unit, so it outlives the caller
# (the dead-man service's cgroup is torn down when rollback.sh exits).
start_argv() {
    local exe="$1"
    shift
    if [[ "$exe" != /* ]]; then
        exe="$(command -v -- "$exe")" || { err "cannot find $1 in PATH"; return 1; }
    fi
    systemd-run --user --quiet --collect ${WAYLAND_DISPLAY:+"--setenv=WAYLAND_DISPLAY=$WAYLAND_DISPLAY"} \
        "$exe" "$@"
}

# ---- org.freedesktop.Notifications ----------------------------------------
owner_pid() {
    local out
    out="$(busctl --user status org.freedesktop.Notifications 2>/dev/null)" || return 0
    printf '%s\n' "$out" | sed -n '/^PID=/{s///p;q}'
}
owner_comm() {
    local pid
    pid="$(owner_pid)"
    if [ -n "$pid" ]; then proc_comm "$pid"; fi
}
wait_owner() {
    local want="$1" i
    for i in $(seq 1 50); do
        [ "$(owner_comm)" = "$want" ] && return 0
        sleep 0.1
    done
    err "org.freedesktop.Notifications owner is '$(owner_comm)', expected '$want'"
    return 1
}

# Stop whoever owns the name now (by pid) and start the daemon recorded in the
# backup (OWNER_COMM / OWNER_ARGV), whatever it was: dunst, swaync, anything.
restore_owner() {
    local cur
    cur="$(owner_pid)"
    if [ -n "$cur" ]; then
        log "stopping Notifications owner $(proc_comm "$cur") (pid $cur)"
        stop_pid "$cur"
    fi
    if [ -z "$OWNER_COMM" ]; then
        log "nothing owned org.freedesktop.Notifications at backup time; leaving it unowned"
        return 0
    fi
    if [ "${#OWNER_ARGV[@]}" -eq 0 ]; then
        err "no command line recorded for $OWNER_COMM; start it by hand"
        return 1
    fi
    log "starting $OWNER_COMM: ${OWNER_ARGV[*]}"
    start_argv "${OWNER_ARGV[@]}"
    wait_owner "$OWNER_COMM"
    log "Notifications owner: $OWNER_COMM (pid $(owner_pid))"
}

unit_active() {
    local s
    s="$(systemctl --user is-active "$1" 2>/dev/null)" || true
    case "$s" in active | activating | reloading | deactivating | refreshing) return 0 ;; esac
    return 1
}

# ---- tar of exactly the given HOME-relative paths --------------------------
tar_paths() {
    local out="$1"
    shift
    if [ $# -eq 0 ]; then
        tar -cf "$out" -T /dev/null
    else
        tar -cf "$out" -C "$HOME_DIR" "$@"
    fi
}

# ---- rollback.sh body -------------------------------------------------------
# Baked by the generator: ID BK HOME_DIR STATE DEADMAN COMPS RELS KINDS SUMS
# OWNER_COMM OWNER_ARGV WAYBAR_STATE WSEV_STATE WSEV_UNIT NMA_REAL NMA_RUN NMA_ARGS IDLE_UNIT IDLE_INHIBIT_UNIT
# IDLE_STATE IDLE_INHIBIT_STATE TA_PATH_UNIT TA_UNIT TA_STATE DSP_UNIT DSP_STATE.

current_sum() {   # kind-specific fingerprint of HOME_DIR/$1 now
    local p="$HOME_DIR/$1"
    if [ -L "$p" ]; then printf 'symlink %s' "$(readlink -- "$p")"
    elif [ -f "$p" ]; then printf 'file %s' "$(sha256sum < "$p" | cut -d' ' -f1)"
    elif [ -d "$p" ]; then printf 'dir -'
    else printf 'absent -'; fi
}

restore_paths() {
    local i rel kind dst tmp="$BK/restore" now=()
    for rel in "${RELS[@]}"; do
        if [ -e "$HOME_DIR/$rel" ] || [ -L "$HOME_DIR/$rel" ]; then now+=("$rel"); fi
    done
    # whatever is there now is kept, so a rollback never loses a later edit
    tar_paths "$BK/pre-rollback-$(date -u +%Y%m%dT%H%M%SZ).tar" "${now[@]}"
    rm -rf -- "$tmp"
    mkdir -m 700 -- "$tmp"
    tar -xpf "$BK/files.tar" -C "$tmp"   # -p: modes as archived, not masked by umask 077
    for i in "${!RELS[@]}"; do
        rel="${RELS[$i]}" kind="${KINDS[$i]}" dst="$HOME_DIR/${RELS[$i]}"
        if [[ "$rel" == .local/share/seclegion/host/* ]]; then
            # an installed copy: ours to replace wholesale
            rm -rf -- "$dst"
            if [ "$kind" != absent ]; then
                mkdir -p -- "$(dirname -- "$dst")"
                cp -a -T -- "$tmp/$rel" "$dst"
            fi
            log "restored ~/$rel ($kind)"
            continue
        fi
        if [ "$(current_sum "$rel")" = "$kind ${SUMS[$i]}" ]; then
            log "unchanged ~/$rel"
            continue
        fi
        if [ -d "$dst" ] && [ ! -L "$dst" ]; then
            if [ -f "$dst/.seclegion-managed" ]; then
                # a directory seclegion-host generated (gtk-4.0): ours to remove; what is
                # inside is kept in the pre-rollback tar, and rm -rf never follows a symlink
                rm -rf -- "$dst"
            elif [ "$kind" = absent ]; then
                # a directory the apply created for a file of ours: remove it when it is empty
                if rmdir -- "$dst" 2>/dev/null; then log "restored ~/$rel (absent)"
                else log "left ~/$rel in place: it is not empty"; fi
                continue
            else
                err "~/$rel is a directory now; restore it by hand from $BK/files.tar"
                return 1
            fi
        fi
        case "$kind" in
            absent) rm -f -- "$dst" ;;
            file | symlink | dir)
                mkdir -p -- "$(dirname -- "$dst")"
                cp -a -T -- "$tmp/$rel" "$dst.sl-restore"
                mv -f -T -- "$dst.sl-restore" "$dst"
                ;;
            *) err "cannot restore ~/$rel of kind $kind"; return 1 ;;
        esac
        log "restored ~/$rel ($kind)"
    done
    rm -rf -- "$tmp"
}

# Undo what ensure_theme did for one backup directory: drop the theme dirs the
# apply created and put `current` back as it was (absent, a symlink, or the
# real directory ensure_theme moved into the backup). Idempotent: the record is
# renamed to theme-undo.done once it is undone.
undo_theme() {
    local bk="$1" f="$1/theme-undo" root="$STATE/theme" k v before="" target="" legacy="" root_created="" created=()
    [ -f "$f" ] || return 0
    while IFS== read -r k v; do
        case "$k" in
            before) before="$v" ;;
            target) target="$v" ;;
            legacy) legacy="$v" ;;
            root_created) root_created="$v" ;;
            created) created+=("$v") ;;
        esac
    done < "$f"
    if [ -L "$root/current" ]; then rm -f -- "$root/current"; fi
    for v in "${created[@]}"; do
        if [[ "$v" =~ ^[0-9a-f]{16}$ ]]; then rm -rf -- "${root:?}/$v"; fi
    done
    case "$before" in
        moved)
            if [ -e "$bk/$legacy" ]; then
                [ ! -e "$root/current" ] || { err "$root/current exists; the old theme directory stays in $bk/$legacy"; return 1; }
                mv -T -- "$bk/$legacy" "$root/current"
            fi
            ;;
        symlink) ln -sfn -- "$target" "$root/current" ;;
    esac
    if [ -n "$root_created" ]; then rmdir -- "$root" 2>/dev/null || true; fi
    mv -f -- "$f" "$f.done"
    log "restored the theme state of ${bk##*/} (current was: ${before:-unknown})"
}

# baseline-0 undoes every later apply's theme change, newest first.
undo_theme_all() {
    local d dirs=() i
    for d in "$(dirname -- "$BK")"/2*Z-*/; do
        if [ -f "${d}theme-undo" ]; then dirs+=("${d%/}"); fi
    done
    for ((i = ${#dirs[@]} - 1; i >= 0; i--)); do undo_theme "${dirs[$i]}"; done
}

# The waybar apply restarted nm-applet through the shim (no --indicator). Put back the command the
# backup recorded (NMA_RUN 1, NMA_ARGS), run by absolute path. NMA_RUN empty (a backup from before
# the shim) or 0 (it was not running): nothing to start; the shim file itself is gone with restore_paths.
restore_nm_applet() {
    local p
    [ "${NMA_RUN:-}" = 1 ] || return 0
    for p in $(pids_of nm-applet); do stop_pid "$p"; done
    log "starting ${NMA_REAL:-/usr/bin/nm-applet} ${NMA_ARGS[*]-}"
    start_argv "${NMA_REAL:-/usr/bin/nm-applet}" ${NMA_ARGS[@]+"${NMA_ARGS[@]}"}
}

has_comp() {
    local c
    [ "${SL_SYSTEM_BACKUP:-}" != 1 ] || return 1   # a --system backup: no live daemon or unit to touch
    for c in "${COMPS[@]}"; do [ "$c" = "$1" ] && return 0; done
    return 1
}

rollback_main() {
    umask 077
    enable -n kill   # PATH kill: /usr/bin/kill on the host, a stub in tests
    trap '[ "$BASHPID" != "$$" ] || err "rollback of $ID FAILED at line $LINENO; fix the cause and re-run: bash $BK/rollback.sh"' ERR
    session_env
    log "rolling back $ID (${COMPS[*]})"
    # seen by confirm: a dead-man run that failed is collected and leaves no unit state
    date -u +%FT%TZ > "$BK/ROLLBACK_STARTED"
    # the timer only: if the dead-man service is what runs us, stopping it would kill us
    [ "${SL_SYSTEM_BACKUP:-}" = 1 ] || systemctl --user stop "$DEADMAN.timer" 2>/dev/null || true
    # the workspace-pill helper: stop it before its files go, reload units after
    if has_comp waybar; then systemctl --user stop "$WSEV_UNIT" 2>/dev/null || true; fi
    # the autolock units: stop both before their files go (the inhibitor ends with them)
    if has_comp idle; then
        systemctl --user stop "$IDLE_UNIT" 2>/dev/null || true
        systemctl --user stop "$IDLE_INHIBIT_UNIT" 2>/dev/null || true
    fi
    # the theme-auto units: disabled and stopped before their files go
    if has_comp theme-auto; then
        systemctl --user disable --now "$TA_PATH_UNIT" 2>/dev/null || true
        systemctl --user stop "$TA_UNIT" 2>/dev/null || true
    fi
    # the ghost-monitor daemon: disabled and stopped before its files go
    if has_comp display; then systemctl --user disable --now "$DSP_UNIT" 2>/dev/null || true; fi
    restore_paths
    if [ "$ID" = baseline-0 ]; then undo_theme_all; else undo_theme "$BK"; fi
    if has_comp waybar; then
        # non-fatal: an unreachable user manager must not stop the waybar restart or ROLLED_BACK
        systemctl --user daemon-reload || log "warning: systemctl --user daemon-reload failed; run it from the session"
        if [ "$WSEV_STATE" = active ]; then
            systemctl --user start "$WSEV_UNIT" || log "warning: could not start $WSEV_UNIT; start it from the session"
        fi
    fi
    if has_comp idle; then
        # non-fatal, like waybar: start again only what ran before the apply (inhibitor first)
        systemctl --user daemon-reload || log "warning: systemctl --user daemon-reload failed; run it from the session"
        if [ "$IDLE_INHIBIT_STATE" = active ]; then
            systemctl --user start "$IDLE_INHIBIT_UNIT" || log "warning: could not start $IDLE_INHIBIT_UNIT; start it from the session"
        fi
        if [ "$IDLE_STATE" = active ]; then
            systemctl --user start "$IDLE_UNIT" || log "warning: could not start $IDLE_UNIT; start it from the session"
        fi
    fi
    if has_comp theme-auto; then
        # non-fatal; the units of an earlier apply are back with restore_paths: start again only what ran before
        systemctl --user daemon-reload || log "warning: systemctl --user daemon-reload failed; run it from the session"
        if [ "$TA_STATE" = active ]; then
            systemctl --user start "$TA_PATH_UNIT" || log "warning: could not start $TA_PATH_UNIT; start it from the session"
        fi
    fi
    if has_comp display; then
        # non-fatal; an earlier apply's unit and wants link are back with restore_paths
        systemctl --user daemon-reload || log "warning: systemctl --user daemon-reload failed; run it from the session"
        if [ "$DSP_STATE" = active ]; then
            systemctl --user start "$DSP_UNIT" || log "warning: could not start $DSP_UNIT; start it from the session"
        fi
    fi
    if has_wayland; then
        if has_comp notifications; then restore_owner; fi
        if has_comp waybar && [ "$WAYBAR_STATE" = active ]; then
            if systemctl --user restart waybar; then log "waybar restarted"
            else log "warning: could not restart waybar; run: systemctl --user restart waybar"; fi
        fi
        if has_comp waybar; then
            restore_nm_applet || log "warning: could not restart nm-applet; run: nm-applet --indicator"
        fi
        if { has_comp border || has_comp keys; } && has_hyprland; then
            if hyprctl reload >/dev/null; then log "hyprland reloaded"
            else log "warning: hyprctl reload failed; run it from the session"; fi
        fi
    else
        log "no Wayland session reachable: files restored, daemons untouched; run this again from the session to restart them"
    fi
    date -u +%FT%TZ > "$BK/ROLLED_BACK"
    if [ -f "$STATE/host-pending" ]; then
        local p
        p="$(cat "$STATE/host-pending")"
        if [ "$p" = "$ID" ] || [ "$ID" = baseline-0 ]; then rm -f -- "$STATE/host-pending"; fi
    fi
    log "rollback of $ID complete"
}
