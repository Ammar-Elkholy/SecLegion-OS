# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""CP-C VM (installed base): G38 M6-roles checked on the installed target, not on the repo.

Same harness as test_m6_target.py (cached installed base, `tester` on the serial getty). The roles, the
provider lists and the owners come from desktop/roles.toml via desktop/roles_check.py, not copies.

G38 M6-roles checks on the target: exactly one D-Bus service file naming org.freedesktop.Notifications
  (/usr/share/dbus-1/services, /etc/xdg and tester's ~/.local/share/dbus-1/services) and its package is the
  notifications role's package; exactly one installed package of POLKIT_PROVIDERS, the polkit role's
  package; exactly one org.freedesktop.secrets service file and one installed SECRETS_PROVIDERS package,
  both the secrets role's package; every role's package is installed and its binary is executable.
  NOT checked: which daemon is running (no graphical session on the serial console).
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "desktop"))

import roles_check  # noqa: E402
from test_m6_target import _gate  # noqa: E402

SERVICE_DIRS = "/usr/share/dbus-1/services /etc/xdg /home/tester/.local/share/dbus-1/services"


def _service_files(sh, bus_name):
    # a missing user dir makes grep exit 2 even with matches: read the paths, not the status
    _, out = sh.run(f"grep -rlx 'Name={bus_name}' {SERVICE_DIRS} 2>/dev/null")
    return re.findall(r"^/\S+$", out, re.M)


def _owner(sh, path):
    rc, out = sh.run(f"pacman -Qoq {path} 2>/dev/null")
    return re.findall(r"^[\w.+@-]+$", out, re.M) if rc == 0 else []


def _installed(sh, candidates):
    rc, out = sh.run("pacman -Qq 2>/dev/null")
    assert rc == 0 and len(out.split()) > 100, out
    have = set(out.split())
    return sorted(p for p in candidates if p in have)


def roles_target(sh):
    roles = roles_check.load()

    files = _service_files(sh, "org.freedesktop.Notifications")
    assert len(files) == 1, f"Notifications service files: {files}"
    assert _owner(sh, files[0]) == [roles["notifications"]["package"]], (files, _owner(sh, files[0]))
    assert _installed(sh, roles_check.NOTIFICATION_PROVIDERS) == [roles["notifications"]["package"]]
    sh.say(f"M6-ROLES notifications one service file owner {roles['notifications']['package']}")

    assert _installed(sh, roles_check.POLKIT_PROVIDERS) == [roles["polkit"]["package"]]
    sh.say("M6-ROLES polkit one agent installed")

    files = _service_files(sh, "org.freedesktop.secrets")
    assert len(files) == 1, f"secrets service files: {files}"
    assert _owner(sh, files[0]) == [roles["secrets"]["package"]], (files, _owner(sh, files[0]))
    assert _installed(sh, roles_check.SECRETS_PROVIDERS) == [roles["secrets"]["package"]]
    sh.say("M6-ROLES secrets one provider installed")

    for name, role in roles.items():
        rc, out = sh.run(f"pacman -Qq {role['package']} 2>/dev/null")
        assert rc == 0, f"role {name}: package {role['package']} not installed: {out}"
        rc, out = sh.run(f"test -x {role['binary']}")
        assert rc == 0, f"role {name}: {role['binary']} missing or not executable: {out}"
    sh.say("M6-ROLES every role package installed binary present")


@pytest.mark.iso
def test_m6_roles_target():
    _gate("M6-roles", "M6RLC", roles_target,
          "one Notifications service file, one polkit and one secrets provider, role binaries present",
          "the installed system has one owner each for notifications, polkit and secrets and one "
          "Notifications D-Bus service file; every role package is installed with its binary")
