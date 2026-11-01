#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Build the signed [seclegion] file repository. Runs as an UNPRIVILEGED user: inside the build
# container as 'builder' (tools/container-build.sh repo), and from tests/unit/test_repo.py on the
# host. It never starts a container itself.
#
#   mkrepo.sh <srcroot> <outdir> <workdir> <pkgs/dir>...
#
#   srcroot  a tree holding pkgs/<name>/PKGBUILD (the repository, or a copy of it)
#   outdir   receives seclegion/ (db, files, packages, every .sig) and dev-key.fingerprint;
#            it must not hold either yet
#   workdir  scratch for the package builds (no secret ever goes there)
#
# What it does, in this order (spec A8, plan r14 R1, rule R3):
#   1. a throwaway DEV key (ed25519, no passphrase) in a GNUPGHOME on tmpfs, refused anywhere else;
#   2. pkgs/seclegion-keyring is built FIRST from the PUBLIC key, its trust line and an empty
#      revocation list (the pacman-key keyring format);
#   3. every listed pkgs/ directory is built with makepkg;
#   4. every package gets a detached .sig, and the database is made with
#      repo-add --sign --verify --include-sigs;
#   5. everything is verified again with gpgv against the exported public key;
#   6. only the public key FINGERPRINT is written next to the repository, and the GNUPGHOME,
#      with the secret key and its revocation certificate, is destroyed on every exit.
# MKREPO_MAKEPKG_FLAGS adds makepkg flags (the container passes --syncdeps).
# MKREPO_GNUPG_PARENT moves the tmpfs the key lives on (default /dev/shm).
set -euo pipefail

die() { echo "mkrepo: $*" >&2; exit 1; }

umask 022  # a repository the ISO and its readers must be able to read

[[ $# -ge 4 ]] || die "usage: $0 <srcroot> <outdir> <workdir> <pkgs/dir>..."
srcroot=$1 outdir=$2 workdir=$3
shift 3
[[ -d $srcroot && -d $outdir && -d $workdir ]] || die "srcroot, outdir and workdir must be existing directories"

keyring_dir=pkgs/seclegion-keyring
pkg_re='^pkgs/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$'
dirs=("$keyring_dir")
for d in "$@"; do
    [[ $d =~ $pkg_re && /$d/ != */../* && /$d/ != */./* ]] || die "bad package directory '$d'"
    [[ -f $srcroot/$d/PKGBUILD && ! -L $srcroot/$d/PKGBUILD ]] || die "no plain PKGBUILD in $d"
    [[ $d == "$keyring_dir" ]] || dirs+=("$d")
done
[[ -f $srcroot/$keyring_dir/PKGBUILD ]] || die "no $keyring_dir/PKGBUILD"

repo=$outdir/seclegion
fprfile=$outdir/dev-key.fingerprint
[[ ! -e $repo && ! -e $fprfile ]] || die "$repo or $fprfile exists already"

# The key lives in tmpfs, never on disk (rule R3): a disk-backed directory is refused.
parent=${MKREPO_GNUPG_PARENT:-/dev/shm}
fstype=$(stat -f -c %T -- "$parent" 2>/dev/null) || die "cannot stat $parent"
[[ $fstype == tmpfs || $fstype == ramfs ]] || die "$parent is $fstype, not tmpfs: the DEV key must stay in memory"
GNUPGHOME=$(mktemp -d "$parent/seclegion-dev-gnupg.XXXXXX")
export GNUPGHOME
# With a /run/user/<uid>/gnupg directory present, gpg puts the agent sockets in a per-home
# d.<hash> subdirectory there. It outlives the agent, so remove it (rmdir: only if empty).
sockdir=$(gpgconf --list-dirs socketdir 2>/dev/null || true)
cleanup() {
    gpgconf --homedir "$GNUPGHOME" --kill all >/dev/null 2>&1 || true
    rm -rf -- "$GNUPGHOME"
    [[ $sockdir == */gnupg/d.* ]] && rmdir -- "$sockdir" 2>/dev/null
    return 0
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

quiet() {  # quiet <cmd>...: run it, show its output only when it fails
    local out
    out=$("$@" 2>&1) || { printf '%s\n' "$out" >&2; return 1; }
}

quiet gpg --batch --quiet --pinentry-mode loopback --passphrase '' \
    --quick-generate-key 'SecLegion DEV (throwaway, one build) <dev@seclegion.invalid>' ed25519 sign 1y \
    || die "cannot generate the DEV key"
fpr=$(gpg --batch --with-colons --list-keys | awk -F: '$1 == "fpr" { print $10; exit }')
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "unexpected fingerprint '$fpr'"

pubring=$workdir/dev-public.gpg
gpg --batch --export "$fpr" > "$pubring"
[[ -s $pubring ]] || die "public key export is empty"
if gpg --batch --list-packets "$pubring" 2>/dev/null | grep -qi 'secret'; then
    die "the exported key file holds secret key material"
fi

pkgdest=$workdir/pkgdest
mkdir -p -- "$pkgdest" "$workdir/build"
read -r -a mkpkg_flags <<< "${MKREPO_MAKEPKG_FLAGS:-}"

built=()
for d in "${dirs[@]}"; do
    bdir=$workdir/build/${d//\//_}
    mkdir -p -- "$bdir"
    cp -a --no-preserve=ownership -- "$srcroot/$d/." "$bdir/"
    if [[ $d == "$keyring_dir" ]]; then
        cp -- "$pubring" "$bdir/seclegion.gpg"
        printf '%s:4:\n' "$fpr" > "$bdir/seclegion-trusted"
        : > "$bdir/seclegion-revoked"
    fi
    before=$(find "$pkgdest" -name '*.pkg.tar.zst' | wc -l)
    # makepkg gets the user's own GNUPGHOME (it checks upstream source signatures there), not ours.
    (cd "$bdir" && env -u GNUPGHOME PKGDEST="$pkgdest" makepkg --clean --cleanbuild --nosign --noconfirm "${mkpkg_flags[@]}") \
        || die "makepkg failed in $d"
    [[ $(find "$pkgdest" -name '*.pkg.tar.zst' | wc -l) -gt $before ]] || die "makepkg produced no package in $d"
    built+=("$d")
done

# Sign every package, then build and sign the database in a staging copy of the repository.
stage=$workdir/repo
mkdir -p -- "$stage"
for p in "$pkgdest"/*.pkg.tar.zst; do
    gpg --batch --yes --detach-sign --no-armor --local-user "$fpr" --output "$p.sig" -- "$p" \
        || die "cannot sign ${p##*/}"
    cp -- "$p" "$p.sig" "$stage/"
done
(cd "$stage" && repo-add --quiet --sign --verify --include-sigs --key "$fpr" seclegion.db.tar.zst -- ./*.pkg.tar.zst) \
    || die "repo-add failed"

# Check what was made, with the public key only, the way a client sees it.
for f in "$stage"/*.sig; do
    gpgv --quiet --keyring "$pubring" "$f" "${f%.sig}" 2>/dev/null || die "bad signature on ${f##*/}"
done
for need in seclegion.db seclegion.db.sig seclegion.files seclegion.files.sig; do
    [[ -e $stage/$need ]] || die "repository file $need is missing"
done
kpkg=$(find "$stage" -name 'seclegion-keyring-*.pkg.tar.zst' | head -n 1)
[[ -n $kpkg ]] || die "the keyring package is missing from the repository"
kdir=/usr/share/pacman/keyrings
[[ $(bsdtar -xOf "$kpkg" "${kdir#/}/seclegion-trusted") == "$fpr:4:" ]] || die "keyring trust line does not match the DEV key"
cmp -s <(bsdtar -xOf "$kpkg" "${kdir#/}/seclegion.gpg") "$pubring" || die "keyring package does not hold the DEV public key"

cp -a -- "$stage" "$repo"
printf '%s\n' "$fpr" > "$fprfile"
for f in "$repo"/*.pkg.tar.zst; do echo "pkg-ok ${f##*/}"; done
echo "repo-ok seclegion: ${#built[@]} packages from pkgs/ ($(find "$repo" -name '*.pkg.tar.zst' | wc -l) files), signed, key $fpr"
