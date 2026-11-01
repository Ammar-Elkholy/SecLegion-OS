# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Hardware and tool detection. Never raises: a missing thing becomes `Cap(False, reason)`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .env import Ctx

NOT_HW = "Not supported on this hardware: "
NOT_INSTALLED = "Not available: "


@dataclass(frozen=True)
class Cap:
    ok: bool
    reason: str = ""


def _glob(base: Path, pattern: str) -> list[Path]:
    try:
        return sorted(base.glob(pattern))
    except OSError:
        return []


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def batteries(ctx: Ctx) -> list[Path]:
    out = []
    for p in _glob(ctx.sysfs, "class/power_supply/*"):
        if _read(p / "type").lower() == "battery" or p.name.startswith("BAT"):
            out.append(p)
    return out


def conservation_file(ctx: Ctx) -> Path | None:
    """The ideapad_laptop driver's `conservation_mode` attribute (Lenovo IdeaPad/Legion only)."""
    found = _glob(ctx.sysfs, "bus/platform/drivers/ideapad_acpi/*/conservation_mode")
    return found[0] if found else None


def kbd_backlight_device(ctx: Ctx) -> str | None:
    devs = _glob(ctx.sysfs, "class/leds/*kbd_backlight")
    return devs[0].name if devs else None


def mem_sleep_modes(ctx: Ctx) -> tuple[list[str], str | None]:
    """(modes, selected) from <sysfs>/power/mem_sleep, e.g. 's2idle [deep]'."""
    modes, sel = [], None
    for tok in _read(ctx.sysfs / "power" / "mem_sleep").split():
        name = tok.strip("[]")
        modes.append(name)
        if tok.startswith("["):
            sel = name
    return modes, sel


def _tool(ctx: Ctx, name: str) -> Cap:
    return Cap(True) if ctx.which(name) else Cap(False, f"{NOT_INSTALLED}{name} is not installed")


def _all_tools(ctx: Ctx, *names: str) -> Cap:
    for n in names:
        c = _tool(ctx, n)
        if not c.ok:
            return c
    return Cap(True)


def _hw(ctx: Ctx, tools: tuple[str, ...], present: bool, missing_hw: str) -> Cap:
    c = _all_tools(ctx, *tools)
    if not c.ok:
        return c
    return Cap(True) if present else Cap(False, NOT_HW + missing_hw)


def _hyprland(ctx: Ctx) -> Cap:
    """A Hyprland session to ask: hyprctl on PATH and this session's instance signature."""
    if not ctx.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Cap(False, NOT_INSTALLED + "Hyprland is not running in this session")
    return _tool(ctx, "hyprctl")


def _display_menu(ctx: Ctx) -> Cap:
    c = _hyprland(ctx)
    if not c.ok:
        return c
    if find_display_menu(ctx):
        return Cap(True)
    return Cap(False, NOT_INSTALLED + "the display menu is not installed")


def detect(ctx: Ctx) -> dict[str, Cap]:
    """Detect every capability a registry row can name. Cached on the Ctx."""
    if ctx.caps is not None:
        return ctx.caps
    bats = batteries(ctx)
    modes, _ = mem_sleep_modes(ctx)
    lid = any("lid switch" in _read(p).lower() for p in _glob(ctx.sysfs, "class/input/input*/name"))
    wifi = bool(_glob(ctx.sysfs, "class/ieee80211/*") or _glob(ctx.sysfs, "class/net/*/wireless"))
    caps = {
        "battery": Cap(True) if bats else Cap(False, NOT_HW + "no battery"),
        "charge_threshold": Cap(True)
        if any((b / "charge_control_end_threshold").exists() for b in bats)
        else Cap(False, NOT_HW + "no charge threshold file"),
        "conservation": Cap(True)
        if conservation_file(ctx)
        else Cap(False, NOT_HW + "no ideapad_laptop conservation_mode file (Lenovo IdeaPad and Legion only)"),
        "sleep_modes": Cap(True)
        if "s2idle" in modes and "deep" in modes
        else Cap(False, NOT_HW + "/sys/power/mem_sleep does not offer both s2idle and deep"),
        "lid": Cap(True) if lid else Cap(False, NOT_HW + "no lid switch"),
        "lid_inhibit": _hw(ctx, ("systemctl", "systemd-inhibit"), lid, "no lid switch"),
        "ppd": _tool(ctx, "powerprofilesctl"),
        "backlight": _hw(
            ctx, ("brightnessctl",), bool(_glob(ctx.sysfs, "class/backlight/*")), "no backlight device"
        ),
        "kbd_backlight": _hw(
            ctx, ("brightnessctl",), kbd_backlight_device(ctx) is not None, "no keyboard backlight"
        ),
        "hyprsunset": _all_tools(ctx, "hyprsunset", "hyprctl"),
        "hyprland": _hyprland(ctx),
        "display_menu": _display_menu(ctx),
        "audio": _tool(ctx, "wpctl"),
        "wifi": _hw(ctx, ("nmcli",), wifi, "no Wi-Fi adapter"),
        "rfkill": _tool(ctx, "rfkill"),
        "bluetooth": _hw(
            ctx, ("bluetoothctl",), bool(_glob(ctx.sysfs, "class/bluetooth/*")), "no Bluetooth adapter"
        ),
        "blueman": _hw(
            ctx, ("blueman-manager",), bool(_glob(ctx.sysfs, "class/bluetooth/*")), "no Bluetooth adapter"
        ),
        "gio": _tool(ctx, "gio"),
        "pacman_updates": _tool(ctx, "checkupdates"),
        "terminal": _tool(ctx, "xdg-terminal-exec"),
        "snapper": _tool(ctx, "snapper"),
        "systemctl": _tool(ctx, "systemctl"),
        "wl_copy": _tool(ctx, "wl-copy"),
        "ss": _tool(ctx, "ss"),
        "sshd": _all_tools(ctx, "systemctl", "sshd"),
        "ufw": _all_tools(ctx, "systemctl", "ufw"),
        "dnd": _tool(ctx, "swaync-client"),
        "xdg": _all_tools(ctx, "xdg-mime", "xdg-settings"),
        "autolock": Cap(True)
        if find_autolock_cli(ctx)
        else Cap(False, NOT_INSTALLED + "the automatic lock is not set up on this system"),
        "theme": Cap(True)
        if find_theme_cli(ctx)
        else Cap(False, NOT_INSTALLED + "seclegion-theme is not installed"),
    }
    ctx.caps = caps
    return caps


def find_theme_cli(ctx: Ctx) -> str | None:
    """`seclegion-theme` on PATH, else the launcher beside the host-installed python/
    directory (host/settings/seclegion-theme), else the one in this checkout's tools/."""
    found = ctx.which("seclegion-theme")
    if found:
        return found
    here = Path(__file__).resolve()
    for cand in (here.parents[3] / "seclegion-theme", here.parents[4] / "tools" / "seclegion-theme"):
        if cand.is_file():
            return str(cand)
    return None


def find_autolock_cli(ctx: Ctx) -> str | None:
    """`seclegion-autolock` on PATH, else the link `seclegion-host apply idle` makes in ~/.local/bin."""
    found = ctx.which("seclegion-autolock")
    if found:
        return found
    cand = ctx.home / ".local" / "bin" / "seclegion-autolock"
    return str(cand) if cand.is_file() and os.access(cand, os.X_OK) else None


def find_display_menu(ctx: Ctx) -> str | None:
    """The display menu (owner issue 14): the link `seclegion-host apply display` makes in ~/.local/bin,
    else the packaged one on PATH (/usr/bin/seclegion-display-menu)."""
    cand = ctx.home / ".local" / "bin" / "seclegion-display-menu"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return ctx.which("seclegion-display-menu")


def check(ctx: Ctx, name: str | None) -> Cap:
    if name is None:
        return Cap(True)
    return detect(ctx).get(name, Cap(False, f"unknown capability {name}"))
