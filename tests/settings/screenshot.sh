#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
# G5: run seclegion-settings --page PAGE inside a NESTED Hyprland (never the live session), grim the
# nested output, and check theme pixels: the sidebar is sl_bg and the active choice button is sl_accent.
#   bash tests/settings/screenshot.sh power  -> sidebar-bg-ok accent-ok (+ the PNG path)
# The app runs on fakes only: SL_HOME/SL_ETC under .build/t8, SL_SYSFS=sysfs-nobat, PATH of stubs.
# Exit 1 on failure, 77 if no nested Hyprland can start (UNVERIFIED). OCR is skipped (no tesseract).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
page="${1:?usage: screenshot.sh PAGE}"
out="$repo/.build/t8"
png="$out/settings-$page.png"
# shellcheck source=tests/ws/nested.sh
. "$repo/tests/ws/nested.sh"
app_pid=""
cleanup() {
    [ -z "$app_pid" ] || kill "$app_pid" 2>/dev/null || true
    nested_stop
}
trap cleanup EXIT

rm -rf -- "$out/home" "$out/etc" "$out/state" "$out/bin" "$out/rt"
mkdir -p "$out/home" "$out/etc" "$out/state" "$out/rt"
chmod 700 "$out/rt"
PYTHONPATH="$repo/desktop/settings/tests" /usr/bin/python3 -c \
    'import sys; from pathlib import Path; import stubs; stubs.make_bin(Path(sys.argv[1]))' "$out/bin" || exit 1

hex() { /usr/bin/python3 - "$@" <<'PY'
import sys
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

png, x0, y0, w, h = sys.argv[1], *map(int, sys.argv[2:6])
pb = GdkPixbuf.Pixbuf.new_from_file(png)
n, stride, px = pb.get_n_channels(), pb.get_rowstride(), pb.get_pixels()
def at(x, y):
    i = y * stride + x * n
    return px[i], px[i + 1], px[i + 2]
close = lambda a, b: all(abs(p - q) <= 6 for p, q in zip(a, b))
want = tuple(int(sys.argv[6][i:i + 2], 16) for i in (0, 2, 4))
# sidebar mode: one pixel near the window's left edge; accent mode: count matching pixels in the box
if sys.argv[7] == "pixel":
    print("ok" if close(at(x0, y0), want) else "bad %s" % (at(x0, y0),))
else:
    c = sum(close(at(x, y), want) for y in range(y0, min(y0 + h, pb.get_height())) for x in range(x0, min(x0 + w, pb.get_width())))
    print("ok" if c >= 400 else "bad count=%d" % c)
PY
}

nested_start || exit 77
sock="$(nested_hyprctl instances -j | /usr/bin/python3 -c \
    'import json,sys; print([i["wl_socket"] for i in json.load(sys.stdin) if i["instance"]==sys.argv[1]][0])' "$NESTED_SIG")"
[ -n "$sock" ] || { echo "screenshot: no nested wayland socket" >&2; exit 1; }
bg="$(grep -o 'sl_bg #[0-9a-f]*' "$repo/desktop/theme/default/colors.css" | cut -d'#' -f2)"
acc="$(grep -o 'sl_accent #[0-9a-f]*' "$repo/desktop/theme/default/colors.css" | cut -d'#' -f2)"

env -i PATH="$out/bin" HOME="$out/home" SL_HOME="$out/home" SL_ETC="$out/etc" \
    SL_SYSFS="$repo/desktop/settings/tests/fixtures/sysfs-nobat" SL_STUB_STATE="$out/state" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$sock" GDK_BACKEND=wayland \
    /usr/bin/python3 "$repo/tools/seclegion-settings" --page "$page" > "$out/app.log" 2>&1 &
app_pid=$!

geom=""
for _ in $(seq 1 100); do
    kill -0 "$app_pid" 2>/dev/null || { echo "screenshot: app exited:" >&2; cat "$out/app.log" >&2; exit 1; }
    geom="$(nested_hyprctl clients -j | /usr/bin/python3 -c \
        'import json,sys; c=json.load(sys.stdin); print(*c[0]["at"], *c[0]["size"]) if c else None')"
    [ "$geom" != "None" ] && [ -n "$geom" ] && break
    sleep 0.2
done
[ -n "$geom" ] && [ "$geom" != "None" ] || { echo "screenshot: no window appeared" >&2; exit 1; }
sleep 1.5   # first frame + page build
geom="$(nested_hyprctl clients -j | /usr/bin/python3 -c 'import json,sys; c=json.load(sys.stdin)[0]; print(*c["at"], *c["size"])')"
read -r gx gy gw gh <<< "$geom"
env -i XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$sock" grim "$png" || { echo "screenshot: grim failed" >&2; exit 1; }

fail=0
# sidebar: a pixel just inside the window's left edge, 40px below the top
r="$(hex "$png" $((gx + 4)) $((gy + gh - 20)) 0 0 "$bg" pixel)"
if [ "$r" = ok ]; then printf 'sidebar-bg-ok '; else echo "sidebar-bg-FAIL: $r" >&2; fail=1; fi
# content area: right 70% of the window, count #accent pixels (the active Balanced button)
r="$(hex "$png" $((gx + gw * 3 / 10)) $((gy + 40)) $((gw * 7 / 10)) $((gh - 40)) "$acc" box)"
if [ "$r" = ok ]; then echo 'accent-ok'; else echo "accent-FAIL: $r" >&2; fail=1; fi
echo "$png"
exit "$fail"
