#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# The ONLY place in this repository that starts a container (enforced by
# tools/check-container-start, run by `make lint`).
#
# Why: membership of the docker group is root-equivalent on the host. Every flag,
# mount and the image are therefore hard-coded here, not taken from arguments:
#   - image pinned by digest (never a tag)
#   - repository mounted READ-ONLY at /src
#   - build workdir mounted at /work, must be under /var/tmp, on a Linux filesystem
#     with enough space (tools/check-space refuses NTFS/fuseblk and /mnt/Dev_Lab)
#   - every bind source is canonical (realpath == literal path, so no symlink
#     component anywhere) and the workdir and its subdirs belong to the invoking user
#   - nothing else is mounted: never $HOME, /, /etc, /var/run/docker.sock
#   - results are chowned back to the invoking user inside the container, also when
#     the build fails (tools/container-build.sh, trap EXIT)
#   - --privileged is kept on purpose; see docs/decisions.md (M0-5)
#
# Usage: tools/docker-build.sh iso     (build the ISO; results in $WORKDIR/out)
#        tools/docker-build.sh theme   (build only the GRUB theme; $WORKDIR/out/grub-theme.sha256)
#        tools/docker-build.sh pkgs <dir>   (build one PKGBUILD directory under pkgs/ in the
#                                      container; $WORKDIR/out/pkgs/*.pkg.tar.zst, 'pkg-ok <file>' each)
#        tools/docker-build.sh repo <dir>...   (build the signed [seclegion] repository: pkgs/seclegion-keyring
#                                      plus each <dir>, signed by a per-build DEV key that is born and
#                                      destroyed in the container; $WORKDIR/out/repo/seclegion/. Use
#                                      tools/build-pkgs, which lists the directories)
#        tools/docker-build.sh check   (validate repo/workdir layout; starts nothing)
set -euo pipefail

# archlinux:latest as pulled 2026-10-14 (image created 2026-10-12T17:57:16Z).
# Bump deliberately, together with the archive-date pin (A13).
readonly IMAGE='archlinux@sha256:3c64b538588416593f69a1aebd2f2ec0f2541b29159f32556fa7def2167147a0'
readonly DIGEST_RE='^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$'

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

die() { echo "docker-build: REFUSED: $*" >&2; exit 1; }

[[ $IMAGE =~ $DIGEST_RE ]] || die "image must be pinned by digest"
mode=${1:-}
[[ $mode == iso || $mode == theme || $mode == check || $mode == pkgs || $mode == repo ]] \
    || die "usage: $0 iso|theme|pkgs <dir>|check|repo <dir>..."
if [[ $mode == pkgs ]]; then
    [[ $# -eq 2 ]] || die "usage: $0 pkgs <dir under pkgs/>"
elif [[ $mode == repo ]]; then
    [[ $# -ge 2 ]] || die "usage: $0 repo <dir under pkgs/>..."
else
    [[ $# -eq 1 ]] || die "usage: $0 iso|theme|check (no further arguments)"
fi

# pkgs <dir> and repo <dir>...: a plain directory under <repo>/pkgs holding a PKGBUILD. Checked
# first, before anything touches the workdir: lexically (no '..', no odd characters), then
# canonically (realpath equal to the literal path, so no symlink component anywhere).
plain_pkgdir() {  # plain_pkgdir <arg>: prints pkgs/<path>, or refuses
    local arg=$1
    [[ $arg == "$repo_root"/pkgs/* ]] && arg=${arg#"$repo_root"/}
    [[ $arg =~ ^pkgs/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] || die "$mode: '$1' must be a plain path under pkgs/"
    [[ /$arg/ != */../* && /$arg/ != */./* ]] || die "$mode: '$1' must not contain '.' or '..' components"
    [[ $(realpath -e -- "$repo_root/$arg" 2>/dev/null) == "$repo_root/$arg" ]] \
        || die "$mode: '$1' does not exist or has a symlink component"
    [[ -d $repo_root/$arg && -f $repo_root/$arg/PKGBUILD && ! -L $repo_root/$arg/PKGBUILD ]] \
        || die "$mode: '$1' is not a directory with a plain PKGBUILD"
    printf '%s\n' "$arg"
}
pkgdir_rel=
pkgdirs_rel=
if [[ $mode == pkgs ]]; then
    pkgdir_rel=$(plain_pkgdir "$2")
elif [[ $mode == repo ]]; then
    for a in "${@:2}"; do
        d=$(plain_pkgdir "$a")
        [[ " $pkgdirs_rel " == *" $d "* ]] || pkgdirs_rel+="${pkgdirs_rel:+ }$d"
    done
fi

# Production: everything lives under /var/tmp with >= 25 GiB free. SECLEGION_TEST_ROOT
# exists for the unit tests only: it moves that root and drops the space floor, and
# it is accepted in 'check' mode, which never reaches a container engine.
base=/var/tmp
default_workdir=/var/tmp/seclegion-build
min_gib=25
[[ $mode == pkgs || $mode == repo ]] && min_gib=5  # a PKGBUILD build needs far less room than an ISO
if [[ -n ${SECLEGION_TEST_ROOT:-} ]]; then
    [[ $mode == check ]] || die "SECLEGION_TEST_ROOT is for 'check' only; it never starts a container"
    [[ $SECLEGION_TEST_ROOT =~ ^/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] \
        || die "SECLEGION_TEST_ROOT must be a plain absolute path"
    base=$SECLEGION_TEST_ROOT
    default_workdir=$base/seclegion-build
    min_gib=0
fi
workdir=${SECLEGION_WORKDIR:-$default_workdir}

# Workdir: absolute, under the base, no '..' or odd characters.
[[ $workdir == "$base"/* && ${workdir#"$base"/} =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] \
    || die "workdir '$workdir' must be a plain path under $base"
[[ $workdir != *..* ]] || die "workdir must not contain '..'"
case $repo_root in
    "$workdir"|"$workdir"/*) die "workdir must not contain the repository" ;;
esac

# A bind source must be exactly what it says: realpath equal to the literal path means
# no component is a symlink (a symlinked pkgcache would bind-mount somewhere else).
# -m before the directories exist (resolves what is there), -e once they do.
canonical() {  # canonical <flag> <path>
    local real
    real=$(realpath "$1" -- "$2") || die "cannot resolve '$2'"
    [[ $real == "$2" ]] || die "'$2' resolves to '$real': no path component may be a symlink"
}
owned_by_me() {
    [[ -d $1 && ! -L $1 ]] || die "'$1' is not a plain directory"
    [[ $(stat -c %u -- "$1") == "$(id -u)" ]] || die "'$1' is not owned by uid $(id -u)"
}

dirs=("$workdir" "$workdir/work" "$workdir/out" "$workdir/pkgcache")
canonical -e "$repo_root"
for d in "${dirs[@]}"; do canonical -m "$d"; done

"$repo_root/tools/check-space" --min-gib "$min_gib" "$workdir" || die "build workdir unsuitable"
mkdir -p -- "${dirs[@]}"
for d in "${dirs[@]}"; do canonical -e "$d"; owned_by_me "$d"; done

if [[ $mode == check ]]; then
    echo "docker-build: check OK: repo $repo_root workdir $workdir"
    exit 0
fi

# One container build at a time (they share the workdir and pkgcache). Never for 'check'.
# shellcheck source=lib/locks.sh disable=SC1091
source "$repo_root/tools/lib/locks.sh"
sl_build_lock

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"

name="seclegion-build-$$"
# Stop first (SIGTERM lets the build's EXIT trap chown the output back), then remove. bash runs
# that trap only after the running step (mksquashfs, pacstrap) ends, hence the long grace time.
cleanup() {
    docker stop --time 600 "$name" >/dev/null 2>&1 || true
    docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "docker-build: image $IMAGE"
echo "docker-build: repo $repo_root (read-only) workdir $workdir"
# --privileged: mkarchiso needs loop devices and mounts. Accepted risk, docs/decisions.md M0-5.
docker run --name "$name" --privileged --pull=never \
    --mount "type=bind,source=$repo_root,target=/src,readonly" \
    --mount "type=bind,source=$workdir,target=/work" \
    --mount "type=bind,source=$workdir/pkgcache,target=/var/cache/pacman/pkg" \
    --env "PKG_DIR=$pkgdir_rel" \
    --env "PKG_DIRS=$pkgdirs_rel" \
    --env "HOST_UID=$(id -u)" --env "HOST_GID=$(id -g)" \
    --env "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(date +%s)}" \
    "$IMAGE" bash /src/tools/container-build.sh "$mode"

echo "docker-build: $mode done; results in $workdir/out"
