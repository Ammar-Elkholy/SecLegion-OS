# Workspace click spike (plan r8 C2.1), Hyprland 0.56.2, Waybar 0.15.0-3

Result: no compatibility option exists, no newer waybar is packaged, so the custom/wsN route (plan step 2) was built.

## Questions and answers

1. Does Hyprland 0.56 have a legacy-dispatch compatibility option? No.
   - `hyprctl getoption` returned "no such option" for misc:legacy_dispatch, misc:legacy_dispatchers, misc:lua_legacy, general:legacy_dispatch and config:legacy.
   - `hyprctl(1)` and `Hyprland(1)` mention no legacy toggle. Its `dispatch` examples are the Lua form, `hyprctl dispatch "hl.dsp.exec_cmd('kitty')"`.
   - The binary holds `Config::Legacy::CDispatcherTranslator`, but that only translates legacy `.conf` files; it is not on the socket path.
   - The socket path builds the string `return hl.dispatch(<arg>)` and evaluates it as Lua. So `dispatch workspace 3` becomes `return hl.dispatch(workspace 3)`.
   - `keyword` is refused in Lua mode ("keyword can't work with non-legacy parsers. Use eval").
2. Is there a newer packaged waybar? No. `pacman -Si waybar` shows extra/waybar 0.15.0-3, which is the installed version (built 2026-09-01); no other waybar package is in the sync databases.

## Reproduction (nested Hyprland, own config under .build/ws, parent display wayland-1)

`bash tests/ws/repro.sh` prints `lua-rejects-legacy`:
- `hyprctl dispatch 'workspace 2'` gives `error: [string "return hl.dispatch(workspace 2)"]:1: ')' expected near '2'`.
- `hyprctl dispatch 'hl.dsp.focus({ workspace = "2" })'` gives `ok` and the active workspace becomes 2.

## Facts used by the implementation

- `hl.workspace_rule({ workspace = "1", persistent = true })` is valid (HL.WorkspaceRuleSpec has `persistent`). In a nested instance `workspacerules -j` lists the rules and `workspaces -j` lists empty workspaces 1-5. So `seclegion-ws` needs only `workspaces -j` and `activeworkspace -j`.
- `hl.dsp.focus({ workspace = "e+1" })` and `"e-1"` work for scroll (tests/ws/click.sh).
- The JSON from `workspaces -j`, `activeworkspace -j` and `clients -j` has no urgent flag. Urgent therefore comes from the `urgent>>ADDRESS` event, kept by seclegion-wsevents in `$XDG_RUNTIME_DIR/seclegion/ws-urgent` and cleared on `activewindowv2` or `closewindow` for that address.
- The user systemd environment carries HYPRLAND_INSTANCE_SIGNATURE, but it goes stale when Hyprland restarts; seclegion-wsevents falls back to the newest `.socket2.sock`.

## Not verified here

Waybar itself was not run against the pills (a real pointer click and the rendering of hidden pills). The on-click, scroll and pill commands are verified against a nested Hyprland by tests/ws/click.sh.
