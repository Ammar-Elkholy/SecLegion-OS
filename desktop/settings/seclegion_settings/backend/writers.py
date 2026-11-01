# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""User-level writers: `writer(ctx, value) -> WriteResult`.

Values arrive already coerced and range-checked by the registry (bool, int, or str). Writers do the
cross-field checks, then record every file and command through `ctx` so a `--dry-run` shows exactly
what a real run would do. Privileged rows only ever preview; nothing here can write /etc or run a
root command. seclegion-root-apply uses `root_file` and `root_commands` to act as root.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import capabilities as cap
from . import readers, render
from .env import CommandFailed, Ctx, InvalidValue, Refused, Unavailable, WriteResult

SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"


def _res(ctx: Ctx) -> WriteResult:
    return WriteResult(dry_run=ctx.dry_run)


def _onoff(v: bool) -> str:
    return "on" if v else "off"


def read_only(ctx: Ctx, value) -> WriteResult:
    raise Refused("this setting is read-only")


# -- power ---------------------------------------------------------------------------------------
def conservation_mode(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    f = cap.conservation_file(ctx)
    if f is None:
        raise Unavailable("no ideapad_laptop conservation_mode file")
    ctx.write_sysfs(r, f, "1\n" if v else "0\n")
    r.applied_live = True
    r.notes.append("the firmware stops charging at about 80%; takes effect at once")
    return r


def power_profile(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["powerprofilesctl", "set", v], live=True)
    return r


def _write_battery(ctx: Ctx, low: int, critical: int) -> WriteResult:
    if not critical < low:
        raise InvalidValue(f"critical ({critical} %) must be below low ({low} %)")
    r = _res(ctx)
    ctx.write_file(r, ctx.config_dir / "battery.toml", render.render_battery_toml(low, critical))
    r.notes.append("read by the low-battery alert helper on its next check")
    return r


def alert_low(ctx: Ctx, v: int) -> WriteResult:
    return _write_battery(ctx, v, readers.alert_critical(ctx))


def alert_critical(ctx: Ctx, v: int) -> WriteResult:
    return _write_battery(ctx, readers.alert_low(ctx), v)


def lid_ignore(ctx: Ctx, v: bool) -> WriteResult:
    """A user unit holding a handle-lid-switch inhibitor: no root, applies at once."""
    r = _res(ctx)
    unit = ctx.home / ".config" / "systemd" / "user" / render.LID_UNIT
    if v:
        ctx.write_file(r, unit, render.render_lid_inhibit_unit())
        ctx.exec(r, ["systemctl", "--user", "daemon-reload"])
        ctx.exec(r, ["systemctl", "--user", "enable", "--now", render.LID_UNIT], live=True)
    else:
        # nothing to disable when the unit was never written
        ctx.exec(
            r, ["systemctl", "--user", "disable", "--now", render.LID_UNIT], required=unit.exists(), live=True
        )
    return r


# Everything below that calls ctx.preview_file is text for display. seclegion-root-apply re-validates
# each value and re-renders with root_file(installed=True); it never installs preview text.
ROOT_FILES = {
    "power.lid_battery": render.LID_FILE,
    "power.lid_ac": render.LID_FILE,
    "power.lid_docked": render.LID_FILE,
    "power.power_button": render.POWER_FILE,
    "power.charge_limit": render.CHARGE_FILE,
    "power.suspend_mode": render.SLEEP_FILE,
    "updates.snapshot_keep": render.SNAPPER_FILE,
}
_LID_IDX = {"power.lid_battery": 0, "power.lid_ac": 1, "power.lid_docked": 2}


def root_file(ctx: Ctx, sid: str, v, installed: bool = False) -> tuple[str, str]:
    """(path, text) for a privileged row. One renderer for the preview and for seclegion-root-apply."""
    if sid in _LID_IDX:
        # The current values come from a file in /etc: keep only ones that are still valid choices.
        vals = [
            x if x in render.LID_ACTIONS else d
            for x, d in zip(readers.lid_values(ctx), ("suspend", "suspend", "ignore"), strict=True)
        ]
        vals[_LID_IDX[sid]] = v
        return render.LID_FILE, render.render_logind_lid(*vals, installed=installed)
    if sid == "power.power_button":
        return render.POWER_FILE, render.render_logind_power(v, installed=installed)
    if sid == "power.suspend_mode":
        return render.SLEEP_FILE, render.render_sleep_mode(v, installed=installed)
    if sid == "power.charge_limit":
        f = readers.charge_limit_file(ctx)
        bat = f.parent.name if f else (cap.batteries(ctx) or [None])[0]
        name = bat if isinstance(bat, str) else (bat.name if bat else "BAT0")
        try:
            return render.CHARGE_FILE, render.render_charge_limit(name, v, installed=installed)
        except ValueError as e:
            raise Unavailable(f"battery {name!r} has an unusual name; refusing a charge limit") from e
    if sid == "updates.snapshot_keep":
        try:
            config = (ctx.etc / Path(render.SNAPPER_FILE).relative_to("/etc")).read_text(encoding="utf-8")
        except OSError as e:
            why = e.strerror or e
            raise Unavailable(f"cannot read {render.SNAPPER_FILE} ({why}); not creating one") from e
        try:
            return render.SNAPPER_FILE, render.edit_snapshot_keep(config, v)
        except ValueError as e:
            raise InvalidValue(str(e)) from e
    raise Refused(f"{sid} is not a privileged setting")


# Root rows that run commands instead of writing a file. Absolute binaries, argv lists only.
TIMEDATECTL = "/usr/bin/timedatectl"
SYSTEMCTL = "/usr/bin/systemctl"
UFW = "/usr/bin/ufw"
ZONEINFO = "/usr/share/zoneinfo"
# The units the installer masks (installer/installd/post.py SSHD_MASKED); a test keeps them equal.
SSHD_UNITS = ("sshd.service", "sshd.socket", "sshd@.service", "sshd-unix-local.socket")


def zone_file(ctx: Ctx, tz: str) -> Path:
    """The zoneinfo file for `tz`, or InvalidValue. `SL_ZONEINFO` replaces /usr/share/zoneinfo in tests."""
    if not render.TZ_RE.match(tz) or ".." in tz or tz.startswith("/"):
        raise InvalidValue(f"{tz!r} is not a time zone name")
    root = os.path.realpath(ctx.environ.get("SL_ZONEINFO") or ZONEINFO)
    f = Path(root) / tz
    if not f.is_file() or not os.path.realpath(f).startswith(root + os.sep):
        raise InvalidValue(f"{tz!r} is not a time zone in {ZONEINFO}")
    return f


def _tz_argvs(ctx: Ctx, v: str) -> list[list[str]]:
    zone_file(ctx, v)
    return [[TIMEDATECTL, "set-timezone", v]]


def _ssh_argvs(ctx: Ctx, v: bool) -> list[list[str]]:
    if v:
        return [[SYSTEMCTL, "unmask", *SSHD_UNITS], [SYSTEMCTL, "enable", "--now", "sshd.service"]]
    return [[SYSTEMCTL, "disable", "--now", "sshd.service"], [SYSTEMCTL, "mask", *SSHD_UNITS]]


def _ufw_argvs(ctx: Ctx, v: bool) -> list[list[str]]:
    return [[UFW, "--force", "enable"] if v else [UFW, "disable"]]


ROOT_COMMANDS = {
    "region.timezone": _tz_argvs,
    "security.ssh_enable": _ssh_argvs,
    "security.firewall": _ufw_argvs,
}
# Every privileged row seclegion-root-apply can act on: the source of registry.root_ready.
ROOT_WRITERS = frozenset(ROOT_FILES) | frozenset(ROOT_COMMANDS)


def root_commands(ctx: Ctx, sid: str, v) -> list[list[str]]:
    """The argvs a command-based privileged row runs as root, in order; the value is checked first."""
    if sid not in ROOT_COMMANDS:
        raise Refused(f"{sid} is not a privileged command setting")
    return ROOT_COMMANDS[sid](ctx, v)


ASKS = "Needs root: asks for the administrator password."


def _preview(ctx: Ctx, sid: str, v) -> WriteResult:
    r = _res(ctx)
    ctx.preview_file(r, *root_file(ctx, sid, v))
    return r


def lid_battery(ctx: Ctx, v: str) -> WriteResult:
    return _preview(ctx, "power.lid_battery", v)


def lid_ac(ctx: Ctx, v: str) -> WriteResult:
    return _preview(ctx, "power.lid_ac", v)


def lid_docked(ctx: Ctx, v: str) -> WriteResult:
    return _preview(ctx, "power.lid_docked", v)


def power_button(ctx: Ctx, v: str) -> WriteResult:
    return _preview(ctx, "power.power_button", v)


def charge_limit(ctx: Ctx, v: int) -> WriteResult:
    return _preview(ctx, "power.charge_limit", v)


def suspend_mode(ctx: Ctx, v: str) -> WriteResult:
    return _preview(ctx, "power.suspend_mode", v)


def snapshot_keep(ctx: Ctx, v: int) -> WriteResult:
    return _preview(ctx, "updates.snapshot_keep", v)


# -- sleep / lock / idle -------------------------------------------------------------------------
def _idle(ctx: Ctx, **change) -> WriteResult:
    st = readers.idle_state(ctx).with_(**change)
    try:
        text = render.render_idle(st, battery=cap.detect(ctx)["battery"].ok)
    except ValueError as e:
        raise InvalidValue(str(e)) from e
    r = _res(ctx)
    ctx.write_file(r, ctx.config_dir / "idle.conf", text)
    r.notes.append("takes effect when hypridle restarts; include the file from hypridle.conf once (D5)")
    return r


def idle_lock(ctx: Ctx, v: str) -> WriteResult:
    return _idle(ctx, lock=render.parse_minutes(v))


def idle_screen_off(ctx: Ctx, v: str) -> WriteResult:
    return _idle(ctx, screen_off=render.parse_minutes(v))


def idle_suspend_battery(ctx: Ctx, v: str) -> WriteResult:
    return _idle(ctx, suspend_battery=render.parse_minutes(v))


def idle_suspend_ac(ctx: Ctx, v: str) -> WriteResult:
    return _idle(ctx, suspend_ac=render.parse_minutes(v))


def idle_lock_before_sleep(ctx: Ctx, v: bool) -> WriteResult:
    return _idle(ctx, lock_before_sleep=v)


# -- display -------------------------------------------------------------------------------------
def brightness(ctx: Ctx, v: int) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["brightnessctl", "-c", "backlight", "set", f"{v}%"], live=True)
    return r


def kbd_brightness(ctx: Ctx, v: int) -> WriteResult:
    dev = cap.kbd_backlight_device(ctx)
    if dev is None:
        raise Refused("no keyboard backlight")
    r = _res(ctx)
    ctx.exec(r, ["brightnessctl", "-d", dev, "set", f"{v}%"], live=True)
    return r


NO_SECOND_DISPLAY = "No second display is connected."
NO_LAPTOP_SCREEN = "No laptop screen was found."


def display_layout(ctx: Ctx, v: str) -> WriteResult:
    """Runs the display menu with the mode. With one output every mode is refused before anything
    runs: the menu has nothing safe to do there, and the laptop screen must stay on."""
    exe = cap.find_display_menu(ctx)
    if exe is None:
        raise Unavailable("the display menu is not installed")
    try:
        ms = readers.monitors(ctx)
    except readers.ReadError as e:
        raise CommandFailed(f"hyprctl -j monitors all: {e}") from e
    if len(ms) < 2:
        raise Unavailable(NO_SECOND_DISPLAY)
    if readers.split_monitors(ctx, ms)[0] is None:
        raise Unavailable(NO_LAPTOP_SCREEN)
    r = _res(ctx)
    ctx.exec(r, [exe, v], live=True)
    r.notes.append("applies at once; signing in again goes back to the configured monitors")
    return r


def _nightlight(ctx: Ctx, enabled: bool, temp: int) -> WriteResult:
    r = _res(ctx)
    ctx.write_file(r, ctx.config_dir / "nightlight.toml", render.render_nightlight_toml(enabled, temp))
    sunset = ["hyprctl", "hyprsunset"]
    live = [*sunset, "temperature", str(temp)] if enabled else [*sunset, "identity"]
    ctx.exec(r, live, required=False, live=True)
    return r


def nightlight(ctx: Ctx, v: bool) -> WriteResult:
    return _nightlight(ctx, v, readers.nightlight_temp(ctx))


def nightlight_temp(ctx: Ctx, v: int) -> WriteResult:
    enabled = readers.nightlight(ctx)
    if enabled:
        return _nightlight(ctx, True, v)
    r = _res(ctx)  # off: remember the temperature, change nothing on screen
    ctx.write_file(r, ctx.config_dir / "nightlight.toml", render.render_nightlight_toml(False, v))
    return r


# -- sound ---------------------------------------------------------------------------------------
def volume(ctx: Ctx, v: int) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["wpctl", "set-volume", SINK, f"{v}%"], live=True)
    return r


def mute(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["wpctl", "set-mute", SINK, "1" if v else "0"], live=True)
    return r


def mic_mute(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["wpctl", "set-mute", SOURCE, "1" if v else "0"], live=True)
    return r


# -- network -------------------------------------------------------------------------------------
def wifi(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["nmcli", "radio", "wifi", _onoff(v)], live=True)
    return r


def airplane(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["rfkill", "block" if v else "unblock", "all"], live=True)
    return r


def bluetooth(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["bluetoothctl", "power", _onoff(v)], live=True)
    return r


# -- bluetooth, storage, updates -------------------------------------------------------------------
def bluetooth_advanced(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.launch(r, ["blueman-manager"])
    return r


def empty_trash(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["gio", "trash", "--empty"], live=True)
    return r


def low_disk(ctx: Ctx, v: int) -> WriteResult:
    r = _res(ctx)
    ctx.write_file(r, ctx.config_dir / "storage.toml", render.render_storage_toml(v))
    r.notes.append("read by the low-disk alert helper on its next check")
    return r


UPDATE_SCRIPT = 'sudo pacman -Syu; printf "\\nFinished. Press Enter to close. "; read _'


def update_now(ctx: Ctx, v: str) -> WriteResult:
    """Opens a terminal running pacman; the password prompt is sudo's, in that terminal."""
    r = _res(ctx)
    ctx.launch(r, ["xdg-terminal-exec", "sh", "-c", UPDATE_SCRIPT])
    r.notes.append("pacman runs in the terminal window; this app never sees the password")
    return r


# -- notifications -------------------------------------------------------------------------------
def dnd(ctx: Ctx, v: bool) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["swaync-client", "-dn" if v else "-df"], live=True)
    return r


# -- apps ----------------------------------------------------------------------------------------
def file_manager(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["xdg-mime", "default", v, "inode/directory"], live=True)
    return r


def browser(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["xdg-settings", "set", "default-web-browser", v], live=True)
    return r


def terminal(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.write_file(r, ctx.home / ".config" / "xdg-terminals.list", render.render_terminal_list(v))
    r.applied_live = True  # read at launch time by xdg-terminal-exec
    return r


# -- autolock: seclegion-autolock owns the units and its state file; no root, applies at once ---
def autolock(ctx: Ctx, v: str) -> WriteResult:
    exe = cap.find_autolock_cli(ctx)
    if exe is None:
        raise Refused("Automatic lock: not changed. It is not set up on this system.")
    r = _res(ctx)
    ctx.exec(r, ["seclegion-autolock" if ctx.which("seclegion-autolock") else exe, "set", v], live=True)
    return r


# -- appearance: seclegion-theme is the only writer of colour files ------------------------------
def _theme(ctx: Ctx, mode: str, contrast: str) -> WriteResult:
    exe = cap.find_theme_cli(ctx)
    if exe is None:
        raise Refused("seclegion-theme is not installed")
    prog = "seclegion-theme" if ctx.which("seclegion-theme") else exe
    cmd = [prog, "apply", "--mode", mode, "--contrast", contrast]
    if mode == "auto":  # keep a hand-picked accent when only the contrast changes
        accent = (readers.theme_current(ctx).get("source") or {}).get("accent_override")
        if isinstance(accent, str) and accent:
            cmd += ["--accent", accent]
    r = _res(ctx)
    ctx.exec(r, cmd, live=True)
    return r


def _theme_cmd(ctx: Ctx, *args: str) -> WriteResult:
    exe = cap.find_theme_cli(ctx)
    if exe is None:
        raise Refused("seclegion-theme is not installed")
    r = _res(ctx)
    ctx.exec(r, ["seclegion-theme" if ctx.which("seclegion-theme") else exe, *args], live=True)
    return r


def theme_id(ctx: Ctx, v: str) -> WriteResult:
    return _theme_cmd(ctx, "apply", "--theme", v)


def theme_auto(ctx: Ctx, v: bool) -> WriteResult:
    return _theme_cmd(ctx, "auto", "on" if v else "off")


def theme_reset(ctx: Ctx, v: str) -> WriteResult:
    return _theme_cmd(ctx, "reset")


def theme_mode(ctx: Ctx, v: str) -> WriteResult:
    return _theme(ctx, v, readers.theme_contrast(ctx))


def theme_contrast(ctx: Ctx, v: str) -> WriteResult:
    return _theme(ctx, readers.theme_mode(ctx), v)


# -- input, region, troubleshoot ---------------------------------------------------------------------
def _input(ctx: Ctx, **change) -> WriteResult:
    r = _res(ctx)
    ctx.write_file(
        r, ctx.config_dir / "input.lua", render.render_input_lua({**readers.input_values(ctx), **change})
    )
    r.notes.append("applies at the next Hyprland reload; this app never reloads it")
    return r


def repeat_rate(ctx: Ctx, v: int) -> WriteResult:
    return _input(ctx, repeat_rate=v)


def repeat_delay(ctx: Ctx, v: int) -> WriteResult:
    return _input(ctx, repeat_delay=v)


def tap_to_click(ctx: Ctx, v: bool) -> WriteResult:
    return _input(ctx, tap_to_click=v)


def natural_scroll(ctx: Ctx, v: bool) -> WriteResult:
    return _input(ctx, natural_scroll=v)


def disable_while_typing(ctx: Ctx, v: bool) -> WriteResult:
    return _input(ctx, disable_while_typing=v)


def clock_format(ctx: Ctx, v: str) -> WriteResult:
    r = _res(ctx)
    ctx.write_file(r, ctx.config_dir / "clock.toml", render.render_clock_toml(v))
    r.notes.append("read by the bar clock on its next start")
    return r


def timezone(ctx: Ctx, v: str) -> WriteResult:
    return _root_preview(ctx, "region.timezone", v)


SERVICES = {"waybar": "waybar.service", "swaync": "swaync.service", "hypridle": "hypridle.service"}


def _restart(ctx: Ctx, name: str) -> WriteResult:
    r = _res(ctx)
    ctx.exec(r, ["systemctl", "--user", "restart", SERVICES[name]], live=True)
    return r


def restart_waybar(ctx: Ctx, v: str) -> WriteResult:
    return _restart(ctx, "waybar")


def restart_swaync(ctx: Ctx, v: str) -> WriteResult:
    return _restart(ctx, "swaync")


def restart_hypridle(ctx: Ctx, v: str) -> WriteResult:
    return _restart(ctx, "hypridle")


def diagnostics_text(ctx: Ctx) -> str:
    """Versions, failed user units and Hyprland config errors, with the home path, user and host
    names and addresses removed."""

    def got(fn, *a):
        try:
            return fn(ctx, *a)
        except readers.ReadError as e:
            return f"unavailable ({e})"

    def cmd(argv: list[str]) -> str:
        p = ctx.run(argv)
        return p.out.strip() if p.ok else f"unavailable ({(p.err or p.out).strip() or 'exit ' + str(p.rc)})"

    failed = cmd(["systemctl", "--user", "list-units", "--state=failed", "--no-legend", "--plain"])
    raw = "\n".join(
        [
            "SecLegion diagnostics",
            f"settings: {got(readers.seclegion_version)}",
            f"kernel: {got(readers.kernel)}",
            f"hyprland: {got(readers.hyprland_version)}",
            "failed user units: " + (failed or "none"),
            "hyprland config errors: " + (cmd(["hyprctl", "configerrors"]) or "none"),
            "",
        ]
    )
    user = ctx.environ.get("USER") or ctx.environ.get("LOGNAME") or ctx.home.name
    return render.redact(raw, home=str(ctx.home), user=user, host=os.uname().nodename)


def copy_diagnostics(ctx: Ctx, v: str) -> WriteResult:
    text = diagnostics_text(ctx)
    r = _res(ctx)
    ctx.exec(r, ["wl-copy"], input_text=text, live=True)
    r.notes.append("copied to the clipboard; home path, user and host names and addresses are removed")
    return r


# -- security, users --------------------------------------------------------------------------------
def _root_preview(ctx: Ctx, sid: str, v) -> WriteResult:
    """Preview only: the root commands are listed, never run; seclegion-root-apply runs them."""
    r = _res(ctx)
    r.commands.extend(root_commands(ctx, sid, v))
    r.notes.append(ASKS)
    return r


def ssh_enable(ctx: Ctx, v: bool) -> WriteResult:
    return _root_preview(ctx, "security.ssh_enable", v)


def firewall(ctx: Ctx, v: bool) -> WriteResult:
    return _root_preview(ctx, "security.firewall", v)


PASSWD_SCRIPT = 'passwd; printf "\\nPress Enter to close. "; read _'


def change_password(ctx: Ctx, v: str) -> WriteResult:
    """Opens a terminal running `passwd` for the signed-in user; the prompts are passwd's."""
    r = _res(ctx)
    ctx.launch(r, ["xdg-terminal-exec", "sh", "-c", PASSWD_SCRIPT])
    r.notes.append("passwd runs in the terminal window; this app never sees the password")
    return r
