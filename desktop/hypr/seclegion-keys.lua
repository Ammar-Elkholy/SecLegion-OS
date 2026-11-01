-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
-- SecLegion workspace keybinds. Loaded by seclegion-host.lua through a
-- guarded pcall(require, "seclegion-keys"); installed on the host by
-- `seclegion-host apply keys` and shipped as-is in the ISO.
--
-- Only hl.bind calls, only on keys the owner's keybinds.lua leaves free:
-- this file never unbinds or rebinds an owner key (tools/seclegion-keys-lint
-- checks that before every install).
--
-- Digits and the period key are bound by keycode (code:N), not keysym, so the
-- same physical key works on both layouts in kb_layout = "us,ara" (on ara the
-- number row and the period key produce other keysyms). Keycodes are xkb:
-- code:10..19 = the 1..9,0 keys, code:60 = the period key.
--
-- Every bind carries a "seclegion-keys: " description so `hyprctl binds -j`
-- tells ours from the owner's.
--
-- `hyprctl reload` re-runs this file: Hyprland builds a new Lua state per
-- reload, so there is no require cache to clear (tests/keys/broken-file.sh).
--
--   Super + .                   focus the first empty workspace
--   Super + Shift + .           move the focused window to an empty workspace, follow it
--   Super + Alt + .             the same, silently (focus stays here)
--   Super + Ctrl + Left/Right   previous / next workspace (e-1 / e+1)
--   Super + Alt + 1..0          focus workspace 11..20
--   Super + Alt + Shift + 1..0  move the focused window to workspace 11..20
--   Super + Shift + T           rofi theme picker (~/.local/bin/seclegion-theme-pick, settings component)
--   Super + Ctrl + 1/2/3        float the window if tiled, 50 / 70 / 90 % of the monitor, centred
--   Super + Alt + R             resize mode (a submap, see the end of this file)
--   Super + /  (and Super + F1) keybinding cheat sheet (seclegion-keys; decision O11)
--   Super + A                   AI picker (seclegion-ai-pick: installed/configured entries only; decision O11)
--   Super + Ctrl + E            emoji picker (seclegion-emoji)
--   Super + Ctrl + N            night light on/off (seclegion-night-light)
--   Super + Ctrl + I            stay awake on/off (seclegion-stay-awake)
--   Super + Ctrl + M            reduced motion on/off (seclegion-reduced-motion)
--   Super + Ctrl + P            cycle the power profile (seclegion-power-profile)
--   Alt + Print                 screenshot a region (seclegion-screenshot; plain Print is the owner's)
--   Alt + Shift + Print         screenshot the whole screen
--   Super + Alt + Print         screenshot the active window
--   Super + Ctrl + O            OCR a region to the clipboard (seclegion-ocr)
--   Super + Ctrl + Q            decode a QR code in a region to the clipboard (seclegion-qr)
--   Super + Ctrl + R            start / stop a screen recording (seclegion-record)
--   XF86Display (Fn+F7 on many laptops), Super + Shift + P
--                               display menu: laptop only / extend / mirror / external only
--                               (seclegion-display-menu, issue 14; XF86Display is locked, so it
--                               fires on the lock screen too; the menu shows once unlocked).
--                               No XF86Project: xkbcommon has no such keysym, and Hyprland rejects
--                               the bind (an error in this file would drop every bind below it).

hl.bind("SUPER + code:60", hl.dsp.focus({ workspace = "empty" }), { description = "seclegion-keys: focus empty workspace" })
hl.bind("SUPER + SHIFT + code:60", hl.dsp.window.move({ workspace = "empty" }), { description = "seclegion-keys: move window to empty workspace" })
hl.bind("SUPER + ALT + code:60", hl.dsp.window.move({ workspace = "empty", follow = false }), { description = "seclegion-keys: move window to empty workspace (silent)" })

hl.bind("SUPER + CONTROL + Left", hl.dsp.focus({ workspace = "e-1" }), { description = "seclegion-keys: previous workspace" })
hl.bind("SUPER + CONTROL + Right", hl.dsp.focus({ workspace = "e+1" }), { description = "seclegion-keys: next workspace" })

hl.bind("SUPER + ALT + code:10", hl.dsp.focus({ workspace = 11 }), { description = "seclegion-keys: workspace 11" })
hl.bind("SUPER + ALT + code:11", hl.dsp.focus({ workspace = 12 }), { description = "seclegion-keys: workspace 12" })
hl.bind("SUPER + ALT + code:12", hl.dsp.focus({ workspace = 13 }), { description = "seclegion-keys: workspace 13" })
hl.bind("SUPER + ALT + code:13", hl.dsp.focus({ workspace = 14 }), { description = "seclegion-keys: workspace 14" })
hl.bind("SUPER + ALT + code:14", hl.dsp.focus({ workspace = 15 }), { description = "seclegion-keys: workspace 15" })
hl.bind("SUPER + ALT + code:15", hl.dsp.focus({ workspace = 16 }), { description = "seclegion-keys: workspace 16" })
hl.bind("SUPER + ALT + code:16", hl.dsp.focus({ workspace = 17 }), { description = "seclegion-keys: workspace 17" })
hl.bind("SUPER + ALT + code:17", hl.dsp.focus({ workspace = 18 }), { description = "seclegion-keys: workspace 18" })
hl.bind("SUPER + ALT + code:18", hl.dsp.focus({ workspace = 19 }), { description = "seclegion-keys: workspace 19" })
hl.bind("SUPER + ALT + code:19", hl.dsp.focus({ workspace = 20 }), { description = "seclegion-keys: workspace 20" })

hl.bind("SUPER + ALT + SHIFT + code:10", hl.dsp.window.move({ workspace = 11 }), { description = "seclegion-keys: move window to workspace 11" })
hl.bind("SUPER + ALT + SHIFT + code:11", hl.dsp.window.move({ workspace = 12 }), { description = "seclegion-keys: move window to workspace 12" })
hl.bind("SUPER + ALT + SHIFT + code:12", hl.dsp.window.move({ workspace = 13 }), { description = "seclegion-keys: move window to workspace 13" })
hl.bind("SUPER + ALT + SHIFT + code:13", hl.dsp.window.move({ workspace = 14 }), { description = "seclegion-keys: move window to workspace 14" })
hl.bind("SUPER + ALT + SHIFT + code:14", hl.dsp.window.move({ workspace = 15 }), { description = "seclegion-keys: move window to workspace 15" })
hl.bind("SUPER + ALT + SHIFT + code:15", hl.dsp.window.move({ workspace = 16 }), { description = "seclegion-keys: move window to workspace 16" })
hl.bind("SUPER + ALT + SHIFT + code:16", hl.dsp.window.move({ workspace = 17 }), { description = "seclegion-keys: move window to workspace 17" })
hl.bind("SUPER + ALT + SHIFT + code:17", hl.dsp.window.move({ workspace = 18 }), { description = "seclegion-keys: move window to workspace 18" })
hl.bind("SUPER + ALT + SHIFT + code:18", hl.dsp.window.move({ workspace = 19 }), { description = "seclegion-keys: move window to workspace 19" })
hl.bind("SUPER + ALT + SHIFT + code:19", hl.dsp.window.move({ workspace = 20 }), { description = "seclegion-keys: move window to workspace 20" })

hl.bind("SUPER + SHIFT + T", hl.dsp.exec_cmd("~/.local/bin/seclegion-theme-pick"), { description = "seclegion-keys: theme picker" })
hl.bind("SUPER + slash", hl.dsp.exec_cmd("seclegion-keys"), { description = "seclegion-keys: keybinding cheat sheet" })
hl.bind("SUPER + F1", hl.dsp.exec_cmd("seclegion-keys"), { description = "seclegion-keys: keybinding cheat sheet (F1)" })

hl.bind("SUPER + CONTROL + E", hl.dsp.exec_cmd("seclegion-emoji"), { description = "seclegion-keys: emoji picker" })
hl.bind("SUPER + CONTROL + N", hl.dsp.exec_cmd("seclegion-night-light toggle"), { description = "seclegion-keys: night light on/off" })
hl.bind("SUPER + CONTROL + I", hl.dsp.exec_cmd("seclegion-stay-awake toggle"), { description = "seclegion-keys: stay awake on/off" })
hl.bind("SUPER + CONTROL + M", hl.dsp.exec_cmd("seclegion-reduced-motion toggle"), { description = "seclegion-keys: reduced motion on/off" })
hl.bind("ALT + Print", hl.dsp.exec_cmd("seclegion-screenshot region"), { description = "seclegion-keys: screenshot region" })
hl.bind("ALT + SHIFT + Print", hl.dsp.exec_cmd("seclegion-screenshot screen"), { description = "seclegion-keys: screenshot screen" })
hl.bind("SUPER + ALT + Print", hl.dsp.exec_cmd("seclegion-screenshot window"), { description = "seclegion-keys: screenshot window" })
hl.bind("SUPER + CONTROL + O", hl.dsp.exec_cmd("seclegion-ocr"), { description = "seclegion-keys: OCR a region to the clipboard" })
hl.bind("SUPER + CONTROL + Q", hl.dsp.exec_cmd("seclegion-qr"), { description = "seclegion-keys: decode a QR code to the clipboard" })
hl.bind("SUPER + CONTROL + R", hl.dsp.exec_cmd("seclegion-record screen toggle"), { description = "seclegion-keys: screen recording start/stop" })
hl.bind("SUPER + A", hl.dsp.exec_cmd("seclegion-ai-pick"), { description = "seclegion-keys: AI picker" })
hl.bind("SUPER + CONTROL + P", hl.dsp.exec_cmd("seclegion-power-profile cycle"), { description = "seclegion-keys: cycle power profile" })
hl.bind("XF86Display", hl.dsp.exec_cmd("seclegion-display-menu"), { locked = true, description = "seclegion-keys: display menu" })
hl.bind("SUPER + SHIFT + P", hl.dsp.exec_cmd("seclegion-display-menu"), { description = "seclegion-keys: display menu (Super+Shift+P)" })

-- Window sizes and the keyboard resize mode (the `keys` component, plan r12 K1).
--
-- Facts checked in a nested Hyprland 0.56.2 (tests/keys/resize-submap.sh header):
--   * hl.define_submap(name, fn) holds the binds of a submap; hl.dsp.submap("name")
--     enters it and hl.dsp.submap("reset") leaves it.
--   * hl.dsp.window.resize({ x, y, relative = true }) grows/shrinks the active window
--     (a floating one keeps its centre; a tiled one moves the split);
--     resize({ x, y }) sets an absolute size. hl.dsp.window.center() centres a floating window.
--   * hl.get_active_monitor() has width, height and scale.
--   * a bind may be a Lua function; the file returns a table so tests can call winsize().
local M = {}

-- Float the active window if it is tiled, give it pct % of its monitor and centre it.
function M.winsize(pct)
    local w = hl.get_active_window()
    if not w then return end
    if w.fullscreen ~= 0 then hl.dispatch(hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })) end
    if not w.floating then hl.dispatch(hl.dsp.window.float({ action = "enable" })) end
    local m = w.monitor or hl.get_active_monitor()
    local scale = (m.scale and m.scale > 0) and m.scale or 1
    local width = math.floor(m.width / scale * pct / 100 + 0.5)
    local height = math.floor(m.height / scale * pct / 100 + 0.5)
    hl.dispatch(hl.dsp.window.resize({ x = width, y = height }))
    hl.dispatch(hl.dsp.window.center())
end

hl.bind("SUPER + CONTROL + code:10", function() M.winsize(50) end, { description = "seclegion-keys: window 50 % of the monitor, centred" })
hl.bind("SUPER + CONTROL + code:11", function() M.winsize(70) end, { description = "seclegion-keys: window 70 % of the monitor, centred" })
hl.bind("SUPER + CONTROL + code:12", function() M.winsize(90) end, { description = "seclegion-keys: window 90 % of the monitor, centred" })

-- Super+Alt+R enters the `resize` submap (Super+R stays the owner's rofi). Inside it:
--   arrows / H J K L   40 px, with Shift 10 px, with Ctrl 200 px (left/up shrink, right/down grow)
--   equal / minus      grow / shrink both axes        C  centre      F  toggle floating
--   Return / Escape    leave
hl.bind("SUPER + ALT + R", hl.dsp.submap("resize"), { description = "seclegion-keys: resize mode" })
hl.define_submap("resize", function()
    hl.bind("left", hl.dsp.window.resize({ x = -40, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 40 px" })
    hl.bind("h", hl.dsp.window.resize({ x = -40, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 40 px" })

    hl.bind("right", hl.dsp.window.resize({ x = 40, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 40 px" })
    hl.bind("l", hl.dsp.window.resize({ x = 40, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 40 px" })

    hl.bind("up", hl.dsp.window.resize({ x = 0, y = -40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 40 px" })
    hl.bind("k", hl.dsp.window.resize({ x = 0, y = -40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 40 px" })

    hl.bind("down", hl.dsp.window.resize({ x = 0, y = 40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 40 px" })
    hl.bind("j", hl.dsp.window.resize({ x = 0, y = 40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 40 px" })

    hl.bind("SHIFT + left", hl.dsp.window.resize({ x = -10, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 10 px" })
    hl.bind("SHIFT + h", hl.dsp.window.resize({ x = -10, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 10 px" })

    hl.bind("SHIFT + right", hl.dsp.window.resize({ x = 10, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 10 px" })
    hl.bind("SHIFT + l", hl.dsp.window.resize({ x = 10, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 10 px" })

    hl.bind("SHIFT + up", hl.dsp.window.resize({ x = 0, y = -10, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 10 px" })
    hl.bind("SHIFT + k", hl.dsp.window.resize({ x = 0, y = -10, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 10 px" })

    hl.bind("SHIFT + down", hl.dsp.window.resize({ x = 0, y = 10, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 10 px" })
    hl.bind("SHIFT + j", hl.dsp.window.resize({ x = 0, y = 10, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 10 px" })

    hl.bind("CTRL + left", hl.dsp.window.resize({ x = -200, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 200 px" })
    hl.bind("CTRL + h", hl.dsp.window.resize({ x = -200, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: narrower 200 px" })

    hl.bind("CTRL + right", hl.dsp.window.resize({ x = 200, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 200 px" })
    hl.bind("CTRL + l", hl.dsp.window.resize({ x = 200, y = 0, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: wider 200 px" })

    hl.bind("CTRL + up", hl.dsp.window.resize({ x = 0, y = -200, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 200 px" })
    hl.bind("CTRL + k", hl.dsp.window.resize({ x = 0, y = -200, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shorter 200 px" })

    hl.bind("CTRL + down", hl.dsp.window.resize({ x = 0, y = 200, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 200 px" })
    hl.bind("CTRL + j", hl.dsp.window.resize({ x = 0, y = 200, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: taller 200 px" })

    hl.bind("equal", hl.dsp.window.resize({ x = 40, y = 40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: grow both axes" })
    hl.bind("minus", hl.dsp.window.resize({ x = -40, y = -40, relative = true }), { repeating = true, description = "seclegion-keys: resize mode: shrink both axes" })

    hl.bind("c", hl.dsp.window.center(), { description = "seclegion-keys: resize mode: centre" })
    hl.bind("f", hl.dsp.window.float({ action = "toggle" }), { description = "seclegion-keys: resize mode: toggle floating" })
    hl.bind("Return", hl.dsp.submap("reset"), { description = "seclegion-keys: resize mode: leave" })
    hl.bind("Escape", hl.dsp.submap("reset"), { description = "seclegion-keys: resize mode: leave (Escape)" })
end)

return M
