-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
--
-- SecLegion OS default Hyprland config (from /etc/skel). Only loads what the seclegion-desktop
-- package ships under /usr/share/seclegion/hypr, starts the session daemons and binds a few
-- launch keys. Edit freely: it is your copy.
--
-- Only calls the repository already uses elsewhere: package.path, require, hl.on("hyprland.start"),
-- hl.exec_cmd, hl.bind with hl.dsp.exec_cmd. UNVERIFIED on a live session: this file has not been
-- loaded by a running Hyprland (no live session in the build).

package.path = "/usr/share/seclegion/hypr/?.lua;" .. package.path

-- Border colours, window rules and the workspace keybinds (it loads seclegion-keys itself).
local ok, err = pcall(require, "seclegion-host")
if not ok then print("hyprland.lua: seclegion-host not loaded: " .. tostring(err)) end

-- waybar, swaync, swayosd, hypridle and the polkit agent are systemd user units
-- (seclegion-*.service, bound to graphical-session.target) started by uwsm; no exec-once here.

hl.bind("SUPER + Return", hl.dsp.exec_cmd("foot"), { description = "terminal" })
hl.bind("SUPER + D", hl.dsp.exec_cmd("rofi -show drun"), { description = "launcher" })
hl.bind("SUPER + L", hl.dsp.exec_cmd("hyprlock"), { description = "lock the screen" })

-- Last: the user's own overrides win. A missing file is fine; a broken one is reported, not fatal.
local user = (os.getenv("HOME") or "") .. "/.config/hypr/user.lua"
local f = io.open(user, "r")
if f then
    f:close()
    local uok, uerr = pcall(dofile, user)
    if not uok then print("hyprland.lua: user.lua failed: " .. tostring(uerr)) end
end
