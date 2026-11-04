-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
-- Live session only (loaded last by hyprland.lua): the live user has no password, so there is
-- no lock. The skel config binds SUPER+L to hyprlock; take the key away again.
pcall(hl.unbind, "SUPER + L")
