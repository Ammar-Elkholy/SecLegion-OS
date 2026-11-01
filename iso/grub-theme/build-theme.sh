#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Build the GRUB theme at ISO build time (plan r13 J1b). Runs INSIDE the build
# container (tools/container-build.sh), where grub and ttf-jetbrains-mono are installed.
# Nothing it generates (.pf2 fonts, the copied background, theme.txt) is committed.
#
# Usage: build-theme.sh DEST_DIR SHA_FILE
#   DEST_DIR  e.g. /work/profile/grub/themes/seclegion (recreated empty)
#   SHA_FILE  e.g. /work/out/grub-theme.sha256 (sha256 of every file in DEST_DIR)
#
# Inputs, all read from the repository checkout this script lives in:
#   desktop/theme/tokens.toml       [colors] -> @BG@ @SURFACE@ @SURFACE2@ @MUTED@ @ACCENT@
#   "Grub Splash.png"               -> background.png (byte for byte)
#   iso/grub-theme/theme.txt.in     -> theme.txt
# Reproducible: no timestamps in the outputs; mtimes are set to SOURCE_DATE_EPOCH.
set -euo pipefail

die() { echo "build-theme: $*" >&2; exit 1; }

(( $# == 2 )) || die "usage: $0 DEST_DIR SHA_FILE"
dest=$1
sha_file=$2
: "${SOURCE_DATE_EPOCH:?}"
[[ $SOURCE_DATE_EPOCH =~ ^[0-9]+$ ]] || die "SOURCE_DATE_EPOCH must be a number"

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$here/../.." && pwd)
tokens=$repo/desktop/theme/tokens.toml
splash="$repo/Grub Splash.png"
template=$here/theme.txt.in
ttf_dir=${SECLEGION_TTF_DIR:-/usr/share/fonts/TTF}
regular=$ttf_dir/JetBrainsMono-Regular.ttf
bold=$ttf_dir/JetBrainsMono-Bold.ttf

for f in "$tokens" "$splash" "$template" "$regular" "$bold"; do
    [[ -f $f ]] || die "missing input: $f"
done
command -v grub-mkfont >/dev/null || die "grub-mkfont not found (install grub)"

# One colour from the [colors] table of tokens.toml: it must be a #RRGGBB value.
token() {  # token <key>
    local value
    value=$(awk -v key="$1" '
        /^\[/ { in_colors = ($0 == "[colors]"); next }
        in_colors && $1 == key && $2 == "=" { gsub(/"/, "", $3); print $3; exit }' "$tokens")
    [[ $value =~ ^#[0-9A-Fa-f]{6}$ ]] || die "tokens.toml [colors] $1 is not #RRGGBB: '$value'"
    printf '%s' "$value"
}

# The font name grub-mkfont embedded in a .pf2: the theme must quote it exactly.
font_name() {  # font_name <file.pf2>
    local name
    name=$(grep -a -o -m1 'JetBrains Mono[ A-Za-z]* [0-9][0-9]*' "$1" | head -n1)
    [[ -n $name ]] || die "no font name found in $1"
    printf '%s' "$name"
}

rm -rf -- "$dest"
mkdir -p -- "$dest"

grub-mkfont -s 18 -o "$dest/jetbrains-mono-18.pf2" "$regular"
grub-mkfont -s 28 -o "$dest/jetbrains-mono-bold-28.pf2" "$bold"
cp -- "$splash" "$dest/background.png"
chmod 0644 -- "$dest/background.png"  # the source file mode must not leak into the theme

body=$(font_name "$dest/jetbrains-mono-18.pf2")
title=$(font_name "$dest/jetbrains-mono-bold-28.pf2")

# Plain assignments, so a bad token stops the build (a failure inside $(...) in an
# argument list would not).
bg=$(token bg)
surface=$(token surface)
surface2=$(token surface2)
muted=$(token muted)
accent=$(token accent)

sed -e "s|@BG@|$bg|g" \
    -e "s|@SURFACE@|$surface|g" \
    -e "s|@SURFACE2@|$surface2|g" \
    -e "s|@MUTED@|$muted|g" \
    -e "s|@ACCENT@|$accent|g" \
    -e "s|@FONT_BODY@|$body|g" \
    -e "s|@FONT_TITLE@|$title|g" \
    "$template" > "$dest/theme.txt"
! grep -q '@[A-Z0-9_]*@' "$dest/theme.txt" || die "unfilled placeholder left in theme.txt"

# Fixed mtimes, then one sha256 per file in a fixed order: the same inputs and the same
# SOURCE_DATE_EPOCH give a byte-identical sha file.
find "$dest" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
mkdir -p -- "$(dirname "$sha_file")"
(cd "$dest" && LC_ALL=C find . -type f -printf '%P\n' | LC_ALL=C sort | xargs -d '\n' sha256sum --) > "$sha_file"
echo "build-theme: $(wc -l < "$sha_file") files in $dest, hashes in $sha_file"
