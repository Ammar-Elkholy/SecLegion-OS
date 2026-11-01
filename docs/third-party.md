# Third-party components

Implements [spec.md A8](spec/v1/spec.md) and PRD sections 7.1 and 8.2: every non-official package or
imported file is recorded with source, version, trust model, update owner and removal procedure.

Status: SKELETON (M0). Only build-time and placeholder inputs exist so far.

| Component | Source | Version | Trust model | Update owner | Removal |
|---|---|---|---|---|---|
| archiso `releng` profile (placeholder in `iso/profile`) | Arch Linux `archiso` package, `/usr/share/archiso/configs/releng` | as installed on the build host, 2026-10-14 | Arch official repo signature | owner | replaced in M1 |
| `archlinux` container image (build only, never shipped) | Docker Hub official image | digest in `tools/docker-build.sh` | pinned by sha256 digest | owner (bump deliberately) | n/a |
| QEMU, edk2-ovmf (test host only) | Arch official repos | host packages | Arch official repo signature | owner | n/a |
| pytest, ruff, reuse, shellcheck-py (dev `.venv` only) | PyPI | unpinned in `requirements-dev.txt` | PyPI, no hash pinning yet | owner | `rm -rf .venv` |

## Theme packages and font (R3b, D6)

Built into `[seclegion]` from upstream sources fetched at build time; nothing binary is committed.
Trust model for each row: upstream GitHub tag tarball pinned by sha256 in the PKGBUILD (`makepkg` rejects a
mismatch; `tests/pkgs/test_theme_pkgs.py` G13b checks it). Update owner: owner (bump tag and sha256 together).

| Component | Source | Version (tag) | Pinned | sha256 | Licence | Removal |
|---|---|---|---|---|---|---|
| `seclegion-themes-graphite` (GTK, Graphite-Dark, built with sassc) | https://github.com/vinceliuice/Graphite-gtk-theme/archive/refs/tags/2026-08-23.tar.gz | 2026-08-23 | 2026-10-18 | `a46a5c4bd9562332221c504a58da0d6f4d729c8a74ab26e002b41516df52acb9` | GPL-3.0 | `pacman -R seclegion-themes-graphite` |
| `seclegion-themes-bibata` (Bibata Modern Classic, Modern Ice; sizes 22 to 96) release asset `Bibata-Modern-Classic.tar.xz` | https://github.com/ful1e5/Bibata_Cursor/releases/download/v2.0.7/Bibata-Modern-Classic.tar.xz | v2.0.7 | 2026-10-18 | `7d3495864e5bbef02f5e77de760b2905903b63c71495a78ef6306d19a3b556d8` | GPL-3.0 | `pacman -R seclegion-themes-bibata` |
| same package, release asset `Bibata-Modern-Ice.tar.xz` | https://github.com/ful1e5/Bibata_Cursor/releases/download/v2.0.7/Bibata-Modern-Ice.tar.xz | v2.0.7 | 2026-10-18 | `a68cae60c4dc706350e194ebc91c5fe48bc7bc9d59e119555834a2a7ee5078ef` | GPL-3.0 | as above |
| same package, tag source tarball (licence text only) | https://github.com/ful1e5/Bibata_Cursor/archive/refs/tags/v2.0.7.tar.gz | v2.0.7 | 2026-10-18 | `1f21e5cade53d668476f973bd8ec827882a0e32c38e0e766abf007f8b3b46313` | GPL-3.0 | as above |
| `seclegion-fonts-figtree` (two variable TTFs) | https://github.com/erikdkennedy/figtree/archive/refs/tags/v2.0.3.tar.gz | v2.0.3 | 2026-10-18 | `0338c574a26a0f0ba0b796c0c205a4174d09399cf7deed2e4c4123bae789d7f3` | OFL-1.1 | `pacman -R seclegion-fonts-figtree` |
| Tela-circle icons (grey), no package of ours | Arch official `extra/tela-circle-icon-theme-grey` | 2026_07_07-1 at the time of writing | 2026-10-18 | Arch repo signature | GPL-3.0 | `pacman -R tela-circle-icon-theme-grey` |

Why Bibata uses release assets: building the cursors needs `python-clickgen` and an SVG toolchain,
neither of which is in the Arch repositories (`pacman -Si python-clickgen` finds nothing). Why no Tela
package: Arch already ships it, so D6's "vendor" is satisfied by the official package. Papirus-Dark remains
the fallback icon theme (Arch `papirus-icon-theme`).

## Vendor fetchers: VS Code, Brave and Claude Code (R5, U14, O8)

The `[seclegion]` repository and the ISO never contain a Microsoft, Brave or Anthropic binary (Microsoft's licence for
the VS Code binaries is proprietary and does not allow us to redistribute them). The packages
`seclegion-vscode-fetch`, `seclegion-brave-fetch` and `seclegion-claude-fetch` ship only a fetch script, a pinned manifest
(`/usr/share/seclegion/vendor/<name>.toml`: version, url, sha256, where the vendor publishes its hash) and a
package template. The user runs `seclegion-<name>-fetch` on an online machine (first online boot): it
downloads the versioned vendor URL (https only), checks the sha256 against the pin (and, for Brave, against
the `.sha256` file the release publishes), writes nothing on a mismatch, then builds a local package with
`makepkg` and installs it with `sudo pacman -U` into `/opt/<name>`. So redistribution happens on the user's
own machine, never from our servers. The locally built packages carry the vendor licence text in
`/usr/share/licenses/seclegion-<name>/`.

Trust model for both rows: TLS to the vendor host plus the sha256 pinned in the manifest in this repository
(reviewed in git), cross-checked by `tools/vendor-bump` against the vendor-published hash before the pin is
changed. Update owner: owner. VS Code publishes no signature for the tarball; Brave's
`.sha256.asc` signature URL is recorded in the manifest but not verified on the user's machine (no Brave
key is shipped). Claude Code publishes `manifest.json` per release with the sha256 of every platform binary
and a detached GPG signature `manifest.json.sig` (key fingerprint `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF
1A7E CACE`, https://downloads.claude.ai/keys/claude-code.asc); the pin is `platforms.linux-x64.checksum`
of the `stable` release, checked when pinned (signature verified with gpg in a scratch keyring), and the
fetcher checks the downloaded bytes against it. The binary is a single file installed to
`/opt/claude-code/claude`; `/usr/bin/claude` is a wrapper that sets `DISABLE_AUTOUPDATER=1` and
`DISABLE_UPDATES=1`, so only `tools/vendor-bump claude` plus `seclegion-claude-fetch` move the version.

| Component | Source | Version | Pinned | sha256 | Licence | Trust model | Update owner | Removal |
|---|---|---|---|---|---|---|---|---|
| `seclegion-vscode-fetch` (fetcher, no Microsoft binary inside) | https://update.code.visualstudio.com/1.142.0/linux-x64/stable (Microsoft x64 tarball) | 1.142.0 | 2026-10-18 | per-manifest (`pkgs/seclegion-vscode-fetch/vscode.toml`) | fetcher MIT; the installed VS Code build is `custom:Microsoft` | TLS plus pinned sha256, cross-checked with the update API `sha256hash` | owner (`tools/vendor-bump vscode`) | `pacman -R seclegion-vscode-fetch seclegion-vscode` |
| `seclegion-brave-fetch` (fetcher, no Brave binary inside) | https://github.com/brave/brave-browser/releases/download/v1.97.59/brave-browser-1.97.59-linux-amd64.zip | 1.97.59 | 2026-10-18 | per-manifest (`pkgs/seclegion-brave-fetch/brave.toml`) | fetcher MIT; the installed Brave build is MPL-2.0 (with Chromium components) | TLS plus pinned sha256, cross-checked with the release `.sha256` file at fetch time and by `tools/vendor-bump` | owner (`tools/vendor-bump brave`) | `pacman -R seclegion-brave-fetch seclegion-brave` |
| `seclegion-claude-fetch` (fetcher, no Anthropic binary inside) | https://downloads.claude.ai/claude-code-releases/2.1.308/linux-x64/claude | 2.1.308 | 2026-10-30 | per-manifest (`pkgs/seclegion-claude-fetch/claude.toml`) | fetcher MIT; the installed Claude Code build is `custom:Anthropic` (proprietary) | TLS plus pinned sha256 from the vendor's release `manifest.json` (signed with Anthropic's release key, verified when pinned) | owner (`tools/vendor-bump claude`) | `pacman -R seclegion-claude-fetch seclegion-claude` |

### Update SLA (O8) and the canary

Brave and VS Code must be at most 7 days behind the vendor. `tools/canary` prints the pinned and latest
version per vendor and the days between their release dates, and exits nonzero when a vendor is more than 7
days ahead. It runs weekly on the OWNER's host from `systemd/seclegion-canary.timer` (a user timer; copy the
two units to `~/.config/systemd/user/`, point `ExecStart` at the checkout, `systemctl --user enable --now
seclegion-canary.timer`; they are never installed on a SecLegion system). When it fails: run
`tools/vendor-bump <name>` (network; prints the diff), update the version in the row above, rebuild the
fetcher package and commit.
