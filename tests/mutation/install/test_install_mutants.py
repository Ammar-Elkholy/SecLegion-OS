# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Install mutation suite: each mutant breaks a clean target (or the configurator's refusals) and the
checks must catch it. A mutant that passes clean ("green mutant") fails the gate."""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "tests", "install"))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import configurator as c  # noqa: E402
import target_check  # noqa: E402
import target_fixture as fx  # noqa: E402

MB = 1 << 20


def _append(rel, text):
    def m(root):
        with open(os.path.join(root, rel), "a") as f:
            f.write(text)
    return m


def _w(rel, text):
    return lambda root: fx.write(root, rel, text)


def _sub(rel, old, new):
    def m(root):
        p = os.path.join(root, rel)
        with open(p) as f:
            t = f.read()
        assert old in t
        with open(p, "w") as f:
            f.write(t.replace(old, new))
    return m


def _os_release_symlink(root):
    p = os.path.join(root, "etc/os-release")
    os.remove(p)
    os.symlink("../usr/lib/os-release", p)


def _rm_cmdline(root):
    os.remove(os.path.join(root, "etc/kernel/cmdline"))


TARGET_MUTANTS = {
    "install_nopasswd_sudoers": _append("etc/sudoers", "ammar ALL=(ALL) NOPASSWD: ALL\n"),
    "install_nopasswd_dropin": _w("etc/sudoers.d/90-x", "%wheel ALL=(ALL) NOPASSWD: ALL\n"),
    "install_empty_shadow_hash": _sub("etc/shadow", "$6$salt$hashhashhash", ""),
    "install_nullok": _append("etc/pam.d/system-auth", "auth sufficient pam_unix.so nullok\n"),
    "install_live_package": _w("var/lib/pacman/local/mkinitcpio-archiso-1-1/desc",
                               "%NAME%\nmkinitcpio-archiso\n"),
    "install_live_sudoers_file": _w("etc/sudoers.d/10-seclegion-live", "# harmless\n"),
    "install_getty_autologin": _w("etc/systemd/system/getty@tty1.service.d/autologin.conf",
                                  "[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin ammar tty1\n"),
    "install_greetd_initial_session": _append("etc/greetd/config.toml",
                                              '[initial_session]\ncommand = "sh"\nuser = "ammar"\n'),
    "install_live_user_passwd": _append("etc/passwd", "seclegion-live:x:1001:1001::/home/l:/bin/bash\n"),
    "install_live_user_group": _append("etc/group", "seclegion-installer:x:1002:\n"),
    "install_live_polkit_rule": _w("etc/polkit-1/rules.d/49-live.rules",
                                   'if (subject.user == "seclegion-live") return polkit.Result.YES;\n'),
    "install_archiso_hook": _sub("etc/mkinitcpio.conf", "HOOKS=(base", "HOOKS=(base archiso"),
    "install_archiso_hook_dropin": _w("etc/mkinitcpio.conf.d/live.conf", "HOOKS=(base archiso)\n"),
    "install_missing_kernel_cmdline": _rm_cmdline,
    "install_arch_os_release_symlink": _os_release_symlink,
    "install_siglevel_optional_seclegion": _sub("etc/pacman.conf", "Required DatabaseRequired",
                                                "Optional TrustAll"),
    "install_siglevel_never_core": _sub("etc/pacman.conf", "[core]\n", "[core]\nSigLevel = Never\n"),
}


def _facts():
    with open(os.path.join(REPO, "tests", "install", "fixtures", "facts.json")) as f:
        return json.load(f)


def _answers(**kw):
    base = dict(disk="/dev/disk/by-id/ata-QEMU_HARDDISK_vda", username="ammar", password="test-pass-1",
                confirm="QEMU HARDDISK", mode="erase", luks=False, timezone="UTC")
    base.update(kw)
    return c.Answers(**base)


def _mounted_facts():
    f = _facts()
    d = next(d for d in f["lsblk"]["blockdevices"] if d["name"] == "vda")
    d["children"] = [{"name": "vda1", "path": "/dev/vda1", "type": "part", "start": 2048,
                      "size": MB, "mountpoints": ["/mnt/x"]}]
    return f


def refused_code(validate, answers, facts):
    """The Refusal code validate raises, or None if it lets the install through."""
    try:
        validate(answers, facts)
    except c.Refusal as e:
        return e.code
    return None


def _validate_skipping(code):
    """The real validate with one refusal swallowed: the mutant."""
    real = c.validate

    def mutant(answers, facts):
        try:
            return real(answers, facts)
        except c.Refusal as e:
            if e.code != code:
                raise
    return mutant


def _config_problems(validate, answers, facts, code):
    got = refused_code(validate, answers, facts)
    return [] if got == code else [f"validate did not refuse {code} (got {got})"]


CONFIG_MUTANTS = {
    "install_skipped_mounted_refusal": lambda: _config_problems(
        _validate_skipping("mounted"), _answers(), _mounted_facts(), "mounted"),
    "install_wrong_confirm_accepted": lambda: _config_problems(
        _validate_skipping("confirm_mismatch"), _answers(confirm="wrong name"), _facts(),
        "confirm_mismatch"),
}


def run_mutant(name, tmp_path):
    if name in CONFIG_MUTANTS:
        return CONFIG_MUTANTS[name]()
    root = fx.build_clean(tmp_path)
    TARGET_MUTANTS[name](root)
    return target_check.check(root, fx.LIVE_ONLY)


ALL = sorted(list(TARGET_MUTANTS) + list(CONFIG_MUTANTS))


@pytest.mark.parametrize("name", ALL)
def test_install_mutant_is_caught(name, tmp_path):
    assert run_mutant(name, tmp_path), f"green mutant: {name}"


def test_install_real_validate_refuses_mounted_and_wrong_confirm():
    assert refused_code(c.validate, _answers(), _mounted_facts()) == "mounted"
    assert refused_code(c.validate, _answers(confirm="wrong name"), _facts()) == "confirm_mismatch"
    assert refused_code(c.validate, _answers(), _facts()) is None


def test_install_mutant_count_and_none_green(tmp_path):
    assert len(ALL) >= 14
    green = [n for n in ALL if not run_mutant(n, tmp_path / n)]
    assert green == []



def test_install_siglevel_never_in_options_is_caught(tmp_path):
    """Repos without their own SigLevel inherit [options]: a weakened default must be caught too."""
    root = fx.build_clean(tmp_path)
    conf = os.path.join(root, "etc/pacman.conf")
    text = open(conf).read()
    assert "[options]" in text
    with open(conf, "w") as fh:
        fh.write(text.replace("[options]\n", "[options]\nSigLevel = Never\n", 1))
    assert any("[options] SigLevel" in p for p in target_check.check(root, fx.LIVE_ONLY))
