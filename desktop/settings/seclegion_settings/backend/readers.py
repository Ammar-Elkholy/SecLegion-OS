# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Readers: parse files or run read-only commands. `reader(ctx) -> value`.

A reader never writes. When the value cannot be read it raises ReadError; the registry turns that
into `value=None` plus the message, so a flaky tool never takes `list` down.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

from .. import __version__
from . import capabilities as cap
from . import render
from .env import Ctx


class ReadError(Exception):
    pass


def _cmd(ctx: Ctx, cmd: list[str]) -> str:
    p = ctx.run(cmd)
    if not p.ok:
        raise ReadError((p.err or p.out).strip() or f"{cmd[0]} exited {p.rc}")
    return p.out


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _toml(path: Path) -> dict:
    t = _text(path)
    if t is None:
        return {}
    try:
        return tomllib.loads(t)
    except tomllib.TOMLDecodeError:
        return {}


# -- power ---------------------------------------------------------------------------------------
def power_profile(ctx: Ctx) -> str:
    return _cmd(ctx, ["powerprofilesctl", "get"]).strip()


def battery_status(ctx: Ctx) -> str:
    dev = None
    p = ctx.run(["upower", "-e"])
    if p.ok:
        dev = next((ln.strip() for ln in p.out.splitlines() if "battery" in ln), None)
    if dev:
        q = ctx.run(["upower", "-i", dev])
        if q.ok:
            kv = {}
            for ln in q.out.splitlines():
                k, sep, v = ln.partition(":")
                if sep:
                    kv.setdefault(k.strip(), v.strip())
            state = kv.get("state", "unknown").capitalize()
            pct = kv.get("percentage", "?")
            eta = kv.get("time to empty") or kv.get("time to full")
            return f"{state}, {pct}" + (f" ({eta})" if eta else "")
    bats = cap.batteries(ctx)  # upower missing or failing: fall back to sysfs
    if not bats:
        raise ReadError("no battery")
    b = bats[0]
    state = (_text(b / "status") or "unknown").strip().capitalize()
    return f"{state}, {(_text(b / 'capacity') or '?').strip()}%"


def _battery_cfg(ctx: Ctx) -> dict:
    return _toml(ctx.config_dir / "battery.toml").get("alerts", {})


def alert_low(ctx: Ctx) -> int:
    v = _battery_cfg(ctx).get("low")
    return v if isinstance(v, int) else 15


def alert_critical(ctx: Ctx) -> int:
    v = _battery_cfg(ctx).get("critical")
    return v if isinstance(v, int) else 7


def _logind(ctx: Ctx, fname: str) -> dict:
    t = _text(ctx.etc / "systemd" / "logind.conf.d" / fname) or ""
    kv = {}
    for ln in t.splitlines():
        k, sep, v = ln.partition("=")
        if sep and not ln.lstrip().startswith("#"):
            kv[k.strip()] = v.strip()
    return kv


def lid_values(ctx: Ctx) -> tuple[str, str, str]:
    """(battery, ac, docked) as configured, else the systemd defaults."""
    kv = _logind(ctx, "50-seclegion-lid.conf")
    bat = kv.get("HandleLidSwitch", "suspend")
    return bat, kv.get("HandleLidSwitchExternalPower", bat), kv.get("HandleLidSwitchDocked", "ignore")


def lid_battery(ctx: Ctx) -> str:
    return lid_values(ctx)[0]


def lid_ac(ctx: Ctx) -> str:
    return lid_values(ctx)[1]


def lid_docked(ctx: Ctx) -> str:
    return lid_values(ctx)[2]


def lid_ignore(ctx: Ctx) -> bool:
    """On when the user unit is enabled and running (a live handle-lid-switch inhibitor)."""
    en = ctx.run(["systemctl", "--user", "is-enabled", render.LID_UNIT])
    if en.rc in (124, 126, 127):
        raise ReadError((en.err or en.out).strip() or "systemctl unavailable")
    return en.ok and ctx.run(["systemctl", "--user", "is-active", render.LID_UNIT]).ok


def power_button(ctx: Ctx) -> str:
    return _logind(ctx, "50-seclegion-power.conf").get("HandlePowerKey", "poweroff")


def charge_limit_file(ctx: Ctx) -> Path | None:
    for b in cap.batteries(ctx):
        f = b / "charge_control_end_threshold"
        if f.exists():
            return f
    return None


def charge_limit(ctx: Ctx) -> int:
    f = charge_limit_file(ctx)
    if f is None:
        raise ReadError("no charge threshold file")
    try:
        return int((_text(f) or "").strip())
    except ValueError as e:
        raise ReadError(f"unreadable {f.name}") from e


def conservation_mode(ctx: Ctx) -> bool:
    f = cap.conservation_file(ctx)
    if f is None:
        raise ReadError("no conservation_mode file")
    v = (_text(f) or "").strip()
    if v not in ("0", "1"):
        raise ReadError(f"unreadable {f.name}")
    return v == "1"


def suspend_mode(ctx: Ctx) -> str:
    _, sel = cap.mem_sleep_modes(ctx)
    if sel is None:
        raise ReadError("no mem_sleep selection")
    return sel


# -- sleep / lock / idle -------------------------------------------------------------------------
def idle_state(ctx: Ctx) -> render.IdleState:
    t = _text(ctx.config_dir / "idle.conf")
    return (render.parse_idle_state(t) if t else None) or render.IdleState()


def _m(v: int | None) -> str:
    return "never" if v is None else str(v)


def idle_lock(ctx: Ctx) -> str:
    return _m(idle_state(ctx).lock)


def idle_screen_off(ctx: Ctx) -> str:
    return _m(idle_state(ctx).screen_off)


def idle_suspend_battery(ctx: Ctx) -> str:
    return _m(idle_state(ctx).suspend_battery)


def idle_suspend_ac(ctx: Ctx) -> str:
    return _m(idle_state(ctx).suspend_ac)


def idle_lock_before_sleep(ctx: Ctx) -> bool:
    return idle_state(ctx).lock_before_sleep


# -- display -------------------------------------------------------------------------------------
def _pct(line: str) -> int:
    # brightnessctl -m: name,class,current,percent%,max
    try:
        return int(line.strip().split(",")[3].rstrip("%"))
    except (IndexError, ValueError) as e:
        raise ReadError(f"unexpected brightnessctl output: {line.strip()!r}") from e


def brightness(ctx: Ctx) -> int:
    return _pct(_cmd(ctx, ["brightnessctl", "-m", "-c", "backlight"]))


def kbd_brightness(ctx: Ctx) -> int:
    dev = cap.kbd_backlight_device(ctx)
    if dev is None:
        raise ReadError("no keyboard backlight")
    return _pct(_cmd(ctx, ["brightnessctl", "-m", "-d", dev]))


def _nl(ctx: Ctx) -> dict:
    return _toml(ctx.config_dir / "nightlight.toml").get("nightlight", {})


def nightlight(ctx: Ctx) -> bool:
    return _nl(ctx).get("enabled") is True


def nightlight_temp(ctx: Ctx) -> int:
    v = _nl(ctx).get("temperature")
    return v if isinstance(v, int) and 3500 <= v <= 6500 else 4500


# The display menu's split (desktop/display/seclegion-display-menu); a test keeps these equal.
INTERNAL_PREFIXES = ("eDP", "LVDS", "DSI")
FALLBACK = "FALLBACK"  # the monitor Hyprland adds when every output is disabled


def monitors(ctx: Ctx) -> list[dict]:
    """The connected outputs from one `hyprctl -j monitors all` (disabled ones included)."""
    try:
        ms = json.loads(_cmd(ctx, ["hyprctl", "-j", "monitors", "all"]))
    except json.JSONDecodeError as e:
        raise ReadError("unexpected hyprctl output") from e
    if not isinstance(ms, list):
        raise ReadError("unexpected hyprctl output")
    return [m for m in ms if isinstance(m, dict) and m.get("name") and m["name"] != FALLBACK]


def split_monitors(ctx: Ctx, ms: list[dict]) -> tuple[dict | None, list[dict]]:
    """(the laptop screen or None, [the other outputs]), as the display menu splits them."""
    internal = ctx.environ.get("SL_DISPLAY_INTERNAL") or next(
        (m["name"] for m in ms if m["name"].startswith(INTERNAL_PREFIXES)), None
    )
    inner = next((m for m in ms if m["name"] == internal), None)
    return inner, [m for m in ms if m is not inner]


def _mirroring(m: dict) -> bool:
    return str(m.get("mirrorOf", "none")) != "none"


def display_layout(ctx: Ctx) -> str:
    """laptop, extend, mirror or external: what the outputs show now. One output is laptop."""
    ms = monitors(ctx)
    if len(ms) < 2:
        return "laptop"
    inner, ext = split_monitors(ctx, ms)
    if inner is None:
        raise ReadError("no laptop screen found")
    on = [m for m in ext if not m.get("disabled")]
    if inner.get("disabled"):
        return "external"
    if not on:
        return "laptop"
    return "mirror" if all(_mirroring(m) for m in on) else "extend"


def _output_line(m: dict) -> str:
    w, h, rate = m.get("width"), m.get("height"), m.get("refreshRate")
    if not (w and h):
        return f"{m['name']}: off" if m.get("disabled") else f"{m['name']}: no mode"
    hz = f"@{rate:.2f}".rstrip("0").rstrip(".") + "Hz" if isinstance(rate, int | float) and rate else ""
    scale = m.get("scale") if isinstance(m.get("scale"), int | float) else 1
    return f"{m['name']}: {w}x{h}{hz}, scale {scale:g}" + (", off" if m.get("disabled") else "")


def display_outputs(ctx: Ctx) -> str:
    """One line per connected output: name, resolution@refresh, scale, and off when disabled."""
    ms = monitors(ctx)
    if not ms:
        raise ReadError("no display is connected")
    return "\n".join(_output_line(m) for m in ms)


# -- sound ---------------------------------------------------------------------------------------
_VOL = re.compile(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?")


def _wp(ctx: Ctx, target: str) -> tuple[int, bool]:
    m = _VOL.search(_cmd(ctx, ["wpctl", "get-volume", target]))
    if not m:
        raise ReadError("unexpected wpctl output")
    return round(float(m.group(1)) * 100), m.group(2) is not None


def volume(ctx: Ctx) -> int:
    return _wp(ctx, "@DEFAULT_AUDIO_SINK@")[0]


def mute(ctx: Ctx) -> bool:
    return _wp(ctx, "@DEFAULT_AUDIO_SINK@")[1]


def mic_mute(ctx: Ctx) -> bool:
    return _wp(ctx, "@DEFAULT_AUDIO_SOURCE@")[1]


# -- network -------------------------------------------------------------------------------------
def wifi(ctx: Ctx) -> bool:
    return _cmd(ctx, ["nmcli", "radio", "wifi"]).strip() == "enabled"


def airplane(ctx: Ctx) -> bool:
    states = _cmd(ctx, ["rfkill", "-n", "-o", "SOFT", "list"]).split()
    return bool(states) and all(s == "blocked" for s in states)


def bluetooth(ctx: Ctx) -> bool:
    for ln in _cmd(ctx, ["bluetoothctl", "show"]).splitlines():
        k, _, v = ln.strip().partition(":")
        if k == "Powered":
            return v.strip() == "yes"
    raise ReadError("no Bluetooth controller")


# -- notifications -------------------------------------------------------------------------------
def dnd(ctx: Ctx) -> bool:
    return _cmd(ctx, ["swaync-client", "-D"]).strip() == "true"


# -- apps ----------------------------------------------------------------------------------------
def file_manager(ctx: Ctx) -> str:
    return _cmd(ctx, ["xdg-mime", "query", "default", "inode/directory"]).strip()


def browser(ctx: Ctx) -> str:
    return _cmd(ctx, ["xdg-settings", "get", "default-web-browser"]).strip()


def terminal(ctx: Ctx) -> str:
    t = _text(ctx.home / ".config" / "xdg-terminals.list") or ""
    for ln in t.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            return ln
    return ""


# -- autolock (through seclegion-autolock only) -------------------------------------------------
def autolock(ctx: Ctx) -> str:
    exe = cap.find_autolock_cli(ctx)
    if exe is None:
        raise ReadError("seclegion-autolock is not installed")
    lines = _cmd(ctx, [exe, "status"]).split()
    return lines[0] if lines else "default"


# -- appearance (through seclegion-theme only) ---------------------------------------------------
def theme_current(ctx: Ctx) -> dict:
    exe = cap.find_theme_cli(ctx)
    if exe is None:
        raise ReadError("seclegion-theme is not installed")
    p = ctx.run([exe, "current", "--json"])
    if not p.ok:
        if p.rc == 1:  # "no theme applied yet"
            return {}
        raise ReadError((p.err or p.out).strip() or "seclegion-theme failed")
    try:
        d = json.loads(p.out)
    except ValueError as e:
        raise ReadError("seclegion-theme returned invalid JSON") from e
    return d if isinstance(d, dict) else {}


def theme_list(ctx: Ctx) -> list[dict]:
    """The themes `seclegion-theme list --json` offers: {id,label,accent,bg,surface,text,current}."""
    exe = cap.find_theme_cli(ctx)
    if exe is None:
        raise ReadError("seclegion-theme is not installed")
    p = ctx.run([exe, "list", "--json"])
    if not p.ok:
        raise ReadError((p.err or p.out).strip() or "seclegion-theme failed")
    try:
        d = json.loads(p.out)
    except ValueError as e:
        raise ReadError("seclegion-theme returned invalid JSON") from e
    if not isinstance(d, list):
        raise ReadError("seclegion-theme returned an unexpected list")
    return [t for t in d if isinstance(t, dict) and isinstance(t.get("id"), str)]


def theme_id(ctx: Ctx) -> str:
    """The listed theme that is active; empty for a hand-picked accent."""
    return next((t["id"] for t in theme_list(ctx) if t.get("current")), "")


def theme_auto(ctx: Ctx) -> bool:
    exe = cap.find_theme_cli(ctx)
    if exe is None:
        raise ReadError("seclegion-theme is not installed")
    return _cmd(ctx, [exe, "auto", "status"]).strip() == "on"


def theme_reset(ctx: Ctx) -> str:
    return "run"  # an action row: nothing to read


def theme_mode(ctx: Ctx) -> str:
    d = theme_current(ctx)
    return d.get("requested_mode") or d.get("mode") or "default"


def theme_contrast(ctx: Ctx) -> str:
    return theme_current(ctx).get("contrast") or "normal"


# -- bluetooth -----------------------------------------------------------------------------------
def bluetooth_paired(ctx: Ctx) -> str:
    p = ctx.run(["bluetoothctl", "devices", "Paired"])
    if not p.ok:  # older bluez
        p = ctx.run(["bluetoothctl", "paired-devices"])
    if not p.ok:
        raise ReadError((p.err or p.out).strip() or "bluetoothctl failed")
    names = []
    for ln in p.out.splitlines():
        parts = ln.split(None, 2)  # "Device AA:BB:CC:DD:EE:FF Name"
        if len(parts) == 3 and parts[0] == "Device":
            names.append(parts[2].strip())
    return ", ".join(names) if names else "none paired"


def action_idle(ctx: Ctx) -> str:
    return "run"  # an action row: nothing to read


# -- storage -------------------------------------------------------------------------------------
_PSEUDO_FS = ("tmpfs", "devtmpfs", "squashfs", "efivarfs", "overlay", "ramfs")


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def storage_mounts(ctx: Ctx) -> str:
    cmd = ["df", "-P", "-k"] + [a for fs in _PSEUDO_FS for a in ("-x", fs)]
    out = _cmd(ctx, cmd)
    parts = []
    for ln in out.splitlines()[1:]:
        f = ln.split(None, 5)
        if len(f) == 6 and f[1].isdigit():
            parts.append(f"{f[5]} {f[4]} of {_human(int(f[1]) * 1024)}")
    if not parts:
        raise ReadError("df listed no mounted disks")
    return "; ".join(parts)


def trash_size(ctx: Ctx) -> str:
    root = ctx.home / ".local" / "share" / "Trash" / "files"
    total, entries = 0, 0
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        entries += len(dirs) + len(files)
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return _human(total) if entries else "empty"


def low_disk(ctx: Ctx) -> int:
    v = _toml(ctx.config_dir / "storage.toml").get("storage", {}).get("low_disk_percent")
    return v if isinstance(v, int) and not isinstance(v, bool) and 70 <= v <= 95 else 90


# -- updates -------------------------------------------------------------------------------------
CHECKUPDATES_TIMEOUT_S = 10.0


def updates_pending(ctx: Ctx) -> str:
    p = ctx.run(["checkupdates"], timeout=CHECKUPDATES_TIMEOUT_S)
    if p.rc == 2:  # checkupdates: 2 means nothing to update
        return "up to date"
    if not p.ok:
        raise ReadError((p.err or p.out).strip() or f"checkupdates exited {p.rc}")
    n = sum(1 for ln in p.out.splitlines() if ln.strip())
    return f"{n} pending" if n else "up to date"


_UPGRADE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})[^\]]*\] \[PACMAN\] starting full system upgrade"
)


def updates_last(ctx: Ctx) -> str:
    try:
        with open(ctx.pacman_log, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 512 * 1024))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        raise ReadError("pacman.log is not readable") from None
    for ln in reversed(tail.splitlines()):
        m = _UPGRADE.match(ln)
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return "no full upgrade in the log"


def snapshot_keep(ctx: Ctx) -> int:
    m = re.search(
        r'^NUMBER_LIMIT="?(?:\d+-)?(\d+)"?\s*$', _text(ctx.etc / "snapper" / "configs" / "root") or "", re.M
    )
    v = int(m.group(1)) if m else 10
    return v if 1 <= v <= 50 else 10


# -- about ---------------------------------------------------------------------------------------
def kernel(ctx: Ctx) -> str:
    return os.uname().release


def hostname(ctx: Ctx) -> str:
    return os.uname().nodename


def uptime(ctx: Ctx) -> str:
    t = _text(Path("/proc/uptime"))
    if not t:
        raise ReadError("no /proc/uptime")
    secs = int(float(t.split()[0]))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return (f"{d}d " if d else "") + f"{h}h {m}m"


def cpu(ctx: Ctx) -> str:
    for ln in (_text(Path("/proc/cpuinfo")) or "").splitlines():
        if ln.startswith("model name"):
            return ln.partition(":")[2].strip()
    raise ReadError("no CPU model")


def ram(ctx: Ctx) -> str:
    for ln in (_text(Path("/proc/meminfo")) or "").splitlines():
        if ln.startswith("MemTotal:"):
            return f"{int(ln.split()[1]) / 1048576:.1f} GiB"
    raise ReadError("no MemTotal")


def hyprland_version(ctx: Ctx) -> str:
    out = _cmd(ctx, ["hyprctl", "version"])
    m = re.search(r"Hyprland\s+(\S+)", out) or re.search(r"Tag:\s*(\S+)", out)
    if not m:
        raise ReadError("unexpected hyprctl output")
    return m.group(1)


def seclegion_version(ctx: Ctx) -> str:
    kv = {}
    for ln in (_text(Path("/etc/os-release")) or "").splitlines():
        k, sep, v = ln.partition("=")
        if sep:
            kv[k] = v.strip().strip('"')
    if "seclegion" in kv.get("ID", "").lower() or "seclegion" in kv.get("NAME", "").lower():
        v = kv.get("VERSION_ID") or kv.get("BUILD_ID")
        if v:
            return f"{v} (settings {__version__})"
    return f"settings {__version__} (not a SecLegion install)"


# -- input (~/.config/seclegion/input.lua, written by render_input_lua) ---------------------------
def input_values(ctx: Ctx) -> dict:
    """The five typed values in the file, a default for anything missing or malformed."""
    text = _text(ctx.config_dir / "input.lua") or ""
    out = dict(render.INPUT_DEFAULTS)
    for key, default in render.INPUT_DEFAULTS.items():
        m = re.search(rf"^\s*{key} = (\w+),\s*$", text, re.M)
        if not m:
            continue
        if isinstance(default, bool) and m.group(1) in ("true", "false"):
            out[key] = m.group(1) == "true"
        elif not isinstance(default, bool) and m.group(1).isdigit():
            out[key] = int(m.group(1))
    return out


def repeat_rate(ctx: Ctx) -> int:
    v = input_values(ctx)["repeat_rate"]
    return v if 10 <= v <= 80 else render.INPUT_DEFAULTS["repeat_rate"]


def repeat_delay(ctx: Ctx) -> int:
    v = input_values(ctx)["repeat_delay"]
    return v if 150 <= v <= 1000 else render.INPUT_DEFAULTS["repeat_delay"]


def tap_to_click(ctx: Ctx) -> bool:
    return input_values(ctx)["tap_to_click"]


def natural_scroll(ctx: Ctx) -> bool:
    return input_values(ctx)["natural_scroll"]


def disable_while_typing(ctx: Ctx) -> bool:
    return input_values(ctx)["disable_while_typing"]


# -- region --------------------------------------------------------------------------------------
def clock_format(ctx: Ctx) -> str:
    v = _toml(ctx.config_dir / "clock.toml").get("clock", {}).get("format")
    return v if v in render.CLOCK_FORMATS else "24h"


def locale(ctx: Ctx) -> str:
    for ln in (_text(ctx.etc / "locale.conf") or "").splitlines():
        k, sep, v = ln.partition("=")
        if sep and k.strip() == "LANG":
            return v.strip().strip('"') or "C"
    return ctx.environ.get("LANG") or "C"


def timezone(ctx: Ctx) -> str:
    try:
        target = os.readlink(ctx.etc / "localtime")
    except OSError:
        raise ReadError("/etc/localtime is not a symlink to a zoneinfo file") from None
    _, sep, tz = target.partition("zoneinfo/")
    if not sep or not tz:
        raise ReadError(f"/etc/localtime points at {target}, not into zoneinfo")
    return tz


# -- security ------------------------------------------------------------------------------------
MAX_PORTS_SHOWN = 20


def _ports_text(label: str, ports: set[int]) -> str:
    shown = sorted(ports)[:MAX_PORTS_SHOWN]
    more = f" and {len(ports) - len(shown)} more" if len(ports) > len(shown) else ""
    return f"{label}: {', '.join(map(str, shown))}{more}"


def listening_ports(ctx: Ctx) -> str:
    """TCP ports in LISTEN state from `ss -tln`, split by whether anything but this computer reaches them."""
    exposed: set[int] = set()
    local: set[int] = set()
    for ln in _cmd(ctx, ["ss", "-tln"]).splitlines():
        f = ln.split()
        if len(f) < 5 or f[0] != "LISTEN":
            continue
        addr, _, port = f[3].rpartition(":")
        if not port.isdigit():
            continue
        host = addr.strip("[]").split("%")[0]
        (local if host.startswith("127.") or host == "::1" else exposed).add(int(port))
    local -= exposed
    parts = [
        _ports_text(label, ports)
        for label, ports in (("open to the network", exposed), ("this computer only", local))
        if ports
    ]
    return "; ".join(parts) or "nothing is listening"


def _unit(ctx: Ctx, verb: str, unit: str) -> str:
    """`systemctl is-enabled|is-active UNIT` on the system manager: the state word, rc ignored."""
    return ctx.run(["systemctl", verb, unit]).out.strip() or "unknown"


def sshd_state(ctx: Ctx) -> str:
    enabled = _unit(ctx, "is-enabled", "sshd.service")
    if enabled != "enabled":
        return "off" if enabled in ("disabled", "unknown") else f"off ({enabled})"
    return "on, running" if _unit(ctx, "is-active", "sshd.service") == "active" else "on, not running"


def sshd_enabled(ctx: Ctx) -> bool:
    return _unit(ctx, "is-enabled", "sshd.service") == "enabled"


def firewall_enabled(ctx: Ctx) -> bool:
    """ufw's own switch (ENABLED= in ufw.conf, world-readable): `ufw disable` leaves the unit enabled."""
    m = re.search(r"^ENABLED=(\w+)", _text(ctx.etc / "ufw" / "ufw.conf") or "", re.M)
    if m:
        return m.group(1) == "yes"
    return _unit(ctx, "is-enabled", "ufw.service") == "enabled"


# -- users ---------------------------------------------------------------------------------------
def _login(ctx: Ctx) -> str:
    return ctx.environ.get("USER") or ctx.environ.get("LOGNAME") or ctx.home.name


def user_name(ctx: Ctx) -> str:
    login = _login(ctx)
    for ln in (_text(ctx.etc / "passwd") or "").splitlines():
        f = ln.split(":")
        if len(f) >= 5 and f[0] == login:
            full = f[4].split(",")[0].strip()
            return f"{full} ({login})" if full and full != login else login
    return login


def face(ctx: Ctx) -> str:
    p = ctx.home / ".face"
    try:
        size = p.stat().st_size
    except OSError:
        return "not set"
    return f"set ({_human(size)})"


def autologin(ctx: Ctx) -> str:
    """greetd's initial_session names the user it signs in without a password."""
    user = _toml(ctx.etc / "greetd" / "config.toml").get("initial_session", {}).get("user")
    return f"on for {user}" if isinstance(user, str) and user else "off"
