# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""CP-C VM (installed base): the M6 rows checked on the installed target, not on the repo.

Each test boots a throwaway overlay of the cached install (tests/lib/installed.py), logs in as `tester`
on the serial getty, and prints one M6-* result line per passed check; the evidence rows M6-single-session,
M6-branding and M6-browsers check those lines in order. The constants and regexes come from the static
tests (tests/desktop/test_single_session.py FORBIDDEN, tools/lib/branding.py NAME_RE), not copies.

G45b M6-single-session checks on the target: no installed package named like a GNOME/DM/other-desktop
  package (FORBIDDEN), no gnome-shell/gdm binary or gdm unit, /usr/share/wayland-sessions holds only
  hyprland*.desktop entries (at least one), no /usr/share/xsessions entries. NOT checked: the ISO's own
  package set (static list tests cover it).
G42 M6-branding checks on the target: NAME_RE (grep -P, case-insensitive) over every file of every
  installed seclegion-* package, /etc/greetd, /etc/skel and tester's ~/.config, with /opt and anything
  pacman-named excluded. NOT checked: files of Arch packages (they keep their own names), the rest of /.
G43 M6-browsers checks on the target: `xdg-settings get default-web-browser` as tester is firefox.desktop,
  /etc/xdg/mimeapps.list defaults http/https/html to firefox.desktop, and ~/.config/{code,brave}-flags.conf
  (copied from skel) carry --ozone-platform-hint=auto and no uncommented --no-sandbox. NOT checked: Brave
  and VS Code themselves (vendor binaries fetched on first boot; the offline VM has none), so their
  real Wayland and sandbox state is not observed here.
"""
import os
import re
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "desktop"))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))

from test_i2_run import PASSWORD, finish_gate  # noqa: E402
from test_single_session import FORBIDDEN  # noqa: E402

import branding  # noqa: E402
import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import Shell, installed_vm  # noqa: E402

FLAG_FILES = ("code-flags.conf", "brave-flags.conf")  # pkgs/seclegion-dotfiles/skel/.config


def single_session(sh):
    rc, out = sh.run("pacman -Qq")
    assert rc == 0, out
    names = out.split()
    assert len(names) > 100, out
    bad = [n for n in names if FORBIDDEN.match(n)]
    assert not bad, f"forbidden packages installed: {bad}"
    rc, out = sh.run("ls -d /usr/bin/gnome-shell /usr/bin/gdm /usr/lib/systemd/system/gdm.service 2>&1")
    assert rc != 0 and "No such file" in out and out.count("No such file") == 3, out
    sh.say("M6-SINGLE no gnome gdm gnome-shell")

    rc, out = sh.run("ls -1A /usr/share/wayland-sessions")  # -1: the serial console is a tty
    entries = re.findall(r"^\S+$", out, re.M)
    assert rc == 0 and entries, out
    assert all(re.fullmatch(r"hyprland[\w-]*\.desktop", e) for e in entries), entries
    rc, out = sh.run("ls -A /usr/share/xsessions 2>/dev/null | wc -l")
    assert re.findall(r"^\d+$", out, re.M) == ["0"], out
    sh.say("M6-SINGLE wayland-sessions only hyprland")


def branding_target(sh):
    # 2>/dev/null: pacman warns that the core/extra sync DBs are missing until the first -Sy
    rc, out = sh.run("pacman -Qq 2>/dev/null | grep -c '^seclegion-'")
    counts = re.findall(r"^\d+$", out, re.M)
    assert rc == 0 and counts and int(counts[-1]) >= 5, out
    pat = branding.NAME_RE.pattern  # D-BR-2: files name the base distro technically
    files = ("$(pacman -Qlq $(pacman -Qq 2>/dev/null | grep '^seclegion-') 2>/dev/null | grep -v '/$' "
             "| grep -v -e '^/opt/' -e pacman) /etc/greetd /etc/skel /home/tester/.config")
    sh.sudo_prime()  # root-only files (sudoers.d, greetd) are scanned too; grep exit 2 = unreadable
    rc, out = sh.run(f"sudo -n grep -rIliP -e '{pat}' --exclude='*pacman*' --exclude-dir=pacman* {files}",
                     timeout=180)
    hits = re.findall(r"^/\S+$", out, re.M)
    assert rc == 1 and not hits, f"branding hits: {hits}"  # grep exit 1 = scanned, no match
    sh.say("M6-BRANDING hits 0")


def browsers(sh):
    rc, out = sh.run("xdg-settings get default-web-browser")
    assert rc == 0 and re.findall(r"^\S+$", out, re.M) == ["firefox.desktop"], out
    sh.say("M6-BROWSERS xdg default firefox")

    rc, out = sh.run("cat /etc/xdg/mimeapps.list")
    assert rc == 0, out
    for key in ("text/html", "x-scheme-handler/http", "x-scheme-handler/https"):
        assert re.search(rf"^{re.escape(key)}=firefox\.desktop$", out, re.M), (key, out)
    for name in FLAG_FILES:
        rc, out = sh.run(f"cat /home/tester/.config/{name}")
        assert rc == 0, out
        flags = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
        assert "--ozone-platform-hint=auto" in flags, (name, flags)
        assert not any("--no-sandbox" in f for f in flags), (name, flags)
    sh.say("M6-BROWSERS flags ozone wayland sandbox on")


def _gate(test_id, prefix, session, summary, description):
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m6t-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    sh = Shell(vm, prefix)
                    sh.login()
                    session(sh)
                    assert PASSWORD not in vm.serial.text()
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return summary, command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate(test_id, description, body)


@pytest.mark.iso
def test_m6_single_session_target():
    _gate("M6-single-session", "M6SRC", single_session,
          "no GNOME/gdm/other-desktop package, wayland-sessions holds only Hyprland",
          "no GNOME session, gdm or gnome-shell on the target, and `/usr/share/wayland-sessions/` holds "
          "only the Hyprland entry")


@pytest.mark.iso
def test_m6_branding_target():
    _gate("M6-branding", "M6BRC", branding_target, "branding grep over the target's seclegion files: 0 hits",
          "branding grep returns 0 on the target (seclegion packages, greetd, skel and home config; "
          "vendor `/opt` excluded)")


@pytest.mark.iso
def test_m6_browsers_target():
    _gate("M6-browsers", "M6WRC", browsers,
          "Firefox is the xdg default; code and brave flags Wayland, sandbox on",
          "Firefox is the `xdg-settings` default; the VS Code and Brave flags files select Wayland and "
          "keep the sandbox on (the vendor binaries are absent offline)")
