# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-post tests: a tmp fake root, commands recorded (never run). No VM, no root."""

import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import hwplan  # noqa: E402
import post  # noqa: E402

PASSWORD = "fixture-pw-8c1f"
PACMAN_CONF = """[options]
HoldPkg = pacman glibc
Architecture = auto
SigLevel = Required DatabaseOptional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

#[multilib]
#Include = /etc/pacman.d/mirrorlist
"""
HINTS = {"username": "ammar", "keyboard_extra": ["ara"]}
SNAPPER_TEMPLATE = """# subvolume to snapshot
SUBVOLUME="/"
FSTYPE="btrfs"
QGROUP=""
NUMBER_CLEANUP="yes"
NUMBER_LIMIT="50"
TIMELINE_CREATE="yes"
"""
AFTER_RULES = "# rules.input-after\n-A ufw-after-input -p udp --dport 137 -j DROP\nCOMMIT\n"
SECRET = f'{{"users": [{{"username": "ammar", "!password": "{PASSWORD}"}}]}}'


def make_root(tmp_path):
    root = tmp_path / "mnt"
    creds = tmp_path / "creds"
    for d in ("etc/ufw", "etc/default", "var/log/archinstall", "etc/conf.d"):
        (root / d).mkdir(parents=True)
    for d in ("usr/share/snapper/config-templates",):
        (root / d).mkdir(parents=True)
    creds.mkdir()
    (root / "etc/pacman.conf").write_text(PACMAN_CONF)
    (root / "usr/share/snapper/config-templates/default").write_text(SNAPPER_TEMPLATE)
    (root / "etc/conf.d/snapper").write_text('## Path: System/Snapper\nSNAPPER_CONFIGS=""\n')
    (root / "etc/ufw/ufw.conf").write_text("# ufw\nENABLED=no\nLOGLEVEL=low\n")
    (root / "etc/default/ufw").write_text('DEFAULT_INPUT_POLICY="ACCEPT"\n')
    for name in ("after.rules", "after6.rules"):
        (root / "etc/ufw" / name).write_text(AFTER_RULES)
    (creds / "user_credentials.json").write_text(SECRET)
    (root / "var/log/archinstall/user_credentials.json").write_text(SECRET)
    return root, creds


def run_post(tmp_path):
    root, creds = make_root(tmp_path)
    cmds = []
    p = post.Post(str(root), cmds.append, creds_dir=str(creds), hints=HINTS)
    p.steps()
    return p, root, creds, cmds


def test_post_allowlist(tmp_path):
    p, root, _, _ = run_post(tmp_path)
    want = set(open(os.path.join(HERE, "fixtures", "post-allowlist.txt")).read().split())
    assert set(p.written) == want and len(p.written) == len(want)
    # on disk: every file or link under the root is in the allowlist or was there before
    before = {
        "etc/pacman.conf",
        "etc/ufw/ufw.conf",
        "etc/default/ufw",
        "etc/ufw/after.rules",
        "etc/ufw/after6.rules",
        "usr/share/snapper/config-templates/default",
        "etc/conf.d/snapper",
    }
    found = {os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs}
    assert found == want | before - set()


def test_dry_run_writes_nothing(tmp_path):
    root, creds = make_root(tmp_path)
    cmds = []
    p = post.Post(str(root), cmds.append, dry_run=True, creds_dir=str(creds), hints=HINTS)
    p.steps()
    assert cmds == [] and p.commands
    assert (root / "etc/pacman.conf").read_text() == PACMAN_CONF
    assert (creds / "user_credentials.json").exists()
    assert not (root / "etc/greetd").exists()


def test_no_secret_in_target(tmp_path):
    p, root, creds, _ = run_post(tmp_path)
    assert not (creds / "user_credentials.json").exists()
    assert not (root / "var/log/archinstall/user_credentials.json").exists()
    assert len(p.deleted) == 2
    for d, _, fs in os.walk(root):
        for f in fs:
            path = os.path.join(d, f)
            if not os.path.islink(path):
                assert PASSWORD not in open(path).read(), path


def test_post_sshd_masked_ufw_deny(tmp_path):
    _, root, _, cmds = run_post(tmp_path)
    for u in ("sshd.service", "sshd.socket", "sshd@.service", "sshd-unix-local.socket"):
        link = root / "etc/systemd/system" / u
        assert link.is_symlink() and os.readlink(link) == "/dev/null"
    assert "ENABLED=yes" in (root / "etc/ufw/ufw.conf").read_text().splitlines()
    assert 'DEFAULT_INPUT_POLICY="DROP"' in (root / "etc/default/ufw").read_text().splitlines()
    en = [c for c in cmds if "enable" in c][0]
    assert "ufw.service" in en and "greetd.service" in en


def test_post_docker_user_block_in_both_after_rules_once(tmp_path):
    _, root, _, _ = run_post(tmp_path)
    for name in ("after.rules", "after6.rules"):
        text = (root / "etc/ufw" / name).read_text()
        assert text.startswith(AFTER_RULES), name  # the distro's rules stay first
        assert text.count(post.DOCKER_USER_BEGIN) == 1 and text.count("# END seclegion docker-user") == 1
        rules = text.splitlines()
        jump = rules.index("-A DOCKER-USER -j ufw-user-forward")
        drop = rules.index("-A DOCKER-USER -m conntrack --ctstate NEW -j DROP")
        assert jump < drop  # ufw decides first, then everything new from outside is dropped
        assert "-A DOCKER-USER -i docker0 -j RETURN" in rules and "-A DOCKER-USER -i br-+ -j RETURN" in rules


def test_post_docker_user_declares_every_chain_it_jumps_to(tmp_path):
    """ufw-init restores before.rules, after.rules, then user.rules: a jump in the after.rules block to a
    chain only user.rules declares (ufw-user-forward) fails the restore, and ufw.service with it."""
    _, root, _, _ = run_post(tmp_path)
    builtin = {"ACCEPT", "DROP", "RETURN", "REJECT", "LOG"}
    for name in ("after.rules", "after6.rules"):
        block = (root / "etc/ufw" / name).read_text().split(post.DOCKER_USER_BEGIN)[1]
        declared = set(re.findall(r"^:(\S+) ", block, re.M))
        jumps = set(re.findall(r" -j (\S+)", block)) - builtin
        assert jumps and jumps <= declared, (name, jumps - declared)


def test_with_docker_user_is_idempotent():
    once = post.with_docker_user(AFTER_RULES)
    assert once != AFTER_RULES and post.with_docker_user(once) == once
    assert post.with_docker_user("no trailing newline").startswith("no trailing newline\n# BEGIN")


def test_post_siglevel_required(tmp_path):
    """The install-time conf (with_seclegion) is strict; the final one keeps the same SigLevel, commented."""
    _, root, _, _ = run_post(tmp_path)
    final = (root / "etc/pacman.conf").read_text()
    post.check_installed_conf(final)
    assert "#SigLevel = Required DatabaseRequired" in final
    assert "Optional" not in final.split("#[seclegion]")[1]
    conf = post.with_seclegion(final)
    post.check_pacman_conf(conf)
    assert conf.index("[seclegion]") > conf.index("[extra]")
    sec = conf.split("\n[seclegion]")[1]
    assert "Optional" not in sec and "SigLevel = Required DatabaseRequired" in sec
    for bad in (
        conf.replace("SigLevel = Required DatabaseRequired", "SigLevel = Optional"),
        conf.replace("Required DatabaseRequired", "Required DatabaseOptional"),
        conf.replace("Server = file:///opt", "Server = file:///x"),
    ):
        with pytest.raises(post.PostError):
            post.check_pacman_conf(bad)


def test_post_keyring_first_and_order(tmp_path):
    _, _, _, cmds = run_post(tmp_path)
    flat = [" ".join(c) for c in cmds]
    i_key = next(i for i, c in enumerate(flat) if "seclegion-keyring" in c)
    i_pop = next(i for i, c in enumerate(flat) if "pacman-key --populate seclegion" in c)
    i_all = next(i for i, c in enumerate(flat) if "seclegion-desktop" in c)
    assert i_key < i_pop < i_all
    assert any(
        c[2:4] == ["seclegion-host", "--system"] and c[0] == "arch-chroot" and c[-1] == "ammar" for c in cmds
    )


def test_post_snapper_root_config_and_snap_pac(tmp_path):
    p, root, _, cmds = run_post(tmp_path)
    cfg = dict(
        ln.split("=", 1) for ln in (root / "etc/snapper/configs/root").read_text().splitlines() if "=" in ln
    )
    assert cfg["SUBVOLUME"] == '"/"' and cfg["TIMELINE_CREATE"] == '"no"' and cfg["NUMBER_LIMIT"] == '"50"'
    assert 'SNAPPER_CONFIGS="root"' in (root / "etc/conf.d/snapper").read_text().splitlines()
    # Settings reads NUMBER_LIMIT as the user
    assert (root / "etc/snapper/configs/root").stat().st_mode & 0o777 == 0o644
    assert "snapper" in p.packages and "snap-pac" in p.packages and "seclegion-rescue" in p.packages
    flat = [" ".join(c) for c in cmds]
    i_pkgs = next(i for i, c in enumerate(flat) if "pacman -S --noconfirm --needed" in c and "snap-pac" in c)
    i_chmod = flat.index(f"chmod 750 {root}/.snapshots")
    assert i_pkgs < i_chmod
    # the pitfall: nothing may run create-config (it would make its own /.snapshots over the mounted one)
    assert not any("create-config" in c for c in flat)
    assert any(c.endswith("enable snapper-cleanup.timer") for c in flat)


def test_post_real_run_sets_snap_pac_skip(monkeypatch):
    """snap-pac's documented switch: the install's own pacman transactions take no snapshot pairs."""
    seen = []
    monkeypatch.setattr(post.subprocess, "run", lambda argv, **kw: seen.append((argv, kw)))
    monkeypatch.delenv("SNAP_PAC_SKIP", raising=False)
    post.real_run(["arch-chroot", "/mnt", "pacman", "-S", "x"])
    argv, kw = seen[0]
    assert argv[2:4] == ["pacman", "-S"] and kw["check"] is True
    assert kw["env"]["SNAP_PAC_SKIP"] == "y" and kw["env"]["PATH"] == os.environ["PATH"]


def test_post_single_session(tmp_path):
    _, root, _, _ = run_post(tmp_path)
    cfg = (root / "etc/greetd/config.toml").read_text()
    assert "[initial_session]" not in cfg and cfg.count("command =") == 1
    assert "regreet" in cfg and "SESSION_DIRS=/etc/greetd/sessions" in cfg
    sessions = list((root / "etc/greetd/sessions").iterdir())
    assert [s.name for s in sessions] == ["hyprland.desktop"]
    assert "Exec=uwsm start -- hyprland.desktop" in sessions[0].read_text()


def test_post_packages_exist():
    names = post.read_packages()
    assert names[0] == "seclegion-keyring" and len(names) == len(set(names))
    pkgs = {d for d in os.listdir(os.path.join(REPO, "pkgs")) if d.startswith("seclegion-")}
    mine = {n for n in names if n.startswith("seclegion-")}
    assert mine <= pkgs
    desktop = {ln.split("#")[0].strip() for ln in open(os.path.join(REPO, "iso/packages/desktop.list"))}
    desktop.discard("")
    assert desktop <= set(names)


OFFLINE_CONF = """[options]
SigLevel = Required DatabaseOptional

[seclegion-cache]
Server = file:///opt/seclegion/cache

[seclegion]
SigLevel = Required DatabaseRequired
Server = file:///opt/seclegion/cache/seclegion
"""


def test_post_imports_live_key_before_any_pacman(tmp_path):
    root, creds = make_root(tmp_path)
    cmds = []
    post.Post(str(root), cmds.append, creds_dir=str(creds), hints=HINTS, fingerprints=["AB12"]).steps()
    flat = [" ".join(c) for c in cmds]
    i_add = next(
        i for i, c in enumerate(flat) if "pacman-key --gpgdir" in c and "--add " + post.KEYRING_GPG in c
    )
    i_sign = next(i for i, c in enumerate(flat) if "--lsign-key AB12" in c)
    i_sy = next(i for i, c in enumerate(flat) if "pacman -Sy" in c)
    assert i_add < i_sign < i_sy


def test_post_final_conf_has_no_offline_cache_repo(tmp_path):
    root, creds = make_root(tmp_path)
    (root / "etc/pacman.conf").write_text(OFFLINE_CONF)
    post.Post(str(root), lambda c: None, creds_dir=str(creds), hints=HINTS).steps()
    conf = (root / "etc/pacman.conf").read_text()
    assert "seclegion-cache" not in conf and "opt/seclegion/cache\n" not in conf
    assert conf.index("[core]") < conf.index("[extra]") < conf.index("#[seclegion]")
    post.check_installed_conf(conf)


def test_post_skip_missing_is_opt_in(tmp_path):
    root, creds = make_root(tmp_path)
    cmds = []
    kw = dict(creds_dir=str(creds), hints=HINTS, available=lambda p: p != "uwsm")
    post.Post(str(root), cmds.append, **kw).steps()
    assert any("uwsm" in c for c in cmds[-30:] if c[:3] == ["arch-chroot", str(root), "pacman"])
    root2, creds2 = make_root(tmp_path / "b")
    cmds2 = []
    p = post.Post(
        str(root2),
        cmds2.append,
        creds_dir=str(creds2),
        hints=HINTS,
        available=lambda p: p != "uwsm",
        skip_missing=True,
    )
    p.steps()
    assert p.skipped == ["uwsm"]
    assert not any("uwsm" in c for c in cmds2 if "-S" in c)


def test_post_dev_adds_serial_console(tmp_path):
    root, creds = make_root(tmp_path)
    (root / "etc/kernel").mkdir()
    (root / "etc/kernel/cmdline").write_text("root=UUID=x rw\n")
    cmds = []
    post.Post(str(root), cmds.append, creds_dir=str(creds), hints=dict(HINTS, dev=True)).steps()
    assert (root / "etc/kernel/cmdline").read_text() == "root=UUID=x rw console=ttyS0,115200\n"
    assert ["arch-chroot", str(root), "mkinitcpio", "-P"] in cmds


def test_post_enables_firstboot(tmp_path):
    _, _, _, cmds = run_post(tmp_path)
    assert any("enable" in c and "seclegion-firstboot.service" in c for c in cmds)


def test_post_drops_pambase_nullok(tmp_path):
    """Arch's pambase allows an empty password (nullok); the installed system must not (target_check)."""
    root, creds = make_root(tmp_path)
    (root / "etc/pam.d").mkdir()
    line = "auth       [success=1 default=bad]     pam_unix.so          try_first_pass nullok\n"
    (root / "etc/pam.d/system-auth").write_text("#%PAM-1.0\n" + line + "password required pam_unix.so\n")
    (root / "etc/pam.d/other").write_text("auth required pam_deny.so\n")
    p = post.Post(str(root), lambda c: None, creds_dir=str(creds), hints=HINTS)
    p.steps()
    text = (root / "etc/pam.d/system-auth").read_text()
    assert "nullok" not in text and "try_first_pass\n" in text
    assert "etc/pam.d/system-auth" in p.written and "etc/pam.d/other" not in p.written


def test_post_copies_skel_after_packages_before_seclegion_host(tmp_path):
    """The user exists before seclegion-dotfiles fills /etc/skel (Hyprland started with an autogenerated
    config on the I2 install): post copies skel into the home, never overwriting, then seclegion-host runs."""
    _, root, _, cmds = run_post(tmp_path)
    i_pkgs = max(i for i, c in enumerate(cmds) if "seclegion-desktop" in c)
    i_cp = cmds.index(["arch-chroot", str(root), "cp", "-a", "-n", "/etc/skel/.", "/home/ammar/"])
    i_own = cmds.index(["arch-chroot", str(root), "chown", "-R", "ammar:", "/home/ammar"])
    i_host = next(i for i, c in enumerate(cmds) if c[2:4] == ["seclegion-host", "--system"])
    assert i_pkgs < i_cp < i_own < i_host


@pytest.mark.parametrize("bad", ["../root", "a/b", "Ammar", "x y"])
def test_post_refuses_a_bad_username_in_hints(tmp_path, bad):
    root, creds = make_root(tmp_path)
    with pytest.raises(post.PostError):
        post.Post(str(root), lambda c: None, creds_dir=str(creds), hints=dict(HINTS, username=bad)).steps()


DEV_PACKAGES = ("git", "openssh", "gnupg", "base-devel", post.ENGINE, "socat")
# in the offline cache only as dependencies: gvfs -> gcr-4 -> openssh, pacman -> gnupg
# (the iso lists may not name openssh: tests/iso/test_m2_static.py, docs/decisions.md M2-openssh)
CACHED_AS_DEPENDENCY = {"openssh", "gnupg"}


def test_post_installs_the_dev_profile(tmp_path):
    assert set(DEV_PACKAGES) <= set(post.read_packages())
    _, _, _, cmds = run_post(tmp_path)
    install = next(c for c in cmds if c[:4] == ["arch-chroot", c[1], "pacman", "-S"])
    assert set(DEV_PACKAGES) <= set(install)


def test_post_packages_resolve_from_the_offline_cache_lists():
    have = set()
    for n in ("base", "desktop", "cache"):
        have |= {ln.split("#")[0].strip() for ln in open(os.path.join(REPO, f"iso/packages/{n}.list"))}
    official = {n for n in post.read_packages() if not n.startswith("seclegion-")}
    assert official - have == CACHED_AS_DEPENDENCY


def test_post_openssh_is_client_only(tmp_path):
    _, root, _, cmds = run_post(tmp_path)
    assert "openssh" in post.read_packages()
    for u in post.SSHD_MASKED:
        link = root / "etc/systemd/system" / u
        assert link.is_symlink() and os.readlink(link) == "/dev/null"
    enabled = [u for c in cmds if c[:2] == ["systemctl", "--root"] and "enable" in c for u in c[4:]]
    assert enabled and not [u for u in enabled if u.startswith("sshd")]


def test_post_enables_docker_and_adds_the_user_to_its_group(tmp_path):
    _, _, _, cmds = run_post(tmp_path)
    flat = [" ".join(c) for c in cmds]
    i_pk = next(i for i, c in enumerate(cmds) if c[2:4] == ["pacman", "-S"] and post.ENGINE in c)
    i_en = flat.index(f"systemctl --root {cmds[i_pk][1]} enable {post.ENGINE}.service")
    i_grp = flat.index(f"arch-chroot {cmds[i_pk][1]} usermod -a -G {post.ENGINE} ammar")
    assert i_pk < i_en and i_pk < i_grp


# --- hwdetect's plan applied to the target (docs/DAILY-DRIVER.md gap 1b) ---------------------------------

HYBRID_PLAN = json.loads(
    open(os.path.join(REPO, "hw/fixtures/legion-slim5-16ahp9-hybrid/expected-plan.json")).read()
)
CMDLINE = "root=UUID=x rw\n"
NVIDIA_PARAMS = " nvidia-drm.modeset=1 nvidia.NVreg_PreserveVideoMemoryAllocations=1"


def run_with_plan(tmp_path, plan, hints=HINTS, runner=None, **kw):
    """Post with a hardware plan; the runner snapshots /etc/kernel/cmdline at each mkinitcpio run."""
    root, creds = make_root(tmp_path)
    (root / "etc/kernel").mkdir()
    (root / "etc/kernel/cmdline").write_text(CMDLINE)
    cmds, at_rebuild = [], []

    def record(argv):
        cmds.append(argv)
        if argv[2:4] == ["mkinitcpio", "-P"]:
            at_rebuild.append((root / "etc/kernel/cmdline").read_text())
        if runner:
            runner(argv)

    source = plan if callable(plan) else (lambda: plan)
    p = post.Post(str(root), record, creds_dir=str(creds), hints=hints, plan_source=source, **kw)
    p.steps()
    return p, root, cmds, at_rebuild


def main_install(cmds):
    return next(c for c in cmds if c[2:4] == ["pacman", "-S"] and "seclegion-desktop" in c)


def rebuilds(cmds):
    return [c for c in cmds if c[2:4] == ["mkinitcpio", "-P"]]


def test_post_hwdetect_plan_packages_join_the_one_pacman_call(tmp_path):
    _, _, cmds, _ = run_with_plan(tmp_path, HYBRID_PLAN)
    install = main_install(cmds)
    for pkg in ("nvidia-open", "nvidia-utils", "libva-nvidia-driver", "switcheroo-control", "nvidia-prime"):
        assert install.count(pkg) == 1, pkg
    assert install.count("mesa") == 1 and install.count("vulkan-radeon") == 1  # already listed: once
    # the plan is read in the target, so hwdetect itself is installed before that call
    i_tool = next(i for i, c in enumerate(cmds) if c[2:4] == ["pacman", "-S"] and "seclegion-hwdetect" in c)
    assert i_tool < cmds.index(install)


def test_post_hwdetect_plan_packages_are_recorded_for_target_check(tmp_path):
    p, root, _, _ = run_with_plan(tmp_path, HYBRID_PLAN)
    assert post.HW_PACKAGES == "var/lib/seclegion/hw-packages" and post.HW_PACKAGES in p.written
    lines = (root / post.HW_PACKAGES).read_text().splitlines()
    assert lines[0].startswith("#") and lines[1:] == sorted(set(HYBRID_PLAN["packages"]))


def test_post_hwdetect_plan_record_leaves_out_skipped_packages(tmp_path):
    p, root, _, _ = run_with_plan(
        tmp_path, HYBRID_PLAN, available=lambda x: x != "nvidia-prime", skip_missing=True
    )
    assert "nvidia-prime" in p.skipped
    lines = (root / post.HW_PACKAGES).read_text().splitlines()[1:]
    assert "nvidia-prime" not in lines and "nvidia-open" in lines


def test_post_hwdetect_plan_kernel_params_one_rebuild(tmp_path):
    _, root, cmds, at_rebuild = run_with_plan(tmp_path, HYBRID_PLAN)
    want = CMDLINE.strip() + NVIDIA_PARAMS + "\n"
    assert (root / "etc/kernel/cmdline").read_text() == want
    assert rebuilds(cmds) == [["arch-chroot", str(root), "mkinitcpio", "-P"]]
    assert at_rebuild == [want]  # the parameters were on disk when the UKI was rebuilt


def test_post_hwdetect_plan_dev_console_shares_the_one_rebuild(tmp_path):
    _, root, cmds, at_rebuild = run_with_plan(tmp_path, HYBRID_PLAN, hints=dict(HINTS, dev=True))
    text = (root / "etc/kernel/cmdline").read_text()
    assert text == CMDLINE.strip() + NVIDIA_PARAMS + " console=ttyS0,115200\n"
    assert len(rebuilds(cmds)) == 1 and at_rebuild == [text]


def test_post_hwdetect_plan_enables_the_nvidia_services(tmp_path):
    _, root, cmds, _ = run_with_plan(tmp_path, HYBRID_PLAN)
    units = ["nvidia-suspend.service", "nvidia-resume.service", "nvidia-hibernate.service"]
    enable = ["systemctl", "--root", str(root), "enable", *units]
    assert enable in cmds and cmds.index(enable) > cmds.index(main_install(cmds))  # after their package


def test_post_hwdetect_plan_env_is_written_where_the_session_reads_it(tmp_path):
    p, root, _, _ = run_with_plan(tmp_path, HYBRID_PLAN)
    assert post.HW_ENV == "etc/environment.d/50-seclegion-hw.conf" and post.HW_ENV in p.written
    lines = (root / post.HW_ENV).read_text().splitlines()
    assert f"AQ_DRM_DEVICES={HYBRID_PLAN['env']['AQ_DRM_DEVICES']}" in lines
    assert all(ln.startswith("#") or "=" in ln for ln in lines)


def test_post_hwdetect_plan_writes_the_gpu_udev_rules(tmp_path):
    p, root, _, _ = run_with_plan(tmp_path, HYBRID_PLAN)
    assert post.HW_UDEV == "etc/udev/rules.d/61-seclegion-gpu.rules" and post.HW_UDEV in p.written
    lines = [ln for ln in (root / post.HW_UDEV).read_text().splitlines() if not ln.startswith("#")]
    assert lines == HYBRID_PLAN["udev_rules"] and len(lines) == 2
    assert 'KERNELS=="0000:65:00.0"' in lines[0] and 'KERNELS=="0000:01:00.0"' in lines[1]


def test_post_hwdetect_empty_plan_writes_no_package_record(tmp_path):
    plan = {"packages": [], "kernel_params": [], "services": [], "env": {}}
    p, root, _, _ = run_with_plan(tmp_path, plan)
    assert post.HW_PACKAGES not in p.written and not (root / post.HW_PACKAGES).exists()


def test_post_hwdetect_plan_logs_warnings_and_messages(tmp_path, capsys):
    plan = dict(HYBRID_PLAN, warnings=["unknown GPU 1234:5678"], messages=["older than Turing"])
    run_with_plan(tmp_path, plan)
    err = capsys.readouterr().err
    assert "unknown GPU 1234:5678" in err and "older than Turing" in err


def test_post_hwdetect_plan_without_gpu_extras_writes_nothing_extra(tmp_path):
    plan = {"packages": ["linux-firmware", "mesa"], "kernel_params": [], "services": [], "env": {}}
    p, root, cmds, _ = run_with_plan(tmp_path, plan)
    want = set(open(os.path.join(HERE, "fixtures", "post-allowlist.txt")).read().split())
    assert (root / post.HW_PACKAGES).read_text().splitlines()[1:] == ["linux-firmware", "mesa"]
    want.add(post.HW_PACKAGES)
    assert set(p.written) == want and not (root / "etc/environment.d").exists()
    assert (root / "etc/kernel/cmdline").read_text() == CMDLINE and not rebuilds(cmds)
    enabled = [u for c in cmds if c[:2] == ["systemctl", "--root"] for u in c[4:]]
    assert not [u for u in enabled if u.startswith("nvidia")]
    assert "nvidia-open" not in main_install(cmds)


def test_post_hwdetect_without_a_plan_source_runs_no_hwdetect(tmp_path):
    _, _, _, cmds = run_post(tmp_path)
    assert not [c for c in cmds if "seclegion-hwdetect" in c and "seclegion-desktop" not in c]


def raise_called_process():
    raise subprocess.CalledProcessError(1, ["arch-chroot", "root", "seclegion-hwdetect"])


def raise_bad_json():
    raise json.JSONDecodeError("Expecting value", "", 0)


def raise_timeout():
    raise subprocess.TimeoutExpired("seclegion-hwdetect", 60)


@pytest.mark.parametrize(
    "plan",
    [
        raise_called_process,
        raise_bad_json,
        raise_timeout,
        lambda: {"packages": ["nvidia-open"], "kernel_params": ["quiet\nroot=/dev/sda"]},
        lambda: ["not", "an", "object"],
    ],
    ids=["exit-1", "bad-json", "timeout", "unsafe-value", "not-a-dict"],
)
def test_post_hwdetect_failure_does_not_abort_the_install(tmp_path, plan, capsys):
    p, root, cmds, _ = run_with_plan(tmp_path, plan)
    assert "nvidia-open" not in main_install(cmds)  # the base set still installs
    assert (root / "etc/kernel/cmdline").read_text() == CMDLINE and not rebuilds(cmds)
    assert not (root / "etc/environment.d").exists()
    assert len(p.warnings) == 1 and "hardware plan unavailable" in capsys.readouterr().err
    assert any(c[2:4] == ["seclegion-host", "--system"] for c in cmds)  # post ran to the end


def test_post_hwdetect_install_failure_does_not_abort_the_install(tmp_path):
    def fail_tool_install(argv):
        if argv[2:4] == ["pacman", "-S"] and "seclegion-hwdetect" in argv and "seclegion-desktop" not in argv:
            raise subprocess.CalledProcessError(1, argv)

    p, _, cmds, _ = run_with_plan(tmp_path, HYBRID_PLAN, runner=fail_tool_install)
    assert len(p.warnings) == 1 and "nvidia-open" not in main_install(cmds)


def test_post_hwdetect_service_enable_failure_is_a_warning(tmp_path):
    def fail_enable(argv):
        if argv[:2] == ["systemctl", "--root"] and "nvidia-suspend.service" in argv:
            raise subprocess.CalledProcessError(1, argv)

    p, root, cmds, _ = run_with_plan(tmp_path, HYBRID_PLAN, runner=fail_enable)
    assert len(p.warnings) == 1 and "hardware services" in p.warnings[0]
    assert (root / post.HW_ENV).exists() and any(c[2:4] == ["seclegion-host", "--system"] for c in cmds)


def test_post_hwdetect_dry_run_does_not_ask_for_the_plan(tmp_path):
    root, creds = make_root(tmp_path)

    def never():
        raise AssertionError("dry run must not run hwdetect")

    p = post.Post(
        str(root), lambda c: None, dry_run=True, creds_dir=str(creds), hints=HINTS, plan_source=never
    )
    p.steps()
    assert not p.warnings and not (root / "etc/environment.d").exists()


@pytest.mark.parametrize(
    "bad",
    [
        {"kernel_params": ["a b"]},
        {"kernel_params": ["quiet\n"]},
        {"packages": ["Nvidia Open"]},
        {"packages": [""]},
        {"services": ["x; reboot"]},
        {"services": ["nvidia-suspend"]},
        {"udev_rules": ['KERNEL=="card*", RUN+="/bin/sh -c x"']},
        {"udev_rules": [HYBRID_PLAN["udev_rules"][0] + ', RUN+="/bin/true"']},
        {"udev_rules": [HYBRID_PLAN["udev_rules"][0].replace("0000:65:00.0", "0000:65:00.0\n")]},
        {"udev_rules": [HYBRID_PLAN["udev_rules"][0].replace("seclegion-igpu", "x")]},
        {"udev_rules": "x"},
        {"env": {"A B": "x"}},
        {"env": {"AQ": "a\nB=c"}},
        {"env": {"AQ": "$HOME"}},
        {"env": {"AQ": 1}},
        {"env": ["AQ=1"]},
    ],
)
def test_hwplan_clean_rejects_unsafe_values(bad):
    with pytest.raises(ValueError):
        hwplan.clean(bad)


@pytest.mark.parametrize(
    "name", ["legion-slim5-16ahp9-hybrid", "legion-slim5-16ahp9-discrete", "pascal", "vm"]
)
def test_hwplan_clean_accepts_the_fixture_plans(name):
    plan = json.loads(open(os.path.join(REPO, "hw/fixtures", name, "expected-plan.json")).read())
    out = hwplan.clean(plan)
    assert out["packages"] == list(dict.fromkeys(plan["packages"]))
    assert out["kernel_params"] == plan["kernel_params"] and out["env"] == plan["env"]
    assert out["udev_rules"] == plan["udev_rules"]


FSTAB = """# /dev/vda2
UUID=ab /         btrfs rw,relatime,compress=zstd:3,subvolid=256,subvol=/@ 0 0
UUID=ab /home     btrfs rw,relatime,subvolid=257,subvol=/@home 0 0
UUID=ab /mnt/top  btrfs rw,subvolid=5 0 0
UUID=cd /boot     vfat  rw,relatime,fmask=0077 0 2
"""


def test_post_fstab_drops_subvolid_for_rollback(tmp_path):
    root, creds = make_root(tmp_path)
    (root / "etc/fstab").write_text(FSTAB)
    post.Post(str(root), [].append, creds_dir=str(creds), hints=HINTS).steps()
    got = (root / "etc/fstab").read_text().splitlines()
    assert got[1].split()[3] == "rw,relatime,compress=zstd:3,subvol=/@"
    assert got[2].split()[3] == "rw,relatime,subvol=/@home"
    assert got[3].split()[3] == "rw,subvolid=5"  # no subvol=: the id is the only selector, kept
    assert got[0] == "# /dev/vda2" and got[4] == FSTAB.splitlines()[4]


def test_post_final_conf_seclegion_disabled(tmp_path):
    """D-UPD-1: the installed pacman.conf keeps [seclegion] commented out, so pacman -Syu needs only
    core/extra; the install itself still ran against the active offline section."""
    root, creds = make_root(tmp_path)
    (root / "etc/pacman.conf").write_text(OFFLINE_CONF)
    cmds = []
    post.Post(str(root), cmds.append, creds_dir=str(creds), hints=HINTS).steps()
    conf = (root / "etc/pacman.conf").read_text()
    assert [n for n, _ in post.split_sections(conf)].count("seclegion") == 0
    assert not [ln for ln in conf.splitlines() if re.match(r"\s*Server\s*=\s*file://", ln)]
    assert post.DISABLED_SECLEGION in conf
    assert "#Server = " + post.HOSTED_SERVER in conf
    assert "#SigLevel = Required DatabaseRequired" in conf
    assert "docs/decisions.md D-UPD-1" in conf
    assert "[core]\nInclude = /etc/pacman.d/mirrorlist" in conf and "[extra]" in conf
    post.check_installed_conf(conf)
    assert any("seclegion-keyring" in " ".join(c) for c in cmds)


def test_post_install_time_conf_keeps_active_offline_seclegion(tmp_path):
    root, creds = make_root(tmp_path)
    (root / "etc/pacman.conf").write_text(OFFLINE_CONF)
    seen = []

    def run(c):
        if "pacman" in c and "-Sy" in c:
            seen.append((root / "etc/pacman.conf").read_text())

    post.Post(str(root), run, creds_dir=str(creds), hints=HINTS).steps()
    assert seen
    post.check_pacman_conf(seen[0])
    assert f"Server = {post.SERVER}" in seen[0].splitlines()


STOCK_MULTILIB = "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"


@pytest.mark.parametrize("gaming,on", [(True, True), (False, False), (None, False), ("yes", False)])
def test_post_multilib_only_with_gaming(tmp_path, gaming, on):
    root, creds = make_root(tmp_path)
    assert "#[multilib]\n#Include" in (root / "etc/pacman.conf").read_text()  # Arch's stock commented pair
    cmds = []
    hints = {**HINTS, "gaming": gaming}
    post.Post(str(root), cmds.append, creds_dir=str(creds), hints=hints).steps()
    final = (root / "etc/pacman.conf").read_text()
    assert (STOCK_MULTILIB in final) is on
    assert ("#[multilib]\n#Include" in final) is (not on)
    post.check_installed_conf(final)  # an active [multilib] is accepted
    assert (root / "var/lib/seclegion/steam-pending").exists() is on
    assert any("enable" in c and "seclegion-steam.service" in c for c in cmds) is on


def test_finalize_conf_multilib_appends_when_absent_and_is_idempotent():
    base = "[options]\n\n[core]\nInclude = /x\n"
    out = post.finalize_conf(base, multilib=True)
    assert out.count("[multilib]") == 1 and STOCK_MULTILIB in out
    post.check_installed_conf(out)
    assert post.finalize_conf(out, multilib=True).count("[multilib]") == 1
    assert "multilib" not in post.finalize_conf(base)
