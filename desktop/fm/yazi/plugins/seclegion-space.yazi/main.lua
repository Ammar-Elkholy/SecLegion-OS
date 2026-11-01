-- SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
-- SPDX-License-Identifier: MIT
-- seclegion-space: `free / total` of the filesystem holding the current
-- directory, at the right of yazi's status bar. Written against yazi 26.9
-- (Status:children_add, ps.sub, ya.async, ya.sync, Command, ui.render).
-- Enable in init.lua: require("seclegion-space"):setup()
-- The size comes from `df` run with an argv list (no shell); the path goes
-- after `--`, so a directory name cannot become an option.

local set_text = ya.sync(function(st, cwd, text)
	if st.cwd == cwd then -- drop a late answer for a directory we already left
		st.text = text
		ui.render()
	end
end)

local function query(cwd)
	local out = Command("df"):arg({ "-B1", "--output=avail,size", "--", cwd }):stdout(Command.PIPED):output()
	if not out or not out.status.success then
		return set_text(cwd, nil)
	end
	local avail, size = out.stdout:match("\n%s*(%d+)%s+(%d+)")
	if not avail then
		return set_text(cwd, nil)
	end
	set_text(cwd, string.format(" %s / %s ", ya.readable_size(tonumber(avail)), ya.readable_size(tonumber(size))))
end

local function refresh(st)
	local cwd = cx.active.current.cwd
	if cwd.spec.is_virtual then -- archives, sftp, trash: no local filesystem to ask
		st.cwd, st.text = nil, nil
		return
	end
	local path = tostring(cwd)
	st.cwd = path
	ya.async(function() query(path) end)
end

return {
	setup = function(st)
		Status:children_add(function()
			if not st.text then
				return ""
			end
			return ui.Line { ui.Span(st.text):style(th.status.progress_label) }
		end, 500, Status.RIGHT)
		ps.sub("cd", function() refresh(st) end)
		ps.sub("tab", function() refresh(st) end)
	end,
}
