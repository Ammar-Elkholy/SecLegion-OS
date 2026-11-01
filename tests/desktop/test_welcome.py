# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G44 welcome app: shows once, reachable from the menu, every button resolves (no display needed)."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop/welcome/python"))

from seclegion_welcome import model  # noqa: E402

PKGBUILD = (ROOT / "pkgs/seclegion-desktop/PKGBUILD").read_text()
SOURCE_LIST = (ROOT / "pkgs/seclegion-desktop/source.list").read_text().split()
DESKTOP_FILE = ROOT / "desktop/welcome/applications/seclegion-welcome.desktop"
UNIT = ROOT / "desktop/units/seclegion-welcome.service"


def shipped_binaries_text():
    return "\n".join(p.read_text() for p in sorted((ROOT / "pkgs").glob("*/PKGBUILD")))


def package_list_names():
    names = set()
    for p in (ROOT / "iso/packages").glob("*.list"):
        names |= {ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    return names


def resolves(binary, pkgs_text=None, lists=None):
    """A command resolves when one of our PKGBUILDs installs it into /usr/bin or it is a listed package."""
    pkgs_text = shipped_binaries_text() if pkgs_text is None else pkgs_text
    lists = package_list_names() if lists is None else lists
    pat = rf"usr/bin/{re.escape(binary)}\b|\bfor \w+ in [^\n]*\b{re.escape(binary)}\b"
    return bool(re.search(pat, pkgs_text)) or binary in lists


def command_binaries(argv):
    """The program the button runs, plus the program a terminal wrapper runs."""
    out = [argv[0]]
    if argv[0] == model.TERMINAL:
        rest = list(argv[1:])
        if rest[:1] == ["--title"]:
            rest = rest[2:]
        out.append(rest[0])
    return out


def unresolved(buttons, pkgs_text=None, lists=None):
    return [(b.id, c) for b in buttons for c in command_binaries(b.argv) if not resolves(c, pkgs_text, lists)]


# --- once-only ---------------------------------------------------------------


def test_welcome_shows_once(tmp_path):
    env = {"HOME": str(tmp_path)}
    assert model.should_autostart(env)
    model.mark_done(env)
    assert (tmp_path / ".local/state/seclegion/welcome.done").is_file()
    assert not model.should_autostart(env)


def test_welcome_unit_is_conditioned_on_the_done_marker():
    t = UNIT.read_text()
    assert "ConditionPathExists=!%h/.local/state/seclegion/welcome.done" in t
    assert "graphical-session.target" in t and "--autostart" in t
    assert str(model.done_path({"HOME": "%h"})).endswith(".local/state/seclegion/welcome.done")
    assert resolves(re.search(r"ExecStart=/usr/bin/(\S+)", t).group(1))


# --- reachable from the menu --------------------------------------------------


def test_welcome_reachable_desktop_entry_shipped_and_installed():
    d = DESKTOP_FILE.read_text()
    assert "Type=Application" in d and "Exec=seclegion-welcome" in d
    assert "seclegion-welcome.desktop" in PKGBUILD
    assert "desktop/welcome" in SOURCE_LIST
    assert resolves("seclegion-welcome")


def test_welcome_unit_installed_by_the_pkgbuild_glob():
    assert "desktop/units/*.service" in PKGBUILD and "desktop/units" in SOURCE_LIST


# --- every button resolves ------------------------------------------------------


def test_welcome_every_button_resolves():
    assert unresolved(model.all_buttons()) == []


def test_welcome_a_missing_binary_is_detected():
    bad = model.Button("x", "X", "", model.in_terminal("X", "seclegion-no-such-binary"))
    assert unresolved([bad]) == [("x", "seclegion-no-such-binary")]


def test_welcome_buttons_run_the_documented_commands():
    by = {b.id: b.argv for b in model.all_buttons()}
    assert by["keys"] == ("seclegion-keys",)
    assert by["settings"] == ("seclegion-settings",)
    assert by["updates"][0] == "kitty" and by["updates"][-1] == "seclegion-update"
    assert by["tools"][-1] == "list" and "seclegion-tools" in by["tools"]
    assert by["install-vscode"][-2:] == ("--fetch", "seclegion-vscode-fetch")
    assert by["install-brave"][-2:] == ("--fetch", "seclegion-brave-fetch")
    assert by["install-claude"][-2:] == ("--fetch", "seclegion-claude-fetch")


def test_welcome_dual_boot_doc_and_catalog_are_installed():
    assert model.DUAL_BOOT_DOC == "/usr/share/doc/seclegion/dual-boot.md"
    assert (ROOT / "docs/dual-boot.md").is_file()
    assert "docs/dual-boot.md" in SOURCE_LIST and "usr/share/doc/seclegion/dual-boot.md" in PKGBUILD
    assert "catalog" in SOURCE_LIST and "usr/share/seclegion/catalog" in PKGBUILD
    assert model.CATALOG_DIR == "/usr/share/seclegion/catalog"
    assert (ROOT / "tools/seclegion-tools").is_file()


def test_welcome_terminal_is_in_the_package_lists():
    assert model.TERMINAL in package_list_names()


# --- vendor buttons -------------------------------------------------------------


def ids(buttons):
    return [b.id for b in buttons]


def test_welcome_vendor_buttons_hidden_when_pending_absent(tmp_path):
    env = {"HOME": str(tmp_path)}
    assert model.read_pending(tmp_path / "missing") == []
    shown = ids(model.visible_buttons(model.read_pending(tmp_path / "missing"), env))
    assert not {"install-vscode", "install-brave", "install-claude"} & set(shown)
    assert {"keys", "settings", "updates", "dual-boot", "tools"} <= set(shown)


def test_welcome_vendor_buttons_shown_only_for_pending_entries(tmp_path):
    env = {"HOME": str(tmp_path)}
    p = tmp_path / "pending"
    p.write_text("seclegion-vscode-fetch\nseclegion-brave-fetch\nseclegion-claude-fetch\nrm-rf-slash\n")
    assert model.read_pending(p) == ["seclegion-vscode-fetch", "seclegion-brave-fetch",
                                     "seclegion-claude-fetch"]
    shown = ids(model.visible_buttons(model.read_pending(p), env))
    assert {"install-vscode", "install-brave", "install-claude"} <= set(shown)
    p.write_text("seclegion-brave-fetch\n")
    shown = ids(model.visible_buttons(model.read_pending(p), env))
    assert "install-vscode" not in shown and "install-brave" in shown


def test_welcome_vendor_button_hidden_when_user_marker_present(tmp_path):
    env = {"HOME": str(tmp_path)}
    pending = ["seclegion-vscode-fetch", "seclegion-brave-fetch"]
    model.vendor_marker("seclegion-vscode-fetch", env).parent.mkdir(parents=True)
    model.vendor_marker("seclegion-vscode-fetch", env).write_text("done\n")
    shown = ids(model.visible_buttons(pending, env))
    assert "install-vscode" not in shown and "install-brave" in shown


def test_welcome_fetch_success_leaves_user_marker_failure_does_not(tmp_path):
    env = {"HOME": str(tmp_path)}
    ran = []
    out = []

    def run_ok(argv):
        ran.append(argv)
        return 0

    class Out:
        write = staticmethod(out.append)
        flush = staticmethod(lambda: None)

    assert model.run_fetch("seclegion-vscode-fetch", env, lambda: 1000, run_ok, Out) == 0
    assert ran == [["seclegion-vscode-fetch"]]
    assert model.vendor_marker("seclegion-vscode-fetch", env).is_file()
    assert model.run_fetch("seclegion-brave-fetch", env, lambda: 1000, lambda a: 3, Out) == 3
    assert not model.vendor_marker("seclegion-brave-fetch", env).exists()


def test_welcome_never_runs_fetchers_as_root(tmp_path):
    env = {"HOME": str(tmp_path)}
    ran = []
    out = []

    class Out:
        write = staticmethod(out.append)
        flush = staticmethod(lambda: None)

    rc = model.run_fetch("seclegion-vscode-fetch", env, lambda: 0, lambda a: ran.append(a) or 0, Out)
    assert rc != 0 and ran == []
    assert "refusing" in "".join(out)
    assert not model.vendor_marker("seclegion-vscode-fetch", env).exists()


def test_welcome_unknown_fetcher_is_refused(tmp_path):
    ran = []
    rc = model.run_fetch("rm", {"HOME": str(tmp_path)}, lambda: 1000, lambda a: ran.append(a) or 0)
    assert rc != 0 and ran == []


def test_welcome_launch_is_detached():
    calls = []
    model.launch(model.STATIC_TOP[0], lambda argv, **kw: calls.append((argv, kw)))
    assert calls == [(["seclegion-keys"], {"start_new_session": True})]
