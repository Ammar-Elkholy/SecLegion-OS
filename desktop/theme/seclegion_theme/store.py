# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""State directory, content hash, flock, atomic write and symlink swap."""
from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .palette import ThemeError
from .render import FILES

# The lock covers the whole apply (matugen up to 30 s, hooks ~2.5 s), so a
# second run waits at least that long before giving up.
LOCK_WAIT_S = 40.0
KEEP = 5  # newest theme dirs kept besides current's target
_NAME_LEN = 16


def state_root(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return Path(base) / "seclegion" / "theme"


def lock_path(env=None) -> Path:
    env = os.environ if env is None else env
    run = env.get("XDG_RUNTIME_DIR")
    if run and os.path.isdir(run):
        return Path(run) / "seclegion-theme.lock"
    return state_root(env) / ".lock"


@contextlib.contextmanager
def locked(env=None, wait_s: float = LOCK_WAIT_S):
    """Exclusive flock so two wallpaper changes never interleave. Held for
    the whole apply pipeline (see engine.apply_theme)."""
    path = lock_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES) or time.monotonic() > deadline:
                    raise ThemeError("another seclegion-theme run holds the lock") from e
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)  # closing releases the flock


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(tokens: dict, mode: str, contrast: str, wallpaper: str | None, wp_sha: str | None) -> str:
    blob = json.dumps(
        {"tokens": tokens, "mode": mode, "contrast": contrast, "wallpaper": wallpaper, "sha": wp_sha},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:_NAME_LEN]


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_durable(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def _is_complete(d: Path, wallpaper: Path | None) -> bool:
    """Every contract file present and non-empty, colors.json parses, and the
    wallpaper link is there when one belongs to this theme."""
    try:
        if not all((d / f).is_file() and (d / f).stat().st_size > 0 for f in FILES):
            return False
        json.loads((d / "colors.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # ValueError covers JSON and UTF-8 errors
        return False
    return wallpaper is None or (d / "wallpaper").is_symlink()


def write_theme(root: Path, name: str, files: dict[str, str], wallpaper: Path | None) -> Path:
    """Write theme/<name>/ atomically (tmp dir + fsync + rename). Idempotent:
    an existing complete dir is reused (its mtime bumped so prune keeps it);
    an incomplete or corrupt one is rebuilt."""
    root.mkdir(parents=True, exist_ok=True)
    final = root / name
    if final.is_dir() and not final.is_symlink() and _is_complete(final, wallpaper):
        os.utime(final)
        return final
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-", dir=root))
    try:
        for fname, text in files.items():
            _write_durable(tmp / fname, text)
        if wallpaper is not None:
            os.symlink(os.path.abspath(wallpaper), tmp / "wallpaper")
        os.chmod(tmp, 0o755)
        _fsync_dir(tmp)
        if final.is_symlink() or final.is_file():
            os.unlink(final)
        elif final.exists():  # incomplete leftover: replace
            shutil.rmtree(final)
        os.rename(tmp, final)
        _fsync_dir(root)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def swap_current(root: Path, name: str) -> Path:
    """Atomically point theme/current at theme/<name> (relative symlink)."""
    link = root / "current"
    tmp = root / f".current.{os.getpid()}"
    with contextlib.suppress(FileNotFoundError):
        os.unlink(tmp)
    os.symlink(name, tmp)
    try:
        os.replace(tmp, link)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    _fsync_dir(root)
    return link


def _is_theme_name(n: str) -> bool:
    return len(n) == _NAME_LEN and all(c in "0123456789abcdef" for c in n)


def prune(root: Path, keep: int = KEEP) -> list[str]:
    """Drop old theme dirs and stale .tmp-* dirs. Call with the lock held
    (no other run can be writing a .tmp-* then). Keeps the `keep` newest
    theme dirs plus whatever `current` points at."""
    try:
        target = os.readlink(root / "current")
    except OSError:
        target = None
    dirs, removed = [], []
    for ent in os.scandir(root):
        if not ent.is_dir(follow_symlinks=False):
            continue
        if ent.name.startswith(".tmp-"):
            shutil.rmtree(ent.path, ignore_errors=True)
            removed.append(ent.name)
        elif _is_theme_name(ent.name):
            dirs.append((ent.stat(follow_symlinks=False).st_mtime_ns, ent.name))
    dirs.sort(reverse=True)
    for _, n in dirs[keep:]:
        if n != target:
            shutil.rmtree(root / n, ignore_errors=True)
            removed.append(n)
    return removed


def read_current(root: Path) -> dict | None:
    """The active colors.json, or None when no theme was ever applied.
    Damaged state raises ThemeError with a plain-language message."""
    f = root / "current" / "colors.json"
    fix = "run `seclegion-theme reset` to rebuild it"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if (root / "current").is_symlink() or (root / "current").exists():
            raise ThemeError(f"the active theme is incomplete ({f} is missing); {fix}") from None
        return None
    except NotADirectoryError:
        raise ThemeError(f"{root / 'current'} is not a theme directory; {fix}") from None
    except PermissionError:
        raise ThemeError(f"cannot read {f}: permission denied") from None
    except UnicodeDecodeError:
        raise ThemeError(f"{f} is not readable text; {fix}") from None
    except json.JSONDecodeError:
        raise ThemeError(f"{f} is damaged (not valid JSON); {fix}") from None
    except OSError as e:
        raise ThemeError(f"cannot read {f}: {e.strerror or e}") from None
    if not isinstance(data, dict):
        raise ThemeError(f"{f} is not a theme description; {fix}")
    return data
