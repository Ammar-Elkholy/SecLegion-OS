# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-host --system against the BUILT packages, extracted into a tmp root.

Needs SECLEGION_TEST_REPO (a directory holding the seclegion-*.pkg.tar.zst files) and bsdtar.
Everything runs against tmp dirs with PATH stubs; nothing touches the real $HOME or a session.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "tools" / "seclegion-host"
PACKAGES = ("desktop", "dotfiles", "theme", "settings", "branding")
STUBS = ("systemctl", "hyprctl", "busctl", "systemd-run", "pgrep", "kill", "notify-send", "getent")

_repo_env = os.environ.get("SECLEGION_TEST_REPO", "")
_pkg_dir = Path(_repo_env) if _repo_env else None
if _pkg_dir is None or not list(_pkg_dir.glob("seclegion-desktop-*.pkg.tar.zst")):
    pytest.skip("SECLEGION_TEST_REPO unset or without a seclegion-desktop package", allow_module_level=True)
if not shutil.which("bsdtar"):
    pytest.skip("bsdtar not installed", allow_module_level=True)

# What a first apply adds to a copy of /etc/skel, outside the backups, the staged copy under
# .local/share/seclegion/host and the generated theme (checked separately). "~" is the home.
EXPECTED_NEW = [
    ".config/dolphinrc",
    ".config/gtk-3.0/gtk.css",
    ".config/gtk-4.0/.seclegion-managed",
    ".config/gtk-4.0/gtk.css",
    ".config/kdeglobals",
    ".config/mimeapps.list",
    ".config/qt6ct/colors/SecLegion.conf -> ~/.local/state/seclegion/theme/current/qt6ct.conf",
    ".config/swaync -> ~/.local/share/seclegion/host/notifications",
    ".config/systemd/user/default.target.wants/seclegion-theme-sync.path -> ../seclegion-theme-sync.path",
    ".config/systemd/user/default.target.wants/seclegion-wsevents.service -> ../seclegion-wsevents.service",
    ".config/systemd/user/seclegion-idle-inhibit.service",
    ".config/systemd/user/seclegion-idle.service",
    ".config/systemd/user/seclegion-theme-sync.path",
    ".config/systemd/user/seclegion-theme-sync.service",
    ".config/systemd/user/seclegion-wsevents.service",
    ".config/waybar -> ~/.local/share/seclegion/host/waybar",
    ".config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml",
    ".config/yazi/init.lua",
    ".config/yazi/plugins/seclegion-space.yazi/main.lua",
    ".local/bin/dunstify -> ~/.local/share/seclegion/host/osd/dunstify",
    ".local/bin/nm-applet -> ~/.local/share/seclegion/host/bin/nm-applet",
    ".local/bin/seclegion-autolock -> ~/.local/share/seclegion/host/idle/seclegion-autolock",
    ".local/bin/seclegion-doctor",
    ".local/bin/seclegion-osd -> ~/.local/share/seclegion/host/osd/seclegion-osd",
    ".local/bin/seclegion-set",
    ".local/bin/seclegion-settings",
    ".local/bin/seclegion-theme",
    ".local/bin/seclegion-theme-pick",
    ".local/share/applications/seclegion-settings.desktop",
    ".local/share/color-schemes/SecLegion.colors -> ~/.local/state/seclegion/theme/current/kde.colors",
    ".local/share/seclegion/seclegion-logo.png",
    ".local/state/seclegion/theme/current -> <hash>",
]


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def tree(root):
    """Every path under root (files, dirs, symlinks) relative to it, with symlink targets."""
    out = []
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        out.append(f"{rel} -> {os.readlink(p)}" if p.is_symlink() else rel + ("/" if p.is_dir() else ""))
    return out


@pytest.fixture(scope="module")
def sysroot(tmp_path_factory):
    root = tmp_path_factory.mktemp("sysroot")
    for name in PACKAGES:
        pkg = sorted(_pkg_dir.glob(f"seclegion-{name}-[0-9]*.pkg.tar.zst"))[-1]
        subprocess.run(
            ["bsdtar", "-xf", str(pkg), "-C", str(root), "--exclude", ".PKGINFO", "--exclude", ".BUILDINFO",
             "--exclude", ".MTREE", "--exclude", ".INSTALL"],
            check=True, env=clean_env(),
        )
    assert (root / "etc/skel").is_dir()
    return root


class Env:
    def __init__(self, base, sysroot):
        self.base = base
        self.root = base / "root"
        shutil.copytree(sysroot, self.root, symlinks=True)
        self.home = base / "home"
        shutil.copytree(self.root / "etc/skel", self.home, symlinks=True)
        self.skel_tree = tree(self.home)
        self.log = base / "calls.log"
        self.log.touch()
        self.real_home = base / "realhome"
        self.real_home.mkdir()
        self.stubs = base / "stubs"
        self.stubs.mkdir()
        for name in STUBS:
            stub = self.stubs / name
            if name == "getent":
                pw = f"tester:x:$(id -u):$(id -g)::{self.real_home}:/bin/bash"
                body = f'echo "getent $*" >> "{self.log}"\necho "{pw}"\n'
            elif name == "pgrep":
                body = f'echo "pgrep $*" >> "{self.log}"\nexit 1\n'
            else:
                body = f'echo "{name} $*" >> "{self.log}"\nexit 0\n'
            stub.write_text("#!/bin/sh\n" + body)
            stub.chmod(0o755)

    def run(self, *args, home=None, extra=None, **kw):
        env = clean_env(PATH=f"{self.stubs}:{os.environ['PATH']}", HOME=str(self.real_home))
        env.pop("SL_HOME", None)
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env.update(extra or {})
        return subprocess.run([str(HOST), *args], capture_output=True, text=True, env=env, timeout=120, **kw)

    def apply(self, home=None, **kw):
        return self.run("--system", "--root", str(self.root), "--home", str(home or self.home), **kw)

    def rollback(self, which="--last"):
        return self.run("rollback", which, extra={"SL_HOME": str(self.home)})

    def calls(self):
        return self.log.read_text().splitlines()


@pytest.fixture
def env(tmp_path, sysroot):
    return Env(tmp_path, sysroot)


def out(r):
    return r.stdout + r.stderr


def new_paths(env):
    before = set(env.skel_tree)
    return [t for t in tree(env.home) if t not in before]


def normalised_new(env):
    """New non-directory paths, minus backups/staged copy/generated theme files, home written as ~."""
    got = []
    for t in new_paths(env):
        skip = (".local/state/seclegion/host-backups", ".local/share/seclegion/host/")
        if t.endswith("/") or t.startswith(skip):
            continue
        t = t.replace(str(env.home), "~")
        if t.startswith(".local/state/seclegion/theme/"):
            if not t.startswith(".local/state/seclegion/theme/current"):
                continue
            t = ".local/state/seclegion/theme/current -> <hash>"
        got.append(t)
    return sorted(got)


def test_desktop_apply_files(env):
    r = env.apply()
    assert r.returncode == 0, out(r)
    assert "system-ok" in out(r)
    assert "applied " in out(r)
    assert normalised_new(env) == sorted(EXPECTED_NEW)
    theme = (env.home / ".local/state/seclegion/theme/current").resolve()
    assert (theme / "colors.json").is_file() and (theme / "gtk3.css").is_file()
    for rel in (".config/systemd/user/default.target.wants/seclegion-theme-sync.path",
                ".config/systemd/user/default.target.wants/seclegion-wsevents.service"):
        assert not os.path.isabs(os.readlink(env.home / rel)) and (env.home / rel).exists(), rel
    assert (env.home / ".config/waybar/config.jsonc").is_file()
    assert (env.home / ".config/swaync/config.json").is_file()
    backups = env.home / ".local/state/seclegion/host-backups"
    assert (backups / "baseline-0").is_dir()
    systems = [p for p in backups.iterdir() if p.name.endswith("-system")]
    assert len(systems) == 1
    for d in (backups / "baseline-0", systems[0]):
        assert "SL_SYSTEM_BACKUP=1" in (d / "rollback.sh").read_text().splitlines()
    for line in env.calls():
        verb = line.split()[0]
        assert verb not in ("hyprctl", "busctl", "systemd-run"), line
        if verb == "systemctl":
            assert any(w in line.split() for w in ("is-active", "show")), line


def test_desktop_apply_idempotent(env):
    assert env.apply().returncode == 0
    snapshot = tree(env.home)
    r = env.apply()
    assert r.returncode == 0, out(r)
    assert "already applied" in out(r) and "no-op" in out(r)
    assert tree(env.home) == snapshot


def test_desktop_apply_rollback(env):
    assert env.apply().returncode == 0
    r = env.rollback("--last")
    assert r.returncode == 0, out(r)
    r = env.rollback("baseline-0")
    assert r.returncode == 0, out(r)
    # Only the backup bookkeeping may remain; every file apply created is gone.
    left = [t for t in tree(env.home) if t not in set(env.skel_tree)]
    left = [t for t in left if not t.startswith(".local/state/seclegion/host-backups")]
    files = [t for t in left if not t.endswith("/")]
    assert files == [], files


def test_desktop_apply_refuses(env, tmp_path):
    # baseline-0 from a live (non-system) apply
    h1 = tmp_path / "h1"
    (h1 / ".local/state/seclegion/host-backups/baseline-0").mkdir(parents=True)
    (h1 / ".local/state/seclegion/host-backups/baseline-0/rollback.sh").write_text("#!/bin/bash\n")
    r = env.apply(home=h1)
    assert r.returncode != 0 and "refusing" in out(r), out(r)
    # the owner's dotfiles repo
    h2 = tmp_path / "h2"
    (h2 / ".config/hyprland-dotfiles").mkdir(parents=True)
    r = env.apply(home=h2)
    assert r.returncode != 0 and "hyprland-dotfiles" in out(r), out(r)
    # --home equal to the invoking user's own (getent) home
    r = env.run("--system", "--root", str(env.root), "--home", str(env.real_home))
    assert r.returncode != 0 and "invoking user's own home" in out(r), out(r)
    for h in (h1, h2, env.real_home):
        assert not (h / ".config/waybar").exists()


def test_desktop_apply_missing_file(env):
    (env.root / "usr/share/seclegion/waybar/seclegion-ws").unlink()
    r = env.apply()
    assert r.returncode != 0
    assert "missing packaged file" in out(r)
    assert tree(env.home) == env.skel_tree
