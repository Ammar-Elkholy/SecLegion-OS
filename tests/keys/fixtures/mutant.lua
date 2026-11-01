-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
-- MUTANT of desktop/hypr/seclegion-keys.lua for the lint test (one extra owner key).
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
--   Super + .                   focus the first empty workspace
--   Super + Shift + .           move the focused window to an empty workspace, follow it
--   Super + Alt + .             the same, silently (focus stays here)
--   Super + Ctrl + Left/Right   previous / next workspace (e-1 / e+1)
--   Super + Alt + 1..0          focus workspace 11..20
--   Super + Alt + Shift + 1..0  move the focused window to workspace 11..20

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

-- the mutant: Super+Tab is the owner's next-tab-in-group bind
hl.bind("SUPER + Tab", hl.dsp.focus({ workspace = "e+1" }), { description = "seclegion-keys: mutant" })
