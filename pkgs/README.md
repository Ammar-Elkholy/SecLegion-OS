# pkgs

One directory per package in the signed `[seclegion]` repository, each with a `PKGBUILD`. Build all of
them with `tools/build-pkgs`; `make lint-pkgs` checks this directory.

## Files from outside the package directory: `source.list`

The container build copies only `pkgs/<name>/` into its scratch directory, so a PKGBUILD cannot read
`../../desktop` or `../../LICENSE`. A package that needs repository files lists them in
`pkgs/<name>/source.list` (one repo-relative path per line; `#` comments; a directory means every tracked
file under it). `tools/build-pkgs` runs `tools/pkg-source pkgs/<name>` first, which packs the git-tracked
files of those paths, under their repo-relative names, into `pkgs/<name>/seclegion-src.tar.zst`
(deterministic, gitignored). A path that matches no tracked file stops the build.

The PKGBUILD uses it like the keyring uses its generated key files:

    source=(seclegion-src.tar.zst)
    sha256sums=('SKIP')   # generated for the build

and reads `"$srcdir/desktop/..."`, `"$srcdir/LICENSE"`. Files that live in the package directory itself
(`seclegion-dotfiles/skel`, `seclegion-hwdetect/bin`) are read through `$startdir`. Never use `../`.

## Packages

| package | contents |
|---|---|
| `seclegion-theme` | theme engine (`seclegion_theme`), `seclegion-theme`, `seclegion-theme-pick`, tokens and the default theme in `/usr/share/seclegion/theme` |
| `seclegion-settings` | `seclegion_settings`, `seclegion-set`, `seclegion-settings`, `seclegion-root-apply`, `seclegion-doctor`, the desktop entry |
| `seclegion-sysmon` | `seclegion_sysmon` (GTK4 System Monitor), `seclegion-sysmon`, the desktop entry |
| `seclegion-wifi` | `seclegion_wifi` (GTK4 Wi-Fi panel over libnm), `seclegion-wifi`, the desktop entry |
| `seclegion-desktop` | hypr/waybar/swaync/idle/osd/fm components in `/usr/share/seclegion/<component>`, `seclegion-host` (+ `/usr/lib/seclegion/host-lib.sh`), `seclegion-keys-lint` |
| `seclegion-dotfiles` | `/etc/skel/.config/hypr/hyprland.lua` loader and the `hyprlock.conf` link |
| `seclegion-branding` | the logo in `/usr/share/seclegion/branding` (all rights reserved for now, see its `LICENSE`) |
| `seclegion-hwdetect`, `seclegion-keyring`, `hello` | hardware detection, the repository keyring, a smoke test |

## Dependencies between seclegion packages

`makepkg --syncdeps` in the container resolves `depends` from the Arch repositories only, and the
`[seclegion]` repository does not exist there yet, so a `depends=('seclegion-theme')` would fail the
build. Until the build installs its own earlier packages, the seclegion packages do not list each other
(each PKGBUILD says which sibling it needs); the ISO package list installs them together.
