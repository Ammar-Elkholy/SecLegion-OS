# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import json
import os
import subprocess
import sys

import pytest

import evidence
from tests.mutation import forge
from tests.unit.conftest import REPO

GEN = os.path.join(REPO, "tools", "gen-testing-md")
VERIFY = os.path.join(REPO, "tools", "verify-evidence")
ISO = forge.ISO_SHA


def make_root(tmp_path, status="PASS", exit_code=0, with_artifact=True):
    root, head = forge.make_repo(tmp_path)
    forge.add_run(root, head, status=status, exit_code=exit_code,
                  artifacts=["serial.log"] if with_artifact else [])
    return root


def run_dir_of(root):
    (path,) = (root / "evidence" / "M0-boot" / ISO).iterdir()
    return path


def run(tool, root, *extra):
    return subprocess.run([sys.executable, tool, "--root", str(root), *extra],
                          capture_output=True, text=True, check=False)


def test_generate_then_verify_ok(tmp_path):
    root = make_root(tmp_path)
    assert run(GEN, root).returncode == 0
    text = (root / "TESTING.md").read_text()
    assert "| M0-boot | PASS | AUTO |" in text
    assert run(VERIFY, root).returncode == 0


def test_gen_check_detects_stale(tmp_path):
    root = make_root(tmp_path)
    assert run(GEN, root, "--check").returncode == 1  # no TESTING.md yet
    run(GEN, root)
    assert run(GEN, root, "--check").returncode == 0


def test_empty_evidence_generates_and_verifies(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    assert run(GEN, root).returncode == 0
    assert "No evidence recorded" in (root / "TESTING.md").read_text()
    assert run(VERIFY, root).returncode == 0


def test_g5_hand_edited_row_rejected(tmp_path):
    """Mutation: flip a FAIL row to PASS by hand in TESTING.md -> verify must fail."""
    root = make_root(tmp_path, status="FAIL", exit_code=1)
    run(GEN, root)
    assert run(VERIFY, root).returncode == 0
    md = root / "TESTING.md"
    md.write_text(md.read_text().replace("| FAIL |", "| PASS |"))
    proc = run(VERIFY, root)
    assert proc.returncode == 1
    assert "hand edit" in proc.stderr


def test_added_and_removed_rows_rejected(tmp_path):
    root = make_root(tmp_path)
    run(GEN, root)
    md = root / "TESTING.md"
    original = md.read_text()
    md.write_text(original + "| M9-fake | PASS | AUTO | `x` | `y` | 1 | `z` |\n")
    assert run(VERIFY, root).returncode == 1
    md.write_text("\n".join(original.splitlines()[:-1]) + "\n")
    assert run(VERIFY, root).returncode == 1


def test_missing_artifact_rejected(tmp_path):
    root = make_root(tmp_path)
    run(GEN, root)
    os.remove(run_dir_of(root) / "serial.log")
    proc = run(VERIFY, root)
    assert proc.returncode == 1 and "missing" in proc.stderr
    assert run(VERIFY, root, "--rows-only").returncode == 1  # rows-only never skips artifacts


def test_tampered_artifact_rejected(tmp_path):
    root = make_root(tmp_path)
    run(GEN, root)
    (run_dir_of(root) / "serial.log").write_text("forged\n")
    proc = run(VERIFY, root)
    assert proc.returncode == 1 and "sha256 differs" in proc.stderr


def test_hand_edited_result_json_status_rejected(tmp_path):
    root = make_root(tmp_path, status="FAIL", exit_code=1)
    run(GEN, root)
    path = run_dir_of(root) / "result.json"
    data = json.loads(path.read_text())
    data["status"] = "PASS"  # exit_code still 1 -> inconsistent
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    proc = run(VERIFY, root)
    assert proc.returncode == 1 and "PASS with exit_code" in proc.stderr


def test_pass_without_artifacts_is_invalid(tmp_path):
    root = make_root(tmp_path, with_artifact=False)
    run(GEN, root)
    proc = run(VERIFY, root)
    assert proc.returncode == 1 and "no artifacts" in proc.stderr


def test_artifact_name_cannot_escape():
    result = {"schema": 1, "test_id": "t", "status": "FAIL", "class": "AUTO", "commit": "c",
              "iso_sha256": ISO, "env": {}, "command": "", "expected": "", "serial_patterns": [],
              "actual": "", "exit_code": 1, "artifacts": {"../x": "0" * 64}, "timestamp": "t"}
    problems = evidence.validate(f"/r/t/{ISO}/t", result)
    assert any("escapes" in p for p in problems)


def test_write_result_requires_fields(tmp_path):
    with pytest.raises(ValueError):
        evidence.write_result(str(tmp_path), {"test_id": "t", "iso_sha256": ISO}, [])


def test_ansi_pattern_matches_the_harness_serial_pattern():
    from tests.lib import serial
    assert evidence.ANSI_RE.pattern == serial.ANSI_RE.pattern


def test_commit_id_is_plain_sha_on_a_clean_tree_and_dirty_otherwise(tmp_path):
    root, head = forge.make_repo(tmp_path)
    assert evidence.git_commit_id(str(root)) == head
    (root / "README").write_text("changed\n")
    assert evidence.git_commit_id(str(root)) == head + "-dirty"
    forge.git(root, "checkout", "--", "README")
    (root / "new.py").write_text("untracked\n")
    assert evidence.git_commit_id(str(root)) == head + "-dirty"


def test_commit_id_ignores_evidence_output(tmp_path):
    root, head = forge.make_repo(tmp_path)
    (root / "evidence" / "T" / "x" / "y").mkdir(parents=True)
    (root / "evidence" / "T" / "x" / "y" / "serial.log").write_text("run output\n")
    assert evidence.git_commit_id(str(root)) == head


def test_commit_id_outside_a_repo_is_unknown(tmp_path):
    assert evidence.git_commit_id(str(tmp_path)) == "unknown"


def test_repo_relative_strips_the_repo_prefix():
    cmd = ["qemu", "-drive", "file=/r/repo/out/a.iso,if=none", "/usr/share/edk2/CODE.fd"]
    assert evidence.repo_relative(cmd, "/r/repo") == (
        "qemu -drive file=out/a.iso,if=none /usr/share/edk2/CODE.fd")


def test_new_result_dir_is_fresh_each_time_and_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "now_iso", lambda: "2026-10-14T20:03:22Z")
    run_dir, stamp = evidence.new_result_dir(str(tmp_path), "T", ISO)
    assert run_dir.endswith(f"T/{ISO}/20261014T200322Z") and stamp == "2026-10-14T20:03:22Z"
    with pytest.raises(FileExistsError):
        evidence.new_result_dir(str(tmp_path), "T", ISO)


def test_write_result_refuses_to_overwrite(tmp_path):
    root, head = forge.make_repo(tmp_path)
    run_dir = forge.add_run(root, head)
    record = json.loads((run_dir / "result.json").read_text())
    del record["schema"], record["artifacts"]
    with pytest.raises(FileExistsError):
        evidence.write_result(str(root / "evidence"), record, ["serial.log"])


def test_two_runs_of_the_same_iso_coexist(tmp_path):
    root, head = forge.make_repo(tmp_path)
    forge.add_run(root, head, timestamp="2026-10-14T20:03:22Z")
    forge.add_run(root, head, timestamp="2026-10-14T21:00:00Z", sums=None)
    forge.regenerate(root)
    assert forge.verify(root).returncode == 0
    assert (root / "TESTING.md").read_text().count("| M0-boot | PASS |") == 2


def _selftest_log(mode, kill_kiosk=False, entry=None, gui_facts=False):
    """Serial text in the order seclegion-selftest really prints (start, state, units, privilege, isolation,
    installer, lock, repos, cache, [live: desktop], [kiosk marker, kiosk_error], done): every M2 pattern
    list must match it in order."""
    def line(section, body=""):
        return f'SECLEGION-SELFTEST {{"section": "{section}", "mode": "{mode}"{body}}}\n'
    out = f"[entry {entry}]\n" if entry else ""
    out += f"SECLEGION-MODE={mode}\n" + line("start", ', "action": "report"')
    out += line("state", ', "system": "starting", "failed": [], "pending_jobs": ["time-sync.target"], '
                         '"unexplained_jobs": []')
    out += line("units", ', "part": 1, "of": 1, "active": []')
    out += line("privilege", ', "accounts": {"root": {"exists": true, "uid": 0, "shell": "/bin/zsh", '
                             '"password": "L"}}')
    out += line("isolation", ', "live_user_processes": [], "autologin": false')
    rules = '["/run/polkit-1/rules.d/50-seclegion-installer.rules"]' if mode == "install" else "[]"
    gui = (', "gui_running": true, "pkexec_help_rc": 0, "pkexec_help_usage": true, "pkexec_other_rc": 127'
           if mode == "install" else "")
    out += line("installer", f', "rules_run": {rules}, "rules_etc": []{gui}')
    out += line("lock", ', "locker_processes": [], "locked_sessions": []')
    out += line("repos", ', "sections": ["options", "core", "extra", "seclegion"], '
                         '"openssh_installed": true, '
                         '"sshd_state": {"sshd.service": "masked", "sshd.socket": "masked"}, '
                         '"ssh_host_keys": [], "listening_22": false')
    out += line("cache", ', "packages": 2, "sigs": 2, "without_sig": 0, "database": true, "sync_rc": 0, '
                         '"resolve_rc": 0')
    if mode == "live":
        out += line("desktop", ', "hyprland_lua": true, "hyprland_lua_is_skel": true, '
                               '"live_processes": ["Hyprland", "waybar"]')
    if gui_facts:
        out = ("BOOT_IMAGE=/vmlinuz seclegion.mode=install copytoram=y\n" + out
               + line("gui_facts", ', "rc": 0, "facts": {"install_mode": true, "boot_medium": "/dev/sr0", '
                                   '"disks": [{"path": "/dev/vda", "refusal": null, "partitions": []}]}'))
    if kill_kiosk:
        out += "SECLEGION-KIOSK-ERROR log=/var/log/seclegion/kiosk.log\n"
        out += line("kiosk_error", ', "killed": true, "kiosk": "failed", "error_unit": "active"')
    return out + line("done")


@pytest.mark.parametrize("test_id,log", [
    ("M2-units-install", lambda: _selftest_log("install")),
    ("M2-units-live", lambda: _selftest_log("live")),
    ("M2-units-rescue", lambda: _selftest_log("rescue")),
    ("M2-privilege", lambda: _selftest_log("live", entry="live") + _selftest_log("install", entry="install")),
    ("M2-kiosk-facts", lambda: _selftest_log("install", gui_facts=True)),
    ("M2-installer", lambda: _selftest_log("install", entry="install") + _selftest_log("live", entry="live")
     + _selftest_log("rescue", entry="rescue")),
    ("M2-kiosk-error", lambda: _selftest_log("install", kill_kiosk=True)),
    ("M2-lock", lambda: _selftest_log("live")),
    ("M2-live-desktop", lambda: _selftest_log("live")),
    ("M2-repos", lambda: _selftest_log("live")),
    ("M2-cache", lambda: _selftest_log("live")),
])
def test_m2_canonical_patterns_match_the_selftest_line_order(tmp_path, test_id, log):
    (tmp_path / "serial.log").write_text(log())
    result = {"test_id": test_id, "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
              "artifacts": {"serial.log": "x"}}
    assert evidence.check_serial(str(tmp_path), result) == []


def _m4_log(test_id, secret=""):
    """Serial text in the order tests/install/test_i2_run.py writes it (InstallRun sections)."""
    if test_id == "M4-mutation":
        return "MUTANT a CAUGHT\nMUTANT b CAUGHT\nMUTANTS 2 GREEN 0\n" + secret
    out = ("[phase install-command]\nqemu-system-x86_64 -name x -vga std -nic none -no-reboot\n\n"
           "[phase install]\nprogress\nSECLEGION-INSTALL-OK\nDL-INSTALL 0\n\n"
           "[phase check]\n0\nseclegion-desktop 0.1.0-1\n/dev/null\nDL-CHECK 0\n\n"
           "[phase target-check]\nDL-TARGET 0\n\n")
    if test_id == "M4-alongside":
        out += "[phase ntfs]\nNTFS-SHA256-UNCHANGED " + "ab" * 32 + "\n\n"
    if test_id == "M4-shrink":  # test_m4_shrink.py: its own transcript, no installed boot
        return ("[phase shrink]\nSECLEGION-INSTALL-OK\nDL-INSTALL 0\nCHECK-RC 0\nFIX-RC 0\nDL-TARGET 0\n"
                "NTFS-FILE-SHA256-UNCHANGED " + "ef" * 32 + "\n" + secret)
    if test_id == "M4-partition":
        out += "[phase kept]\nPARTS-SHA256-UNCHANGED " + "cd" * 32 + "\n\n"
    out += ("[phase installed-boot]\nWelcome to SecLegion OS!\n[  OK  ] Started Greeter daemon.\n"
            "\nSecLegion OS 7.2.9-arch1-1 (ttyS0)\n")
    return out + secret


@pytest.mark.parametrize("test_id", evidence.M4_IDS)
def test_m4_canonical_patterns_match_the_install_log_order(tmp_path, test_id):
    (tmp_path / "serial.log").write_text(_m4_log(test_id))
    result = {"test_id": test_id, "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
              "artifacts": {"serial.log": "x"}}
    assert evidence.check_serial(str(tmp_path), result) == []


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
@pytest.mark.parametrize("test_id", evidence.M4_IDS)
def test_m4_log_with_a_test_secret_fails_check_serial(tmp_path, test_id, secret):
    (tmp_path / "serial.log").write_text(_m4_log(test_id, secret=f"leak: {secret}\n"))
    result = {"test_id": test_id, "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
              "artifacts": {"serial.log": "x"}}
    problems = evidence.check_serial(str(tmp_path), result)
    assert len(problems) == 1 and "forbidden" in problems[0]


def test_m4_forbidden_secrets_equal_the_install_test_constants():
    install_test = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "install", "test_i2_run.py")
    with open(install_test) as fh:
        text = fh.read()
    assert f'PASSWORD = "{evidence.M4_TEST_PASSWORD}"' in text
    assert f'LUKS_PASSPHRASE = "{evidence.M4_TEST_LUKS_PASSPHRASE}"' in text


# checkpoint C
def _c_log(test_id):
    """Serial text in the order test_m5_fast.py and test_d2_greeter_vm.py write it."""
    install = ("[phase install]\nprogress\nSECLEGION-INSTALL-OK\nDL-INSTALL 0\n\n"
               "[phase target-check]\nDL-TARGET 0\n\n")
    booted = ("[phase installed-boot]\nWelcome to SecLegion OS!\n[  OK  ] Started Greeter daemon.\n"
              "\nSecLegion OS 7.2.9-arch1-1 (ttyS0)\n")
    if test_id == "M5-fast":
        return (install + booted + "\nM5-FAST elapsed_s=412 limit_s=900\n"
                "M5-FAST ocr=OK greeter screen names tester\n")
    if test_id == "M5-diskfull":
        return ("[phase install]\nrefused: disk_too_small: the target is under 20 GiB\nDL-INSTALL 2\n\n"
                "[phase after]\n0\n0\n0\nDL-AFTER 1\n")
    return (install + booted + "[tester@seclegion ~]$ G41-BEFORE-RC1\n[tester@seclegion ~]$ "
            "G41-SESSIONFILE-RC0\nG41-WRONG-RC1\nG41-ARA-RC1\nG41-RIGHT-RC1\nG41-RIGHT-RC0\nG41-OCR-OK\n")


def _c_check(tmp_path, test_id, log):
    (tmp_path / "serial.log").write_text(log)
    result = {"test_id": test_id, "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
              "artifacts": {"serial.log": "x"}}
    return evidence.check_serial(str(tmp_path), result)


# W3 / V2 (installed-base gates): M7a-defaults and M11-rollback. The guest prints split result lines.
GREETER_LINE = "[  OK  ] Started Greeter daemon.\n"


def _w3_log(test_id, secret=""):
    if test_id == "M7a-defaults":
        out = (GREETER_LINE + "tester@seclegion ~]$ echo M7A''-UFW deny-incoming; echo M7ARC1''1:$?\n"
               "M7A-UFW deny-incoming\nM7ARC11:0\nM7A-SSHD masked inactive\nM7ARC21:0\nM7A-BASELINE 3\n")
    elif test_id == "M7a-docker-ufw":
        out = (GREETER_LINE + "M7A-DKR ufw active and service active\n"
               "M7A-DKR4 ufw-user-forward before NEW drop\nM7A-DKR6 chain absent\n"
               "M7A-DKRINFO tester without sudo\n")
    else:
        out = (GREETER_LINE + "M11-PAIR pre 4 post 5\nM11-ROLLBACK to 4\n" + GREETER_LINE
               + "M11-BACK tesseract-data-ara restored with @broken\n")
    return out + secret


def _w3_problems(tmp_path, test_id, text):
    (tmp_path / "serial.log").write_text(text)
    result = {"test_id": test_id, "serial_patterns": evidence.CANONICAL_SERIAL_PATTERNS[test_id],
              "artifacts": {"serial.log": "x"}}
    return evidence.check_serial(str(tmp_path), result)


@pytest.mark.parametrize("test_id", evidence.M5_M6_IDS)
def test_checkpoint_c_canonical_patterns_match_the_log_order(tmp_path, test_id):
    assert _c_check(tmp_path, test_id, _c_log(test_id)) == []


@pytest.mark.parametrize("test_id,old,new", [
    ("M5-fast", "elapsed_s=412", "elapsed_s=900"),  # the limit itself fails
    ("M5-fast", "elapsed_s=412", "elapsed_s=1412"),
    ("M5-fast", "M5-FAST ocr=OK", "M5-FAST ocr=SKIPPED"),
    ("M5-fast", "Started Greeter daemon.", "Reached target Multi-User."),
    ("M5-fast", "DL-INSTALL 0", "DL-INSTALL 1"),
    ("M5-diskfull", "DL-INSTALL 2", "DL-INSTALL 0"),
    ("M5-diskfull", "refused: disk_too_small", "ok: fine"),
    ("M5-diskfull", "[phase after]\n0\n0\n0\n", "[phase after]\n0\n1\n0\n"),
    ("M6-greeter", "G41-BEFORE-RC1", "G41-BEFORE-RC0"),  # Hyprland ran before any login
    ("M6-greeter", "G41-SESSIONFILE-RC0", "G41-SESSIONFILE-RC1"),
    ("M6-greeter", "G41-WRONG-RC1", "G41-WRONG-RC0"),  # a wrong password started a session
    ("M6-greeter", "G41-ARA-RC1", "G41-ARA-RC0"),  # the toggle did not switch the layout
    ("M6-greeter", "G41-RIGHT-RC1\nG41-RIGHT-RC0", "G41-RIGHT-RC1"),  # the right password never worked
    ("M6-greeter", "G41-OCR-OK", ""),
])
def test_checkpoint_c_a_log_missing_a_required_line_fails_check_serial(tmp_path, test_id, old, new):
    log = _c_log(test_id)
    assert old in log
    problems = _c_check(tmp_path, test_id, log.replace(old, new))
    assert len(problems) == 1 and "does not match" in problems[0]


@pytest.mark.parametrize("test_id,leak", [
    ("M5-fast", "test-pass-1"), ("M5-fast", "test-luks-2"),
    ("M5-diskfull", "test-pass-1"), ("M5-diskfull", "SECLEGION-INSTALL-OK"), ("M5-diskfull", "Traceback"),
    ("M5-diskfull", "archinstall"),
    ("M6-greeter", "test-pass-1"), ("M6-greeter", "wrong-pass-9"),
])
def test_checkpoint_c_log_with_a_secret_or_a_success_marker_fails_check_serial(tmp_path, test_id, leak):
    problems = _c_check(tmp_path, test_id, _c_log(test_id) + f"leak: {leak}\n")
    assert len(problems) == 1 and "forbidden" in problems[0]


def test_checkpoint_c_forbidden_wrong_password_equals_the_greeter_test_constant():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "desktop", "test_d2_greeter_vm.py")
    with open(path) as fh:
        assert f'WRONG = "{evidence.M6_TEST_WRONG_PASSWORD}"' in fh.read()


@pytest.mark.parametrize("test_id", evidence.W3_IDS)
def test_w3_canonical_patterns_match_the_result_lines(tmp_path, test_id):
    assert _w3_problems(tmp_path, test_id, _w3_log(test_id)) == []


@pytest.mark.parametrize("test_id,missing", [
    ("M7a-defaults", "M7A-SSHD masked inactive"),
    ("M7a-defaults", "M7A-BASELINE 3"),
    ("M7a-docker-ufw", "M7A-DKR4 ufw-user-forward before NEW drop"),
    ("M7a-docker-ufw", "M7A-DKRINFO tester without sudo"),
    ("M11-rollback", "M11-ROLLBACK to 4"),
    ("M11-rollback", "M11-PAIR pre 4 post 5"),
])
def test_w3_a_missing_result_line_fails(tmp_path, test_id, missing):
    text = _w3_log(test_id).replace(missing + "\n", "")
    assert missing not in text
    assert len(_w3_problems(tmp_path, test_id, text)) == 1


def test_w3_m11_needs_the_greeter_again_after_the_rollback(tmp_path):
    text = _w3_log("M11-rollback").replace(GREETER_LINE + "M11-BACK", "M11-BACK")
    assert len(_w3_problems(tmp_path, "M11-rollback", text)) == 1


@pytest.mark.parametrize("test_id", evidence.W3_IDS)
def test_w3_the_typed_echo_alone_is_not_a_result_line(tmp_path, test_id):
    typed = {"M7a-defaults": "echo M7A''-UFW deny-incoming\necho M7A''-SSHD masked inactive\n"
                             "echo M7A''-BASELINE 3\n",
             "M7a-docker-ufw": "echo M7A''-DKR ufw active and service active\n"
                               "echo M7A''-DKR4 ufw-user-forward before NEW drop\n"
                               "echo M7A''-DKRINFO tester without sudo\n",
             "M11-rollback": "echo M11''-PAIR pre 4 post 5\necho M11''-ROLLBACK to 4\n"
                             "echo M11''-BACK x restored with @broken\n"}[test_id]
    assert len(_w3_problems(tmp_path, test_id, GREETER_LINE + typed + GREETER_LINE)) == 1


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
@pytest.mark.parametrize("test_id", evidence.W3_IDS)
def test_w3_log_with_a_test_secret_fails_check_serial(tmp_path, test_id, secret):
    problems = _w3_problems(tmp_path, test_id, _w3_log(test_id, secret=f"leak: {secret}\n"))
    assert len(problems) == 1 and "forbidden" in problems[0]


# CP-C VM (installed-base): M6 rows (tests/install/test_m6_target.py). The guest prints split result lines.
_M6_LINES = {
    "M6-single-session": ["M6-SINGLE no gnome gdm gnome-shell", "M6-SINGLE wayland-sessions only hyprland"],
    "M6-branding": ["M6-BRANDING hits 0"],
    "M6-browsers": ["M6-BROWSERS xdg default firefox", "M6-BROWSERS flags ozone wayland sandbox on"],
    "M6-roles": [
        "M6-ROLES notifications one service file owner swaync",
        "M6-ROLES polkit one agent installed",
        "M6-ROLES secrets one provider installed",
        "M6-ROLES every role package installed binary present",
    ],
}


@pytest.mark.parametrize("line", [ln for lns in _M6_LINES.values() for ln in lns])
def test_m6_result_lines_are_sayable(line):
    # the guest prints them with Shell.say, which refuses anything else (a comma failed M6-roles on ISO #9)
    from tests.lib.installed import SAY_RE
    assert SAY_RE.fullmatch(line), line


def _m6_log(test_id, secret=""):
    return GREETER_LINE + "".join(f"{ln}\n" for ln in _M6_LINES[test_id]) + secret


@pytest.mark.parametrize("test_id", evidence.M6_TARGET_IDS)
def test_m6_target_canonical_patterns_match_the_result_lines(tmp_path, test_id):
    assert _w3_problems(tmp_path, test_id, _m6_log(test_id)) == []


@pytest.mark.parametrize("test_id,missing", [(t, ln) for t, lns in _M6_LINES.items() for ln in lns])
def test_m6_target_a_missing_result_line_fails(tmp_path, test_id, missing):
    text = _m6_log(test_id).replace(missing + "\n", "")
    assert missing not in text
    assert len(_w3_problems(tmp_path, test_id, text)) == 1


def test_m6_target_single_session_lines_out_of_order_fail(tmp_path):
    a, b = _M6_LINES["M6-single-session"]
    text = GREETER_LINE + b + "\n" + a + "\n"
    assert len(_w3_problems(tmp_path, "M6-single-session", text)) == 1


@pytest.mark.parametrize("test_id", evidence.M6_TARGET_IDS)
def test_m6_target_the_typed_echo_alone_is_not_a_result_line(tmp_path, test_id):
    typed = "".join(f"echo {ln[:3]}''{ln[3:]}\n" for ln in _M6_LINES[test_id])
    assert len(_w3_problems(tmp_path, test_id, GREETER_LINE + typed)) == 1


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
@pytest.mark.parametrize("test_id", evidence.M6_TARGET_IDS)
def test_m6_target_log_with_a_test_secret_fails_check_serial(tmp_path, test_id, secret):
    problems = _w3_problems(tmp_path, test_id, _m6_log(test_id, secret=f"leak: {secret}\n"))
    assert len(problems) == 1 and "forbidden" in problems[0]


# VG10 (installed-base): M12-desktop-units (tests/install/test_m12_desktop_units.py), split result lines.
_M12_LINES = [
    "M12-PKGS wifi sysmon settings desktop branding libnm psutil installed",
    "M12-HELPER root 755 polkit action registered",
    "M12-ROOTAPPLY dry-run then real timezone set bad value refused",
    "M12-SNAPPER config mode 644 readable",
    "M12-UNITS displayd wallpaper enabled launchers executable",
    "M12-IMPORTS wifi sysmon data modules import",
]


def _m12_log(secret=""):
    return GREETER_LINE + "".join(f"{ln}\n" for ln in _M12_LINES) + secret


@pytest.mark.parametrize("line", _M12_LINES)
def test_m12_result_lines_are_sayable(line):
    from tests.lib.installed import SAY_RE
    assert SAY_RE.fullmatch(line), line


def test_m12_canonical_patterns_match_the_result_lines(tmp_path):
    assert _w3_problems(tmp_path, "M12-desktop-units", _m12_log()) == []


@pytest.mark.parametrize("missing", _M12_LINES)
def test_m12_a_missing_result_line_fails(tmp_path, missing):
    text = _m12_log().replace(missing + "\n", "")
    assert missing not in text
    assert len(_w3_problems(tmp_path, "M12-desktop-units", text)) == 1


def test_m12_the_typed_echo_alone_is_not_a_result_line(tmp_path):
    typed = "".join(f"echo {ln[:3]}''{ln[3:]}\n" for ln in _M12_LINES)
    assert len(_w3_problems(tmp_path, "M12-desktop-units", GREETER_LINE + typed)) == 1


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
def test_m12_log_with_a_test_secret_fails_check_serial(tmp_path, secret):
    problems = _w3_problems(tmp_path, "M12-desktop-units", _m12_log(secret=f"leak: {secret}\n"))
    assert len(problems) == 1 and "forbidden" in problems[0]


# G39 (installed-base): S6-userlua (tests/desktop/test_s6_userlua_vm.py), split result lines.
_S6_LINES = [
    "S6-USERLUA user.lua written in the home of tester",
    "S6-HYPRLAND started through the greeter and answers hyprctl",
    "S6-BINDS SUPER L maps to the user command and the new bind is present",
    "S6-OVERRIDE SUPER L created the marker and started no hyprlock",
    "S6-NEWBIND SUPER F9 created the second marker",
]


def _s6_log(secret=""):
    return GREETER_LINE + "".join(f"{ln}\n" for ln in _S6_LINES) + secret


@pytest.mark.parametrize("line", _S6_LINES)
def test_s6_result_lines_are_sayable(line):
    from tests.lib.installed import SAY_RE
    assert SAY_RE.fullmatch(line), line


def test_s6_canonical_patterns_match_the_result_lines(tmp_path):
    assert _w3_problems(tmp_path, "S6-userlua", _s6_log()) == []


@pytest.mark.parametrize("missing", _S6_LINES)
def test_s6_a_missing_result_line_fails(tmp_path, missing):
    text = _s6_log().replace(missing + "\n", "")
    assert missing not in text
    assert len(_w3_problems(tmp_path, "S6-userlua", text)) == 1


def test_s6_the_typed_echo_alone_is_not_a_result_line(tmp_path):
    typed = "".join(f"echo {ln[:3]}''{ln[3:]}\n" for ln in _S6_LINES)
    assert len(_w3_problems(tmp_path, "S6-userlua", GREETER_LINE + typed)) == 1


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
def test_s6_log_with_a_test_secret_fails_check_serial(tmp_path, secret):
    problems = _w3_problems(tmp_path, "S6-userlua", _s6_log(secret=f"leak: {secret}\n"))
    assert len(problems) == 1 and "forbidden" in problems[0]


# G46 (installed-base): S7-result (tests/desktop/test_s7_lock_vm.py), split result lines.
_S7_LINES = [
    "S7-HYPRLAND started through the greeter and answers hyprctl",
    "S7-CONTROL a word typed over QMP reaches the focused client while unlocked",
    "S7-LOCK SUPER L started hyprlock for tester",
    "S7-LOCKED a word typed over QMP under the lock reached no client",
    "S7-UNLOCK the tester password typed over QMP ended hyprlock",
    "S7-AFTER a word typed over QMP reaches the client again after the unlock",
]


def _s7_log(secret=""):
    return GREETER_LINE + "".join(f"{ln}\n" for ln in _S7_LINES) + secret


@pytest.mark.parametrize("line", _S7_LINES)
def test_s7_result_lines_are_sayable(line):
    from tests.lib.installed import SAY_RE
    assert SAY_RE.fullmatch(line), line


def test_s7_canonical_patterns_match_the_result_lines(tmp_path):
    assert _w3_problems(tmp_path, "S7-result", _s7_log()) == []


@pytest.mark.parametrize("missing", _S7_LINES)
def test_s7_a_missing_result_line_fails(tmp_path, missing):
    text = _s7_log().replace(missing + "\n", "")
    assert missing not in text
    assert len(_w3_problems(tmp_path, "S7-result", text)) == 1


def test_s7_the_typed_echo_alone_is_not_a_result_line(tmp_path):
    typed = "".join(f"echo {ln[:3]}''{ln[3:]}\n" for ln in _S7_LINES)
    assert len(_w3_problems(tmp_path, "S7-result", GREETER_LINE + typed)) == 1


@pytest.mark.parametrize("secret", ["test-pass-1", "test-luks-2"])
def test_s7_log_with_a_test_secret_fails_check_serial(tmp_path, secret):
    problems = _w3_problems(tmp_path, "S7-result", _s7_log(secret=f"leak: {secret}\n"))
    assert len(problems) == 1 and "forbidden" in problems[0]
