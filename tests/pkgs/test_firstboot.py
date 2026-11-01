# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-firstboot against a temp --root with a fake runner. Names: test_firstboot_*."""

import importlib.machinery
import importlib.util
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "pkgs" / "seclegion-firstboot"


def load():
    loader = importlib.machinery.SourceFileLoader("seclegion_firstboot", str(PKG / "seclegion-firstboot"))
    spec = importlib.util.spec_from_loader("seclegion_firstboot", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


F = load()


class Fake:
    def __init__(self, online=True):
        self.calls, self.online, self.snaps = [], online, []

    def __call__(self, argv, capture=False):
        self.calls.append(list(argv))
        if argv[0] == "snapper" and argv[3] == "list":
            return 0, "Description\n" + "\n".join(self.snaps) + "\n"
        if argv[0] == "snapper" and argv[3] == "create":
            self.snaps.append(argv[argv.index("--description") + 1])
        if argv[0] == "nm-online":
            return (0 if self.online else 1), ""
        return 0, ""

    def ran(self, name):
        return [c for c in self.calls if c[0] == name]


def go(tmp_path, fake, extra=None):
    if extra is not None:
        (tmp_path / "etc/seclegion").mkdir(parents=True, exist_ok=True)
        (tmp_path / "etc/seclegion/keyboard-extra").write_text(extra)
    return F.main(["--root", str(tmp_path)], fake)


def test_firstboot_done_marker_idempotent(tmp_path):
    f = Fake()
    assert go(tmp_path, f) == 0
    assert (tmp_path / "var/lib/seclegion/firstboot.done").exists()
    n = len(f.calls)
    assert go(tmp_path, f) == 0
    assert len(f.calls) == n


def test_firstboot_baseline_exactly_once(tmp_path):
    f = Fake()
    go(tmp_path, f)
    (tmp_path / "var/lib/seclegion/firstboot.done").unlink()  # even a forced re-run
    go(tmp_path, f)
    assert f.snaps == ["seclegion-baseline"]
    assert len([c for c in f.ran("snapper") if c[3] == "create"]) == 1


def test_firstboot_keyboard_extra_layout(tmp_path):
    go(tmp_path, Fake(), extra="ara\n")
    assert 'kb_layout = "us,ara"' in (tmp_path / "etc/seclegion/kb-layout.lua").read_text()


def test_firstboot_keyboard_absent_is_us_only(tmp_path):
    go(tmp_path, Fake())
    assert 'kb_layout = "us"' in (tmp_path / "etc/seclegion/kb-layout.lua").read_text()


def test_firstboot_never_runs_the_vendor_fetchers_as_root(tmp_path):
    """makepkg refuses root and the fetchers prompt for sudo: first boot only marks them pending."""
    f = Fake()
    assert go(tmp_path, f) == 0
    for fetcher in ("seclegion-vscode-fetch", "seclegion-brave-fetch", "seclegion-claude-fetch"):
        assert not f.ran(fetcher)
    pending = (tmp_path / "var/lib/seclegion/vendor-fetch-pending").read_text().split()
    assert pending == ["seclegion-vscode-fetch", "seclegion-brave-fetch", "seclegion-claude-fetch"]
    assert (tmp_path / "var/lib/seclegion/firstboot.done").exists()
