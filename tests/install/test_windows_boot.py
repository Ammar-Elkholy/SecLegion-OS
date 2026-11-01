# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Windows entry on SecLegion's own ESP (alongside only) and the root-side alongside guard.
Fake root, recorded commands; the real script was run in QEMU/OVMF behind systemd-boot (winboot.py)."""

import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
sys.path.insert(0, os.path.join(REPO, "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(REPO, "installer", "ui"))
sys.path.insert(0, HERE)
import configurator as c  # noqa: E402
import post  # noqa: E402
import winboot  # noqa: E402
from test_i2_run import load_install  # noqa: E402
from test_plan import alongside, answers, load_facts  # noqa: E402
from test_post import HINTS, make_root  # noqa: E402

WIN_UUID = "7b94c0d2-1111-4a5b-9c3d-0123456789ab"
SHELL_BYTES = b"MZ-fake-shell"
NTFS_GUID = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
LSBLK = {"blockdevices": [
    {"path": "/dev/vdb", "type": "disk", "children": [
        {"path": "/dev/vdb1", "type": "part", "fstype": "vfat", "parttype": winboot.ESP_GUID,
         "partuuid": WIN_UUID, "mountpoints": [None]},
        {"path": "/dev/vdb2", "type": "part", "fstype": "ntfs", "parttype": NTFS_GUID,
         "partuuid": "x", "mountpoints": [None]},
        {"path": "/dev/vdb3", "type": "part", "fstype": "vfat", "parttype": winboot.ESP_GUID,
         "partuuid": "mounted-one", "mountpoints": ["/mnt/boot"]},
        {"path": "/dev/vdb4", "type": "part", "fstype": "ext4", "parttype": winboot.ESP_GUID,
         "partuuid": "wrong-fs", "mountpoints": [None]},
    ]}]}
# what `lsblk -J -o PATH,...` really prints (no NAME column): partitions flat beside their disk
LSBLK_FLAT = {"blockdevices": [{k: v for k, v in LSBLK["blockdevices"][0].items() if k != "children"},
                               *LSBLK["blockdevices"][0]["children"]]}
OUR_PATHS = ("boot/EFI/seclegion/", "boot/loader/entries/windows.conf")


def run_post(tmp_path, hints, finder):
    root, creds = make_root(tmp_path)
    (root / "usr/share/edk2-shell/x64").mkdir(parents=True)
    (root / "usr/share/edk2-shell/x64/Shell.efi").write_bytes(SHELL_BYTES)
    cmds = []
    p = post.Post(str(root), cmds.append, creds_dir=str(creds), hints=hints, windows_esp=finder)
    p.steps()
    return p, root, cmds


def installed(cmds):
    return next(x for x in cmds if x[2:4] == ["pacman", "-S"] and "--needed" in x and len(x) > 8)


def test_windows_alongside_writes_entry_script_and_shell_to_our_esp(tmp_path):
    p, root, cmds = run_post(tmp_path, {**HINTS, "alongside": True}, lambda: ("/dev/vdb1", WIN_UUID, 1))
    assert winboot.SHELL_PKG in installed(cmds)
    assert (root / winboot.SHELL_DST).read_bytes() == SHELL_BYTES
    entry = (root / winboot.ENTRY_DST).read_text().splitlines()
    assert entry == ["title   Windows 11", "efi     /EFI/seclegion/shellx64.efi",
                     "options -nostartup \\EFI\\seclegion\\windows.nsh"]
    nsh = (root / winboot.SCRIPT_DST).read_text()
    assert "\\EFI\\Microsoft\\Boot\\bootmgfw.efi" in nsh and WIN_UUID in nsh
    assert "for %n run (0 15)" in nsh and "F12" in nsh
    # everything new under /boot is ours; no command names the Windows device
    new = [w for w in p.written if w.startswith("boot/")]
    assert sorted(new) == sorted([winboot.SHELL_DST, winboot.SCRIPT_DST, winboot.ENTRY_DST])
    assert all(w.startswith(OUR_PATHS) for w in new)
    assert not [x for x in cmds if "/dev/vdb1" in " ".join(x)]


@pytest.mark.parametrize("hints,finder", [
    (HINTS, lambda: pytest.fail("erase mode must not even look for a Windows ESP")),
    ({**HINTS, "alongside": True}, lambda: None),  # alongside, but no Windows ESP on the machine
])
def test_windows_erase_or_no_windows_esp_writes_nothing(tmp_path, hints, finder):
    p, root, cmds = run_post(tmp_path, hints, finder)
    assert not [w for w in p.written if w.startswith("boot/")]
    assert not (root / "boot").exists()
    assert winboot.SHELL_PKG not in installed(cmds)


def test_windows_missing_shell_package_warns_and_skips(tmp_path):
    root, creds = make_root(tmp_path)
    p = post.Post(str(root), lambda a: None, creds_dir=str(creds), hints={**HINTS, "alongside": True},
                  windows_esp=lambda: ("/dev/vdb1", WIN_UUID, 1))
    p.steps()
    assert not (root / "boot").exists() and any("edk2-shell" in w for w in p.warnings)


@pytest.mark.parametrize("lsblk", [LSBLK, LSBLK_FLAT], ids=["nested", "flat"])
def test_windows_finder_reads_only(tmp_path, lsblk):
    """lsblk, then a read-only mount of each unmounted vfat ESP; nothing else touches any device."""
    calls = []

    def run(argv):
        calls.append(list(argv))
        if argv[0] == "lsblk":
            return json.dumps(lsblk)
        if argv[0] == "mount":
            os.makedirs(os.path.join(argv[-1], "EFI/Microsoft/Boot"))
            open(os.path.join(argv[-1], "EFI/Microsoft/Boot/bootmgfw.efi"), "w").close()
        if argv[0] == "umount":
            shutil.rmtree(os.path.join(argv[-1], "EFI"))
        return ""

    def mkdtemp(**kw):
        d = tmp_path / f"m{len(calls)}"
        d.mkdir()
        return str(d)

    got = winboot.find_windows_esp(run=run, probe=lambda d: winboot.has_bootmgr(d, run, mkdtemp))
    assert got == ("/dev/vdb1", WIN_UUID, 1)
    mounts = [x for x in calls if x[0] == "mount"]
    assert len(mounts) == 1 and mounts[0][1] == "-o" and mounts[0][2].split(",")[0] == "ro"
    assert "rw" not in mounts[0][2].split(",") and mounts[0][3] == "/dev/vdb1"
    assert {x[0] for x in calls} == {"lsblk", "mount", "umount"}


def test_windows_script_refuses_a_bad_partuuid():
    with pytest.raises(ValueError):
        winboot.script('x"\nrm fs0:\\')


def test_windows_edk2_shell_is_in_the_offline_cache_list():
    names = {ln.split("#")[0].strip() for ln in open(os.path.join(REPO, "iso/packages/cache.list"))}
    assert winboot.SHELL_PKG in names


def test_windows_post_hint_only_for_alongside():
    assert c.post_hints(alongside())["alongside"] is True
    assert "alongside" not in c.post_hints(answers())


# --- alongside facts: the kiosk user's probes vs the root-side guard ----------------------------------


def _facts(**probes):
    f = load_facts()
    f["probes"] = probes
    return f


def test_alongside_gui_does_not_block_on_unreadable_probes():
    from model import Model
    from pages import p4_alongside
    f = _facts(**{"/dev/vdb3": "unreadable", "/dev/vdb4": "unreadable"})
    m = Model(f)
    m.pages["disk"].set_disk("/dev/disk/by-id/ata-QEMU_HARDDISK_vdb")
    m.pages["disk"].set_mode("alongside")
    page = m.pages["alongside"]
    assert page.refusal() is None and page.can_next()
    assert page.unchecked() == ["/dev/vdb3", "/dev/vdb4"] and "when installing" in page.UNCHECKED_NOTE
    assert p4_alongside.partition_refusal(page.disk(), f) is None
    f["probes"]["/dev/vdb3"] = "bitlocker"  # a probe the GUI could read still blocks
    assert page.refusal()[0] == "bitlocker"


def test_alongside_root_side_guard_refuses_what_the_gui_could_not_see(tmp_path, monkeypatch):
    """seclegion-install gathers facts itself as root: a BitLocker or hibernated volume is refused there,
    whatever the kiosk GUI saw. configurator.validate defers nothing by default."""
    m = load_install()
    ran = []
    monkeypatch.setattr(m, "run", lambda argv: ran.append(argv))
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"disk": "/dev/disk/by-id/ata-QEMU_HARDDISK_vdb", "username": "ammar",
                             "password": "p", "confirm": "QEMU HARDDISK", "mode": "alongside",
                             "luks": False, "timezone": "UTC"}))
    for result, code in (("bitlocker", "bitlocker"), ("hibernated", "windows_hibernated"),
                         ("unreadable", "windows_unreadable")):
        facts = {**_facts(**{"/dev/vdb3": result, "/dev/vdb4": "clean"}), "install_mode": True}
        monkeypatch.setattr(m.facts_mod, "gather", lambda install_mode=None, dev_build=None, f=facts: f)
        with pytest.raises(c.Refusal) as e:
            c.validate(c.Answers.from_dict(json.loads(a.read_text())), facts)
        assert e.value.code == code
        assert m.main(["--answers", str(a), "--force-install-mode", "--dev"]) == 2
    assert ran == []  # archinstall and seclegion-post never started
