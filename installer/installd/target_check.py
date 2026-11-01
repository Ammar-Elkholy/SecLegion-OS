#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Target-clean checker: reads files under an installed root and lists every trace of the live ISO
(live users, passwordless sudo, nullok, autologin, empty hashes, archiso hook, live-only packages
unless the target's hardware plan installed them, live polkit rules) or a weakened trust setup.
Stdlib only.

    target_check.py --root DIR --live-list FILE     one problem per line, exit 1 if any
"""

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post  # noqa: E402

LIVE_USERS = ("seclegion-live", "seclegion-installer")
NOLOGIN = ("nologin", "false")
OS_RELEASE_LINK = "../usr/lib/seclegion/os-release"  # seclegion-release's tmpfiles L+


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _files(root, pattern):
    return sorted(p for p in glob.glob(os.path.join(root, pattern), recursive=True) if os.path.isfile(p))


def _code(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def read_live_list(path):
    """Package names in a live.list (comments stripped): the caller passes the live-only list."""
    with open(path, encoding="utf-8") as f:
        return {ln.split("#")[0].strip() for ln in f if ln.split("#")[0].strip()}


def installed_packages(root, explicit_only=False):
    """Package names in the target's pacman db. explicit_only skips %REASON% 1 (pulled in as a
    dependency): a live-only package is a leftover only if something installed it on purpose."""
    out = set()
    for d in glob.glob(os.path.join(root, "var/lib/pacman/local/*/desc")):
        text = _read(d) or ""
        m = re.search(r"%NAME%\s*\n(\S+)", text)
        if m and not (explicit_only and re.search(r"%REASON%\s*\n1\b", text)):
            out.add(m.group(1))
    return out


def check(root, live_only=()):
    """Problems found under the installed root (empty list = clean)."""
    probs = []
    rel = lambda p: os.path.relpath(p, root)  # noqa: E731
    passwd = _read(os.path.join(root, "etc/passwd")) or ""
    shadow = _read(os.path.join(root, "etc/shadow")) or ""
    group = _read(os.path.join(root, "etc/group")) or ""
    for name, text in (("passwd", passwd), ("shadow", shadow), ("group", group)):
        for ln in text.splitlines():
            if ln.split(":")[0] in LIVE_USERS:
                probs.append(f"live user/group {ln.split(':')[0]} in /etc/{name}")
    shells = {ln.split(":")[0]: ln.split(":")[-1] for ln in passwd.splitlines() if ln.count(":") >= 6}
    for ln in shadow.splitlines():
        f = ln.split(":")
        sh = os.path.basename(shells.get(f[0], "nologin"))
        if len(f) > 1 and f[1] == "" and sh not in NOLOGIN:
            probs.append(f"empty password hash for login user {f[0]}")

    for p in _files(root, "etc/sudoers") + _files(root, "etc/sudoers.d/**"):
        if os.path.basename(p) == "10-seclegion-live":
            probs.append(f"live sudoers file {rel(p)}")
        if any("NOPASSWD" in ln for ln in _code(_read(p))):
            probs.append(f"NOPASSWD in {rel(p)}")

    for p in _files(root, "etc/pam.d/*"):
        if any(re.search(r"\bnullok\b", ln) for ln in _code(_read(p))):
            probs.append(f"nullok in {rel(p)}")

    for p in _files(root, "etc/systemd/system/**/*.conf"):
        if "--autologin" in (_read(p) or ""):
            probs.append(f"autologin in {rel(p)}")
    for p in _files(root, "etc/greetd/**"):
        if any(ln.startswith("initial_session") or ln == "[initial_session]" for ln in _code(_read(p))):
            probs.append(f"greetd initial_session in {rel(p)}")

    for p in _files(root, "etc/mkinitcpio.conf") + _files(root, "etc/mkinitcpio.conf.d/*"):
        for ln in _code(_read(p)):
            if ln.startswith("HOOKS") and "archiso" in ln:
                probs.append(f"archiso hook in {rel(p)}")

    hw = set(_code(_read(os.path.join(root, "var/lib/seclegion/hw-packages"))))
    for n in sorted(installed_packages(root, explicit_only=True) & (set(live_only) - hw)):
        probs.append(f"live-only package installed: {n}")

    for p in _files(root, "etc/polkit-1/rules.d/*"):
        if "seclegion-live" in (_read(p) or ""):
            probs.append(f"live polkit rule {rel(p)}")

    if not os.path.isfile(os.path.join(root, "etc/kernel/cmdline")):
        probs.append("/etc/kernel/cmdline missing")

    osr = os.path.join(root, "etc/os-release")
    if not os.path.lexists(osr):
        probs.append("/etc/os-release missing")
    else:
        if os.path.islink(osr) and os.readlink(osr) != OS_RELEASE_LINK:
            probs.append(f"/etc/os-release is a symlink to {os.readlink(osr)}")
        if re.search(r"^ID=\"?arch\"?\s*$", _read(osr) or "", re.M):
            probs.append("/etc/os-release is Arch's (ID=arch)")

    conf = _read(os.path.join(root, "etc/pacman.conf"))
    if conf is None:
        probs.append("/etc/pacman.conf missing")
    else:
        try:
            post.check_installed_conf(conf)
        except post.PostError as e:
            probs.append(f"pacman.conf: {e}")
        for name, lines in post.split_sections(conf):
            if name == "options":
                # repos without their own SigLevel inherit this one; Arch's default "Required
                # DatabaseOptional" is fine, anything that lets an unsigned package through is not
                for ln in lines:
                    m = re.match(r"\s*SigLevel\s*=(.*)", ln)
                    weak = {
                        "Never",
                        "Optional",
                        "PackageNever",
                        "PackageOptional",
                        "TrustAll",
                        "PackageTrustAll",
                    }
                    if m and weak & set(m.group(1).split("#")[0].split()):
                        probs.append(f"pacman.conf [options] SigLevel weakened:{m.group(1).rstrip()}")
                continue
            if name is None:
                continue
            for ln in lines:
                m = re.match(r"\s*SigLevel\s*=(.*)", ln)
                if m and re.search(r"Optional|Never", m.group(1).split("#")[0]):
                    probs.append(f"pacman.conf [{name}] SigLevel weakened:{m.group(1).rstrip()}")
    return probs


def main(argv=None):
    ap = argparse.ArgumentParser(description="target-clean checker")
    ap.add_argument("--root", required=True)
    ap.add_argument("--live-list", required=True)
    a = ap.parse_args(argv)
    probs = check(a.root, read_live_list(a.live_list))
    for p in probs:
        print(p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
