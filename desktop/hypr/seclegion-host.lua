-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
-- SecLegion host overlay. Loaded by one line in hyprland.lua, after the
-- owner's own border module, so these values win.
--
-- Fixes the ARGB/RGBA mix-up (0xRRGGBBAA written where Hyprland reads
-- 0xAARRGGBB) that made the active border invisible, and takes the border
-- colours from the theme contract when it exists.

local home = os.getenv("HOME") or ""

-- Border colours come from the theme contract: hyprland-colors.lua (a table of
-- rgba(rrggbbaa) strings, used as given), the live theme first, then the
-- shipped default, then the literals below. dofile re-reads the file on every
-- evaluation, which is what makes `hyprctl reload` pick up a new theme.
local active, inactive = "rgba(00ff88ff)", "rgba(0b1e1cff)"

local function rgba(v)
    return type(v) == "string" and v:match("^rgba%(%x%x%x%x%x%x%x%x%)$") ~= nil
end

for _, path in ipairs({
    home .. "/.local/state/seclegion/theme/current/hyprland-colors.lua",
    "/usr/share/seclegion/theme/default/hyprland-colors.lua",
}) do
    local ok, t = pcall(dofile, path)
    if ok and type(t) == "table" and rgba(t.active_border) and rgba(t.inactive_border) then
        active, inactive = t.active_border, t.inactive_border
        break
    end
end

-- Edge grab: windows resize by dragging a border or the 20 px around it, and the
-- cursor shows the resize arrow there (the owner's module leaves resize_on_border off).
hl.config({
    general = {
        resize_on_border = true,
        extend_border_grab_area = 20,
        hover_icon_on_border = true,
        col = {
            active_border = active,
            inactive_border = inactive,
        },
    },
})

-- Reduced motion: seclegion-reduced-motion writes this file (animations off) and removes it
-- again; absent file = nothing happens.
pcall(dofile, home .. "/.local/state/seclegion/reduced-motion.lua")

-- Workspaces 1-5 always exist, so their pills stay on the bar when empty.
hl.workspace_rule({ workspace = "1", persistent = true })
hl.workspace_rule({ workspace = "2", persistent = true })
hl.workspace_rule({ workspace = "3", persistent = true })
hl.workspace_rule({ workspace = "4", persistent = true })
hl.workspace_rule({ workspace = "5", persistent = true })

-- Helper windows float and open centred, so a volume mixer, the Bluetooth manager,
-- the network editor and the Settings app do not tile into a half-screen column.
-- Each rule matches one window class, anchored, so nothing else is caught. The owner's
-- own rules for pavucontrol/blueman (size, opacity) still apply. Settings also asks for
-- 980x680 (its own default size; the nested test compositor does not honour a rule size,
-- so tests/keys/winrules.sh checks float and centre only). A reload builds a new Lua
-- state, so these rules never stack.
for _, w in ipairs({
    { name = "pavucontrol", class = "^(org\\.pulseaudio\\.pavucontrol|pavucontrol)$" },
    { name = "blueman-manager", class = "^(blueman-manager|\\.blueman-manager-wrapped)$" },
    { name = "nm-connection-editor", class = "^nm-connection-editor$" },
    { name = "settings", class = "^org\\.seclegion\\.Settings$", size = { 980, 680 } },
}) do
    hl.window_rule({
        name = "seclegion-float-" .. w.name,
        match = { class = w.class },
        float = true,
        center = true,
        size = w.size,
    })
end

-- Hyprland and hypridle run with PATH=/usr/local/bin:/usr/bin, so a shim in
-- ~/.local/bin (the `osd` component's dunstify) is invisible to binds and
-- autostart. Put it first, once: hl.env sets the variable in the compositor,
-- and every exec_cmd child inherits it. Skipped when it is already first, so
-- `hyprctl reload` does not stack the entry.
if home ~= "" then
    local localbin = home .. "/.local/bin"
    local path = os.getenv("PATH") or ""
    if path:sub(1, #localbin + 1) ~= localbin .. ":" then
        hl.env("PATH", path == "" and localbin or (localbin .. ":" .. path))
    end
end

-- hyprland.lua only un-caches its own modules on reload; do the same here
-- so `hyprctl reload` re-evaluates this file.
package.loaded["seclegion-host"] = nil

-- Workspace keybinds (the `keys` component). require finds
-- ~/.config/hypr/seclegion-keys.lua: Hyprland puts the config dir first on
-- package.path. Absent until `seclegion-host apply keys`, so it is guarded;
-- an error inside the file still shows in `hyprctl configerrors`.
local keys_ok, keys_err = pcall(require, "seclegion-keys")
if not keys_ok then print("seclegion-host: seclegion-keys not loaded: " .. tostring(keys_err)) end

-- Keyboard layout ("us" plus the installer's extras) generated at first boot by seclegion-firstboot.
local kb_file = io.open("/etc/seclegion/kb-layout.lua", "r")
if kb_file then
    kb_file:close()
    local kb_ok, kb_err = pcall(dofile, "/etc/seclegion/kb-layout.lua")
    if not kb_ok then print("seclegion-host: kb-layout.lua not loaded: " .. tostring(kb_err)) end
end

-- Input settings written by the Settings app (Input page): key repeat and touchpad.
-- Absent until the owner changes one; a bad file only prints, it never stops this file.
-- It is evaluated again on every `hyprctl reload`, which is when a change takes effect.
if home ~= "" then
    local input_path = home .. "/.config/seclegion/input.lua"
    local f = io.open(input_path, "r")
    if f then
        f:close()
        local input_ok, input_err = pcall(dofile, input_path)
        if not input_ok then print("seclegion-host: input.lua not loaded: " .. tostring(input_err)) end
    end
end
