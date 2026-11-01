# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-update: in-process runs against a temp root with a fake command runner (no root,
no pacman, no snapper). Names: test_update_* ; the abort cases are test_update_abort_*."""

import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

PKG = Path(__file__).resolve().parents[2] / "pkgs" / "seclegion-update"
GIB = 1024**3


def load():
    loader = importlib.machinery.SourceFileLoader("seclegion_update", str(PKG / "seclegion-update"))
    spec = importlib.util.spec_from_loader("seclegion_update", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


U = load()


class Fake:
    """Records every argv; `bash <migration>` fails when its name is in `fail`."""

    def __init__(self, fail=(), pacman_rc=0):
        self.calls, self.fail, self.pacman_rc, self.envs = [], set(fail), pacman_rc, []

    def __call__(self, argv, env=None):
        self.calls.append(list(argv))
        self.envs.append(env)
        rc, out = 0, ""
        if argv[0] == "snapper" and "--print-number" in argv:
            out = "41\n"
        elif argv[0] == "pacman":
            rc = self.pacman_rc
        elif argv[0] == "bash" and Path(argv[1]).name in self.fail:
            rc = 3
        return SimpleNamespace(returncode=rc, stdout=out)

    def snaps(self, kind):
        return [c for c in self.calls if c[0] == "snapper" and kind in c and c[c.index("--type") + 1] == kind]

    def migs(self):
        return [Path(c[1]).name for c in self.calls if c[0] == "bash"]


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "root"
    mig = r / "usr/share/seclegion/migrate"
    mig.mkdir(parents=True)
    for n in ("0001-noop.sh", "0002-a.sh", "0003-b.sh"):
        (mig / n).write_text("#!/bin/bash\n")
    (r / "var/lib/pacman").mkdir(parents=True)
    (r / "etc/mkinitcpio.d").mkdir(parents=True)
    (r / "efi/EFI/Linux").mkdir(parents=True)
    (r / "efi/EFI/Linux/arch.efi").write_text("x")
    (r / "etc/mkinitcpio.d/linux.preset").write_text(
        "PRESETS=('default')\ndefault_uki=\"/efi/EFI/Linux/arch.efi\"\n")
    (r / "sys/class/power_supply/BAT0").mkdir(parents=True)
    (r / "sys/class/power_supply/BAT0/capacity").write_text("80\n")
    (r / "sys/class/power_supply/BAT0/status").write_text("Discharging\n")
    return r


def run(root, fake, free=50 * GIB, args=()):
    return U.main(["--root", str(root), *args], runner=fake, disk_free=lambda p: free)


def marks(root):
    d = root / "var/lib/seclegion/migrations"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_update_one_snapshot_pair_and_migrations_once(root):
    f = Fake()
    assert run(root, f) == 0
    pre, post = f.snaps("pre"), f.snaps("post")
    assert len(pre) == 1 and len(post) == 1
    assert post[0][post[0].index("--pre-number") + 1] == "41"
    assert "seclegion=update" in pre[0] and "seclegion=update" in post[0]
    pac = [i for i, c in enumerate(f.calls) if c[0] == "pacman"]
    assert len(pac) == 1 and f.envs[pac[0]] == {"SNAP_PAC_SKIP": "y"}
    assert f.calls.index(pre[0]) < pac[0] < f.calls.index(post[0])
    assert f.migs() == ["0001-noop.sh", "0002-a.sh", "0003-b.sh"]
    assert marks(root) == ["0001", "0002", "0003"]


def test_update_rerun_is_noop_for_migrations(root):
    run(root, Fake())
    f = Fake()
    assert run(root, f) == 0
    assert f.migs() == []
    assert len(f.snaps("pre")) == 1 and len(f.snaps("post")) == 1


def test_update_only_new_migration_runs_later(root):
    run(root, Fake())
    (root / "usr/share/seclegion/migrate/0004-c.sh").write_text("#!/bin/bash\n")
    f = Fake()
    assert run(root, f) == 0
    assert f.migs() == ["0004-c.sh"]


def test_update_abort_failing_migration_keeps_snapshot_and_stops(root, capsys):
    f = Fake(fail={"0002-a.sh"})
    assert run(root, f) == 1
    assert f.migs() == ["0001-noop.sh", "0002-a.sh"]
    assert marks(root) == ["0001"]
    assert len(f.snaps("pre")) == 1
    assert not any(c[:2] == ["snapper", "delete"] or "delete" in c for c in f.calls if c[0] == "snapper")
    assert "0002-a.sh failed" in capsys.readouterr().err


def test_update_abort_missing_uki(root, capsys):
    (root / "efi/EFI/Linux/arch.efi").unlink()
    f = Fake()
    assert run(root, f) == 1
    assert f.migs() == [] and marks(root) == []
    assert len(f.snaps("pre")) == 1
    assert "missing" in capsys.readouterr().err


def test_update_abort_pacman_failure(root):
    f = Fake(pacman_rc=1)
    assert run(root, f) == 1
    assert f.migs() == [] and len(f.snaps("pre")) == 1 and f.snaps("post") == []


def test_update_abort_low_battery(root):
    (root / "sys/class/power_supply/BAT0/capacity").write_text("15\n")
    f = Fake()
    assert run(root, f) == 1 and f.calls == []


def test_update_low_battery_while_charging_is_fine(root):
    (root / "sys/class/power_supply/BAT0/capacity").write_text("15\n")
    (root / "sys/class/power_supply/BAT0/status").write_text("Charging\n")
    assert run(root, Fake()) == 0


def test_update_abort_low_disk(root):
    f = Fake()
    assert run(root, f, free=GIB) == 1 and f.calls == []


def test_update_abort_pacman_lock(root):
    (root / "var/lib/pacman/db.lck").write_text("")
    f = Fake()
    assert run(root, f) == 1 and f.calls == []


def test_update_refresh_config_backs_up_then_copies(root, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config/hypr").mkdir(parents=True)
    (home / ".config/hypr/hyprland.conf").write_text("mine")
    (root / "usr/share/seclegion/hypr").mkdir(parents=True)
    (root / "usr/share/seclegion/hypr/hyprland.conf").write_text("packaged")
    monkeypatch.setenv("HOME", str(home))
    f = Fake()
    assert run(root, f, args=["--refresh-config", "hypr"]) == 0
    assert (home / ".config/hypr/hyprland.conf").read_text() == "packaged"
    baks = list((home / ".local/state/seclegion/refresh").glob("*/hypr/hyprland.conf"))
    assert len(baks) == 1 and baks[0].read_text() == "mine"
    assert f.calls == []


def test_update_abort_refresh_config_unknown_name(root, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (root / "usr/share/seclegion/bash").mkdir(parents=True)
    assert run(root, Fake(), args=["--refresh-config", "bash"]) == 1
    assert not (tmp_path / "home/.config/bash").exists()


def test_update_package_files():
    assert (PKG / "migrate/0001-noop.sh").is_file()
    assert subprocess.run(["bash", "-n", str(PKG / "migrate/0001-noop.sh")]).returncode == 0
    assert "NOPASSWD" not in (PKG / "seclegion-update").read_text().replace("never NOPASSWD", "")


def test_update_refresh_config_keeps_the_users_user_lua(root, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config/hypr").mkdir(parents=True)
    (home / ".config/hypr/user.lua").write_text("my overrides")
    (root / "usr/share/seclegion/hypr").mkdir(parents=True)
    (root / "usr/share/seclegion/hypr/hyprland.lua").write_text("packaged")
    monkeypatch.setenv("HOME", str(home))
    assert run(root, Fake(), args=["--refresh-config", "hypr"]) == 0
    assert (home / ".config/hypr/hyprland.lua").read_text() == "packaged"
    assert (home / ".config/hypr/user.lua").read_text() == "my overrides"
