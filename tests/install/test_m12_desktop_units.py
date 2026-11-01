# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""VG10 (VM, installed base): the desktop work of 2026-10-31 is really on an installed system.

The installed system is a throwaway overlay on the cached install (tests/lib/installed.py). The test logs
in as `tester` on the serial getty (root checks through `sudo -n`) and the guest prints one M12-* line per
passed check; the evidence row M12-desktop-units checks them in order. No GUI is started.

Checked: the wifi/sysmon/settings/desktop/branding packages and libnm/python-psutil are installed; the
root helper /usr/bin/seclegion-root-apply (root, 0755) and its polkit action are installed and registered;
the helper as root prints the timedatectl argv on --dry-run, really sets region.timezone, and refuses a
path-like value without touching /etc/localtime; /etc/snapper/configs/root is 0644; the displayd and
wallpaper user units are installed and enabled by the package's wants symlinks on graphical-session.target;
the default wallpaper and the display-menu/sysmon/wifi launchers are present; the wifi and sysmon data
modules import with the launchers' python path. NOT checked: any GUI, and pkexec itself (no agent here).
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

from test_i2_run import PASSWORD, finish_gate  # noqa: E402

import evidence  # noqa: E402
from tests.lib import devloop  # noqa: E402
from tests.lib.installed import Shell, installed_vm  # noqa: E402

PACKAGES = ("seclegion-wifi", "seclegion-sysmon", "seclegion-settings", "seclegion-desktop",
            "seclegion-branding", "libnm", "python-psutil")
HELPER = "/usr/bin/seclegion-root-apply"  # pkgs/seclegion-settings/PKGBUILD
POLICY = "/usr/share/polkit-1/actions/org.seclegion.settings.policy"
ACTION = "org.seclegion.settings.root-apply"
TZ = "Europe/Berlin"
BAD_TZ = "../../etc/passwd"
USER_UNITS = "/usr/lib/systemd/user"  # pkgs/seclegion-desktop/PKGBUILD: desktop/units/*.service
WANTS = f"{USER_UNITS}/graphical-session.target.wants"  # ... each with a wants symlink here
UNITS = ("seclegion-displayd.service", "seclegion-wallpaper.service")
WALLPAPER = "/usr/share/backgrounds/seclegion/default.png"  # pkgs/seclegion-branding/PKGBUILD
LAUNCHERS = ("/usr/bin/seclegion-display-menu", "/usr/bin/seclegion-sysmon", "/usr/bin/seclegion-wifi")
PYPATH = "/usr/lib/seclegion/python"  # where tools/seclegion-wifi and tools/seclegion-sysmon look


def lines(out):
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def packages(sh):
    rc, out = sh.run("pacman -Q " + " ".join(PACKAGES) + " 2>&1")
    assert rc == 0, out
    for name in PACKAGES:
        assert re.search(rf"^{re.escape(name)} \S+\s*$", out, re.M), (name, out)
    sh.say("M12-PKGS wifi sysmon settings desktop branding libnm psutil installed")


def root_helper(sh):
    rc, out = sh.run(f"stat -c 'MODE %U %G %a' {HELPER}")
    assert rc == 0 and re.search(r"^MODE root root 755\s*$", out, re.M), out
    rc, out = sh.run(f"grep -c 'action id=\"{ACTION}\"' {POLICY}")
    assert rc == 0 and re.search(r"^1\s*$", out, re.M), out
    rc, out = sh.run(f"pkaction --action-id {ACTION}")
    assert rc == 0 and re.search(rf"^{re.escape(ACTION)}:?\s*$", out, re.M), out
    sh.say("M12-HELPER root 755 polkit action registered")


def root_apply(sh):
    sh.sudo_prime()
    rc, out = sh.run(f"sudo -n {HELPER} --dry-run region.timezone {TZ}")
    assert rc == 0, out
    assert re.search(rf"^would run: /usr/bin/timedatectl set-timezone {re.escape(TZ)}\s*$", out, re.M), out
    assert not re.search(r"^running:", out, re.M), out

    rc, out = sh.run(f"sudo -n {HELPER} region.timezone {TZ}")
    assert rc == 0, out
    assert re.search(rf"^running: /usr/bin/timedatectl set-timezone {re.escape(TZ)}\s*$", out, re.M), out
    rc, out = sh.run("readlink /etc/localtime")
    assert rc == 0 and re.search(rf"/{re.escape(TZ)}\s*$", out, re.M), out
    before = lines(out)[-1]

    rc, passwd = sh.run("sha256sum /etc/passwd")
    assert rc == 0, passwd
    rc, out = sh.run(f"sudo -n {HELPER} region.timezone {BAD_TZ}")
    assert rc != 0, out
    assert "not a valid value" in out and not re.search(r"^running:", out, re.M), out
    rc, out = sh.run("readlink /etc/localtime")
    assert rc == 0 and lines(out)[-1] == before, (before, out)
    rc, after = sh.run("sha256sum /etc/passwd")
    assert rc == 0 and re.findall(r"^[0-9a-f]{64}", after, re.M) == re.findall(r"^[0-9a-f]{64}", passwd, re.M)
    sh.say("M12-ROOTAPPLY dry-run then real timezone set bad value refused")


def snapper(sh):
    rc, out = sh.run("stat -c 'MODE %a' /etc/snapper/configs/root")
    assert rc == 0 and re.search(r"^MODE 644\s*$", out, re.M), out
    rc, out = sh.run("test -r /etc/snapper/configs/root")  # as tester, not root
    assert rc == 0, out
    sh.say("M12-SNAPPER config mode 644 readable")


def units(sh):
    for unit in UNITS:
        rc, out = sh.run(f"test -f {USER_UNITS}/{unit}")
        assert rc == 0, (unit, out)
        rc, out = sh.run(f"readlink {WANTS}/{unit}")
        assert rc == 0 and re.search(rf"^{re.escape(USER_UNITS)}/{re.escape(unit)}\s*$", out, re.M), out
    rc, out = sh.run(f"test -s {WALLPAPER}")
    assert rc == 0, out
    for path in LAUNCHERS:
        rc, out = sh.run(f"test -x {path}")
        assert rc == 0, (path, out)
    sh.say("M12-UNITS displayd wallpaper enabled launchers executable")


def imports(sh):
    code = (f"import sys; sys.path.insert(0, \"{PYPATH}\"); "
            "import seclegion_wifi.data, seclegion_sysmon.data; "
            "print(seclegion_wifi.data.__file__); print(seclegion_sysmon.data.__file__)")
    rc, out = sh.run(f"python3 -I -c '{code}'")
    assert rc == 0, out
    for pkg in ("seclegion_wifi", "seclegion_sysmon"):
        assert re.search(rf"^{re.escape(PYPATH)}/{pkg}/data\.py\s*$", out, re.M), (pkg, out)
    sh.say("M12-IMPORTS wifi sysmon data modules import")


def desktop_units_session(vm):
    sh = Shell(vm, "M12RC")
    sh.login()
    packages(sh)
    root_helper(sh)
    root_apply(sh)
    snapper(sh)
    units(sh)
    imports(sh)
    assert PASSWORD not in vm.serial.text()


@pytest.mark.iso
def test_m12_desktop_units():
    def body(result_dir, iso):
        os.makedirs(devloop.SCRATCH_ROOT, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="m12-", dir=devloop.SCRATCH_ROOT)
        try:
            with installed_vm(iso, scratch) as vm:
                command = evidence.repo_relative(vm.command, REPO)
                try:
                    desktop_units_session(vm)
                finally:
                    with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
                        out.write(vm.serial.text())
            return ("desktop packages, root helper and polkit action, timezone apply, snapper mode, "
                    "user units, launchers and imports present on the target"), command, "n/a"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    finish_gate("M12-desktop-units", "the 2026-10-31 desktop work is on the installed target: packages, "
                "root helper with polkit action, timezone apply, snapper config 0644, displayd and wallpaper "
                "user units enabled, launchers and python imports", body)
