#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Sourced by tools/container-build.sh (iso mode): the steps that put the signed [seclegion]
# repository into the ISO build. Kept apart so tests/unit/test_iso_seclegion.py can run them on a
# fake tree, outside a container. Each function prints its own error and returns 1.

sl_runtime_server='Server = file:///opt/seclegion/cache/seclegion'
sl_build_server='Server = file:///work/profile/airootfs/opt/seclegion/cache/seclegion'

# sl_lock_conf <in> <out>: the pacman.conf without its [seclegion] section, for resolving and
# downloading the official packages (the repository is not in the cache yet at that point).
sl_lock_conf() {
    awk '/^\[/ { skip = ($0 == "[seclegion]") } !skip' "$1" > "$2" || return 1
    if grep -q '^\[seclegion\]' "$2"; then
        echo "seclegion-iso: lock pacman.conf still has a [seclegion] section" >&2
        return 1
    fi
}

# sl_build_conf <file>: point the [seclegion] Server of the profile's pacman.conf at the build tree,
# for mkarchiso. The caller installed the runtime copy into the airootfs before.
sl_build_conf() {
    if [[ $(grep -c -x -F "$sl_runtime_server" "$1") != 1 ]]; then
        echo "seclegion-iso: $1 needs exactly one '$sl_runtime_server' line" >&2
        return 1
    fi
    sed -i "s|^$sl_runtime_server\$|$sl_build_server|" "$1" || return 1
    if [[ $(grep -c -x -F "$sl_build_server" "$1") != 1 ]]; then
        echo "seclegion-iso: the build [seclegion] Server line was not written" >&2
        return 1
    fi
}

# sl_extract_keyring <keyring package> <dev-key.fingerprint> <outdir>: the three pacman-key keyring
# files from the package into <outdir>, after checking that they are the key of the fingerprint
# file: seclegion-trusted is exactly '<fingerprint>:4:' and seclegion.gpg holds exactly that one key.
sl_extract_keyring() {
    local pkg=$1 fprfile=$2 out=$3 fpr keys kdir=usr/share/pacman/keyrings
    if [[ ! -f $fprfile ]]; then
        echo "seclegion-iso: no $fprfile" >&2
        return 1
    fi
    fpr=$(<"$fprfile")
    if [[ ! $fpr =~ ^[0-9A-F]{40}$ ]]; then
        echo "seclegion-iso: $fprfile is not a 40 hex digit fingerprint" >&2
        return 1
    fi
    if [[ ! -f $pkg ]]; then
        echo "seclegion-iso: no keyring package $pkg" >&2
        return 1
    fi
    mkdir -p -- "$out" || return 1
    bsdtar -xf "$pkg" -C "$out" "$kdir/seclegion.gpg" "$kdir/seclegion-trusted" "$kdir/seclegion-revoked" \
        || { echo "seclegion-iso: the keyring package lacks seclegion.gpg, seclegion-trusted or seclegion-revoked" >&2; return 1; }
    if [[ $(<"$out/$kdir/seclegion-trusted") != "$fpr:4:" ]]; then
        echo "seclegion-iso: seclegion-trusted is not exactly '<fingerprint>:4:' of $fprfile" >&2
        return 1
    fi
    keys=$(gpg --show-keys --with-colons "$out/$kdir/seclegion.gpg" 2>/dev/null \
        | awk -F: '$1 == "pub" { n++ } $1 == "fpr" && !f { f = $10 } END { print n, f }')
    if [[ $keys != "1 $fpr" ]]; then
        echo "seclegion-iso: seclegion.gpg is not exactly the key of $fprfile" >&2
        return 1
    fi
}

# sl_check_nvidia_pair <resolved-file>: the cached NVIDIA kernel modules must be the same driver release
# as the cached nvidia-utils (nvidia-open depends on nvidia-utils=<exact version>; a mismatch would fail
# the offline install). Lines are "<repo> <name> <version> <url>"; versions compare without pkgrel.
sl_check_nvidia_pair() {
    awk '
        { v = $3; sub(/-[^-]*$/, "", v); sub(/^[0-9]+:/, "", v); ver[$2] = v }
        END {
            if (!("nvidia-utils" in ver)) exit 0
            bad = 0
            for (m in ver) if (m ~ /^nvidia-open(-lts)?$/ && ver[m] != ver["nvidia-utils"]) {
                printf "nvidia pair: %s %s != nvidia-utils %s\n", m, ver[m], ver["nvidia-utils"] > "/dev/stderr"
                bad = 1
            }
            exit bad
        }' "$1"
}
