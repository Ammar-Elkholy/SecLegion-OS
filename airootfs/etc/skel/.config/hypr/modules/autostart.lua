-------------------
---- AUTOSTART ----
-------------------

hl.on("hyprland.start", function () 
    hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
    hl.exec_cmd("/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1")
    hl.exec_cmd("swaync")
    hl.exec_cmd("hypridle")
    hl.exec_cmd("nm-applet --indicator")
    hl.exec_cmd("awww-daemon")
    hl.exec_cmd("copyq")
    hl.exec_cmd("~/.config/hypr/scripts/restore-wallpaper.sh")
end)
