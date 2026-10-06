---------------------
---- KEYBINDINGS ----
---------------------

local terminal    = "kitty"
local fileManager = "nautilus"
local menu        = "pkill -x rofi || rofi -show drun"
local ide         = "antigravity-ide"
local osd         = "~/.config/hypr/scripts/ae-osd.sh"

local mainMod = "SUPER"

-- ── Core Apps ───────────────────────────────────────────────────────────────
-- Terminal (Super+Return, Super+KP_Enter, Super+T, Arabic ف)
hl.bind(mainMod .. " + return",           hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + KP_Enter",         hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + T",                hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + Arabic_feh",       hl.dsp.exec_cmd(terminal))

-- IDE (Super+Shift+Return, Super+I)
hl.bind(mainMod .. " + SHIFT + return",   hl.dsp.exec_cmd(ide))
hl.bind(mainMod .. " + SHIFT + KP_Enter", hl.dsp.exec_cmd(ide))
hl.bind(mainMod .. " + I",                hl.dsp.exec_cmd(ide))

-- File Manager (Super+E, Arabic ث) → Nautilus
hl.bind(mainMod .. " + E",                hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + Arabic_theh",      hl.dsp.exec_cmd(fileManager))

-- Browser (Super+B)
hl.bind(mainMod .. " + B",                hl.dsp.exec_cmd("brave || firefox"))

-- ── App Launcher ────────────────────────────────────────────────────────────
-- Rofi (Super+R, Super+D, Arabic ي ق)
hl.bind(mainMod .. " + D",                hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + Arabic_yeh",       hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + R",                hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + Arabic_qaf",       hl.dsp.exec_cmd(menu))

-- ── Window Operations ───────────────────────────────────────────────────────
-- Close (Super+Q, Super+C, Arabic ض)
hl.bind(mainMod .. " + Q",               hl.dsp.window.close())
hl.bind(mainMod .. " + Arabic_dad",      hl.dsp.window.close())
hl.bind(mainMod .. " + C",               hl.dsp.window.close())

-- Fullscreen (Super+F)
hl.bind(mainMod .. " + F",               hl.dsp.window.fullscreen())

-- Float toggle (Super+V, Super+W, Super+Shift+F, Arabic ر ص)
hl.bind(mainMod .. " + V",               hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + Arabic_ra",       hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + W",               hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + Arabic_sad",      hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))
hl.bind(mainMod .. " + SHIFT + F",       hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-floating.sh"))

-- Layout split toggle (Super+J, Super+P pseudo)
hl.bind(mainMod .. " + P",               hl.dsp.window.pseudo())
hl.bind(mainMod .. " + J",               hl.dsp.layout("togglesplit"))

-- ── Language Switch ─────────────────────────────────────────────────────────
-- Super+Space — switches keyboard layout + shows OSD
hl.bind(mainMod .. " + Space", hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-layout.sh"))

-- ── INFINITY TABS (Groups) ──────────────────────────────────────────────────
hl.bind(mainMod .. " + G",            hl.dsp.group.toggle(),   { description = "Toggle Group / Tabs" })
hl.bind(mainMod .. " + Tab",          hl.dsp.group.next(),     { description = "Next Tab in Group" })
hl.bind(mainMod .. " + SHIFT + Tab",  hl.dsp.group.prev(),     { description = "Prev Tab in Group" })
hl.bind(mainMod .. " + bracketright", hl.dsp.group.next(),     { description = "Next Tab >" })
hl.bind(mainMod .. " + bracketleft",  hl.dsp.group.prev(),     { description = "Prev Tab <" })

-- ── Wallpapers ──────────────────────────────────────────────────────────────
hl.bind(mainMod .. " + SHIFT + W",   hl.dsp.exec_cmd(terminal .. " -e ~/.config/hypr/scripts/wallpaper-yazi.sh"))
hl.bind(mainMod .. " + CONTROL + W", hl.dsp.exec_cmd(terminal .. " -e ~/.config/hypr/scripts/live-wallpaper-yazi.sh"))
hl.bind(mainMod .. " + Y",           hl.dsp.exec_cmd(terminal .. " -e yazi"))

-- ── Clipboard (CopyQ) ───────────────────────────────────────────────────────
hl.bind(mainMod .. " + SHIFT + V",         hl.dsp.exec_cmd("copyq toggle"))
hl.bind(mainMod .. " + SHIFT + Arabic_ra", hl.dsp.exec_cmd("copyq toggle"))

-- ── Notification Center (SwayNC) ────────────────────────────────────────────
hl.bind(mainMod .. " + N",           hl.dsp.exec_cmd("swaync-client -t -sw"))
hl.bind(mainMod .. " + Arabic_alef", hl.dsp.exec_cmd("swaync-client -t -sw"))

-- ── Power & Lock ────────────────────────────────────────────────────────────
-- Wlogout power menu (Super+Escape, Super+Backspace)
hl.bind(mainMod .. " + Escape",    hl.dsp.exec_cmd(osd .. " logout-menu"))
hl.bind(mainMod .. " + BackSpace", hl.dsp.exec_cmd(osd .. " logout-menu"))
-- Lock screen (Super+Shift+L)
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.exec_cmd(osd .. " lock"))

-- ── Toggle Waybar ───────────────────────────────────────────────────────────
hl.bind(mainMod .. " + SHIFT + B", hl.dsp.exec_cmd(osd .. " waybar-toggle"))

-- ── Screenshots ─────────────────────────────────────────────────────────────
-- Print            → interactive region → clipboard + save + notify
-- Shift+Print      → interactive region → opens in Swappy for annotation
-- Super+Print      → capture active window
-- Control+Print    → capture full screen
-- Super+Shift+S    → interactive region (same as Print, keyboard alternative)
hl.bind("Print",              hl.dsp.exec_cmd(osd .. " screenshot-area"))
hl.bind("SHIFT + Print",      hl.dsp.exec_cmd(osd .. " screenshot-edit"))
hl.bind(mainMod .. " + Print",hl.dsp.exec_cmd(osd .. " screenshot-active"))
hl.bind("CONTROL + Print",    hl.dsp.exec_cmd(osd .. " screenshot-screen"))
-- NOTE: Super+Shift+S = screenshot area (keyboard shortcut, no conflict with scratchpad)
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.exec_cmd(osd .. " screenshot-area"))

-- ── Move Focus (Arrows & Vim keys) ──────────────────────────────────────────
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))
hl.bind(mainMod .. " + H",     hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + L",     hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + K",     hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + M",     hl.dsp.focus({ direction = "down" }))  -- was missing

-- ── Move Windows (Shift + Arrows & Vim keys) ─────────────────────────────
hl.bind(mainMod .. " + SHIFT + left",  hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + up",    hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + down",  hl.dsp.window.move({ direction = "down" }))
hl.bind(mainMod .. " + SHIFT + H",     hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + L",     hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + K",     hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + J",     hl.dsp.window.move({ direction = "down" }))

-- ── Workspaces 1–10 ─────────────────────────────────────────────────────────
for i = 1, 10 do
    local key = i % 10
    hl.bind(mainMod .. " + " .. key,         hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

-- ── Scratchpad / Special Workspace ──────────────────────────────────────────
-- Super+S        → toggle scratchpad (show/hide)
-- Super+Shift+A  → move focused window INTO scratchpad
-- Super+Z        → pull focused window OUT of scratchpad back to current workspace
-- NOTE: Super+Shift+S is screenshot; scratchpad uses Super+S / Super+Shift+A / Super+Z
hl.bind(mainMod .. " + S",                    hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + Arabic_seen",          hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + A",            hl.dsp.exec_cmd("~/.config/hypr/scripts/scratchpad-send.sh"))
hl.bind(mainMod .. " + SHIFT + Arabic_sheen", hl.dsp.exec_cmd("~/.config/hypr/scripts/scratchpad-send.sh"))
hl.bind(mainMod .. " + Z",                    hl.dsp.exec_cmd("~/.config/hypr/scripts/scratchpad-restore.sh"))
hl.bind(mainMod .. " + Arabic_hamza",         hl.dsp.exec_cmd("~/.config/hypr/scripts/scratchpad-restore.sh"))

-- ── Mouse Controls ──────────────────────────────────────────────────────────
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))
hl.bind(mainMod .. " + mouse:272",  hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273",  hl.dsp.window.resize(), { mouse = true })

-- ── Media & Brightness OSD (volume/brightness pop-up) ───────────────────────
hl.bind("XF86AudioRaiseVolume",  hl.dsp.exec_cmd(osd .. " vol-up"),     { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume",  hl.dsp.exec_cmd(osd .. " vol-down"),   { locked = true, repeating = true })
hl.bind("XF86AudioMute",         hl.dsp.exec_cmd(osd .. " vol-mute"),   { locked = true })
hl.bind("XF86AudioMicMute",      hl.dsp.exec_cmd(osd .. " mic-mute"),   { locked = true })
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd(osd .. " bright-up"),  { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd(osd .. " bright-down"),{ locked = true, repeating = true })
hl.bind("XF86AudioPlay",         hl.dsp.exec_cmd(osd .. " media-play"), { locked = true })
hl.bind("XF86AudioNext",         hl.dsp.exec_cmd(osd .. " media-next"), { locked = true })
hl.bind("XF86AudioPrev",         hl.dsp.exec_cmd(osd .. " media-prev"), { locked = true })

-- Keyboard media shortcuts (no physical media keys)
hl.bind(mainMod .. " + F10", hl.dsp.exec_cmd(osd .. " media-play"))
hl.bind(mainMod .. " + F11", hl.dsp.exec_cmd(osd .. " media-prev"))
hl.bind(mainMod .. " + F12", hl.dsp.exec_cmd(osd .. " media-next"))
