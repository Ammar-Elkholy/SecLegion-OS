-------------------
---- AUTOSTART ----
-------------------

hl.on("hyprland.start", function () 
    -- Wayland environment setup (must be first)
    hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")

    -- Auth agent
    hl.exec_cmd("/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1")

    -- Notification daemon (dunst with AE branding for OSD popups)
    hl.exec_cmd("dunst")

    -- Notification center (swaync for the Control Center panel)
    hl.exec_cmd("swaync")

    -- Idle / lock
    hl.exec_cmd("hypridle")

    -- Network tray
    hl.exec_cmd("nm-applet --indicator")

    -- Animation daemon
    hl.exec_cmd("awww-daemon")

    -- Clipboard manager
    hl.exec_cmd("copyq")

    -- Restore last wallpaper
    hl.exec_cmd("~/.config/hypr/scripts/restore-wallpaper.sh")

    -- First-login onboarding wizard (SecLegion Edition)
    hl.exec_cmd("bash -c 'if [ ! -f ~/.config/.ae-welcome-done ]; then sleep 2 && kitty --title \"SecLegion Setup Wizard\" ~/.config/hypr/scripts/ae-welcome.sh; fi'")
end)
