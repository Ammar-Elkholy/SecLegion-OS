<!-- SPDX-License-Identifier: MIT -->
# Theme coverage

Which surfaces follow the `seclegion-theme` tokens, how each one gets them, and the lines the owner may add for the three
files SecLegion never edits (kitty, rofi, starship). The engine writes everything below into
`~/.local/state/seclegion/theme/current/` (contract in `desktop/theme/README.md`); a wallpaper or theme change rewrites it and the
hooks signal what can reload.

Status: **themed** = follows the tokens with no owner action; **opt-in** = the engine writes the file, the owner adds one line;
**image only** = shipped inside the ISO, never on the host; **not themed** = outside the engine, with the reason.

| Surface | Engine output | How it reaches the surface | Status |
|---|---|---|---|
| Hyprland borders | `hyprland-colors.lua` | `desktop/hypr/seclegion-host.lua` reads it with `pcall(dofile, ...)`, falls back to the shipped default (component `border`) | themed |
| hyprlock | `hyprlock-colors.conf` | `desktop/hypr/hyprlock.conf` sources it (component `lock`) | themed |
| Waybar | `colors.css` | `desktop/waybar/style.css` imports it; the apply hook sends waybar SIGUSR2 | themed |
| swaync popups and centre | `swaync-colors.css` | `desktop/swaync/style.css` imports it; the hook runs `swaync-client --reload-css` | themed |
| Volume / brightness OSD | `swaync-colors.css`, `swayosd-colors.css` | the swaync popup and the swayosd sheet use the `sl_osd_*` names; swayosd is restarted only through its user unit | themed |
| GTK 3 apps (Thunar, ...) | `gtk3.css` | `~/.config/gtk-3.0/gtk.css` imports it (component `gtk`); apps pick it up on their next start | themed |
| GTK 4 / libadwaita apps | `gtk4.css` | `~/.config/gtk-4.0/gtk.css` imports the old theme, then this file (component `gtk`) | themed |
| KDE apps (Dolphin) | `kde.colors` | `~/.local/share/color-schemes/SecLegion.colors` links to it, `kdeglobals` names it (component `gtk`) | themed |
| Qt apps through qt6ct | `qt6ct.conf` | `~/.config/qt6ct/colors/SecLegion.conf` links to it; `gtk` reports a dangling link and relinks it. Picking it in qt6ct is the owner's step, and the kvantum style stays | opt-in |
| yazi | `yazi-theme.toml` | the engine's yazi hook writes `theme.toml` under its ownership rules (marker, backup, adopt once) | themed |
| kitty | `kitty-colors.conf` | the hook sends kitty SIGUSR1 to reload; the include line below is the owner's | opt-in |
| rofi | `rofi-colors.rasi` | defines `sl-*` variables only; the owner's `.rasi` imports it and uses `@sl-bg` and friends | opt-in |
| starship prompt | `starship.toml`, `starship-palette.toml` | starship has no include, so either point `STARSHIP_CONFIG` at the generated file or paste the palette table | opt-in |
| Login screen (ReGreet) | `regreet.css` | the ISO build installs the default export as `/etc/greetd/regreet.css` inside the image (`iso/profile/airootfs/etc/greetd/`); no host tool touches greetd or the display manager | image only |
| Boot menu (GRUB) | none | static branding from the ISO milestone, not wallpaper-driven | not themed |
| Browsers, Electron apps | none | they draw their own chrome; GTK colour hints are a per-app choice | not themed |

## Owner opt-in lines

SecLegion does not edit `kitty.conf`, your rofi theme, or your shell rc. Each line below is yours to add; nothing breaks if you
skip them, and the files they name always exist after any `seclegion-theme apply` or `reset`.

kitty, in `~/.config/kitty/kitty.conf` (a reload with SIGUSR1 follows each theme change):

    include ~/.local/state/seclegion/theme/current/kitty-colors.conf

rofi, at the top of your theme `.rasi`, before the first rule that uses a colour (check with `rofi -dump-theme`):

    @import "~/.local/state/seclegion/theme/current/rofi-colors.rasi"

starship, either whole-file in your shell rc:

    export STARSHIP_CONFIG="$HOME/.local/state/seclegion/theme/current/starship.toml"

or keep your own `starship.toml`, paste the `[palettes.seclegion]` table from
`~/.local/state/seclegion/theme/current/starship-palette.toml` into it, and set `palette = "seclegion"` at its top.

qt6ct: run `qt6ct`, open Appearance, set the palette to Custom and pick `SecLegion` (the style stays kvantum). `seclegion-host apply gtk`
prints this line too; it never edits your `qt6ct.conf`.

## Not on the host, by design

`regreet.css` is written by the theme engine like the other files, but only the ISO build copies it, to
`/etc/greetd/regreet.css` inside the image. `tests/iso/test_regreet.py` keeps that copy equal to the engine's default export and
fails if any host-side script or Makefile recipe mentions greetd, ReGreet or a display manager.
