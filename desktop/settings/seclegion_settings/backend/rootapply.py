# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-root-apply: install ONE privileged setting, run as root by the owner (sudo).

    seclegion-root-apply [--dry-run] <setting-id> <value>

Only the privileged ids of the registry are accepted; the value is validated against the row, the
file text is re-rendered here with the backend's own renderer (never taken from a preview), and it
is written atomically to one of a few fixed /etc paths. Command rows (time zone, SSH server,
firewall) run fixed /usr/bin argvs from writers.root_commands, which checks the value first.
Commands run as argv lists, never a shell. Tests redirect everything with SL_ETC (the /etc root),
SL_ROOT_STATE (backup dir), SL_SYSFS and SL_ZONEINFO; then binaries are stubs found on PATH.
"""
from __future__ import annotations

import contextlib
import datetime
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from . import capabilities as cap
from . import registry, render, writers
from .env import CommandFailed, Ctx, Refused, SettingError, Unavailable

STATE_DIR = "/var/lib/seclegion/settings-backups"
ALLOWED = {s.id for s in registry.SETTINGS if s.privileged}
FIXED_PATHS = frozenset(writers.ROOT_FILES.values())


def _overridden(env: dict) -> bool:
    return bool(env.get("SL_ETC") or env.get("SL_ROOT_STATE"))


def _exe(env: dict, name: str) -> str | None:
    if _overridden(env):  # tests: stubs on PATH
        exe = shutil.which(os.path.basename(name), path=env.get("PATH", os.defpath))
        if exe and os.path.isabs(name) and os.path.realpath(exe) == os.path.realpath(name):
            return None  # an absolute command row never runs the real binary under a test override
        return exe
    return name if os.path.isabs(name) else "/usr/bin/" + name


def _run(env: dict, argv: list[str], required: bool = False) -> None:
    exe = _exe(env, argv[0])
    if exe is None:
        if required:
            raise Unavailable(f"{os.path.basename(argv[0])} is not available")
        print(f"seclegion-root-apply: {argv[0]} not found; skipped", file=sys.stderr)
        return
    subprocess.run([exe, *argv[1:]], check=True, stdin=subprocess.DEVNULL, env=env)


def run_commands(env: dict, argvs: list[list[str]], dry_run: bool) -> None:
    for argv in argvs:
        print(f"{'would run' if dry_run else 'running'}: {' '.join(argv)}")
        if dry_run:
            continue
        try:
            _run(env, argv, required=True)
        except subprocess.CalledProcessError as e:  # the tool printed its own reason above
            raise CommandFailed(f"the system refused the change (exit {e.returncode})") from e


def target_for(env: dict, path: str) -> Path:
    if path not in FIXED_PATHS:
        raise Refused(f"refusing to write {path}: not one of the fixed SecLegion paths")
    etc = Path(env.get("SL_ETC") or "/etc")
    return etc / Path(path).relative_to("/etc")


def check_target(etc: Path, target: Path) -> None:
    if target.is_symlink():
        raise Refused(f"refusing to replace {target}: it is a symlink")
    want = os.path.join(os.path.realpath(etc), target.parent.relative_to(etc))
    if target.parent.exists() and os.path.realpath(target.parent) != want:
        raise Refused(f"refusing to write under {target.parent}: a path component is a symlink")


def atomic_write(target: Path, text: str, mode: int = 0o644) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def backup(env: dict, target: Path) -> Path | None:
    if not target.is_file():
        return None
    d = Path(env.get("SL_ROOT_STATE") or STATE_DIR)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    dst = d / f"{target.name}.{stamp}.bak"
    shutil.copy2(target, dst)
    os.chmod(dst, stat.S_IRUSR | stat.S_IWUSR)
    return dst


def apply(setting_id: str, raw: str, dry_run: bool, environ: dict) -> int:
    if setting_id not in ALLOWED:  # the allowlist: nothing else is ever rendered or written
        raise Refused(f"{setting_id!r} is not a privileged setting this tool may apply")
    if not dry_run and os.geteuid() != 0 and not _overridden(environ):
        raise Refused("run as root: sudo seclegion-root-apply <id> <value> (or use --dry-run)")
    s = registry.get(setting_id)
    ctx = Ctx(environ, dry_run=True)  # read-only context: used for validation and rendering
    c = cap.check(ctx, s.capability)
    if not c.ok:
        raise Unavailable(f"{s.id}: {c.reason}")
    value = s.coerce(raw)
    if s.id in writers.ROOT_COMMANDS:
        run_commands(environ, writers.root_commands(ctx, s.id, value), dry_run)
        if not dry_run:
            _run(environ, ["logger", "-t", "seclegion-root-apply", f"set {s.id}={raw}"])
        return 0
    path, text = writers.root_file(ctx, s.id, value, installed=True)
    target = target_for(environ, path)
    etc = Path(environ.get("SL_ETC") or "/etc")
    check_target(etc, target)
    print(f"{'would write' if dry_run else 'writing'} {target} ({s.id} = {raw}):\n{text}", end="")
    if dry_run:
        return 0
    keep_mode = path == render.SNAPPER_FILE and target.is_file()  # snapper's own file: keep its mode
    mode = stat.S_IMODE(target.stat().st_mode) if keep_mode else 0o644
    bak = backup(environ, target)
    atomic_write(target, text, mode)
    if bak:
        print(f"backup: {bak}")
    if path.startswith("/etc/systemd/logind.conf.d/"):
        _run(environ, ["systemctl", "kill", "-s", "HUP", "systemd-logind"])  # reload; never restart
    elif path.startswith("/etc/tmpfiles.d/"):
        _run(environ, ["systemd-tmpfiles", "--create", str(target)])
    _run(environ, ["logger", "-t", "seclegion-root-apply", f"set {s.id}={raw} in {target}"])
    return 0


def main(argv: list[str] | None = None, environ: dict | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    environ = dict(os.environ if environ is None else environ)
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) != 2:
        print("usage: seclegion-root-apply [--dry-run] <setting-id> <value>", file=sys.stderr)
        return 2
    try:
        return apply(args[0], args[1], dry, environ)
    except SettingError as e:
        print(f"seclegion-root-apply: {e}", file=sys.stderr)
        return e.code
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"seclegion-root-apply: {e}", file=sys.stderr)
        return 1
