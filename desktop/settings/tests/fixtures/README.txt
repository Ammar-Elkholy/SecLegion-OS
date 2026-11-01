Fake /sys trees for SL_SYSFS.
sysfs-full: a laptop with a charge threshold file and the ideapad_laptop conservation_mode file.
sysfs-nobat: the owner's laptop shape (battery, no charge_control_end_threshold, no conservation_mode).
(LED names avoid ':' because the dev filesystem rejects it; the glob is *kbd_backlight.)
