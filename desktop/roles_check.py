# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Check desktop/roles.toml: one owner per role, owner packaged, binary shipped, one notification daemon."""
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Packages that install an org.freedesktop.Notifications D-Bus service file.
NOTIFICATION_PROVIDERS = ("swaync", "mako", "dunst", "deadd-notification-center")
# Polkit authentication agents and org.freedesktop.secrets providers; only the role owner may be installed.
POLKIT_PROVIDERS = ("hyprpolkitagent", "polkit-gnome", "polkit-kde-agent", "lxqt-policykit", "mate-polkit",
                    "xfce-polkit", "lxsession")
SECRETS_PROVIDERS = ("gnome-keyring", "kwallet", "keepassxc")
STARTS = {"unit", "bind", "dbus"}
REQUIRED = {"notifications", "polkit", "secrets", "osd", "idle", "lock", "bar", "launcher"}


def read_list(path):
    out = set()
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def load(path=ROOT / "desktop" / "roles.toml"):
    return tomllib.loads(pathlib.Path(path).read_text())["role"]


def package_lists():
    pk = set()
    for f in ("desktop.list", "base.list", "seclegion.list"):
        pk |= read_list(ROOT / "iso" / "packages" / f)
    return pk


def check(roles, packages, units_dir=ROOT / "desktop" / "units", files_of=None):
    """Return a list of problems. files_of(pkg) -> iterable of paths, or None when unknown."""
    errs = [f"role {m}: no owner" for m in sorted(REQUIRED - set(roles))]
    for name, r in roles.items():
        for k in ("package", "binary", "start"):
            if k not in r:
                errs.append(f"role {name}: missing {k}")
        if r.get("package") not in packages:
            errs.append(f"role {name}: package {r.get('package')} is not in the package lists")
        if r.get("start") not in STARTS:
            errs.append(f"role {name}: unknown start {r.get('start')!r}")
        if r.get("start") == "unit" and not (pathlib.Path(units_dir) / r.get("unit", "-")).is_file():
            errs.append(f"role {name}: unit {r.get('unit')} is not shipped in desktop/units")
        if files_of and r.get("package"):
            files = files_of(r["package"])
            if files is not None and r.get("binary") not in set(files):
                errs.append(f"role {name}: {r.get('binary')} is not shipped by {r['package']}")
    owner = roles.get("notifications", {}).get("package")
    listed = sorted(p for p in NOTIFICATION_PROVIDERS if p in packages)
    if [p for p in listed if p != owner]:
        errs.append(f"notifications: more than one provider of org.freedesktop.Notifications: {listed}")
    owners = [n for n, r in roles.items() if r.get("dbus_name") == "org.freedesktop.Notifications"]
    if len(owners) != 1:
        errs.append(f"org.freedesktop.Notifications must have exactly one owner, got {owners}")
    return errs
