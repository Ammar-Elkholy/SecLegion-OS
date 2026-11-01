#!/bin/bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# tools/seclegion-theme-pick against a stub rofi and a stub seclegion-theme: every choice must
# end in the right seclegion-theme call. Prints "theme-pick-ok".
set -u
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
W="$(mktemp -d "${TMPDIR:-/tmp}/sl-theme-pick.XXXXXX")"
trap 'rm -rf -- "$W"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

cat > "$W/theme" <<'STUB'
#!/bin/bash
echo "$*" >> "$W_LOG"
case "$1 $2" in
    "list --json") cat "$W_JSON" ;;
    "auto status") echo "${W_AUTO:-off}" ;;
esac
STUB
# rofi stub: records its args and input, then answers with the 0-based index of the first input
# line containing $W_PICK (empty W_PICK = Escape)
cat > "$W/rofi" <<'STUB'
#!/bin/bash
echo "$*" > "$W_ROFI_ARGS"
cat > "$W_ROFI_IN"
[ -n "${W_PICK:-}" ] || exit 1
n="$(grep -n -F -- "$W_PICK" "$W_ROFI_IN" | head -n1 | cut -d: -f1)"
echo $((n - 1))
STUB
chmod +x "$W/theme" "$W/rofi"
cat > "$W/list.json" <<'J'
[{"id":"seclegion-dark","label":"SecLegion Dark","accent":"#00ff88","current":true},
 {"id":"seclegion-teal","label":"SecLegion Teal","accent":"#3df0cb","current":false},
 {"id":"wallpaper:ab12cd34","label":"Wallpaper ab12cd34","accent":"#00edf7","current":false}]
J
export W_LOG="$W/log" W_JSON="$W/list.json" W_ROFI_ARGS="$W/rofi-args" W_ROFI_IN="$W/rofi-in"
export SECLEGION_THEME="$W/theme" SECLEGION_ROFI="$W/rofi" XDG_STATE_HOME="$W/state"
mkdir -p "$W/state/seclegion/theme/current"
echo '* { sl-bg: #000000; }' > "$W/state/seclegion/theme/current/rofi-colors.rasi"

# pick PATTERN [AUTO]: run the picker choosing the first entry containing PATTERN; print the
# seclegion-theme calls it made besides the two it always makes (list, auto status)
pick() {
    : > "$W_LOG"
    W_PICK="$1" W_AUTO="${2:-off}" bash "$SRC/tools/seclegion-theme-pick" || fail "picker rc $? for '$1'"
    grep -v '^list --json$\|^auto status$' "$W_LOG"
}

[ "$(pick 'Teal')" = "apply --theme seclegion-teal" ] || fail "teal: $(cat "$W_LOG")"
[ "$(pick 'ab12cd34')" = "apply --theme wallpaper:ab12cd34" ] || fail "wallpaper: $(cat "$W_LOG")"
[ "$(pick 'Auto theme' off)" = "auto on" ] || fail "auto on: $(cat "$W_LOG")"
[ "$(pick 'Auto theme' on)" = "auto off" ] || fail "auto off: $(cat "$W_LOG")"
[ "$(pick 'Reset')" = "reset" ] || fail "reset: $(cat "$W_LOG")"
[ -z "$(pick '')" ] || fail "Escape applied something: $(cat "$W_LOG")"

grep -q '^\* SecLegion Dark' "$W_ROFI_IN" || fail "current theme not marked: $(cat "$W_ROFI_IN")"
[ "$(wc -l < "$W_ROFI_IN")" = 5 ] || fail "want 3 themes + auto + reset, got: $(cat "$W_ROFI_IN")"
grep -qF "$W/state/seclegion/theme/current/rofi-colors.rasi" "$W_ROFI_ARGS" || fail "rofi not themed by rofi-colors.rasi: $(cat "$W_ROFI_ARGS")"

echo theme-pick-ok
