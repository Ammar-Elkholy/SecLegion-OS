# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Live reload hooks. Run after the symlink swap, in parallel, 2 s budget each.

A hook never raises and never fails the apply: the result is a status that the
CLI logs. A target that is not running is "skipped" (logged at -v, silent
otherwise). Everything is argv lists or signals; no shell, no eval.

Signals go only to a pid that passes every check in `_is_target()`: same uid,
expected comm, /proc/<pid>/exe basename exactly the program, and the same
WAYLAND_DISPLAY as this run (so another session's kitty is never touched).
Without WAYLAND_DISPLAY no signal is sent; without HYPRLAND_INSTANCE_SIGNATURE
no hyprctl runs, and the border is reloaded only if the border component is applied. swayosd is restarted
only through its systemd user unit; this module never starts a process that outlives the run.

The wallpaper hook runs seclegion-wallpaper (seclegion-desktop's display component), which paints
the theme's wallpaper on every output through awww; an auto sync skips it, because the wallpaper
tool that changed ~/.cache/current_wallpaper has painted it already.

UNVERIFIED on a real session: `hyprctl reload` re-evaluating seclegion-host.lua,
the swayosd unit restart, waybar SIGUSR2 style reload, swaync-client --reload-css.
kitty reloads its config on SIGUSR1; remote control is never enabled.
"""

from __future__ import annotations

import concurrent.futures as cf
import contextlib
import hashlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT_S = 2.0


@dataclass
class HookResult:
    name: str
    status: str  # ok | skipped | kept | failed | timeout
    detail: str = ""


@dataclass
class Ctx:
    active_border: str  # rgba(rrggbbaa), already validated by the renderer
    inactive_border: str
    env: dict
    pids: dict[str, list[int]]
    runner: Callable = subprocess.run
    kill: Callable = os.kill
    which: Callable = shutil.which
    timeout: float = TIMEOUT_S
    proc_root: str = "/proc"
    uid: int = field(default_factory=os.getuid)
    theme_dir: Path | None = None  # the <hash>/ dir just written (yazi hook source)
    wallpaper: Path | None = None  # the theme's wallpaper, painted by hook_wallpaper
    paint_wallpaper: bool = True  # False for an auto sync (see the module docstring)


WATCHED = ("waybar", "kitty", "swayosd-server", "swaync")


def running_pids(names=WATCHED, proc_root: str = "/proc", uid: int | None = None) -> dict[str, list[int]]:
    """Own-user pids by process name, from /proc/*/comm (no pgrep fork)."""
    uid = os.getuid() if uid is None else uid
    found: dict[str, list[int]] = {n: [] for n in names}
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return found
    for ent in entries:
        if not ent.isdigit():
            continue
        base = os.path.join(proc_root, ent)
        try:
            if os.stat(base).st_uid != uid:
                continue
            comm = Path(base, "comm").read_text().strip()
        except OSError:
            continue
        if comm in found:
            found[comm].append(int(ent))
    return found


def _run(ctx: Ctx, argv: list[str], name: str, **kw) -> HookResult:
    try:
        p = ctx.runner(argv, capture_output=True, text=True, timeout=ctx.timeout, check=False, **kw)
    except subprocess.TimeoutExpired:
        return HookResult(name, "timeout", f"{argv[0]} > {ctx.timeout}s")
    except OSError as e:
        return HookResult(name, "failed", str(e))
    if p.returncode != 0:
        return HookResult(name, "failed", (p.stderr or "").strip()[:200] or f"exit {p.returncode}")
    return HookResult(name, "ok")


def _environ_var(path: str, key: str) -> bytes | None:
    with open(path, "rb") as fh:
        for item in fh.read().split(b"\0"):
            k, sep, v = item.partition(b"=")
            if sep and k == key.encode():
                return v
    return None


def _is_target(ctx: Ctx, pid: int, proc: str, wayland_display: str) -> bool:
    """True only if pid is our user's `proc` binary in our Wayland session.
    Re-checked right before signalling, so a recycled pid is not hit."""
    base = os.path.join(ctx.proc_root, str(pid))
    try:
        if os.stat(base).st_uid != ctx.uid:
            return False
        if Path(base, "comm").read_text().strip() != proc:
            return False
        if os.path.basename(os.readlink(os.path.join(base, "exe"))) != proc:
            return False
        return _environ_var(os.path.join(base, "environ"), "WAYLAND_DISPLAY") == os.fsencode(wayland_display)
    except (OSError, UnicodeDecodeError):
        return False


def _signal(ctx: Ctx, name: str, proc: str, sig: int) -> HookResult:
    wd = ctx.env.get("WAYLAND_DISPLAY")
    if not wd:
        return HookResult(name, "skipped", f"WAYLAND_DISPLAY unset; not signalling {proc}")
    pids = ctx.pids.get(proc, [])
    if not pids:
        return HookResult(name, "skipped", f"{proc} not running")
    targets = [p for p in pids if _is_target(ctx, p, proc, wd)]
    if not targets:
        return HookResult(name, "skipped", f"no {proc} of this user on {wd}")
    sent = 0
    for pid in targets:
        try:
            ctx.kill(pid, sig)
            sent += 1
        except OSError:
            pass
    return HookResult(name, "ok" if sent else "failed", f"signalled {sent}/{len(targets)}")


def _config_home(env: dict) -> Path | None:
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"])
    if env.get("HOME"):
        return Path(env["HOME"]) / ".config"
    return None


def hook_hyprland(ctx: Ctx) -> HookResult:
    """`hyprctl reload`: re-evaluates ~/.config/hypr/seclegion-host.lua (the
    border component), which reads the new hyprland-colors.lua. Only the
    border component's own file is a reason to reload the owner's compositor."""
    if not ctx.env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return HookResult("hyprland", "skipped", "HYPRLAND_INSTANCE_SIGNATURE unset; not running hyprctl")
    cfg = _config_home(ctx.env)
    if cfg is None or not (cfg / "hypr" / "seclegion-host.lua").is_file():
        return HookResult("hyprland", "skipped", "border component not applied (no hypr/seclegion-host.lua)")
    exe = ctx.which("hyprctl")
    if not exe:
        return HookResult("hyprland", "skipped", "hyprctl not found")
    return _run(ctx, [exe, "reload"], "hyprland")


def hook_waybar(ctx: Ctx) -> HookResult:
    return _signal(ctx, "waybar", "waybar", signal.SIGUSR2)


def hook_kitty(ctx: Ctx) -> HookResult:
    return _signal(ctx, "kitty", "kitty", signal.SIGUSR1)


def hook_swaync(ctx: Ctx) -> HookResult:
    if not ctx.pids.get("swaync"):
        return HookResult("swaync", "skipped", "swaync not running")
    exe = ctx.which("swaync-client")
    if not exe:
        return HookResult("swaync", "skipped", "swaync-client not found")
    return _run(ctx, [exe, "--reload-css"], "swaync")


# seclegion-wallpaper, packaged, then as `seclegion-host apply display` installs it
WALLPAPER_HELPERS = ("/usr/share/seclegion/display/seclegion-wallpaper",
                     ".local/share/seclegion/host/display/seclegion-wallpaper")


def hook_wallpaper(ctx: Ctx) -> HookResult:
    """Paint the theme's wallpaper on every output (owner issue 16). SL_WALLPAPER (split like a
    shell) replaces the helper lookup for tests."""
    if not ctx.paint_wallpaper:
        return HookResult("wallpaper", "skipped", "auto sync: the wallpaper tool painted it")
    if not ctx.env.get("WAYLAND_DISPLAY"):
        return HookResult("wallpaper", "skipped", "WAYLAND_DISPLAY unset; not painting")
    if ctx.env.get("SL_WALLPAPER"):
        cmd = shlex.split(ctx.env["SL_WALLPAPER"])
    else:
        home = ctx.env.get("HOME")
        paths = [h for h in WALLPAPER_HELPERS if h.startswith("/")]
        paths += [os.path.join(home, h) for h in WALLPAPER_HELPERS if home and not h.startswith("/")]
        found = [p for p in paths if os.path.isfile(p)]
        if not found:
            return HookResult("wallpaper", "skipped", "seclegion-wallpaper not installed")
        cmd = [sys.executable, "-I", found[0]]
    extra = ["--image", str(ctx.wallpaper)] if ctx.wallpaper else []
    return _run(ctx, [*cmd, "--tries", "3", *extra], "wallpaper", env=ctx.env)


_UNIT_RE = re.compile(r"swayosd[A-Za-z0-9@._:-]*\.service")


def _active_swayosd_unit(ctx: Ctx, exe: str) -> str | None:
    def run(*args: str):
        try:
            return ctx.runner(
                [exe, "--user", *args], capture_output=True, text=True, timeout=ctx.timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    p = run("is-active", "swayosd.service")
    if p is not None and p.returncode == 0 and p.stdout.strip() == "active":
        return "swayosd.service"
    p = run("list-units", "--plain", "--no-legend", "--state=active", "swayosd*")
    if p is None or p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        unit = line.split(None, 1)[0] if line.strip() else ""
        if _UNIT_RE.fullmatch(unit):
            return unit
    return None


def hook_swayosd(ctx: Ctx) -> HookResult:
    """Restart swayosd's systemd user unit so it re-reads its stylesheet.
    A swayosd-server started any other way is left alone."""
    if not ctx.pids.get("swayosd-server"):
        return HookResult("swayosd", "skipped", "swayosd-server not running")
    exe = ctx.which("systemctl")
    unit = _active_swayosd_unit(ctx, exe) if exe else None
    if not unit:
        return HookResult("swayosd", "skipped", "swayosd: restart manually to restyle")
    res = _run(ctx, [exe, "--user", "restart", unit], "swayosd")
    if res.status == "ok":
        res.detail = f"restarted {unit}"
    return res


YAZI_MARKER = "# generated by seclegion-theme"  # == render.YAZI_MARKER (no import: hooks stay render-free)


def _yazi_config_dir(env: dict) -> Path | None:
    """yazi's own lookup: $YAZI_CONFIG_HOME, else $XDG_CONFIG_HOME/yazi, else ~/.config/yazi."""
    if env.get("YAZI_CONFIG_HOME"):
        return Path(env["YAZI_CONFIG_HOME"])
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"]) / "yazi"
    if env.get("HOME"):
        return Path(env["HOME"]) / ".config" / "yazi"
    return None


def _first_line(path: Path) -> str:
    with open(path, "rb") as fh:
        return fh.read(256).split(b"\n", 1)[0].rstrip(b"\r").decode("utf-8", "replace")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    """Exclusive, no-follow temp file in the same dir, fsync, os.replace, then a
    best-effort fsync of the directory."""
    tmp = path.with_name(f".{path.name}.seclegion-{os.getpid()}")
    try:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)  # a stale temp, or a planted symlink: unlink removes the link, never follows it
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    with contextlib.suppress(OSError):
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def hook_yazi(ctx: Ctx) -> HookResult:
    """Copy yazi-theme.toml to <yazi config>/theme.toml.
    - absent: created.
    - first line is the marker: ours, replaced. If it changed since we last wrote
      it (sidecar theme.toml.seclegion-sha256), the edited file is first copied to
      theme.toml.seclegion-bak (status ok-backed-up).
    - no marker, regular file, no theme.toml.seclegion-orig: moved to
      theme.toml.seclegion-orig and ours written (status adopted); an old hand-made
      file is usually dead config under yazi 26.x anyway.
    - no marker and .seclegion-orig exists, a symlink target, or a symlinked config
      dir: left alone (kept). Writes are atomic and keep the old file's mode."""
    if ctx.theme_dir is None:
        return HookResult("yazi", "skipped", "no theme dir")
    cfg = _yazi_config_dir(ctx.env)
    if cfg is None:
        return HookResult("yazi", "skipped", "HOME unset")
    if cfg.is_symlink():
        return HookResult("yazi", "kept", "config dir is a symlink")
    if not cfg.is_dir() and not ctx.which("yazi"):
        return HookResult("yazi", "skipped", "yazi not installed")
    target = cfg / "theme.toml"
    orig = cfg / "theme.toml.seclegion-orig"
    bak = cfg / "theme.toml.seclegion-bak"
    side = cfg / "theme.toml.seclegion-sha256"
    if target.is_symlink():
        return HookResult("yazi", "kept", f"{target} is a symlink; not replaced")
    status, note, mode = "ok", f"wrote {target}", 0o644
    try:
        text = (ctx.theme_dir / "yazi-theme.toml").read_bytes()
        if target.exists():
            if not target.is_file():
                return HookResult("yazi", "kept", f"{target} is not a regular file; not replaced")
            mode = target.stat().st_mode & 0o7777
            if _first_line(target) == YAZI_MARKER:
                if (
                    side.is_file()
                    and not side.is_symlink()
                    and side.read_text().strip() != _sha256_file(target)
                ):
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(bak)
                    _atomic_write(bak, target.read_bytes(), mode)
                    status, note = "ok-backed-up", f"wrote {target}; your edits are saved in {bak}"
            elif os.path.lexists(orig):
                return HookResult("yazi", "kept", f"{target} is hand-edited; not overwritten")
            else:
                os.rename(target, orig)
                status, note = "adopted", f"moved your {target} to {orig}; restore with: mv {orig} {target}"
        cfg.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, text, mode)
        _atomic_write(side, hashlib.sha256(text).hexdigest().encode() + b"\n", 0o644)
    except OSError as e:
        return HookResult("yazi", "failed", str(e))
    return HookResult("yazi", status, note)


HOOKS = (hook_hyprland, hook_waybar, hook_swaync, hook_kitty, hook_swayosd, hook_yazi, hook_wallpaper)


def run_hooks(ctx: Ctx, hooks=HOOKS) -> list[HookResult]:
    """Run every hook in parallel; none can raise out of here."""
    results: list[HookResult] = []
    ex = cf.ThreadPoolExecutor(max_workers=len(hooks))
    futs = {ex.submit(h, ctx): h.__name__.removeprefix("hook_") for h in hooks}
    done, pending = cf.wait(futs, timeout=ctx.timeout + 0.5)
    for f in done:
        name = futs[f]
        try:
            results.append(f.result())
        except Exception as e:  # a hook bug must never fail the swap
            results.append(HookResult(name, "failed", f"{type(e).__name__}: {e}"))
    for f in pending:
        results.append(HookResult(futs[f], "timeout", "hook exceeded budget"))
    ex.shutdown(wait=False, cancel_futures=True)
    return sorted(results, key=lambda r: r.name)
