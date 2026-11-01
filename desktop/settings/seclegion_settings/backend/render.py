# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Pure functions that turn setting values into config text. No I/O, no clock."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

LOCK_CHOICES = ("1", "2", "3", "5", "10", "15", "30", "never")
SCREEN_OFF_CHOICES = LOCK_CHOICES
SUSPEND_BATTERY_CHOICES = ("5", "10", "15", "30", "60", "never")
SUSPEND_AC_CHOICES = SUSPEND_BATTERY_CHOICES

# True when any external supply reports online=1: AC*/ADP* adapters by name, plus any supply whose
# type is Mains or USB (a USB-C-only laptop reports its charger as ucsi-source-psy-*, type USB). An
# unmatched glob just makes cat fail, which reads as "not on AC". No dollar sign or backslash:
# hyprlang may expand them.
ON_AC_TEST = (
    "(cat /sys/class/power_supply/AC*/online /sys/class/power_supply/ADP*/online; "
    'grep -lxE "Mains|USB" /sys/class/power_supply/*/type | sed "s|/type|/online|" | xargs -r cat) '
    "2>/dev/null | grep -qx 1"
)
SUSPEND_CMD = "systemctl suspend"
LOCK_CMD = "loginctl lock-session"
# Hyprland Lua-mode DPMS dispatch: hl.dsp.dpms is in /usr/share/hypr/stubs/hl.meta.lua and the
# hypridle sample config uses the same hyprctl dispatch form.
DPMS_OFF = """hyprctl dispatch 'hl.dsp.dpms({action="off"})'"""
DPMS_ON = """hyprctl dispatch 'hl.dsp.dpms({action="on"})'"""


@dataclass(frozen=True)
class IdleState:
    """Minutes, or None for "never"."""

    lock: int | None = 5
    screen_off: int | None = 10
    suspend_battery: int | None = 15
    suspend_ac: int | None = None
    lock_before_sleep: bool = True

    def with_(self, **kw) -> IdleState:
        return replace(self, **kw)


def _mins(v: int | None) -> str:
    return "never" if v is None else str(v)


def parse_minutes(s: str) -> int | None:
    return None if s == "never" else int(s)


def validate_idle(st: IdleState) -> None:
    """lock < screen off < suspend (battery and AC), over the timeouts that are set."""

    def need(a_name, a, b_name, b):
        if a is not None and b is not None and not a < b:
            raise ValueError(f"{b_name} ({b} min) must come after {a_name} ({a} min)")

    need("lock", st.lock, "screen off", st.screen_off)
    need("screen off", st.screen_off, "suspend on battery", st.suspend_battery)
    need("screen off", st.screen_off, "suspend on AC", st.suspend_ac)
    need("lock", st.lock, "suspend on battery", st.suspend_battery)
    need("lock", st.lock, "suspend on AC", st.suspend_ac)


_STATE_RE = re.compile(r"^# sl-state: (.*)$", re.M)


def idle_state_line(st: IdleState) -> str:
    return (
        f"# sl-state: lock={_mins(st.lock)} screen_off={_mins(st.screen_off)} "
        f"suspend_battery={_mins(st.suspend_battery)} suspend_ac={_mins(st.suspend_ac)} "
        f"lock_before_sleep={'on' if st.lock_before_sleep else 'off'}"
    )


def _readback(kv: dict, key: str, choices: tuple[str, ...], default: int | None) -> int | None:
    """A value read back from the header counts only if it is exactly one of the offered choices
    (which also rules out signs, non-ASCII digits and huge numbers); anything else is the default."""
    v = kv.get(key)
    return parse_minutes(v) if v in choices else default


def parse_idle_state(text: str) -> IdleState | None:
    """Read back the values from the sl-state header line; None if absent or malformed.

    The file is user-writable, so every value is re-validated against its choices.
    """
    m = _STATE_RE.search(text)
    if not m:
        return None
    try:
        kv = dict(p.split("=", 1) for p in m.group(1).split())
    except ValueError:
        return None
    d = IdleState()
    return IdleState(
        lock=_readback(kv, "lock", LOCK_CHOICES, d.lock),
        screen_off=_readback(kv, "screen_off", SCREEN_OFF_CHOICES, d.screen_off),
        suspend_battery=_readback(kv, "suspend_battery", SUSPEND_BATTERY_CHOICES, d.suspend_battery),
        suspend_ac=_readback(kv, "suspend_ac", SUSPEND_AC_CHOICES, d.suspend_ac),
        lock_before_sleep=kv.get("lock_before_sleep") == "on",
    )


def _listener(minutes: int, on_timeout: str, on_resume: str | None = None, comment: str = "") -> str:
    out = [
        "",
        f"# {comment}" if comment else None,
        "listener {",
        f"    timeout = {minutes * 60}",
        f"    on-timeout = {on_timeout}",
    ]
    if on_resume:
        out.append(f"    on-resume = {on_resume}")
    out.append("}")
    return "\n".join(x for x in out if x is not None)


def render_idle(st: IdleState, battery: bool = True) -> str:
    """The full hypridle config SecLegion Settings owns (~/.config/seclegion/idle.conf).

    `battery=False` (no battery on this machine) leaves out the suspend-on-battery listener; the
    value stays in the sl-state line so it survives if a battery shows up.
    """
    validate_idle(st)
    lines = [
        # REUSE-IgnoreStart
        "# SPDX-License-Identifier: MIT",
        # REUSE-IgnoreEnd
        "# Generated by SecLegion Settings. Do not edit: change it with seclegion-set or the Settings app.",
        "# Include it once from your own hypridle.conf with:  source = ~/.config/seclegion/idle.conf",
        idle_state_line(st),
        "",
        "general {",
        "    lock_cmd = pidof hyprlock || hyprlock",
    ]
    if st.lock_before_sleep:
        lines.append(f"    before_sleep_cmd = {LOCK_CMD}")
    lines += [f"    after_sleep_cmd = {DPMS_ON}", "}"]
    body = "\n".join(lines)
    if st.lock is not None:
        body += _listener(st.lock, LOCK_CMD, comment="lock the session")
    if st.screen_off is not None:
        body += _listener(st.screen_off, DPMS_OFF, DPMS_ON, comment="screen off")
    if battery and st.suspend_battery is not None:
        # Suspend never happens on AC: the guard skips it while a mains adapter is online.
        body += _listener(
            st.suspend_battery,
            f"sh -c '{ON_AC_TEST} || {SUSPEND_CMD}'",
            comment="suspend on battery only (AC guard)",
        )
    if st.suspend_ac is not None:
        body += _listener(
            st.suspend_ac,
            f"sh -c '{ON_AC_TEST} && {SUSPEND_CMD}'",
            comment="suspend on AC only",
        )
    return body + "\n"


# -- privileged rows (installed by seclegion-root-apply through pkexec) ------------------------------
LID_ACTIONS = ("suspend", "lock", "ignore", "hibernate", "poweroff")
POWER_ACTIONS = ("poweroff", "suspend", "hibernate", "lock", "ignore")
LID_FILE = "/etc/systemd/logind.conf.d/50-seclegion-lid.conf"
POWER_FILE = "/etc/systemd/logind.conf.d/50-seclegion-power.conf"
CHARGE_FILE = "/etc/tmpfiles.d/50-seclegion-charge-limit.conf"
SLEEP_FILE = "/etc/tmpfiles.d/50-seclegion-sleep.conf"
SNAPPER_FILE = "/etc/snapper/configs/root"  # edited in place: only NUMBER_LIMIT changes

# PREVIEW TEXT ONLY. seclegion-root-apply never installs this text: it re-validates every value
# (choices, battery name) itself and re-renders from scratch as root (_ROOT_HDR_INSTALLED).
_ROOT_HDR = (
    # REUSE-IgnoreStart
    "# SPDX-License-Identifier: MIT\n"
    # REUSE-IgnoreEnd
    "# sl-preview: generated by SecLegion Settings for display; the privileged helper re-validates\n"
    "# and re-renders it, so do not edit."
)
_ROOT_HDR_INSTALLED = (
    # REUSE-IgnoreStart
    "# SPDX-License-Identifier: MIT\n"
    # REUSE-IgnoreEnd
    "# Installed by seclegion-root-apply (SecLegion Settings). "
    "Change it with seclegion-root-apply, not by hand."
)


def _hdr(installed: bool) -> str:
    return _ROOT_HDR_INSTALLED if installed else _ROOT_HDR


BATTERY_NAME = re.compile(r"^BAT[0-9]+$")


def render_logind_lid(battery: str, ac: str, docked: str, installed: bool = False) -> str:
    for v in (battery, ac, docked):
        if v not in LID_ACTIONS:
            raise ValueError(f"not a lid action: {v!r}")
    return (
        f"{_hdr(installed)}\n[Login]\nHandleLidSwitch={battery}\n"
        f"HandleLidSwitchExternalPower={ac}\nHandleLidSwitchDocked={docked}\n"
    )


def render_logind_power(action: str, installed: bool = False) -> str:
    if action not in POWER_ACTIONS:
        raise ValueError(f"not a power key action: {action!r}")
    return f"{_hdr(installed)}\n[Login]\nHandlePowerKey={action}\n"


def render_charge_limit(battery: str, percent: int, installed: bool = False) -> str:
    if not BATTERY_NAME.match(battery):
        raise ValueError(f"not a battery name: {battery!r}")
    return (
        f"{_hdr(installed)}\n"
        f"w /sys/class/power_supply/{battery}/charge_control_end_threshold - - - - {percent}\n"
    )


_NUMBER_LIMIT = re.compile(r"^NUMBER_LIMIT=.*$", re.M)


def edit_snapshot_keep(config: str, keep: int) -> str:
    """The snapper config with NUMBER_LIMIT set to `keep`; every other line is kept as it is."""
    if not 1 <= keep <= 50:
        raise ValueError(f"not a snapshot count: {keep!r}")
    line = f'NUMBER_LIMIT="{keep}"'
    if _NUMBER_LIMIT.search(config):
        return _NUMBER_LIMIT.sub(line, config)
    return config + ("" if config.endswith("\n") or not config else "\n") + line + "\n"


def render_sleep_mode(mode: str, installed: bool = False) -> str:
    if mode not in ("s2idle", "deep"):
        raise ValueError(f"not a sleep mode: {mode!r}")
    return f"{_hdr(installed)}\nw /sys/power/mem_sleep - - - - {mode}\n"


# -- user state files ----------------------------------------------------------------------------
def render_battery_toml(low: int, critical: int) -> str:
    return (
        # REUSE-IgnoreStart
        "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n"
        # REUSE-IgnoreEnd
        f"[alerts]\nlow = {low}\ncritical = {critical}\n"
    )


def render_nightlight_toml(enabled: bool, temperature: int) -> str:
    return (
        # REUSE-IgnoreStart
        "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n"
        # REUSE-IgnoreEnd
        f"[nightlight]\nenabled = {'true' if enabled else 'false'}\ntemperature = {temperature}\n"
    )


def render_storage_toml(low_disk: int) -> str:
    return (
        # REUSE-IgnoreStart
        "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n"
        # REUSE-IgnoreEnd
        f"[storage]\nlow_disk_percent = {low_disk}\n"
    )


def render_terminal_list(desktop_id: str) -> str:
    # REUSE-IgnoreStart
    hdr = "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings (xdg-terminals.list).\n"
    # REUSE-IgnoreEnd
    return f"{hdr}{desktop_id}\n"


# -- user unit: keep running when the lid is closed (no root) --------------------------------------
LID_UNIT = "seclegion-lid-inhibit.service"
LID_UNIT_FILE = "~/.config/systemd/user/" + LID_UNIT


def render_lid_inhibit_unit() -> str:
    return (
        # REUSE-IgnoreStart
        "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings (power.lid_ignore).\n"
        # REUSE-IgnoreEnd
        "[Unit]\nDescription=SecLegion: keep running when the lid is closed\n\n"
        "[Service]\nExecStart=/usr/bin/systemd-inhibit --what=handle-lid-switch --who=SecLegion "
        '--why="Lid close ignored (SecLegion Settings)" --mode=block sleep infinity\n\n'
        "[Install]\nWantedBy=default.target\n"
    )


# -- input: a Lua file seclegion-host.lua loads with pcall(dofile); read at the next reload --------
INPUT_FILE = "~/.config/seclegion/input.lua"
INPUT_DEFAULTS = {
    "repeat_rate": 25,
    "repeat_delay": 600,
    "tap_to_click": True,
    "natural_scroll": False,
    "disable_while_typing": True,
}


def render_input_lua(v: dict) -> str:
    """The whole file from five typed values (ints and bools only, so nothing needs quoting)."""

    def b(x: bool) -> str:
        return "true" if x else "false"

    return (
        # REUSE-IgnoreStart
        "-- SPDX-License-Identifier: MIT\n"
        # REUSE-IgnoreEnd
        "-- Written by SecLegion Settings (Input page). Loaded by seclegion-host.lua at the next reload.\n"
        "hl.config({\n    input = {\n"
        f"        repeat_rate = {int(v['repeat_rate'])},\n"
        f"        repeat_delay = {int(v['repeat_delay'])},\n"
        "        touchpad = {\n"
        f"            tap_to_click = {b(v['tap_to_click'])},\n"
        f"            natural_scroll = {b(v['natural_scroll'])},\n"
        f"            disable_while_typing = {b(v['disable_while_typing'])},\n"
        "        },\n    },\n})\n"
    )


# -- region ----------------------------------------------------------------------------------------
CLOCK_FORMATS = ("12h", "24h")
TZ_RE = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+){0,2}$")
LOCALTIME_FILE = "/etc/localtime"


def render_clock_toml(fmt: str) -> str:
    # REUSE-IgnoreStart
    return f'# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n[clock]\nformat = "{fmt}"\n'
    # REUSE-IgnoreEnd


# -- troubleshoot: redact before anything leaves the app ---------------------------------------------
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_IPV6 = re.compile(
    r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){4,7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5})?::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5})?)(?![\w:])"
)
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def redact(text: str, *, home: str, user: str = "", host: str = "") -> str:
    """Hide the home path, user name, host name, MAC and IP addresses."""
    if home and home != "/":
        text = text.replace(home, "~")
    text = _MAC.sub("<mac>", text)
    text = _IPV6.sub("<ip>", text)
    text = _IPV4.sub("<ip>", text)
    for word, tag in ((user, "<user>"), (host, "<host>")):
        if len(word) >= 2:
            text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", tag, text)
    return text
