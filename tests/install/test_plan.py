# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""I1 tests: installer configurator (answers + facts -> archinstall JSON). No disk access."""
import copy
import importlib.machinery
import importlib.util
import json
import logging
import os
import stat
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import configurator as c  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
PASSWORD = "test-pass-1"
PASSPHRASE = "test-luks-2"
MB = 1 << 20


def load_facts():
    with open(os.path.join(FIX, "facts.json")) as f:
        return json.load(f)


def answers(**kw):
    base = dict(disk="/dev/disk/by-id/ata-QEMU_HARDDISK_vda", username="ammar", password=PASSWORD,
                confirm="QEMU HARDDISK", mode="erase", luks=False, timezone="UTC")
    base.update(kw)
    return c.Answers(**base)


def alongside(**kw):
    return answers(disk="/dev/disk/by-id/ata-QEMU_HARDDISK_vdb", mode="alongside", **kw)


def disk_of(facts, name):
    return next(d for d in facts["lsblk"]["blockdevices"] if d["name"] == name)


def add_part(disk, n, start_mib, size_mib):
    disk["children"].append({"name": f"vdb{n}", "path": f"/dev/vdb{n}", "type": "part",
                             "start": start_mib * 2048, "size": size_mib * MB,
                             "fstype": "ext4", "parttype": "x", "mountpoints": [None]})


def golden(name, cfg):
    p = os.path.join(FIX, "golden", name + ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        with open(p, "w") as f:
            json.dump(cfg, f, indent=2, sort_keys=True)
            f.write("\n")
    with open(p) as f:
        assert json.load(f) == json.loads(json.dumps(cfg))


def load_cli():
    path = os.path.join(REPO, "installer", "installd", "seclegion-configure")
    loader = importlib.machinery.SourceFileLoader("seclegion_configure", path)
    spec = importlib.util.spec_from_loader("seclegion_configure", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---- golden configs --------------------------------------------------------

def test_golden_erase():
    cfg, creds = c.build_config(answers(), load_facts())
    golden("erase", cfg)
    assert "disk_encryption" not in cfg["disk_config"] and "encryption_password" not in creds
    assert cfg["disk_config"]["device_modifications"][0]["wipe"] is True


def test_golden_erase_luks_default_ticked():
    a = answers(luks=None, luks_passphrase=PASSPHRASE)
    assert a.use_luks
    cfg, creds = c.build_config(a, load_facts())
    golden("erase-luks", cfg)
    assert creds["encryption_password"] == PASSPHRASE
    root = cfg["disk_config"]["device_modifications"][0]["partitions"][-1]
    assert cfg["disk_config"]["disk_encryption"]["partitions"] == [root["obj_id"]]


def test_luks_passphrase_defaults_to_password():
    _, creds = c.build_config(answers(luks=True), load_facts())
    assert creds["encryption_password"] == PASSWORD


def test_golden_alongside_keeps_existing():
    cfg, _ = c.build_config(alongside(), load_facts())
    golden("alongside", cfg)
    dm = cfg["disk_config"]["device_modifications"][0]
    assert dm["wipe"] is False
    kinds = [p["status"] for p in dm["partitions"]]
    assert kinds == ["existing"] * 4 + ["create"] * 2
    assert all(p["fs_type"] != "btrfs" for p in dm["partitions"][:4])
    created = dm["partitions"][4:]
    assert created[0]["start"]["value"] >= (62581 + 1024 - 1024)  # inside the gap only


def test_defaults_and_tz_fallback(tmp_path):
    assert c.default_timezone(str(tmp_path / "missing")) == "UTC"
    link = tmp_path / "lt"
    link.symlink_to("/usr/share/zoneinfo/Africa/Cairo")
    assert c.default_timezone(str(link)) == "Africa/Cairo"
    a = c.Answers(disk="d", username="u", password="x")
    assert a.hostname == "seclegion" and a.keyboard == "us" and a.locale == "en_US.UTF-8"


def test_post_hints_carry_extra_keyboard():
    a = answers(keyboard_extra=["ara"])
    assert c.post_hints(a)["keyboard_extra"] == ["ara"]


# ---- refusals --------------------------------------------------------------

def refuse(code, a, facts):
    with pytest.raises(c.Refusal) as e:
        c.build_config(a, facts)
    assert e.value.code == code


def test_refuse_not_install_mode():
    f = load_facts()
    f["install_mode"] = False
    refuse("not_install_mode", answers(), f)


def test_refuse_root_disk():
    refuse("root_disk", answers(disk="/dev/vdc", confirm="QEMU DISK"), load_facts())


def test_refuse_boot_medium():
    f = load_facts()
    disk_of(f, "sda")["children"][0]["mountpoints"] = [None]
    refuse("boot_medium", answers(disk="/dev/sda", confirm="Flash Drive"), f)


def test_refuse_mounted_disk():
    f = load_facts()
    disk_of(f, "vda")["children"] = [{"name": "vda1", "path": "/dev/vda1", "type": "part",
                                      "start": 2048, "size": MB, "mountpoints": ["/mnt/x"]}]
    refuse("mounted", answers(), f)


def test_refuse_mbr_disk():
    refuse("mbr_disk", answers(disk="/dev/vdd", confirm="QEMU MBR"), load_facts())


@pytest.mark.parametrize("mode", ["erase", "erase-luks"])
def test_refuse_disk_too_small(mode):
    """Under 20 GiB is refused before anything is written (it used to fail late, half installed: U5 G49)."""
    f = load_facts()
    disk_of(f, "vda")["size"] = (20 << 30) - 1
    refuse("disk_too_small", answers(mode=mode, luks=None, luks_passphrase="test-luks-2"), f)
    disk_of(f, "vda")["size"] = 20 << 30
    c.validate(answers(mode=mode, luks=None, luks_passphrase="test-luks-2"), f)


def test_refuse_gap_too_small():
    f = load_facts()
    add_part(disk_of(f, "vdb"), 5, 62581, 110000)
    refuse("gap_too_small", alongside(confirm="QEMU HARDDISK"), f)


def test_refuse_gap_not_contiguous():
    f = load_facts()
    d = disk_of(f, "vdb")
    d["size"] = 150 << 30
    add_part(d, 5, 62581 + 30000, 1000)
    add_part(d, 6, 62581 + 61000, 1000)
    refuse("gap_not_contiguous", alongside(confirm="QEMU HARDDISK"), f)


def test_refuse_confirm_mismatch():
    refuse("confirm_mismatch", answers(confirm="qemu harddisk"), load_facts())
    refuse("confirm_mismatch", answers(confirm=""), load_facts())


def test_refuse_dev_build_real_disk():
    refuse("dev_build_real_disk",
           answers(disk="/dev/nvme0n1", confirm="Samsung SSD 980"), load_facts())


def test_refuse_unknown_disk():
    refuse("no_such_disk", answers(disk="/dev/nope"), load_facts())


def test_non_dev_build_allows_real_disk():
    f = load_facts()
    f["dev_build"] = False
    cfg, _ = c.build_config(answers(disk="/dev/nvme0n1", confirm="Samsung SSD 980"), f)
    assert cfg["disk_config"]["device_modifications"][0]["device"] == "/dev/nvme0n1"


# ---- files, CLI, secrets ---------------------------------------------------

def test_write_mode_0600(tmp_path):
    cfg, creds = c.build_config(answers(), load_facts())
    paths = c.write(cfg, creds, str(tmp_path / "out"), c.post_hints(answers()))
    assert len(paths) == 3
    for p in paths:
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert json.load(open(paths[0])) == json.loads(json.dumps(cfg))


def test_secret_never_logged(tmp_path, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    a = answers(luks=True, luks_passphrase=PASSPHRASE)
    cfg, creds = c.build_config(a, load_facts())
    out = tmp_path / "out"
    seen = []
    c.dry_run(cfg, a, str(out))
    paths = c.write(cfg, creds, str(out), c.post_hints(a))
    seen += [repr(a), str(a), repr(c.post_hints(a)), c.summary(cfg, a), json.dumps(cfg)]
    # exception messages
    with pytest.raises(c.Refusal) as e:
        c.build_config(answers(confirm="wrong", luks_passphrase=PASSPHRASE), load_facts())
    seen += [str(e.value), repr(e.value)]
    with pytest.raises(c.Refusal) as e2:
        c.Answers(disk="d", username="BAD NAME", password=PASSWORD)
    seen += [str(e2.value)]
    # CLI paths
    facts_file = tmp_path / "facts.json"
    facts_file.write_text(json.dumps(load_facts()))
    ans_file = tmp_path / "answers.json"
    ans_file.write_text(json.dumps({
        "disk": "/dev/vda", "username": "ammar", "password": PASSWORD,
        "luks_passphrase": PASSPHRASE, "mode": "erase-luks", "confirm": "QEMU HARDDISK",
        "timezone": "UTC"}))
    cli = load_cli()
    assert cli.main(["--facts", str(facts_file), "--answers", str(ans_file),
                     "--out", str(tmp_path / "o2"), "--dry-run"]) == 0
    assert cli.main(["--facts", str(facts_file), "--answers", str(ans_file),
                     "--out", str(tmp_path / "o3")]) == 0
    ans_file.write_text(json.dumps({
        "disk": "/dev/vda", "username": "ammar", "password": PASSWORD,
        "luks_passphrase": PASSPHRASE, "confirm": "bad"}))
    assert cli.main(["--facts", str(facts_file), "--answers", str(ans_file),
                     "--out", str(tmp_path / "o4")]) == 2
    cap = capsys.readouterr()
    seen += [cap.out, cap.err, caplog.text]
    for text in seen:
        assert PASSWORD not in text and PASSPHRASE not in text
    # only the credentials file may hold plaintext
    assert PASSWORD not in open(paths[0]).read() and PASSWORD not in open(paths[2]).read()
    assert PASSWORD in open(paths[1]).read()
    assert not os.path.exists(tmp_path / "o2")  # dry-run writes nothing
    assert "archinstall --config" in cap.out and "--silent" in cap.out


def test_dry_run_command_line(tmp_path):
    cfg, _ = c.build_config(answers(), load_facts())
    lines = []
    c.dry_run(cfg, answers(), str(tmp_path), out=lines.append)
    assert any(ln.startswith("Would run: archinstall --config ") and ln.endswith("--silent")
               for ln in lines)


def test_config_is_deterministic():
    f = load_facts()
    assert c.build_config(answers(), f) == c.build_config(answers(), copy.deepcopy(f))
