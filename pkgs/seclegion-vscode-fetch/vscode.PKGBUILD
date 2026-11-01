# shellcheck shell=bash disable=SC2034,SC2154
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Template that seclegion-vscode-fetch copies to a scratch directory and builds on the user's machine.
# It is never built into our repository. VENDOR_VERSION, VENDOR_SHA256 and VENDOR_PAYLOAD (the already
# verified tarball) come from the fetch script's environment; makepkg checks the sha256 again.
pkgname=seclegion-vscode
pkgver=${VENDOR_VERSION:?run through seclegion-vscode-fetch}
pkgrel=1
pkgdesc='Visual Studio Code, Microsoft build (installed by seclegion-vscode-fetch)'
arch=('x86_64')
url='https://code.visualstudio.com'
license=('custom:Microsoft')
depends=('gtk3' 'nss' 'alsa-lib' 'libxkbfile' 'libsecret')
provides=('code')
conflicts=('code')
options=('!strip' '!debug' '!lto')
source=("vscode-$pkgver.tar.gz::file://${VENDOR_PAYLOAD:?run through seclegion-vscode-fetch}")
noextract=("vscode-$pkgver.tar.gz")
sha256sums=("${VENDOR_SHA256:?run through seclegion-vscode-fetch}")

package() {
    install -d "$pkgdir/opt/vscode" "$pkgdir/usr/bin" "$pkgdir/usr/share/applications" "$pkgdir/usr/share/pixmaps"
    bsdtar -xf "$srcdir/vscode-$pkgver.tar.gz" -C "$pkgdir/opt/vscode" --strip-components=1 --no-same-owner
    chmod 4755 "$pkgdir/opt/vscode/chrome-sandbox"
    # Like Arch's own wrappers: one flag per line from ~/.config/code-flags.conf (skel ships
    # --ozone-platform-hint=auto), so the upstream launcher runs Wayland-native.
    cat > "$pkgdir/usr/bin/code" <<'EOF'
#!/bin/bash
flags=()
conf="${XDG_CONFIG_HOME:-$HOME/.config}/code-flags.conf"
if [[ -f $conf ]]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*(#|$) ]] || flags+=("$line")
    done < "$conf"
fi
exec /opt/vscode/bin/code "${flags[@]}" "$@"
EOF
    chmod 755 "$pkgdir/usr/bin/code"
    install -Dm644 "$pkgdir/opt/vscode/resources/app/resources/linux/code.png" "$pkgdir/usr/share/pixmaps/seclegion-vscode.png"
    install -Dm644 "$pkgdir/opt/vscode/resources/app/LICENSE.rtf" "$pkgdir/usr/share/licenses/$pkgname/LICENSE.rtf"
    cat > "$pkgdir/usr/share/applications/seclegion-vscode.desktop" <<'EOF'
[Desktop Entry]
Name=Visual Studio Code
Comment=Code editing, redefined
Exec=/usr/bin/code %F
Icon=seclegion-vscode
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=Utility;TextEditor;Development;IDE;
MimeType=text/plain;
Keywords=vscode;
EOF
}
