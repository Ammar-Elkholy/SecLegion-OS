# grub-theme

Sources of the GRUB theme. Only sources are committed: `theme.txt.in` (template) and
`build-theme.sh`. The build container (`tools/container-build.sh`) runs the script and writes
the result into the profile copy at `grub/themes/seclegion/`:

- `jetbrains-mono-18.pf2`, `jetbrains-mono-bold-28.pf2`: `grub-mkfont` from `ttf-jetbrains-mono`
- `background.png`: the repository's `Grub Splash.png`, copied unchanged
- `theme.txt`: the template with colours from `desktop/theme/tokens.toml` (`[colors]`)

It also writes `out/grub-theme.sha256` (one sha256 per generated file). The same inputs and
`SOURCE_DATE_EPOCH` give the same file. Build the theme alone with `tools/docker-build.sh theme`.
Never commit `.pf2` or `.png` files here.
