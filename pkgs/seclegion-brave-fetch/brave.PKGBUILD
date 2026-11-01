# shellcheck shell=bash disable=SC2034,SC2154
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Template that seclegion-brave-fetch copies to a scratch directory and builds on the user's machine.
# It is never built into our repository. VENDOR_VERSION, VENDOR_SHA256 and VENDOR_PAYLOAD (the already
# verified zip) come from the fetch script's environment; makepkg checks the sha256 again.
pkgname=seclegion-brave
pkgver=${VENDOR_VERSION:?run through seclegion-brave-fetch}
pkgrel=1
pkgdesc='Brave browser, official release build (installed by seclegion-brave-fetch)'
arch=('x86_64')
url='https://brave.com'
license=('MPL-2.0')
depends=('gtk3' 'nss' 'alsa-lib' 'libcups' 'libxss')
provides=('brave-browser')
conflicts=('brave-bin')
options=('!strip' '!debug' '!lto')
source=("brave-$pkgver.zip::file://${VENDOR_PAYLOAD:?run through seclegion-brave-fetch}")
noextract=("brave-$pkgver.zip")
sha256sums=("${VENDOR_SHA256:?run through seclegion-brave-fetch}")

package() {
    install -d "$pkgdir/opt/brave" "$pkgdir/usr/bin" "$pkgdir/usr/share/applications" "$pkgdir/usr/share/pixmaps"
    bsdtar -xf "$srcdir/brave-$pkgver.zip" -C "$pkgdir/opt/brave" --no-same-owner
    chmod 755 "$pkgdir/opt/brave/brave" "$pkgdir/opt/brave/brave-browser"
    chmod 4755 "$pkgdir/opt/brave/chrome-sandbox"
    # Like Arch's own wrappers: one flag per line from ~/.config/brave-flags.conf (skel ships
    # --ozone-platform-hint=auto), so the upstream launcher runs Wayland-native.
    cat > "$pkgdir/usr/bin/brave" <<'EOF'
#!/bin/bash
flags=()
conf="${XDG_CONFIG_HOME:-$HOME/.config}/brave-flags.conf"
if [[ -f $conf ]]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*(#|$) ]] || flags+=("$line")
    done < "$conf"
fi
exec /opt/brave/brave-browser "${flags[@]}" "$@"
EOF
    chmod 755 "$pkgdir/usr/bin/brave"
    install -Dm644 "$pkgdir/opt/brave/product_logo_256.png" "$pkgdir/usr/share/pixmaps/seclegion-brave.png"
    install -Dm644 "$pkgdir/opt/brave/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    cat > "$pkgdir/usr/share/applications/seclegion-brave.desktop" <<'EOF'
[Desktop Entry]
Name=Brave Web Browser
GenericName=Web Browser
Comment=Browse the web
Exec=/usr/bin/brave %U
Icon=seclegion-brave
Type=Application
StartupNotify=true
StartupWMClass=Brave-browser
Categories=Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
EOF
}
