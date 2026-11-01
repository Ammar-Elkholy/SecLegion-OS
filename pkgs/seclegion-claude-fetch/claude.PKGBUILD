# shellcheck shell=bash disable=SC2034,SC2154
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
#
# Template that seclegion-claude-fetch copies to a scratch directory and builds on the user's machine.
# It is never built into our repository. VENDOR_VERSION, VENDOR_SHA256 and VENDOR_PAYLOAD (the already
# verified binary) come from the fetch script's environment; makepkg checks the sha256 again.
pkgname=seclegion-claude
pkgver=${VENDOR_VERSION:?run through seclegion-claude-fetch}
pkgrel=1
pkgdesc='Claude Code, Anthropic build (installed by seclegion-claude-fetch)'
arch=('x86_64')
url='https://code.claude.com'
license=('custom:Anthropic')
depends=('glibc')
provides=('claude-code')
conflicts=('claude-code')
options=('!strip' '!debug' '!lto')
source=("claude-$pkgver::file://${VENDOR_PAYLOAD:?run through seclegion-claude-fetch}")
noextract=("claude-$pkgver")
sha256sums=("${VENDOR_SHA256:?run through seclegion-claude-fetch}")

package() {
    install -Dm755 "$srcdir/claude-$pkgver" "$pkgdir/opt/claude-code/claude"
    # pacman owns the version, so Claude Code's own updater is off (DISABLE_UPDATES also blocks
    # `claude update`). A wrapper, not /etc/profile.d: it also holds for launchers that never read it.
    install -d "$pkgdir/usr/bin"
    cat > "$pkgdir/usr/bin/claude" <<'EOF'
#!/bin/sh
export DISABLE_AUTOUPDATER=1 DISABLE_UPDATES=1
exec /opt/claude-code/claude "$@"
EOF
    chmod 755 "$pkgdir/usr/bin/claude"
    install -d "$pkgdir/usr/share/licenses/$pkgname"
    cat > "$pkgdir/usr/share/licenses/$pkgname/LICENSE" <<'EOF'
Claude Code is proprietary software of Anthropic PBC. It is used under Anthropic's Commercial Terms
(https://www.anthropic.com/legal/commercial-terms) or Consumer Terms, and the notes at
https://code.claude.com/docs/en/legal-and-compliance. This package only installed the binary Anthropic
publishes at https://downloads.claude.ai/claude-code-releases; SecLegion OS does not redistribute it.
EOF
}
