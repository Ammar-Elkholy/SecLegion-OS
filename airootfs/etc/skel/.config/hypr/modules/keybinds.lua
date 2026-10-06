---------------------
---- KEYBINDINGS ----
---------------------

local terminal    = "kitty"
local fileManager = "thunar"
local menu        = "pkill -x rofi || rofi -show drun"
local ide         = "antigravity-ide"

local mainMod = "SUPER"

-- Core Apps
hl.bind(mainMod .. " + return",           hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + KP_Enter",         hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + T",                hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + Arabic_feh",       hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + SHIFT + return",   hl.dsp.exec_cmd(ide))
hl.bind(mainMod .. " + SHIFT + KP_Enter", hl.dsp.exec_cmd(ide))
hl.bind(mainMod .. " + I",                hl.dsp.exec_cmd(ide))
hl.bind(mainMod .. " + E",                hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + Arabic_theh",      hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + B",                hl.dsp.exec_cmd("brave || firefox"))

-- App Launcher (Super+R, Super+D - English & Arabic)
hl.bind(mainMod .. " + D",          hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + Arabic_yeh", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + R",          hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + Arabic_qaf", hl.dsp.exec_cmd(menu))

-- Window Operations
-- Close window (Super+Q, Super+C, Super+Shift+Q)
hl.bind(mainMod .. " + Q",          hl.dsp.window.close())
hl.bind(mainMod .. " + Arabic_dad", hl.dsp.window.close())
hl.bind(mainMod .. " + C",          hl.dsp.window.close())
hl.bind(mainMod .. " + SHIFT + Q",  hl.dsp.window.close())

-- Fullscreen (Super+F)
hl.bind(mainMod .. " + F",          hl.dsp.window.fullscreen())

-- Float toggle (Super+V, Super+W, Super+Shift+F in EN & AR - un-fullscreens & centers)
hl.bind(mainMod .. " + V",          hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + Arabic_ra",  hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + W",          hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + Arabic_sad", hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + SHIFT + F",  hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))

-- Language Switch (Super + Space with instant on-screen notification popup)
hl.bind(mainMod .. " + Space",      hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-layout.sh"))

-- Layout toggles
hl.bind(mainMod .. " + P",          hl.dsp.window.pseudo())
hl.bind(mainMod .. " + J",          hl.dsp.layout("togglesplit"))

-- Toggle Waybar Status Bar (Super+Shift+B)
hl.bind(mainMod .. " + SHIFT + B",  hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-waybar.sh"))

-- INFINITY TABS (Groups)
hl.bind(mainMod .. " + G",             hl.dsp.group.toggle(), { description = "Toggle Group / Tabs" })
hl.bind(mainMod .. " + Tab",           hl.dsp.group.next(),   { description = "Next Tab in Group" })
hl.bind(mainMod .. " + SHIFT + Tab",   hl.dsp.group.prev(),   { description = "Prev Tab in Group" })
hl.bind(mainMod .. " + bracketright",  hl.dsp.group.next(),   { description = "Next Tab in Group" })
hl.bind(mainMod .. " + bracketleft",   hl.dsp.group.prev(),   { description = "Prev Tab in Group" })

-- Wallpapers (Yazi & Live Wallpapers) - No Alt key used
hl.bind(mainMod .. " + SHIFT + W",   hl.dsp.exec_cmd(terminal .. " -e ~/.config/hypr/scripts/wallpaper-yazi.sh"))
hl.bind(mainMod .. " + CONTROL + W", hl.dsp.exec_cmd(terminal .. " -e ~/.config/hypr/scripts/live-wallpaper-yazi.sh"))
hl.bind(mainMod .. " + Y",           hl.dsp.exec_cmd(terminal .. " -e yazi"))

-- Clipboard (CopyQ)
hl.bind(mainMod .. " + SHIFT + V",         hl.dsp.exec_cmd("copyq toggle"))
hl.bind(mainMod .. " + SHIFT + Arabic_ra", hl.dsp.exec_cmd("copyq toggle"))

-- Notifications & Control Center (SwayNC)
hl.bind(mainMod .. " + N",           hl.dsp.exec_cmd("swaync-client -t -sw"))
hl.bind(mainMod .. " + Arabic_alef", hl.dsp.exec_cmd("swaync-client -t -sw"))

-- Power / Logout Menu (Wlogout)
hl.bind(mainMod .. " + Escape",      hl.dsp.exec_cmd("wlogout"))
hl.bind(mainMod .. " + BackSpace",   hl.dsp.exec_cmd("wlogout"))

-- Screenshots (Interactive region, clipboard, notification & Swappy annotation)
-- Print: interactive area selection -> copies to clipboard + saves + sends notification
hl.bind("Print",                       hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh area"))
hl.bind(mainMod .. " + SHIFT + S",     hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh area"))
-- Shift + Print: interactive area selection -> opens in Swappy for arrows/text/blur/crop
hl.bind("SHIFT + Print",               hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh edit"))
-- Super + Print: capture active window
hl.bind(mainMod .. " + Print",         hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh active"))
-- Control + Print: capture full screen
hl.bind("CONTROL + Print",             hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh screen"))

-- Lock screen
hl.bind(mainMod .. " + SHIFT + L",   hl.dsp.exec_cmd("hyprlock"))

-- Move Focus (Arrows & Vim keys)
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))
hl.bind(mainMod .. " + H",     hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + L",     hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + K",     hl.dsp.focus({ direction = "up" }))

-- Move Windows (Shift + Arrows & Vim keys)
hl.bind(mainMod .. " + SHIFT + left",  hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + up",    hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + down",  hl.dsp.window.move({ direction = "down" }))
hl.bind(mainMod .. " + SHIFT + H",     hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + L",     hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + K",     hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + J",     hl.dsp.window.move({ direction = "down" }))

-- Switch workspaces 1 - 10
for i = 1, 10 do
    local key = i % 10
    hl.bind(mainMod .. " + " .. key,             hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key,     hl.dsp.window.move({ workspace = i }))
end

-- Special workspace (scratchpad)
hl.bind(mainMod .. " + S",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))

-- Mouse Controls
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))
hl.bind(mainMod .. " + mouse:272",  hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273",  hl.dsp.window.resize(), { mouse = true })

-- Media & Brightness keys
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp",  hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%+"),                  { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown",hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%-"),                  { locked = true, repeating = true })
