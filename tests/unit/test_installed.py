# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tests/lib/installed.py: the installed-base cache key, completeness, pruning and the overlay command."""
import os

import pytest

from tests.lib import installed

ISO_SHA = "ab" * 32


def make_installd(root):
    root.mkdir()
    (root / "post.py").write_text("x = 1\n")
    (root / "sub").mkdir()
    (root / "sub" / "m.py").write_text("y = 2\n")
    return root


def fake_install(monkeypatch, tmp_path, error=None, scratch=None):
    monkeypatch.setattr(installed, "BASE_ROOT", str(tmp_path))
    monkeypatch.setattr(installed, "_sha256_file", lambda path: ISO_SHA)

    class Run:
        pass

    Run.error, Run.scratch = error, scratch

    class I2:
        fresh_install = staticmethod(lambda mode, extra, keep: Run)

    monkeypatch.setattr(installed, "_i2_run", lambda: I2)


def test_key_is_16_hex_and_follows_the_iso():
    key = installed.base_key(ISO_SHA, "cd" * 32)
    assert installed.KEY_RE.fullmatch(key)
    assert installed.base_key("ef" * 32, "cd" * 32) != key


def test_key_changes_when_an_installd_file_changes(tmp_path):
    root = make_installd(tmp_path / "installd")
    before = installed.base_key(ISO_SHA, installed.installer_hash(str(root)))
    assert installed.base_key(ISO_SHA, installed.installer_hash(str(root))) == before  # stable
    (root / "sub" / "m.py").write_text("y = 3\n")
    changed = installed.base_key(ISO_SHA, installed.installer_hash(str(root)))
    assert changed != before
    (root / "sub" / "m.py").write_text("y = 2\n")
    (root / "new.py").write_text("")
    assert installed.base_key(ISO_SHA, installed.installer_hash(str(root))) not in (before, changed)


def test_installer_hash_ignores_bytecode_and_sees_renames(tmp_path):
    root = make_installd(tmp_path / "installd")
    before = installed.installer_hash(str(root))
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "post.cpython-314.pyc").write_bytes(b"\0")
    (root / "stray.pyc").write_bytes(b"\0")
    assert installed.installer_hash(str(root)) == before
    (root / "post.py").rename(root / "post2.py")
    assert installed.installer_hash(str(root)) != before


def test_the_real_installer_hashes():
    assert len(installed.installer_hash()) == 64


def test_a_dir_without_the_complete_marker_is_not_a_hit(tmp_path):
    (tmp_path / "target.qcow2").write_bytes(b"x")
    assert not installed.is_complete(str(tmp_path))
    (tmp_path / installed.COMPLETE).write_text("")
    assert installed.is_complete(str(tmp_path))


def test_a_marker_whose_disk_is_gone_is_not_a_hit_and_is_rebuilt(tmp_path, monkeypatch):
    scratch = tmp_path / "i2-scratch"
    (scratch / "boot").mkdir(parents=True)
    (scratch / "target.qcow2").write_bytes(b"disk")
    (scratch / "boot" / "OVMF_VARS.fd").write_bytes(b"vars")
    fake_install(monkeypatch, tmp_path, scratch=str(scratch))
    stale = tmp_path / installed.base_key(ISO_SHA, installed.installer_hash())
    stale.mkdir()
    (stale / installed.COMPLETE).write_text("")  # the disk was deleted, the marker was not
    assert not installed.is_complete(str(stale))
    disk, _ = installed.installed_base("/some/iso")
    assert open(disk, "rb").read() == b"disk"


def test_installed_base_returns_a_complete_dir_without_installing(tmp_path, monkeypatch):
    fake_install(monkeypatch, tmp_path)
    monkeypatch.setattr(installed, "_i2_run", lambda: pytest.fail("a hit must not install"))
    key_dir = tmp_path / installed.base_key(ISO_SHA, installed.installer_hash())
    key_dir.mkdir()
    (key_dir / installed.COMPLETE).write_text("")
    (key_dir / "target.qcow2").write_bytes(b"x")
    disk, nvram = installed.installed_base("/some/iso")
    assert (disk, nvram) == (str(key_dir / "target.qcow2"), str(key_dir / "OVMF_VARS.fd"))


def test_installed_base_rebuilds_an_incomplete_dir_and_prunes_the_old_one(tmp_path, monkeypatch):
    scratch = tmp_path / "i2-scratch"
    (scratch / "boot").mkdir(parents=True)
    (scratch / "target.qcow2").write_bytes(b"disk")
    (scratch / "boot" / "OVMF_VARS.fd").write_bytes(b"vars")
    fake_install(monkeypatch, tmp_path, scratch=str(scratch))
    stale = tmp_path / installed.base_key(ISO_SHA, installed.installer_hash())
    stale.mkdir()
    (stale / "target.qcow2").write_bytes(b"half")
    old = tmp_path / ("0" * 16)
    old.mkdir()
    (old / installed.COMPLETE).write_text("")
    disk, nvram = installed.installed_base("/some/iso")
    assert open(disk, "rb").read() == b"disk" and open(nvram, "rb").read() == b"vars"
    assert oct(os.stat(disk).st_mode & 0o777) == "0o444"
    assert installed.is_complete(str(stale))
    assert not old.exists() and not scratch.exists()


def test_a_failed_install_leaves_no_complete_marker(tmp_path, monkeypatch):
    fake_install(monkeypatch, tmp_path, error="install failed")
    with pytest.raises(AssertionError, match="install failed"):
        installed.installed_base("/some/iso")
    assert list(tmp_path.iterdir()) == []


def test_prune_keeps_the_current_and_incomplete_dirs_and_other_files(tmp_path):
    keep, old, half = tmp_path / ("a" * 16), tmp_path / ("b" * 16), tmp_path / ("c" * 16)
    for d in (keep, old):
        d.mkdir()
        (d / installed.COMPLETE).write_text("")
        (d / "target.qcow2").write_bytes(b"x")
        os.chmod(d / "target.qcow2", 0o444)
    half.mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / installed.COMPLETE).write_text("")  # not a key-named dir
    installed.prune_other_bases("a" * 16, str(tmp_path))
    assert keep.exists() and half.exists() and (tmp_path / "notes").exists()
    assert not old.exists()


def test_overlay_command_backs_onto_the_base_as_qcow2():
    cmd = installed.overlay_command("/b/target.qcow2", "/s/overlay.qcow2")
    assert cmd[0] == "qemu-img" and cmd[1] == "create"
    assert cmd[cmd.index("-b") + 1] == "/b/target.qcow2"
    assert cmd[cmd.index("-F") + 1] == "qcow2" and cmd[cmd.index("-f") + 1] == "qcow2"
    assert cmd[-1] == "/s/overlay.qcow2"


@pytest.mark.parametrize("bar", ["|", "\u2502"])
def test_snaps_reads_ascii_and_utf8_snapper_tables(bar):
    """snapper draws its table with box characters under a UTF-8 locale (the installed system)."""
    sh = installed.Shell(vm=None)
    table = f" # {bar} Type  \n---+-------\n 0 {bar} single\n 1 {bar} pre\n 2 {bar} post\n"
    sh.run = lambda cmd, timeout=60: (0, table)
    assert sh.snaps() == {0: "single", 1: "pre", 2: "post"}


def test_shell_run_survives_a_prompt_escape_still_arriving_when_the_command_is_sent():
    """An OSC 3008 split across reads is unstripped in text() until complete: no offset may use it."""
    from tests.lib.serial import SerialCapture

    class Serial(SerialCapture):
        def send(self, text):
            line = text.rstrip("\n")
            self._raw += b"pad\x1b\\"  # the rest of the escape sequence, which text() then strips
            self._raw += f"{line}\r\n[tester@h ~]$ {line}\r\nout1\r\nout2\r\nS6RC1:0\r\n".encode()

        def wait_for(self, pattern, timeout):
            return None

    serial = Serial(None)
    partial = b"\x1b]3008;start=" + b"0123456789abcdef" * 12  # unterminated: kept by ANSI_RE
    serial._raw += b"[tester@h ~]$ " + partial
    vm = type("VM", (), {"serial": serial})()
    rc, out = installed.Shell(vm, "S6RC").run("true")
    assert rc == 0 and out.split() == ["out1", "out2"], out
