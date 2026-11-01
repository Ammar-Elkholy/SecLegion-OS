# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Execution context: where HOME, sysfs and /etc are, how commands run, how files are written.

Everything the backend touches goes through a `Ctx`, so tests (and `--dry-run`) can redirect or
suppress it. `SL_HOME` replaces the user's home, `SL_SYSFS` replaces /sys and `SL_ETC` replaces
/etc (read-only previews). Writers never shell out directly: `Ctx.exec` records the command and,
under `dry_run`, skips it.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

CMD_TIMEOUT_S = 5.0


class SettingError(Exception):
    """Base class; `code` is the CLI exit status."""

    code = 1


class UnknownSetting(SettingError):
    code = 1


class InvalidValue(SettingError):
    code = 2


class Refused(SettingError):
    """Privileged or read-only: the backend will not write it."""

    code = 3


class AuthCancelled(Refused):
    """A privileged write: the administrator password prompt was dismissed (pkexec exit 126)."""


class NotAuthorized(Refused):
    """A privileged write: polkit refused it or could not ask (pkexec exit 127)."""


class Unavailable(SettingError):
    """Capability missing on this machine."""

    code = 4


class CommandFailed(SettingError):
    code = 5


@dataclass
class Proc:
    rc: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


@dataclass
class WriteResult:
    """Exactly what a write did (or, under dry_run, would do)."""

    files: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    applied_live: bool = False
    dry_run: bool = False
    # path -> exact text, filled for dry runs and privileged previews
    texts: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "files": list(self.files),
            "commands": [list(c) for c in self.commands],
            "applied_live": self.applied_live,
            "dry_run": self.dry_run,
            "texts": dict(self.texts),
            "notes": list(self.notes),
        }


class Ctx:
    def __init__(self, environ: dict | None = None, dry_run: bool = False):
        self.environ = dict(os.environ if environ is None else environ)
        self.dry_run = dry_run
        self.caps = None  # capabilities.detect() cache

    # -- locations ---------------------------------------------------------------------------
    @property
    def home(self) -> Path:
        h = self.environ.get("SL_HOME") or self.environ.get("HOME") or os.path.expanduser("~")
        return Path(h)

    @property
    def sysfs(self) -> Path:
        return Path(self.environ.get("SL_SYSFS") or "/sys")

    @property
    def etc(self) -> Path:
        return Path(self.environ.get("SL_ETC") or "/etc")

    @property
    def pacman_log(self) -> Path:
        return Path(self.environ.get("SL_PACMAN_LOG") or "/var/log/pacman.log")

    @property
    def config_dir(self) -> Path:
        return self.home / ".config" / "seclegion"

    def tilde(self, p: Path | str) -> str:
        s, h = str(p), str(self.home)
        return "~" + s[len(h):] if s.startswith(h + os.sep) else s

    # -- commands ----------------------------------------------------------------------------
    def child_env(self) -> dict:
        env = dict(self.environ)
        if env.get("SL_HOME"):
            # A sandboxed run must not leak into the real XDG dirs through inherited variables.
            env["HOME"] = env["SL_HOME"]
            for k in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                env.pop(k, None)
        return env

    def which(self, name: str) -> str | None:
        return shutil.which(name, path=self.environ.get("PATH", os.defpath))

    def run(self, cmd: list[str], timeout: float = CMD_TIMEOUT_S, input_text: str | None = None) -> Proc:
        """Run a command. Never raises: a missing binary is rc 127, a timeout rc 124.

        `input_text` is fed to its stdin (the clipboard copy); otherwise stdin is closed."""
        exe = self.which(cmd[0])
        if exe is None:
            return Proc(127, "", f"{cmd[0]}: not found")
        try:
            cp = subprocess.run(
                [exe, *cmd[1:]], capture_output=True, text=True, errors="replace",
                timeout=timeout, env=self.child_env(), input=input_text,
                stdin=None if input_text is not None else subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return Proc(124, "", f"{cmd[0]}: timed out")
        except OSError as e:
            return Proc(126, "", f"{cmd[0]}: {e}")
        return Proc(cp.returncode, cp.stdout, cp.stderr)

    def exec(self, res: WriteResult, cmd: list[str], *, required: bool = True, live: bool = False,
             input_text: str | None = None) -> bool:
        """Record `cmd` on `res` and run it (not under dry_run). `live` marks a live-apply step.

        A required command that fails raises CommandFailed; an optional one returns False.
        """
        if self.dry_run:
            res.commands.append(list(cmd))
            res.applied_live = res.applied_live or live
            return True
        p = self.run(cmd, input_text=input_text)
        if not p.ok:
            why = (p.err or p.out).strip() or f"exit {p.rc}"
            if required:
                raise CommandFailed(f"{' '.join(cmd)}: {why}")
            res.notes.append(f"not applied live: {' '.join(cmd)}: {why}")
            return False
        res.commands.append(list(cmd))
        res.applied_live = res.applied_live or live
        return True

    def launch(self, res: WriteResult, cmd: list[str]) -> None:
        """Start a long-lived program (a window or a terminal) detached; never waits for it.

        Recorded on `res` like `exec`; not started under dry_run. A missing binary raises
        CommandFailed so the caller can say so.
        """
        if not self.dry_run:
            exe = self.which(cmd[0])
            if exe is None:
                raise CommandFailed(f"{cmd[0]}: not found")
            try:
                proc = subprocess.Popen([exe, *cmd[1:]], env=self.child_env(), stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                threading.Thread(target=proc.wait, daemon=True).start()  # reap it when it exits
            except OSError as e:
                raise CommandFailed(f"{cmd[0]}: {e}") from e
        res.commands.append(list(cmd))

    # -- files -------------------------------------------------------------------------------
    def write_file(self, res: WriteResult, path: Path, text: str) -> None:
        """Atomically write `text` to `path`, which must lie inside the (fake) home."""
        path = Path(path)
        shown = self.tilde(path)
        res.files.append(shown)
        res.texts[shown] = text
        if self.dry_run:
            return
        if os.geteuid() == 0:
            raise Refused("refusing to write user settings as root")
        # realpath on both sides: a symlinked ~/.config/seclegion must not carry a write out of home.
        home = os.path.realpath(self.home)
        if not (os.path.realpath(path.parent) + os.sep).startswith(home + os.sep):
            raise Refused(f"refusing to write outside the home directory: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = 0o644
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        with contextlib.suppress(OSError):  # best effort: make the rename itself durable
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

    def write_sysfs(self, res: WriteResult, path: Path, text: str) -> None:
        """Write `text` to one sysfs attribute under `self.sysfs` (no atomic replace: it is a kernel file).

        Not root: the udev rule shipped with seclegion-settings opens the attribute to group wheel."""
        path = Path(path)
        res.files.append(str(path))
        res.texts[str(path)] = text
        if self.dry_run:
            return
        if not os.path.realpath(path).startswith(os.path.realpath(self.sysfs) + os.sep):
            raise Refused(f"refusing to write outside sysfs: {path}")
        try:
            with open(path, "w", encoding="ascii") as f:
                f.write(text)
        except OSError as e:
            raise CommandFailed(f"{path}: {e.strerror or e} (is your user in the wheel group?)") from e

    def preview_file(self, res: WriteResult, path: str, text: str) -> None:
        """Privileged rows: record the exact text for `path`; never touches the disk."""
        res.files.append(path)
        res.texts[path] = text
