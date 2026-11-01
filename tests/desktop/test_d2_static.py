# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""D2 static checks: greeter config, browser defaults and flags, Arch branding in what post installs."""

import configparser
import glob
import os
import re
import sys
import tomllib

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
sys.path.insert(0, os.path.join(REPO, "tools", "lib"))
import post  # noqa: E402

import branding  # noqa: E402

DOT = os.path.join(REPO, "pkgs", "seclegion-dotfiles")


def run(tmp_path, extra):
    root = tmp_path / "mnt"
    for d in ("etc/ufw", "etc/default"):
        (root / d).mkdir(parents=True)
    (root / "etc/pacman.conf").write_text("[core]\nInclude = /x\n")
    (root / "usr/share/snapper/config-templates").mkdir(parents=True)
    (root / "usr/share/snapper/config-templates/default").write_text('SUBVOLUME="/"\nTIMELINE_CREATE="yes"\n')
    (root / "etc/conf.d").mkdir(parents=True)
    (root / "etc/conf.d/snapper").write_text('SNAPPER_CONFIGS=""\n')
    (root / "etc/ufw/ufw.conf").write_text("ENABLED=no\n")
    for rules in ("after.rules", "after6.rules"):
        (root / "etc/ufw" / rules).write_text("COMMIT\n")
    (root / "etc/default/ufw").write_text('DEFAULT_INPUT_POLICY="ACCEPT"\n')
    p = post.Post(str(root), lambda c: None, hints={"username": "u", "keyboard_extra": extra})
    p.steps()
    return root


def test_greeter_one_session_no_autologin(tmp_path):
    root = run(tmp_path, ["ara"])
    cfg = tomllib.loads((root / "etc/greetd/config.toml").read_text())
    assert "initial_session" not in cfg
    cmd = cfg["default_session"]["command"]
    assert "autologin" not in cmd and "regreet" in cmd
    dirs = re.search(r"SESSION_DIRS=(\S+)", cmd).group(1).split(":")
    assert dirs == ["/etc/greetd/sessions"]
    assert os.listdir(root / "etc/greetd/sessions") == ["hyprland.desktop"]
    text = (root / "etc/greetd/sessions/hyprland.desktop").read_text()
    assert "Exec=uwsm start -- hyprland.desktop" in text.splitlines()


def test_greeter_regreet_toml_theme(tmp_path):
    root = run(tmp_path, [])
    t = tomllib.loads((root / "etc/greetd/regreet.toml").read_text())
    assert t["GTK"]["theme_name"] == "Graphite-Dark"
    assert t["GTK"]["cursor_theme_name"].startswith("Bibata")
    assert t["GTK"]["font_name"].startswith("Figtree")
    assert t["background"]["path"] == "/usr/share/seclegion/branding/seclegion-logo.png"
    assert (root / "etc/greetd/regreet.css").read_text().strip()
    assert "--config /etc/greetd/regreet.toml" in (root / "etc/greetd/config.toml").read_text()


def test_greeter_xkb_only_with_keyboard_extra(tmp_path):
    with_x = (run(tmp_path / "a", ["ara"]) / "etc/greetd/config.toml").read_text()
    without = (run(tmp_path / "b", []) / "etc/greetd/config.toml").read_text()
    assert "XKB_DEFAULT_LAYOUT=us,ara" in with_x and "XKB_DEFAULT_OPTIONS=grp:alt_shift_toggle" in with_x
    assert "XKB" not in without
    tomllib.loads(with_x)


def test_browsers_firefox_default():
    cp = configparser.ConfigParser(delimiters=("=",))
    cp.read(os.path.join(DOT, "xdg", "mimeapps.list"))
    d = cp["Default Applications"]
    for k in ("text/html", "x-scheme-handler/http", "x-scheme-handler/https"):
        assert d[k] == "firefox.desktop"
    assert "etc/xdg/mimeapps.list" in open(os.path.join(DOT, "PKGBUILD")).read()


def test_browsers_flags_wayland_sandbox_on():
    paths = glob.glob(os.path.join(DOT, "skel", ".config", "*-flags.conf"))
    assert {os.path.basename(p) for p in paths} == {"code-flags.conf", "brave-flags.conf"}
    for p in paths:
        flags = [ln.strip() for ln in open(p) if ln.strip() and not ln.startswith("#")]
        assert "--ozone-platform-hint=auto" in flags
    scan = glob.glob(os.path.join(REPO, "pkgs", "*", "**", "*"), recursive=True) + paths + [post.__file__]
    for p in scan:
        if os.path.isfile(p) and not p.endswith((".png", ".gz", ".zst")):
            for ln in open(p, errors="replace").read().splitlines():
                if "--no-sandbox" in ln:
                    assert ln.lstrip().startswith(("#", "//")), f"{p}: {ln}"


def test_branding_target_no_arch_hits(tmp_path):
    root = run(tmp_path, ["ara"])
    # errors="replace": a transient non-text file once made this fail with UnicodeDecodeError (cause unseen)
    texts = [(str(f), f.read_text(errors="replace")) for f in root.rglob("*")
             if f.is_file() and "pacman" not in f.name]
    for p in glob.glob(os.path.join(DOT, "**", "*"), recursive=True):
        if os.path.isfile(p) and not p.endswith("PKGBUILD"):  # recipes are not installed
            texts.append((p, open(p, errors="replace").read()))
    for p in glob.glob(os.path.join(REPO, "pkgs", "seclegion-branding", "*")):
        if p.endswith("PKGBUILD"):
            continue
        texts.append((p, open(p, errors="replace").read()))
    assert texts
    for name, t in texts:
        assert branding.scan(t) == [], name
