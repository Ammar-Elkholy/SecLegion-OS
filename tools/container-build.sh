#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Runs INSIDE the pinned archlinux container (started only by tools/docker-build.sh).
# /src = repository (read-only), /work = build workdir on the host's ext4.
#
# Usage: container-build.sh [iso|theme|pkgs|repo]   (default iso; the wrapper passes it)
#   pkgs   build the PKGBUILD directory $PKG_DIR (pkgs/<name>, validated by the wrapper and
#          again here) as an unprivileged user; packages go to /work/out/pkgs
#   repo   build pkgs/seclegion-keyring and the directories in $PKG_DIRS and sign them all with a
#          DEV key made and destroyed in this one run (tools/lib/mkrepo.sh); the signed file
#          repository goes to /work/out/repo/seclegion, its key fingerprint to /work/out/repo
#   iso    the GRUB theme, the package lock and offline cache (with the signed [seclegion] repo of a
#          prior 'repo' run in it, and its keyring trusted by this container's pacman), then the ISO
#   theme  only the GRUB theme: /work/profile/grub/themes/seclegion and
#          /work/out/grub-theme.sha256, no archiso and no ISO
set -euo pipefail

: "${HOST_UID:?}" "${HOST_GID:?}"
mode=${1:-iso}
[[ $mode == iso || $mode == theme || $mode == pkgs || $mode == repo ]] || { echo "container-build: unknown mode '$mode'" >&2; exit 2; }

# Hand everything this build wrote back to the invoking user: /work holds work/, out/,
# pkgcache/ and the profile copy, and pacman's cache is the same pkgcache. Runs on
# every exit, so a failed or stopped build does not leave root-owned files behind.
give_back() {
    chown -R -h "$HOST_UID:$HOST_GID" /work /var/cache/pacman/pkg \
        || echo "container-build: WARNING: chown back failed" >&2
}
trap give_back EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

die() { echo "container-build: $*" >&2; exit 1; }

# The repository and the container's mirrorlist. The SECLEGION_TEST_* overrides exist for
# tests/unit only (they run this script outside a container); the wrapper never sets them.
src=${SECLEGION_TEST_SRC:-/src}
# shellcheck source=lib/seclegion-iso.sh disable=SC1091
source "$src"/tools/lib/seclegion-iso.sh
mirrorlist=${SECLEGION_TEST_MIRRORLIST:-/etc/pacman.d/mirrorlist}

# The archive date lives in ONE place: the Server lines of iso/profile/pacman.conf. The
# container's own pacman reads the same snapshot, so the tools used to build (archiso,
# grub) and the packages put on the ISO come from one consistent, dated set. Always a
# full upgrade (-Syu), never a bare -Sy: no partial upgrades.
# shellcheck disable=SC2016  # a literal $repo/$arch, as in pacman.conf
archive_url_re='^Server = https://archive\.archlinux\.org/repos/([0-9]{4}/[0-9]{2}/[0-9]{2})/\$repo/os/\$arch$'
pin_date=
while IFS= read -r line; do
    if [[ $line =~ $archive_url_re ]]; then
        [[ -z $pin_date || $pin_date == "${BASH_REMATCH[1]}" ]] || die "pacman.conf pins two different archive dates"
        pin_date=${BASH_REMATCH[1]}
    fi
done < "$src"/iso/profile/pacman.conf
[[ -n $pin_date ]] || die "no archive.archlinux.org/repos/<date> Server line in iso/profile/pacman.conf"
# shellcheck disable=SC2016  # pacman expands $repo and $arch
printf 'Server = https://archive.archlinux.org/repos/%s/$repo/os/$arch\n' "$pin_date" > "$mirrorlist"
echo "container-build: archive pin $pin_date"

# grub-mkfont needs grub plus freetype2 (an optional dependency of the package), and the font comes
# from ttf-jetbrains-mono. archiso is needed for the ISO only.
packages=(grub freetype2 ttf-jetbrains-mono)
[[ $mode == iso ]] && packages+=(archiso)
[[ $mode == pkgs || $mode == repo ]] && packages=(base-devel)  # makepkg, fakeroot, sudo (for --syncdeps)

pacman -Syu --noconfirm --needed "${packages[@]}"

# The ISO embeds the [seclegion] repository that 'repo' mode made (tools/build-pkgs).
src_repo_dir=/work/out/repo
seclegion_repo=$src_repo_dir/seclegion
if [[ $mode == iso ]]; then
    for f in seclegion.db seclegion.db.sig seclegion.files seclegion.files.sig; do
        [[ -e $seclegion_repo/$f ]] || die "no signed [seclegion] repository ($seclegion_repo/$f): run tools/build-pkgs first"
    done
fi

if [[ $mode == pkgs || $mode == repo ]]; then
    # makepkg refuses to run as root, so build as an unprivileged user. The container is the
    # clean root (fresh on every run, packages from the archive-pinned mirror): no chroot
    # inside it. --syncdeps installs makedepends through passwordless sudo, which exists for
    # this throwaway user in this throwaway container only.
    pkg_re='^pkgs/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$'
    pkg_dirs=()
    if [[ $mode == pkgs ]]; then
        pkg_dirs=("${PKG_DIR:-}")
    else
        read -r -a pkg_dirs <<< "${PKG_DIRS:-}"
        [[ ${#pkg_dirs[@]} -gt 0 ]] || die "repo: PKG_DIRS is empty"
    fi
    for d in "${pkg_dirs[@]}"; do
        [[ $d =~ $pkg_re && /$d/ != */../* && /$d/ != */./* ]] || die "bad package directory '$d'"
        [[ -f $src/$d/PKGBUILD ]] || die "no PKGBUILD in $d"
    done
    useradd --create-home --shell /bin/bash builder
    printf 'builder ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/builder
    chmod 0440 /etc/sudoers.d/builder
    bdir=/work/pkgbuild
    if [[ $mode == repo ]]; then
        # The DEV key is made inside mkrepo.sh, on tmpfs, as 'builder', and is gone when it exits (R3).
        # builder gets its own copy of what it builds: /src is not necessarily readable by it.
        rm -rf "$bdir" /work/out/repo
        install -d -o builder -g builder "$bdir" "$bdir/src" "$bdir/work" /work/out/repo
        for d in pkgs/seclegion-keyring "${pkg_dirs[@]}"; do
            [[ -e $bdir/src/$d ]] && continue  # the keyring may be listed too
            install -d "$bdir/src/${d%/*}"
            cp -a --no-preserve=ownership -- "$src/$d" "$bdir/src/$d"
        done
        install -m 0755 "$src/tools/lib/mkrepo.sh" "$bdir/mkrepo.sh"
        chown -R builder:builder "$bdir" /work/out/repo
        runuser -u builder -- env HOME=/home/builder MKREPO_MAKEPKG_FLAGS=--syncdeps \
            SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-}" \
            bash "$bdir/mkrepo.sh" "$bdir/src" /work/out/repo "$bdir/work" "${pkg_dirs[@]}"
        exit 0
    fi
    PKG_DIR=${pkg_dirs[0]}
    rm -rf "$bdir" /work/out/pkgs
    install -d -o builder -g builder "$bdir" /work/out/pkgs
    cp -a --no-preserve=ownership -- "$src/$PKG_DIR/." "$bdir/"
    chown -R builder:builder "$bdir"
    # shellcheck disable=SC2016  # $1 is expanded by the inner bash, on purpose
    runuser -u builder -- env PKGDEST=/work/out/pkgs SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-}" \
        bash -c 'cd "$1" && makepkg --clean --cleanbuild --syncdeps --noconfirm' _ "$bdir"
    found=0
    for f in /work/out/pkgs/*.pkg.tar.zst; do
        [[ -f $f ]] || continue
        echo "pkg-ok ${f##*/}"
        found=1
    done
    [[ $found == 1 ]] || die "makepkg produced no .pkg.tar.zst"
    exit 0
fi

# The profile must be writable/owned by root for mkarchiso: build from a copy.
rm -rf /work/profile /work/work
cp -a "$src"/iso/profile /work/profile
rm -f /work/profile/PLACEHOLDER.md

# The GRUB theme is built, never committed (iso/grub-theme/build-theme.sh).
mkdir -p /work/out
rm -f /work/out/grub-theme.sha256
bash "$src"/iso/grub-theme/build-theme.sh /work/profile/grub/themes/seclegion /work/out/grub-theme.sha256

if [[ $mode == theme ]]; then
    ls -l /work/out
    exit 0
fi

# ---- packages: lists, lock, offline cache (plan r13 J2a) -------------------------------------
# iso/packages/*.list are the source of truth. The ISO gets base+live+desktop, the offline
# cache base+desktop+cache with all dependencies. iso/profile/packages.x86_64 is the
# committed copy of the ISO set (tests/iso/test_m2_static.py); a drift stops the build.
read_list() { grep -hv '^[[:space:]]*\(#\|$\)' "$@" | sed 's/[[:space:]]*$//' | LC_ALL=C sort -u; }
cd "$src"/iso/packages
mapfile -t iso_pkgs < <(read_list base.list live.list desktop.list)
# seclegion.list names packages of our own [seclegion] repository: on the ISO, but not in core or
# extra, so never part of the resolve below.
mapfile -t all_iso_pkgs < <(read_list base.list live.list desktop.list seclegion.list)
mapfile -t cache_pkgs < <(read_list base.list desktop.list cache.list)
cd /
[[ ${#iso_pkgs[@]} -gt 0 && ${#cache_pkgs[@]} -gt 0 ]] || die "empty package list"
[[ $(printf '%s\n' "${all_iso_pkgs[@]}") == "$(<"$src"/iso/profile/packages.x86_64)" ]] \
    || die "iso/profile/packages.x86_64 is out of sync with iso/packages/{base,live,desktop,seclegion}.list"

# Resolve in a scratch database (never the container's own): -Syu on an empty local database
# only refreshes the sync databases. Every name must resolve to a core or extra package.
# The [seclegion] repository is not in the cache yet and is not an official one: the lock-only
# configuration is the profile's pacman.conf without that section.
pconf=/work/lock-pacman.conf
sl_lock_conf /work/profile/pacman.conf "$pconf" || exit 1
lockdb=/work/lockdb
rm -rf "$lockdb"
install -d "$lockdb/local"
printf '9\n' > "$lockdb/local/ALPM_DB_VERSION"
pacman --config "$pconf" --dbpath "$lockdb" -Syu --noconfirm
resolve() {  # resolve <pkg>...: "<repo> <name> <version> <url>" per package incl. dependencies
    pacman --config "$pconf" --dbpath "$lockdb" --noconfirm -Sp --print-format '%r %n %v %l' "$@" | LC_ALL=C sort -u
}
resolve "${iso_pkgs[@]}" > /work/iso.resolved || die "cannot resolve the ISO package set"
resolve "${cache_pkgs[@]}" > /work/cache.resolved || die "cannot resolve the offline cache package set"
for f in /work/iso.resolved /work/cache.resolved; do
    [[ -s $f ]] || die "$f is empty"
    while read -r repo name _ver _url; do
        [[ $repo == core || $repo == extra ]] || die "$name resolves to repository '$repo' (only core and extra are allowed)"
    done < "$f"
done
for p in "${iso_pkgs[@]}"; do awk -v p="$p" '$2 == p { f = 1 } END { exit !f }' /work/iso.resolved || die "not a package: $p"; done
for p in "${cache_pkgs[@]}"; do awk -v p="$p" '$2 == p { f = 1 } END { exit !f }' /work/cache.resolved || die "not a package: $p"; done
sl_check_nvidia_pair /work/cache.resolved || die "the cached NVIDIA modules do not match the cached nvidia-utils"

# Download the cache set (full upgrade semantics, download only) into pacman's cache, which is
# the host-side pkgcache: reused across builds. Every package must pass its signature check.
pacman --config "$pconf" --dbpath "$lockdb" -Syuw --noconfirm "${cache_pkgs[@]}"
resolve "${cache_pkgs[@]}" > /work/cache.resolved

# The cache keeps the Arch packager .sig next to every package; its local database is
# unsigned (R13-4). Only the files of this resolution go in, never stale ones from pkgcache.
cache=/work/profile/airootfs/opt/seclegion/cache
rm -rf "$cache"
install -d -m 0755 "$cache"
urldecode() { printf '%b' "${1//%/\\x}"; }
while read -r _repo _name _ver url; do
    file=$(urldecode "${url##*/}")
    [[ -f /var/cache/pacman/pkg/$file && -f /var/cache/pacman/pkg/$file.sig ]] \
        || die "cache: $file or its .sig is missing"
    cp --reflink=auto --no-preserve=ownership -- "/var/cache/pacman/pkg/$file" "/var/cache/pacman/pkg/$file.sig" "$cache/"
done < /work/cache.resolved
(cd "$cache" && repo-add --quiet --include-sigs seclegion-cache.db.tar.zst -- *.pkg.tar.zst)
[[ $(find "$cache" -name '*.pkg.tar.*' -not -name '*.sig' | wc -l) == "$(find "$cache" -name '*.sig' | wc -l)" ]] \
    || die "cache: a package has no .sig"

# The signed [seclegion] repository of tools/build-pkgs goes in as a sub-directory, after the count
# above (which is about the official packages). Every package needs its .sig; the database files
# were checked at the top of the build.
install -d -m 0755 "$cache/seclegion"
cp --no-preserve=ownership -- "$seclegion_repo"/* "$cache/seclegion/"
sl_pkgs=$(find "$cache/seclegion" -name '*.pkg.tar.*' -not -name '*.sig' | wc -l)
[[ $sl_pkgs -gt 0 && $sl_pkgs == "$(find "$cache/seclegion" -name '*.pkg.tar.*.sig' | wc -l)" ]] \
    || die "[seclegion] repository: no package, or a package without .sig"

# out/packages.lock: what the build resolved, from the dated archive.
{
    echo "# seclegion packages.lock v1: <set> <repo> <name> <version> [sha256 of the cached file]"
    echo "# archive $pin_date"
    awk '{ print "iso", $1, $2, $3 }' /work/iso.resolved
    while read -r repo name ver url; do
        file=$(urldecode "${url##*/}")
        sum=$(sha256sum -- "$cache/$file")
        echo "cache $repo $name $ver ${sum%% *}"
    done < /work/cache.resolved
} > /work/out/packages.lock
echo "packages-lock-ok: ${#iso_pkgs[@]} ISO and ${#cache_pkgs[@]} cache packages requested," \
    "$(grep -c '^iso ' /work/out/packages.lock) and $(grep -c '^cache ' /work/out/packages.lock) resolved, archive $pin_date"
rm -rf "$lockdb" /work/iso.resolved /work/cache.resolved

# Trust the [seclegion] key for this container's pacman, which mkarchiso runs: take the three
# keyring files from the keyring package of the repository, check them against the fingerprint
# tools/lib/mkrepo.sh wrote, then pacman-key --populate seclegion. Nothing else adds a key.
kpkgs=("$seclegion_repo"/seclegion-keyring-*.pkg.tar.zst)
[[ ${#kpkgs[@]} == 1 && -f ${kpkgs[0]} ]] || die "[seclegion] repository: need exactly one seclegion-keyring package"
ktmp=$(mktemp -d /work/keyring.XXXXXX)
sl_extract_keyring "${kpkgs[0]}" "$src_repo_dir/dev-key.fingerprint" "$ktmp" || exit 1
kdir=usr/share/pacman/keyrings
install -d -m 0755 /usr/share/pacman/keyrings
install -m 0644 -t /usr/share/pacman/keyrings "$ktmp/$kdir/seclegion.gpg" "$ktmp/$kdir/seclegion-trusted" "$ktmp/$kdir/seclegion-revoked"
rm -rf "$ktmp"
# populate locally signs the trusted key, which needs this container's own master key; the Arch
# image ships a keyring without one. This throwaway container's key never reaches the ISO
# (pacman-init.service makes the live system's own at boot).
gpg --homedir /etc/pacman.d/gnupg --list-secret-keys 2>/dev/null | grep -q '^sec' || pacman-key --init
pacman-key --populate seclegion
echo "seclegion-key-ok: $(<"$src_repo_dir/dev-key.fingerprint")"
# pacman's cache is the reused host pkgcache: a [seclegion] package from an earlier build keeps its
# file name but carries the earlier throwaway key's signature, and pacman would install that copy and
# reject it. Drop exactly this repository's file names from the cache so mkarchiso fetches them anew.
for f in "$seclegion_repo"/*.pkg.tar.zst; do
    rm -f -- "/var/cache/pacman/pkg/${f##*/}" "/var/cache/pacman/pkg/${f##*/}.sig"
done

# The ISO package list is the generated one; the live pacman is pinned to the same archive (A4).
printf '%s\n' "${all_iso_pkgs[@]}" > /work/profile/packages.x86_64
# The live system keeps the runtime [seclegion] Server (the repository sits at
# /opt/seclegion/cache/seclegion there). mkarchiso installs the packages while the airootfs is
# still being built, so its own copy (the profile's pacman.conf) points at the build tree.
install -D -m 0644 /work/profile/pacman.conf /work/profile/airootfs/etc/pacman.conf
sl_build_conf /work/profile/pacman.conf || exit 1

# The desktop components and the tools they need, as files (R13-1). The launchers find
# ../desktop/<component> relative to themselves, hence bin/ next to desktop/.
share=/work/profile/airootfs/usr/share/seclegion
rm -rf "${share:?}/desktop" "${share:?}/bin"  # the airootfs keeps its own files here (kiosk/)
install -d -m 0755 "$share/bin"
cp -a --no-preserve=ownership "$src"/desktop "$share/desktop"
find "$share/desktop" -type d \( -name tests -o -name __pycache__ \) -prune -exec rm -rf {} +
for t in seclegion-doctor seclegion-root-apply seclegion-set seclegion-settings seclegion-sysmon seclegion-theme seclegion-theme-pick seclegion-wifi; do
    install -m 0755 "$src/tools/$t" "$share/bin/$t"
done
install -m 0644 /work/out/packages.lock "$share/packages.lock"

rm -f /work/out/*.iso /work/out/SHA256SUMS
mkarchiso -v -w /work/work -o /work/out /work/profile

cd /work/out
sha256sum -- *.iso > SHA256SUMS
# The work tree (~12 G, read-only dirs) and the profile copy are wiped at the next start anyway;
# drop them now so the VM gates that follow have the space.
rm -rf /work/work /work/profile
ls -l /work/out
