#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Sourced by tools/docker-build.sh. One host-wide build lock: only one container build
# (iso, theme or pkgs) runs at a time, because they share the workdir and pkgcache.

# sl_build_lock [lockfile]: take an exclusive flock on the lock file (default
# /var/tmp/seclegion-build.lock), waiting if another build holds it. The lock is held on
# a file descriptor of the calling shell and released when that shell exits. The file
# argument exists for the unit tests; docker-build.sh never passes one.
sl_build_lock() {
    local lockfile=${1:-/var/tmp/seclegion-build.lock} fd
    exec {fd}>>"$lockfile" || { echo "locks: cannot open $lockfile" >&2; return 1; }
    if ! flock --nonblock "$fd"; then
        echo "locks: waiting for build lock ($lockfile is held by another build)" >&2
        flock "$fd" || return 1
    fi
    echo "locks: build lock acquired" >&2
}
