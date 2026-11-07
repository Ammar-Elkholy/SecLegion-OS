# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""U2: installer GUI pages 1-5 (pure models always; GTK render only under Broadway, else skipped)."""

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(ROOT, "installer", "installd"))
sys.path.insert(0, HERE)
import configurator as c  # noqa: E402
from model import Model  # noqa: E402
from test_plan import add_part, disk_of, load_facts  # noqa: E402

VDA = "/dev/disk/by-id/ata-QEMU_HARDDISK_vda"
VDB = "/dev/disk/by-id/ata-QEMU_HARDDISK_vdb"


def alongside_model(**probes):
    f = load_facts()
    f["probes"] = probes or {"/dev/vdb3": "clean", "/dev/vdb4": "clean"}
    m = Model(f)
    m.pages["disk"].set_disk(VDB)
    m.pages["disk"].set_mode("alongside")
    return m


def test_gui_pages_a_welcome_and_language_fragments():
    m = Model(load_facts())
    assert m.can_next() and m.pages["welcome"].fragment() == {}
    lang = m.pages["language"]
    assert lang.fragment() == {"locale": "en_US.UTF-8", "keyboard": "us", "xkb_layout": "us",
                               "xkb_variant": "", "keyboard_extra": []}
    lang.set_language("ar")
    lang.set_keyboard("ara")
    assert lang.fragment() == {"locale": "ar_EG.UTF-8", "keyboard": "us", "xkb_layout": "ara",
                               "xkb_variant": "", "keyboard_extra": ["ara"]}
    lang.set_keyboard("dvorak")
    assert not lang.can_next() and lang.error()


def test_gui_pages_a_disk_page_luks_default_and_ineligible_disks():
    m = Model(load_facts())
    p = m.pages["disk"]
    assert not p.can_next() and p.error() == "Choose a disk."
    by_id = {d["id"]: d for d in p.disks()}
    assert by_id[VDA]["problem"] is None
    assert by_id["/dev/sda"]["code"] == "boot_medium"
    p.set_disk("/dev/sda")
    assert not p.can_next() and "boot medium" in p.error()
    p.set_disk(VDA)
    assert p.can_next()
    assert p.fragment() == {"disk": VDA, "mode": "erase", "luks": True}
    p.set_luks(False)
    assert p.fragment()["luks"] is False
    p.set_mode("alongside")
    assert p.fragment()["luks"] is False and p.fragment()["mode"] == "alongside"


def test_gui_pages_a_fragments_merge_into_valid_answers():
    m = Model(load_facts())
    m.pages["disk"].set_disk(VDA)
    ans = m.answers()
    ans.update(username="ammar", password="pw-1", confirm="QEMU HARDDISK", timezone="UTC")
    a = c.Answers(**ans)
    c.validate(a, m.facts)  # the CLI's own validator accepts the GUI's fragments


def test_gui_pages_a_navigation_skips_alongside_pages_for_erase():
    m = Model(load_facts())
    assert [p.key for p in m.visible()][:4] == ["welcome", "language", "timezone", "disk"]
    assert "alongside" not in [p.key for p in m.visible()]
    assert m.next() and m.next() and m.next()
    assert not m.next()  # disk not chosen yet
    m.pages["disk"].set_disk(VDA)
    assert m.next() and m.current.key == "encryption"  # erase defaults to LUKS
    m.pages["disk"].set_mode("alongside")
    assert [p.key for p in m.visible()][4] == "alongside"


def test_gui_pages_a_alongside_clean_shows_gap_and_allows_next():
    m = alongside_model()
    p = m.pages["alongside"]
    assert p.can_next() and p.error() is None
    assert any("will be used" in line for line in p.preview())


@pytest.mark.parametrize("result,code", [("bitlocker", "bitlocker"), ("hibernated", "windows_hibernated")])
def test_gui_pages_a_alongside_blocks_next_on_windows_refusals(result, code):
    m = alongside_model(**{"/dev/vdb3": result, "/dev/vdb4": "clean"})
    p = m.pages["alongside"]
    assert not p.can_next()
    assert p.refusal()[0] == code and p.error().rstrip(".") == p.refusal()[1]
    assert p.guide()


def test_gui_pages_a_alongside_unprobed_or_unreadable_is_checked_at_install_not_blocked():
    # the kiosk user cannot read raw partitions: seclegion-install re-probes as root and refuses there
    # (tests/install/test_windows_boot.py), so the page only notes it
    m = alongside_model(**{"/dev/vdb4": "clean"})  # vdb3 is ntfs, never probed
    assert m.pages["alongside"].can_next() and m.pages["alongside"].unchecked() == ["/dev/vdb3"]


def test_gui_pages_a_alongside_gap_too_small():
    m = alongside_model()
    add_part(disk_of(m.facts, "vdb"), 5, 62581, 110000)
    assert m.pages["alongside"].refusal()[0] == "gap_too_small"
    assert not m.pages["alongside"].can_next()


def test_gui_pages_a_manual_page_requires_largest_gap():
    m = alongside_model()
    d = disk_of(m.facts, "vdb")
    d["size"] = 300 << 30  # a big gap at the end
    add_part(d, 5, 62581 + 45000, 500)  # splits the free area into a small and a large gap
    m.open_manual()
    p = m.pages["manual"]
    gaps = p.gaps()
    assert len(gaps) == 2 and gaps[0][1] < gaps[1][1]
    assert not p.can_next()
    p.set_gap(0)
    assert not p.can_next() and "largest" in p.error()
    p.set_gap(1)
    assert p.can_next() and p.fragment() == {}
    assert [q.key for q in m.visible()][5] == "manual"


def test_gui_pages_a_pages_never_import_archinstall_or_write():
    src = ""
    later = ("p9_progress.py", "p11_hardware.py", "p13_finished.py", "p15_about.py", "app.py")  # U4
    for root, _, files in os.walk(os.path.join(ROOT, "installer", "ui", "gtk")):
        for n in files:
            if n.endswith(".py") and n not in later:
                src += open(os.path.join(root, n)).read()
    for word in ("subprocess", "import archinstall", "os.system", "open(", "sgdisk", "parted"):
        assert word not in src, word


def _free_display():
    run = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    for n in range(40, 90):
        if not os.path.exists(os.path.join(run, f"broadway{n}.socket")):
            return n
    return None


def test_gui_pages_a_render_under_broadway(tmp_path):
    broadwayd = shutil.which("gtk4-broadwayd")
    py = "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi; gi.require_version('Gtk','4.0')"],
                      capture_output=True).returncode:
        pytest.skip("gi GTK4 not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display()
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}")
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "gui_render_probe.py")], env=env,
                           capture_output=True, text=True, timeout=60)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert set(got) == {"welcome", "language", "timezone", "disk", "alongside", "manual"}
    assert got["disk"] == {"disk": VDB, "mode": "alongside", "luks": False}
    assert got["language"]["keyboard"] == "us"
