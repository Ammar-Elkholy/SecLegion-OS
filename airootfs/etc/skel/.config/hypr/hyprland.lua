hl.env("AQ_DRM_DEVICES", "/dev/dri/card1:/dev/dri/card0")
hl.env("XDG_CURRENT_DESKTOP", "Hyprland")
hl.env("XDG_SESSION_TYPE", "wayland")
hl.env("XDG_SESSION_DESKTOP", "Hyprland")
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")

hl.config({
    cursor = {
        no_hardware_cursors = true,
    }
})

-- Force un-cache modules on reload so configuration changes apply immediately
for k, _ in pairs(package.loaded) do
    if k:match("^modules%.") or k == "hyprland-border" then
        package.loaded[k] = nil
    end
end

require("modules.autostart")
require("modules.keybinds")
require("modules.monitor")
require("modules.animations")
require("modules.windowrules")
require("modules.layerrules")

-- to change border color with wallust
require("hyprland-border")

-------------------------------
---- ENVIRONMENT VARIABLES ----
-------------------------------

-- See https://wiki.hypr.land/Configuring/Advanced-and-Cool/Environment-variables/

hl.config({
    xwayland = {
        force_zero_scaling = true,
        use_nearest_neighbor = true,
    }
})

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- Layouts
hl.config({
    dwindle = {
        preserve_split = true,
    },
})

hl.config({
    master = {
        new_status = "master",
    },
})

hl.config({
    scrolling = {
        fullscreen_on_one_column = true,
    },
})

----------------
----  MISC  ----
----------------

hl.config({
    misc = {
        force_default_wallpaper = -1,
        disable_hyprland_logo   = false,
    },
})

---------------
---- INPUT ----
---------------

hl.config({
    input = {
        kb_layout  = "us,ara",
        kb_variant = "",
        kb_model   = "",
        kb_options = "grp:ctrl_shift_toggle",
        kb_rules   = "",

        follow_mouse = 1,
        sensitivity = 0,

        touchpad = {
            natural_scroll          = false,
            tap_to_click            = true,
            disable_while_typing    = false,
            tap_and_drag            = false,
            drag_lock               = false,
            tap_button_map          = "lrm",
            clickfinger_behavior    = false,
            middle_button_emulation = true,
        },
    },
})

hl.gesture({
    fingers = 3,
    direction = "horizontal",
    action = "workspace"
})

hl.device({
    name        = "epic-mouse-v1",
    sensitivity = -0.5,
})
