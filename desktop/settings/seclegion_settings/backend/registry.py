# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The settings table. Every setting is one `Setting` row; the CLI and the GTK app both read it.

A row names its reader and writer, the file or command it touches, whether it needs root
(`privileged`: written through pkexec and seclegion-root-apply), and the capability that must be
present for it to be shown. Adding a setting means adding a row here and nothing else.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from . import capabilities as cap
from . import readers as R
from . import render as T
from . import writers as W
from .env import (
    AuthCancelled,
    CommandFailed,
    Ctx,
    InvalidValue,
    NotAuthorized,
    Refused,
    Unavailable,
    UnknownSetting,
    WriteResult,
)

KINDS = ("toggle", "choice", "range", "text", "info", "action")
PAGES = (
    "power",
    "idle",
    "display",
    "sound",
    "network",
    "bluetooth",
    "notifications",
    "apps",
    "appearance",
    "storage",
    "updates",
    "input",
    "region",
    "troubleshoot",
    "security",
    "users",
    "about",
)
PAGE_LABELS = {
    "power": "Power",
    "idle": "Sleep, Lock and Idle",
    "display": "Display",
    "sound": "Sound",
    "network": "Network",
    "bluetooth": "Bluetooth",
    "storage": "Storage",
    "updates": "Updates",
    "input": "Input",
    "region": "Region",
    "troubleshoot": "Troubleshoot",
    "security": "Security",
    "users": "Users",
    "notifications": "Notifications",
    "apps": "Default Apps",
    "appearance": "Appearance",
    "about": "About",
}
# What a choice row's drop-down shows for each stored value (the rest show the value itself).
CHOICE_LABELS = {
    "display.layout": {
        "laptop": "Laptop only", "extend": "Extend", "mirror": "Mirror", "external": "External only",
    },
}
THEME_ID = re.compile(r"^(seclegion-[a-z]+|wallpaper:[0-9a-f]{8})$")
TZ_ID = T.TZ_RE
DESKTOP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.desktop$")


@dataclass(frozen=True)
class Setting:
    id: str
    page: str
    label: str
    kind: str
    reader: Callable[[Ctx], object]
    writer: Callable[[Ctx, object], WriteResult]
    file: str = ""  # what a write touches ("~" paths for user files, absolute for root files)
    command: str = ""  # the command a read or write runs
    privileged: bool = False
    capability: str | None = None
    keywords: tuple[str, ...] = ()
    description: str = ""
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    unit: str = ""
    pattern: re.Pattern | None = None  # kind=text
    action_label: str = ""  # kind=action: the button text
    confirm: str = ""  # kind=action: ask this before running

    @property
    def readonly(self) -> bool:
        return self.kind == "info"

    def coerce(self, raw: str):
        """Turn CLI text into the typed value, or raise InvalidValue."""
        raw = raw.strip()
        if self.kind == "toggle":
            low = raw.lower()
            if low in ("on", "true", "yes", "1"):
                return True
            if low in ("off", "false", "no", "0"):
                return False
            raise InvalidValue(f"{self.id}: expected on or off, got {raw!r}")
        if self.kind == "range":
            try:
                n = int(raw)
            except ValueError:
                raise InvalidValue(f"{self.id}: expected a whole number, got {raw!r}") from None
            if not (self.minimum <= n <= self.maximum):
                raise InvalidValue(f"{self.id}: {n} is outside {self.minimum} to {self.maximum}")
            return n
        if self.kind == "choice":
            low = raw.lower()
            if low not in self.choices:
                raise InvalidValue(f"{self.id}: {raw!r} is not one of {', '.join(self.choices)}")
            return low
        if self.kind == "text":
            if self.pattern is not None and not self.pattern.match(raw):
                raise InvalidValue(f"{self.id}: {raw!r} is not a valid value")
            return raw
        if self.kind == "action":
            if raw.lower() != "run":
                raise InvalidValue(f"{self.id}: an action; the only value is 'run'")
            return "run"
        raise Refused(f"{self.id} is read-only")


def _row(**kw) -> Setting:
    return Setting(**kw)


SETTINGS: tuple[Setting, ...] = (
    # ---- Power ----------------------------------------------------------------------------------
    _row(
        id="power.profile",
        page="power",
        label="Power profile",
        kind="choice",
        reader=R.power_profile,
        writer=W.power_profile,
        command="powerprofilesctl get | set <profile>",
        capability="ppd",
        choices=("power-saver", "balanced", "performance"),
        keywords=("performance", "battery", "saver", "ppd"),
        description="Trade speed against battery life. Applies at once; no root needed.",
    ),
    _row(
        id="power.battery_status",
        page="power",
        label="Battery",
        kind="info",
        reader=R.battery_status,
        writer=W.read_only,
        command="upower -i <battery>",
        capability="battery",
        keywords=("charge", "percentage", "level"),
        description="Charge level and state. Read-only.",
    ),
    _row(
        id="power.alert_low",
        page="power",
        label="Low battery alert",
        kind="range",
        reader=R.alert_low,
        writer=W.alert_low,
        file="~/.config/seclegion/battery.toml",
        capability="battery",
        minimum=5,
        maximum=50,
        unit="%",
        keywords=("warning", "notify"),
        description="Warn when the battery falls to this level.",
    ),
    _row(
        id="power.alert_critical",
        page="power",
        label="Critical battery alert",
        kind="range",
        reader=R.alert_critical,
        writer=W.alert_critical,
        file="~/.config/seclegion/battery.toml",
        capability="battery",
        minimum=2,
        maximum=30,
        unit="%",
        keywords=("warning", "notify"),
        description="Urgent warning at this level. Must be below the low alert.",
    ),
    _row(
        id="power.lid_ignore",
        page="power",
        label="Keep running when the lid is closed",
        kind="toggle",
        reader=R.lid_ignore,
        writer=W.lid_ignore,
        file=T.LID_UNIT_FILE,
        command="systemctl --user enable --now | disable --now seclegion-lid-inhibit.service",
        capability="lid_inhibit",
        keywords=("lid", "close", "suspend", "sleep", "inhibit", "ignore"),
        description="Closing the lid will not suspend the machine. Applies at once; no root needed.",
    ),
    _row(
        id="power.lid_battery",
        page="power",
        label="Lid closed on battery",
        kind="choice",
        reader=R.lid_battery,
        writer=W.lid_battery,
        file=T.LID_FILE,
        privileged=True,
        capability="lid",
        choices=T.LID_ACTIONS,
        keywords=("lid", "close", "suspend"),
        description="What closing the lid does on battery (HandleLidSwitch). "
        "Needs root: asks for the administrator password. For the common case use the toggle above.",
    ),
    _row(
        id="power.lid_ac",
        page="power",
        label="Lid closed on AC",
        kind="choice",
        reader=R.lid_ac,
        writer=W.lid_ac,
        file=T.LID_FILE,
        privileged=True,
        capability="lid",
        choices=T.LID_ACTIONS,
        keywords=("lid", "close", "suspend"),
        description="What closing the lid does on AC (HandleLidSwitchExternalPower). "
        "Needs root: asks for the administrator password. For the common case use the toggle above.",
    ),
    _row(
        id="power.lid_docked",
        page="power",
        label="Lid closed when docked",
        kind="choice",
        reader=R.lid_docked,
        writer=W.lid_docked,
        file=T.LID_FILE,
        privileged=True,
        capability="lid",
        choices=T.LID_ACTIONS,
        keywords=("lid", "dock", "external monitor"),
        description="What closing the lid does when docked (HandleLidSwitchDocked). "
        "Needs root: asks for the administrator password. For the common case use the toggle above.",
    ),
    _row(
        id="power.power_button",
        page="power",
        label="Power button",
        kind="choice",
        reader=R.power_button,
        writer=W.power_button,
        file=T.POWER_FILE,
        privileged=True,
        choices=T.POWER_ACTIONS,
        keywords=("power key", "shutdown"),
        description="What a short press of the power button does (HandlePowerKey). "
        "Needs root: asks for the administrator password.",
    ),
    _row(
        id="power.charge_limit",
        page="power",
        label="Charge limit",
        kind="range",
        reader=R.charge_limit,
        writer=W.charge_limit,
        file=T.CHARGE_FILE,
        privileged=True,
        capability="charge_threshold",
        minimum=60,
        maximum=100,
        unit="%",
        keywords=("battery health", "threshold", "stop charging"),
        description="Stop charging at this level to slow battery wear. "
        "Needs root: asks for the administrator password.",
    ),
    _row(
        id="power.conservation_mode",
        page="power",
        label="Battery conservation mode",
        kind="toggle",
        reader=R.conservation_mode,
        writer=W.conservation_mode,
        command="write 1 | 0 to /sys/bus/platform/drivers/ideapad_acpi/*/conservation_mode",
        capability="conservation",
        keywords=("battery health", "80", "stop charging", "lenovo", "legion", "ideapad"),
        description="Lenovo firmware stops charging at about 80% to slow battery wear. "
        "Applies at once; no root needed (a udev rule opens the file to group wheel).",
    ),
    _row(
        id="power.suspend_mode",
        page="power",
        label="Suspend mode",
        kind="choice",
        reader=R.suspend_mode,
        writer=W.suspend_mode,
        file=T.SLEEP_FILE,
        privileged=True,
        capability="sleep_modes",
        choices=("s2idle", "deep"),
        keywords=("sleep", "s3", "mem_sleep"),
        description="s2idle wakes fast and drains more; deep saves more power. "
        "Needs root: asks for the administrator password.",
    ),
    # ---- Sleep, lock and idle -------------------------------------------------------------------
    _row(
        id="power.autolock",
        page="idle",
        label="Lock after being idle",
        kind="choice",
        reader=R.autolock,
        writer=W.autolock,
        command="seclegion-autolock status | set <choice>",
        capability="autolock",
        choices=("default", "15m", "30m", "60m", "never"),
        keywords=("lock", "idle", "hypridle", "never lock", "screen lock", "inhibit"),
        description="default keeps the 5 minute lock. 15m, 30m and 60m lock later; never does not lock "
        "when idle. Applies at once; no root needed.",
    ),
    _row(
        id="idle.lock_after",
        page="idle",
        label="Lock after (minutes)",
        kind="choice",
        reader=R.idle_lock,
        writer=W.idle_lock,
        file="~/.config/seclegion/idle.conf",
        choices=T.LOCK_CHOICES,
        unit="min",
        keywords=("lock screen", "hypridle", "idle"),
        description="Lock the session after this much idle time.",
    ),
    _row(
        id="idle.screen_off_after",
        page="idle",
        label="Screen off after (minutes)",
        kind="choice",
        reader=R.idle_screen_off,
        writer=W.idle_screen_off,
        file="~/.config/seclegion/idle.conf",
        choices=T.SCREEN_OFF_CHOICES,
        unit="min",
        keywords=("dpms", "display off", "idle"),
        description="Turn the screen off after this much idle time. Must come after the lock time.",
    ),
    _row(
        id="idle.suspend_battery",
        page="idle",
        label="Suspend after, on battery (minutes)",
        kind="choice",
        reader=R.idle_suspend_battery,
        writer=W.idle_suspend_battery,
        file="~/.config/seclegion/idle.conf",
        choices=T.SUSPEND_BATTERY_CHOICES,
        unit="min",
        capability="battery",
        keywords=("sleep", "idle"),
        description="Suspend after this much idle time while on battery. Must come after screen off.",
    ),
    _row(
        id="idle.suspend_ac",
        page="idle",
        label="Suspend after, on AC (minutes)",
        kind="choice",
        reader=R.idle_suspend_ac,
        writer=W.idle_suspend_ac,
        file="~/.config/seclegion/idle.conf",
        choices=T.SUSPEND_AC_CHOICES,
        unit="min",
        keywords=("sleep", "idle"),
        description="Suspend after this much idle time while plugged in. Default never.",
    ),
    _row(
        id="idle.lock_before_sleep",
        page="idle",
        label="Lock before sleep",
        kind="toggle",
        reader=R.idle_lock_before_sleep,
        writer=W.idle_lock_before_sleep,
        file="~/.config/seclegion/idle.conf",
        keywords=("suspend", "lock"),
        description="Lock the session whenever the machine goes to sleep.",
    ),
    # ---- Display --------------------------------------------------------------------------------
    _row(
        id="display.brightness",
        page="display",
        label="Brightness",
        kind="range",
        reader=R.brightness,
        writer=W.brightness,
        command="brightnessctl -m -c backlight | brightnessctl -c backlight set N%",
        capability="backlight",
        minimum=1,
        maximum=100,
        unit="%",
        keywords=("backlight", "screen"),
        description="Screen brightness. Applies at once.",
    ),
    _row(
        id="display.kbd_brightness",
        page="display",
        label="Keyboard backlight",
        kind="range",
        reader=R.kbd_brightness,
        writer=W.kbd_brightness,
        command="brightnessctl -d <kbd_backlight> set N%",
        capability="kbd_backlight",
        minimum=0,
        maximum=100,
        unit="%",
        keywords=("keyboard light", "backlight"),
        description="Keyboard backlight level.",
    ),
    _row(
        id="display.nightlight",
        page="display",
        label="Night light",
        kind="toggle",
        reader=R.nightlight,
        writer=W.nightlight,
        file="~/.config/seclegion/nightlight.toml",
        command="hyprctl hyprsunset temperature N | identity",
        capability="hyprsunset",
        keywords=("blue light", "warm", "hyprsunset"),
        description="Warm the screen colours.",
    ),
    _row(
        id="display.nightlight_temp",
        page="display",
        label="Night light temperature",
        kind="range",
        reader=R.nightlight_temp,
        writer=W.nightlight_temp,
        file="~/.config/seclegion/nightlight.toml",
        command="hyprctl hyprsunset temperature N",
        capability="hyprsunset",
        minimum=3500,
        maximum=6500,
        unit="K",
        keywords=("kelvin", "warm"),
        description="Colour temperature while night light is on. Lower is warmer.",
    ),
    _row(
        id="display.layout",
        page="display",
        label="Display layout",
        kind="choice",
        reader=R.display_layout,
        writer=W.display_layout,
        command="hyprctl -j monitors all | seclegion-display-menu laptop|extend|mirror|external",
        capability="display_menu",
        choices=("laptop", "extend", "mirror", "external"),
        keywords=("monitor", "external", "second screen", "hdmi", "projector", "mirror", "extend"),
        description="Which screens show the desktop when a second display is connected, as in the "
        "display key's menu. Applies at once and lasts until you sign in again.",
    ),
    _row(
        id="display.outputs",
        page="display",
        label="Connected displays",
        kind="info",
        reader=R.display_outputs,
        writer=W.read_only,
        command="hyprctl -j monitors all",
        capability="hyprland",
        keywords=("monitor", "resolution", "refresh rate", "scale", "hdmi"),
        description="Each connected display with its resolution, refresh rate and scale.",
    ),
    # ---- Sound ----------------------------------------------------------------------------------
    _row(
        id="sound.volume",
        page="sound",
        label="Volume",
        kind="range",
        reader=R.volume,
        writer=W.volume,
        command="wpctl get-volume | set-volume @DEFAULT_AUDIO_SINK@",
        capability="audio",
        minimum=0,
        maximum=100,
        unit="%",
        keywords=("speaker", "output"),
        description="Volume of the default output.",
    ),
    _row(
        id="sound.mute",
        page="sound",
        label="Mute",
        kind="toggle",
        reader=R.mute,
        writer=W.mute,
        command="wpctl set-mute @DEFAULT_AUDIO_SINK@",
        capability="audio",
        keywords=("speaker",),
        description="Mute the default output.",
    ),
    _row(
        id="sound.mic_mute",
        page="sound",
        label="Microphone mute",
        kind="toggle",
        reader=R.mic_mute,
        writer=W.mic_mute,
        command="wpctl set-mute @DEFAULT_AUDIO_SOURCE@",
        capability="audio",
        keywords=("microphone", "input"),
        description="Mute the default microphone.",
    ),
    # ---- Network --------------------------------------------------------------------------------
    _row(
        id="network.wifi",
        page="network",
        label="Wi-Fi",
        kind="toggle",
        reader=R.wifi,
        writer=W.wifi,
        command="nmcli radio wifi [on|off]",
        capability="wifi",
        keywords=("wireless", "wlan"),
        description="Turn the Wi-Fi radio on or off.",
    ),
    _row(
        id="network.airplane",
        page="network",
        label="Airplane mode",
        kind="toggle",
        reader=R.airplane,
        writer=W.airplane,
        command="rfkill block|unblock all",
        capability="rfkill",
        keywords=("flight", "radios", "rfkill"),
        description="Switch every radio off at once.",
    ),
    _row(
        id="network.bluetooth",
        page="network",
        label="Bluetooth",
        kind="toggle",
        reader=R.bluetooth,
        writer=W.bluetooth,
        command="bluetoothctl show | power on|off",
        capability="bluetooth",
        keywords=("bt",),
        description="Power the Bluetooth controller.",
    ),
    # ---- Bluetooth ------------------------------------------------------------------------------
    _row(
        id="bluetooth.power",
        page="bluetooth",
        label="Bluetooth",
        kind="toggle",
        reader=R.bluetooth,
        writer=W.bluetooth,
        command="bluetoothctl show | power on|off",
        capability="bluetooth",
        keywords=("bt", "wireless", "radio"),
        description="Power the Bluetooth controller. Applies at once.",
    ),
    _row(
        id="bluetooth.paired",
        page="bluetooth",
        label="Paired devices",
        kind="info",
        reader=R.bluetooth_paired,
        writer=W.read_only,
        command="bluetoothctl devices Paired",
        capability="bluetooth",
        keywords=("headphones", "mouse", "keyboard", "pair"),
        description="Devices already paired with this computer. Read-only.",
    ),
    _row(
        id="bluetooth.advanced",
        page="bluetooth",
        label="Advanced",
        kind="action",
        reader=R.action_idle,
        writer=W.bluetooth_advanced,
        command="blueman-manager",
        capability="blueman",
        action_label="Open Bluetooth manager",
        keywords=("pair", "connect", "blueman", "scan"),
        description="Pair, connect and remove devices in the Bluetooth manager window.",
    ),
    # ---- Notifications --------------------------------------------------------------------------
    _row(
        id="notifications.dnd",
        page="notifications",
        label="Do Not Disturb",
        kind="toggle",
        reader=R.dnd,
        writer=W.dnd,
        command="swaync-client -D | -dn | -df",
        capability="dnd",
        keywords=("silence", "focus", "swaync"),
        description="Hold back notification pop-ups.",
    ),
    # ---- Default apps ---------------------------------------------------------------------------
    _row(
        id="apps.file_manager",
        page="apps",
        label="File manager",
        kind="text",
        reader=R.file_manager,
        writer=W.file_manager,
        command="xdg-mime query default inode/directory | xdg-mime default <desktop> inode/directory",
        capability="xdg",
        pattern=DESKTOP_ID,
        keywords=("thunar", "files", "folders"),
        description="Opens folders. SecLegion ships Thunar (thunar.desktop).",
    ),
    _row(
        id="apps.browser",
        page="apps",
        label="Web browser",
        kind="text",
        reader=R.browser,
        writer=W.browser,
        command="xdg-settings get|set default-web-browser",
        capability="xdg",
        pattern=DESKTOP_ID,
        keywords=("web", "links"),
        description="Opens web links.",
    ),
    _row(
        id="apps.terminal",
        page="apps",
        label="Terminal",
        kind="text",
        reader=R.terminal,
        writer=W.terminal,
        file="~/.config/xdg-terminals.list",
        pattern=DESKTOP_ID,
        keywords=("shell", "console"),
        description="Preferred terminal for xdg-terminal-exec.",
    ),
    # ---- Appearance (through seclegion-theme) ---------------------------------------------------
    _row(
        id="appearance.theme",
        page="appearance",
        label="Theme",
        kind="text",
        reader=R.theme_id,
        writer=W.theme_id,
        command="seclegion-theme list --json | apply --theme <id>",
        capability="theme",
        pattern=THEME_ID,
        keywords=("colours", "wallpaper", "teal", "cyan", "swatch"),
        description="Pick SecLegion Dark, a built-in accent or a recent wallpaper. Applies at once.",
    ),
    _row(
        id="appearance.auto",
        page="appearance",
        label="Follow the wallpaper",
        kind="toggle",
        reader=R.theme_auto,
        writer=W.theme_auto,
        command="seclegion-theme auto on|off",
        capability="theme",
        keywords=("auto", "wallpaper", "automatic"),
        description="Re-theme whenever the wallpaper changes. Applies at once.",
    ),
    _row(
        id="appearance.reset",
        page="appearance",
        label="Reset theme",
        kind="action",
        reader=R.theme_reset,
        writer=W.theme_reset,
        command="seclegion-theme reset",
        capability="theme",
        keywords=("default", "dark", "restore"),
        description="Back to SecLegion Dark. Applies at once.",
    ),
    _row(
        id="appearance.theme_mode",
        page="appearance",
        label="Theme mode",
        kind="choice",
        reader=R.theme_mode,
        writer=W.theme_mode,
        command="seclegion-theme apply --mode default|auto",
        capability="theme",
        choices=("default", "auto"),
        keywords=("wallpaper", "colours", "matugen"),
        description="default is SecLegion Dark; auto derives colours from the wallpaper.",
    ),
    _row(
        id="appearance.contrast",
        page="appearance",
        label="Contrast",
        kind="choice",
        reader=R.theme_contrast,
        writer=W.theme_contrast,
        command="seclegion-theme apply --contrast normal|high",
        capability="theme",
        choices=("normal", "high"),
        keywords=("accessibility", "legibility"),
        description="High contrast strengthens text and borders.",
    ),
    # ---- Storage --------------------------------------------------------------------------------
    _row(
        id="storage.mounts",
        page="storage",
        label="Disk usage",
        kind="info",
        reader=R.storage_mounts,
        writer=W.read_only,
        command="df -P -k",
        keywords=("space", "free", "full", "mount", "partition"),
        description="Used space and size of each mounted disk. Read-only.",
    ),
    _row(
        id="storage.trash_size",
        page="storage",
        label="Trash",
        kind="info",
        reader=R.trash_size,
        writer=W.read_only,
        command="read ~/.local/share/Trash/files",
        keywords=("bin", "deleted"),
        description="Size of the files in your trash. Read-only.",
    ),
    _row(
        id="storage.empty_trash",
        page="storage",
        label="Empty trash",
        kind="action",
        reader=R.action_idle,
        writer=W.empty_trash,
        file="~/.local/share/Trash",
        command="gio trash --empty",
        capability="gio",
        action_label="Empty trash",
        confirm="Permanently delete everything in the trash? This cannot be undone.",
        keywords=("bin", "delete", "clean", "free space"),
        description="Permanently delete everything in your trash.",
    ),
    _row(
        id="storage.low_disk",
        page="storage",
        label="Low disk warning",
        kind="range",
        reader=R.low_disk,
        writer=W.low_disk,
        file="~/.config/seclegion/storage.toml",
        minimum=70,
        maximum=95,
        unit="%",
        keywords=("warning", "full", "alert", "notify"),
        description="Warn when a disk is this full. Saved for the low-disk alert helper.",
    ),
    # ---- Updates --------------------------------------------------------------------------------
    _row(
        id="updates.pending",
        page="updates",
        label="Pending updates",
        kind="info",
        reader=R.updates_pending,
        writer=W.read_only,
        command="checkupdates",
        capability="pacman_updates",
        keywords=("pacman", "packages", "upgrade", "available"),
        description="Packages with a newer version in the repositories. Read-only.",
    ),
    _row(
        id="updates.last",
        page="updates",
        label="Last full update",
        kind="info",
        reader=R.updates_last,
        writer=W.read_only,
        command="read /var/log/pacman.log",
        keywords=("pacman", "when", "history", "upgrade"),
        description="When the last full system upgrade started, from the pacman log. Read-only.",
    ),
    _row(
        id="updates.update_now",
        page="updates",
        label="Update now",
        kind="action",
        reader=R.action_idle,
        writer=W.update_now,
        command="xdg-terminal-exec sudo pacman -Syu",
        capability="terminal",
        action_label="Open terminal and update",
        keywords=("pacman", "upgrade", "install", "sudo"),
        description="Runs a full system update in a terminal window. It asks for your password there; "
        "this app never sees it.",
    ),
    _row(
        id="updates.snapshot_keep",
        page="updates",
        label="Snapshots to keep",
        kind="range",
        reader=R.snapshot_keep,
        writer=W.snapshot_keep,
        file=T.SNAPPER_FILE,
        privileged=True,
        capability="snapper",
        minimum=1,
        maximum=50,
        keywords=("snapper", "rollback", "btrfs", "restore"),
        description="How many system snapshots to keep (snapper NUMBER_LIMIT). "
        "Needs root: asks for the administrator password.",
    ),
    # ---- Input (a Lua file the host config loads at the next reload) ---------------------------
    _row(
        id="input.repeat_rate",
        page="input",
        label="Key repeat rate",
        kind="range",
        reader=R.repeat_rate,
        writer=W.repeat_rate,
        file=T.INPUT_FILE,
        minimum=10,
        maximum=80,
        unit="/s",
        keywords=("keyboard", "typing", "repeat"),
        description="How many times a held key repeats each second. Applies at the next Hyprland reload.",
    ),
    _row(
        id="input.repeat_delay",
        page="input",
        label="Key repeat delay",
        kind="range",
        reader=R.repeat_delay,
        writer=W.repeat_delay,
        file=T.INPUT_FILE,
        minimum=150,
        maximum=1000,
        unit="ms",
        keywords=("keyboard", "typing", "repeat"),
        description="How long a key is held before it starts to repeat. Applies at the next Hyprland reload.",
    ),
    _row(
        id="input.tap_to_click",
        page="input",
        label="Tap to click",
        kind="toggle",
        reader=R.tap_to_click,
        writer=W.tap_to_click,
        file=T.INPUT_FILE,
        keywords=("touchpad", "trackpad", "tap"),
        description="Tap the touchpad to click. Applies at the next Hyprland reload.",
    ),
    _row(
        id="input.natural_scroll",
        page="input",
        label="Natural scrolling",
        kind="toggle",
        reader=R.natural_scroll,
        writer=W.natural_scroll,
        file=T.INPUT_FILE,
        keywords=("touchpad", "trackpad", "scroll", "reverse"),
        description="Content follows your fingers on the touchpad. Applies at the next Hyprland reload.",
    ),
    _row(
        id="input.disable_while_typing",
        page="input",
        label="Ignore touchpad while typing",
        kind="toggle",
        reader=R.disable_while_typing,
        writer=W.disable_while_typing,
        file=T.INPUT_FILE,
        keywords=("touchpad", "trackpad", "dwt", "palm"),
        description="Stop the touchpad reacting while you type. Applies at the next Hyprland reload.",
    ),
    # ---- Region ---------------------------------------------------------------------------------
    _row(
        id="region.clock_format",
        page="region",
        label="Clock",
        kind="choice",
        reader=R.clock_format,
        writer=W.clock_format,
        file="~/.config/seclegion/clock.toml",
        choices=T.CLOCK_FORMATS,
        keywords=("12 hour", "24 hour", "time", "am", "pm"),
        description="Show the time as 12 hour (am/pm) or 24 hour.",
    ),
    _row(
        id="region.locale",
        page="region",
        label="Language and formats",
        kind="info",
        reader=R.locale,
        writer=W.read_only,
        command="read /etc/locale.conf",
        keywords=("language", "locale", "lang"),
        description="The system locale (LANG). Read-only.",
    ),
    _row(
        id="region.timezone",
        page="region",
        label="Time zone",
        kind="text",
        reader=R.timezone,
        writer=W.timezone,
        file=T.LOCALTIME_FILE,
        privileged=True,
        pattern=TZ_ID,
        command="timedatectl set-timezone <zone>",
        keywords=("clock", "zone", "utc", "city"),
        description="The zone /etc/localtime points at, like Europe/Berlin. "
        "Needs root: asks for the administrator password.",
    ),
    # ---- Troubleshoot ---------------------------------------------------------------------------
    _row(
        id="troubleshoot.restart_waybar",
        page="troubleshoot",
        label="Restart the top bar",
        kind="action",
        reader=R.action_idle,
        writer=W.restart_waybar,
        command="systemctl --user restart waybar.service",
        capability="systemctl",
        action_label="Restart",
        keywords=("waybar", "bar", "panel", "frozen"),
        description="Restart waybar if the bar is blank or stuck.",
    ),
    _row(
        id="troubleshoot.restart_swaync",
        page="troubleshoot",
        label="Restart notifications",
        kind="action",
        reader=R.action_idle,
        writer=W.restart_swaync,
        command="systemctl --user restart swaync.service",
        capability="systemctl",
        action_label="Restart",
        keywords=("swaync", "notification", "popups"),
        description="Restart the notification daemon if pop-ups stopped appearing.",
    ),
    _row(
        id="troubleshoot.restart_hypridle",
        page="troubleshoot",
        label="Restart idle manager",
        kind="action",
        reader=R.action_idle,
        writer=W.restart_hypridle,
        command="systemctl --user restart hypridle.service",
        capability="systemctl",
        action_label="Restart",
        keywords=("hypridle", "lock", "sleep", "idle"),
        description="Restart hypridle if the screen no longer locks or sleeps on its own.",
    ),
    _row(
        id="troubleshoot.diagnostics",
        page="troubleshoot",
        label="Copy diagnostics",
        kind="action",
        reader=R.action_idle,
        writer=W.copy_diagnostics,
        command="wl-copy",
        capability="wl_copy",
        action_label="Copy to clipboard",
        keywords=("report", "bug", "log", "support"),
        description="Copy versions, failed services and config errors to the clipboard. "
        "Your home path, user and host names and addresses are removed first.",
    ),
    # ---- Security -------------------------------------------------------------------------------
    _row(
        id="security.ports",
        page="security",
        label="Listening ports",
        kind="info",
        reader=R.listening_ports,
        writer=W.read_only,
        file="~/.config/seclegion/",
        command="ss -tln",
        capability="ss",
        keywords=("port", "listen", "network", "open", "tcp"),
        description="TCP ports something is waiting on, and whether other computers can reach them. "
        "Read-only; this row writes nothing.",
    ),
    _row(
        id="security.sshd",
        page="security",
        label="SSH server",
        kind="info",
        reader=R.sshd_state,
        writer=W.read_only,
        command="systemctl is-enabled sshd.service",
        capability="sshd",
        keywords=("ssh", "sshd", "remote", "login"),
        description="Whether other computers can sign in over SSH. Read-only.",
    ),
    _row(
        id="security.ssh_enable",
        page="security",
        label="Turn the SSH server on",
        kind="toggle",
        reader=R.sshd_enabled,
        writer=W.ssh_enable,
        privileged=True,
        capability="sshd",
        command="systemctl enable --now | disable --now sshd.service",
        keywords=("ssh", "sshd", "remote"),
        description="Start the SSH server now and at every boot. "
        "Needs root: asks for the administrator password.",
    ),
    _row(
        id="security.firewall",
        page="security",
        label="Firewall",
        kind="toggle",
        reader=R.firewall_enabled,
        writer=W.firewall,
        privileged=True,
        capability="ufw",
        command="ufw enable | disable",
        keywords=("ufw", "firewall", "block", "incoming"),
        description="Block incoming connections that nothing asked for (ufw). "
        "Needs root: asks for the administrator password.",
    ),
    # ---- Users ----------------------------------------------------------------------------------
    _row(
        id="users.name",
        page="users",
        label="Account",
        kind="info",
        reader=R.user_name,
        writer=W.read_only,
        command="read /etc/passwd",
        keywords=("user", "login", "name", "account"),
        description="Your full name and sign-in name. Read-only.",
    ),
    _row(
        id="users.face",
        page="users",
        label="Profile picture",
        kind="info",
        reader=R.face,
        writer=W.read_only,
        command="read ~/.face",
        keywords=("avatar", "picture", "photo", "face"),
        description="Whether ~/.face exists; the login screen shows it. Read-only.",
    ),
    _row(
        id="users.password",
        page="users",
        label="Change password",
        kind="action",
        reader=R.action_idle,
        writer=W.change_password,
        command="xdg-terminal-exec passwd",
        capability="terminal",
        action_label="Open terminal and change password",
        keywords=("passwd", "secret", "sign in"),
        description="Opens a terminal window to change your password. It is typed there; "
        "this app never sees it.",
    ),
    _row(
        id="users.autologin",
        page="users",
        label="Automatic login",
        kind="info",
        reader=R.autologin,
        writer=W.read_only,
        command="read /etc/greetd/config.toml",
        keywords=("autologin", "sign in", "greetd", "login"),
        description="Whether the login screen signs a user in without a password. Read-only.",
    ),
    # ---- About (read-only) ----------------------------------------------------------------------
    _row(
        id="about.kernel",
        page="about",
        label="Kernel",
        kind="info",
        reader=R.kernel,
        writer=W.read_only,
        command="uname -r",
        description="Running kernel release.",
    ),
    _row(
        id="about.hostname",
        page="about",
        label="Hostname",
        kind="info",
        reader=R.hostname,
        writer=W.read_only,
        command="uname -n",
        description="Machine name.",
    ),
    _row(
        id="about.uptime",
        page="about",
        label="Uptime",
        kind="info",
        reader=R.uptime,
        writer=W.read_only,
        command="read /proc/uptime",
        description="Time since boot.",
    ),
    _row(
        id="about.cpu",
        page="about",
        label="Processor",
        kind="info",
        reader=R.cpu,
        writer=W.read_only,
        command="read /proc/cpuinfo",
        description="CPU model.",
    ),
    _row(
        id="about.ram",
        page="about",
        label="Memory",
        kind="info",
        reader=R.ram,
        writer=W.read_only,
        command="read /proc/meminfo",
        description="Installed RAM.",
    ),
    _row(
        id="about.hyprland",
        page="about",
        label="Hyprland",
        kind="info",
        reader=R.hyprland_version,
        writer=W.read_only,
        command="hyprctl version",
        description="Compositor version.",
    ),
    _row(
        id="about.seclegion",
        page="about",
        label="SecLegion",
        kind="info",
        reader=R.seclegion_version,
        writer=W.read_only,
        command="read /etc/os-release",
        description="SecLegion release.",
    ),
)

BY_ID = {s.id: s for s in SETTINGS}


def get(setting_id: str) -> Setting:
    try:
        return BY_ID[setting_id]
    except KeyError:
        raise UnknownSetting(f"unknown setting {setting_id!r}; try `seclegion-set list`") from None


@dataclass
class Row:
    """A setting plus its state on this machine."""

    setting: Setting
    visible: bool
    reason: str = ""
    value: object = None
    error: str = ""

    def as_dict(self) -> dict:
        s = self.setting
        return {
            "id": s.id,
            "page": s.page,
            "label": s.label,
            "kind": s.kind,
            "value": self.value,
            "visible": self.visible,
            "reason": self.reason,
            "error": self.error,
            "privileged": s.privileged,
            "readonly": s.readonly,
            "file": s.file,
            "command": s.command,
            "choices": list(s.choices),
            "minimum": s.minimum,
            "maximum": s.maximum,
            "unit": s.unit,
            "keywords": list(s.keywords),
            "description": s.description,
            "capability": s.capability,
        }


def read_value(s: Setting, ctx: Ctx) -> tuple[object, str]:
    """(value, error): a reader failure is data, never an exception."""
    try:
        return s.reader(ctx), ""
    except R.ReadError as e:
        return None, str(e)
    except Exception as e:  # a reader bug must not take `list` down
        return None, f"{type(e).__name__}: {e}"


def row(s: Setting, ctx: Ctx) -> Row:
    c = cap.check(ctx, s.capability)
    if not c.ok:
        return Row(s, False, c.reason)
    value, err = read_value(s, ctx)
    return Row(s, True, "", value, err)


def rows(ctx: Ctx, page: str | None = None) -> list[Row]:
    return [row(s, ctx) for s in SETTINGS if page in (None, s.page)]


PKEXEC = "/usr/bin/pkexec"
# The polkit action's exec.path (org.seclegion.settings.policy): fixed, never taken from the environment.
ROOT_APPLY = "/usr/bin/seclegion-root-apply"
POLKIT_ACTION = "org.seclegion.settings.root-apply"
_ROOT_ID = re.compile(r"[a-z]+(\.[a-z0-9_]+)+")
_SANDBOX = ("SL_HOME", "SL_SYSFS", "SL_ETC")


def root_ready(s: Setting) -> bool:
    """A privileged row seclegion-root-apply can write now (the rest are refused before any prompt)."""
    return s.privileged and s.id in W.ROOT_WRITERS


def root_argv(ctx: Ctx, setting_id: str, raw: str) -> list[str]:
    """The argv a privileged write runs. `SL_PKEXEC` replaces pkexec in tests only."""
    return [ctx.environ.get("SL_PKEXEC") or PKEXEC, ROOT_APPLY, setting_id, raw]


def _root_write(s: Setting, ctx: Ctx, raw: str) -> WriteResult:
    """Apply a privileged row as root: pkexec asks for the administrator password, then
    seclegion-root-apply re-checks the id against its allowlist, re-validates the value and writes
    the file or runs the row's commands. Blocks until the prompt is answered, so call it off the UI
    thread. Nothing is written here, so on any failure the stored value is the one it was."""
    from .rootapply import ALLOWED  # deferred: rootapply imports this module

    if not _ROOT_ID.fullmatch(s.id) or s.id not in ALLOWED:
        raise Refused(f"refusing {s.id!r}: not a setting the system helper may change")
    if s.id not in W.ROOT_WRITERS:
        raise Refused(f"{s.label}: this system setting can only be previewed for now")
    value = s.coerce(raw)  # a bad value fails here, before any password prompt
    if s.id in W.ROOT_COMMANDS:
        W.root_commands(ctx, s.id, value)  # builds the argvs only: an unknown time zone fails here too
    if any(ctx.environ.get(k) for k in _SANDBOX) and not ctx.environ.get("SL_PKEXEC"):
        # a redirected home, sysfs or /etc: the real helper would change the real system instead
        raise Refused(f"{s.label}: not changed; this session is sandboxed")
    argv = root_argv(ctx, s.id, raw)
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                            env=ctx.child_env(), stdin=subprocess.DEVNULL)
    except OSError as e:
        raise CommandFailed(f"{s.label}: not changed; the administrator prompt is not available") from e
    if cp.returncode == 126:
        raise AuthCancelled(f"{s.label}: not changed; the administrator password was not entered")
    if cp.returncode == 127:
        raise NotAuthorized(f"{s.label}: not changed; this account may not change system settings")
    if cp.returncode != 0:
        why = (cp.stderr.strip().splitlines() or [f"exit {cp.returncode}"])[-1]
        raise CommandFailed(f"{s.label}: not changed; {why.removeprefix('seclegion-root-apply: ')}")
    files = [W.ROOT_FILES[s.id]] if s.id in W.ROOT_FILES else []
    return WriteResult(files=files, commands=[argv], applied_live=True)


def write(s: Setting, ctx: Ctx, raw: str) -> WriteResult:
    """Validate and apply `raw`. Privileged rows preview under dry_run, else go through pkexec."""
    c = cap.check(ctx, s.capability)
    if not c.ok:
        raise Unavailable(f"{s.id}: {c.reason}")
    if s.readonly:
        raise Refused(f"{s.id} is read-only")
    if s.privileged and not ctx.dry_run:
        return _root_write(s, ctx, raw)
    return s.writer(ctx, s.coerce(raw))
