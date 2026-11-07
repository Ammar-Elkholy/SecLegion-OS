# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r13 J2b (G13): users, privilege and targets of the ISO profile, checked statically.

No ISO, QEMU or root needed. The VM gates (exact units per mode, install isolation, killed
kiosk) are J2c. Run the gate with: python3 -m pytest -q tests/iso -k privilege
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILE = REPO / "iso" / "profile"
AIROOTFS = PROFILE / "airootfs"
SYSTEM = AIROOTFS / "etc" / "systemd" / "system"
SUDOERS = AIROOTFS / "etc" / "sudoers.d" / "10-seclegion-live"
KIOSK = AIROOTFS / "usr" / "share" / "seclegion" / "kiosk"
LIVE_USER, INSTALLER = "seclegion-live", "seclegion-installer"
SPDX_MIT = "SPDX-License-" + "Identifier: MIT"  # split so reuse does not read it as this file's tag


def rel(p: Path) -> str:
    try:
        return p.relative_to(AIROOTFS).as_posix()
    except ValueError:
        return p.as_posix()


def text_files() -> list[tuple[Path, str]]:
    out = []
    for p in sorted(AIROOTFS.rglob("*")):
        if p.is_file() and not p.is_symlink():
            try:
                out.append((p, p.read_text()))
            except UnicodeDecodeError:
                continue  # binary (memtest.efi)
    return out


def live_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


# --- pure checkers: the tests run them on the tree and on planted violations -------------------


def shadow_problems(text: str) -> list[str]:
    bad = []
    for line in text.splitlines():
        name, pw = line.split(":")[:2]
        if pw == "":
            bad.append(f"{name}: empty hash")
        elif not (pw.startswith("!") or pw == "*"):
            bad.append(f"{name}: not a locked entry")
    return bad


def nullok_hits(files) -> list[str]:
    return [rel(p) for p, t in files if re.search(r"\bnullok\b", t)]


def nopasswd_hits(files) -> list[str]:
    return [rel(p) for p, t in files if any("NOPASSWD" in ln for ln in live_lines(t))]


def autologin_hits(files) -> list[str]:
    pat = re.compile(r"--autologin|autologin-user|\binitial_session\b", re.I)
    return [rel(p) for p, t in files if any(pat.search(ln) for ln in live_lines(t))]


def pulled_in_by(files, unit: str) -> list[str]:
    pat = re.compile(rf"^\s*(Wants|Requires|Requisite|BindsTo|Upholds)=.*{re.escape(unit)}", re.M)
    return [rel(p) for p, t in files if pat.search(t)]


def lock_hits(text: str) -> list[str]:
    pat = re.compile(r"lock_cmd|before_sleep_cmd|hyprlock|lock-session|loginctl")
    return [ln for ln in live_lines(text) if pat.search(ln)]


# --- accounts ----------------------------------------------------------------------------------


def test_privilege_shadow_has_no_empty_hash_and_the_planned_entries():
    shadow = (AIROOTFS / "etc" / "shadow").read_text()
    assert shadow_problems(shadow) == []
    entries = {ln.split(":")[0]: ln.split(":")[1] for ln in shadow.splitlines()}
    assert entries == {"root": "!*", LIVE_USER: "!", INSTALLER: "!"}
    gshadow = (AIROOTFS / "etc" / "gshadow").read_text().splitlines()
    assert all(ln.split(":")[1] in ("!", "*", "!*") for ln in gshadow)


def test_privilege_negative_planted_empty_or_unlocked_hash_is_caught():
    assert shadow_problems("root::14871::::::\n") == ["root: empty hash"]
    assert shadow_problems("root:$6$salt$abc:14871::::::\n") == ["root: not a locked entry"]
    assert shadow_problems("root:!*:14871::::::\n") == []


def test_privilege_passwd_users_shells_and_a_single_uid_zero():
    rows = [ln.split(":") for ln in (AIROOTFS / "etc" / "passwd").read_text().splitlines()]
    by_name = {r[0]: r for r in rows}
    assert set(by_name) == {"root", LIVE_USER, INSTALLER}
    assert [r[0] for r in rows if r[2] == "0"] == ["root"]
    assert all(r[1] == "x" for r in rows)  # hashes live in shadow only
    assert by_name[INSTALLER][6] == "/usr/bin/nologin"
    groups = [ln.split(":") for ln in (AIROOTFS / "etc" / "group").read_text().splitlines()]
    assert {LIVE_USER, INSTALLER} <= {g[0] for g in groups}
    assert not any(g[0] in ("wheel", "sudo", "adm") for g in groups)
    assert not any(INSTALLER in g[3].split(",") for g in groups)


def test_privilege_no_nullok_anywhere_in_the_image():
    assert nullok_hits(text_files()) == []


def test_privilege_negative_planted_nullok_is_caught():
    unix = "auth required pam_unix.so try_first_pass"
    assert nullok_hits([(Path("pam.d/x"), unix + " nullok\n")]) == ["pam.d/x"]
    assert nullok_hits([(Path("pam.d/x"), unix + "\n")]) == []


def test_privilege_no_password_or_hash_material_in_any_file():
    hash_re = re.compile(r"\$(1|2[aby]?|5|6|y|7|gy)\$[./0-9A-Za-z]{2,}")
    cmd_re = re.compile(r"\b(chpasswd|passwd\s+--stdin|usermod\s+.*-p|useradd\s+.*-p)\b")
    for p, t in text_files():
        assert not hash_re.search(t), rel(p)
        assert not cmd_re.search(t), rel(p)


# --- sudo --------------------------------------------------------------------------------------


def test_privilege_nopasswd_only_in_the_live_sudoers_file():
    assert nopasswd_hits(text_files()) == [rel(SUDOERS)]
    assert live_lines(SUDOERS.read_text()) == [f"{LIVE_USER} ALL=(ALL:ALL) NOPASSWD: ALL"]


def test_privilege_negative_planted_nopasswd_elsewhere_is_caught():
    oops = (Path("etc/sudoers.d/99-oops"), "%wheel ALL=(ALL) NOPASSWD: ALL\n")
    planted = [(SUDOERS, SUDOERS.read_text()), oops]
    assert nopasswd_hits(planted) != [rel(SUDOERS)]
    assert nopasswd_hits([(Path("x"), "# NOPASSWD only in a comment\n")]) == []


def test_privilege_installer_and_root_have_no_sudo_rule_and_no_other_sudoers():
    sudoers = sorted(rel(p) for p in (AIROOTFS / "etc").rglob("*") if p.is_file() and "sudoers" in rel(p))
    assert sudoers == [rel(SUDOERS)]
    for p, t in text_files():
        assert not re.search(rf"^[^#\n]*\b{INSTALLER}\s+ALL", t, re.M), rel(p)


def test_privilege_sudoers_and_shadow_modes_in_profiledef():
    perms = (PROFILE / "profiledef.sh").read_text()
    assert '["/etc/sudoers.d/10-seclegion-live"]="0:0:440"' in perms
    assert '["/etc/shadow"]="0:0:400"' in perms and '["/etc/gshadow"]="0:0:400"' in perms
    for gone in (".automated_script.sh", ".zlogin"):
        assert gone not in perms


# --- releng leftovers are gone ------------------------------------------------------------------


def test_privilege_releng_autologin_automated_script_zlogin_and_sshd_are_removed():
    for gone in (
        "root/.automated_script.sh",
        "root/.zlogin",
        "etc/ssh",
        "etc/systemd/system/getty@tty1.service.d",
        "etc/systemd/system/multi-user.target.wants/sshd.service",
    ):
        assert not (AIROOTFS / gone).exists(), gone
    assert not [
        rel(p) for p in AIROOTFS.rglob("*") if re.search(r"sshd?", p.name) and rel(p) not in SSHD_MASKS
    ]
    assert not [rel(p) for p, t in text_files() if re.search(r"PermitRootLogin|PasswordAuthentication", t)]


# decisions.md M2-openssh: the openssh package may arrive as a dependency; the server must not run.
SSHD_MASKS = [
    f"etc/systemd/system/{n}" for n in ("sshd.service", "sshd.socket", "sshd@.service", "sshdgenkeys.service",
                                          "sshd-unix-local.socket")
]


def unmasked_sshd(root: Path) -> list[str]:
    """SSHD_MASKS entries under `root` that are not a symlink to /dev/null."""
    return [n for n in SSHD_MASKS if not ((root / n).is_symlink() and os.readlink(root / n) == "/dev/null")]


def test_privilege_sshd_is_masked_in_the_profile():
    assert unmasked_sshd(AIROOTFS) == []


def test_privilege_negative_unmasked_or_missing_sshd_mask_is_caught(tmp_path):
    unit = tmp_path / SSHD_MASKS[0]
    unit.parent.mkdir(parents=True)
    unit.write_text("[Service]\nExecStart=/usr/bin/sshd -D\n")  # a real, startable unit instead of the mask
    assert SSHD_MASKS[0] in unmasked_sshd(tmp_path)
    assert unmasked_sshd(tmp_path) == SSHD_MASKS  # the other three are missing


def test_privilege_autologin_exists_only_in_the_rescue_shell_and_the_live_greetd_config():
    assert sorted(autologin_hits(text_files())) == [
        "etc/greetd/config.toml",
        "etc/systemd/system/seclegion-rescue-shell.service",
    ]


def test_privilege_negative_planted_getty_autologin_is_caught():
    conf = "ExecStart=-/usr/bin/agetty --autologin root -\n"
    planted = [(Path("getty@tty1.service.d/autologin.conf"), conf)]
    assert autologin_hits(planted) == ["getty@tty1.service.d/autologin.conf"]


def test_privilege_greetd_initial_session_is_the_live_user_and_has_a_distinct_greeter():
    cfg = (AIROOTFS / "etc" / "greetd" / "config.toml").read_text()
    initial = cfg.split("[initial_session]")[1]
    assert re.search(rf'^user = "{LIVE_USER}"$', initial, re.M)
    default = cfg.split("[default_session]")[1].split("[initial_session]")[0]
    assert 'user = "greeter"' in default
    assert cfg.count("[initial_session]") == 1


# --- targets -----------------------------------------------------------------------------------


def unit_files():
    return [(p, t) for p, t in text_files() if p.parent == SYSTEM]


def test_privilege_each_mode_unit_is_wanted_only_by_its_own_target():
    units = unit_files()
    assert pulled_in_by(units, "greetd.service") == ["etc/systemd/system/seclegion-live.target"]
    assert pulled_in_by(units, "seclegion-kiosk.service") == ["etc/systemd/system/seclegion-install.target"]
    rescue = pulled_in_by(units, "seclegion-rescue-shell.service")
    assert rescue == ["etc/systemd/system/seclegion-rescue.target"]
    assert pulled_in_by(units, "seclegion-kiosk-error.service") == []  # reached by OnFailure= only
    # no [Install] section in our units: nothing is enabled behind the targets' back
    assert [rel(p) for p, t in units if p.name.startswith("seclegion-") and "[Install]" in t] == []
    # no enable-style symlink for greetd or a display manager
    links = [p for p in AIROOTFS.rglob("*") if p.is_symlink()]
    assert not [rel(p) for p in links if re.search(r"greetd|display-manager|seclegion-", p.name)]


def test_privilege_install_and_rescue_targets_do_not_start_the_live_session():
    for t in ("install", "rescue"):
        text = (SYSTEM / f"seclegion-{t}.target").read_text()
        assert not re.search(r"greetd|seclegion-live|hypridle", text), t
    live = (SYSTEM / "seclegion-live.target").read_text()
    assert not re.search(r"kiosk|rescue-shell", live)


def test_privilege_negative_a_second_target_pulling_greetd_is_caught():
    planted = unit_files() + [(SYSTEM / "seclegion-install.target", "[Unit]\nWants=greetd.service\n")]
    assert len(pulled_in_by(planted, "greetd.service")) == 2


def test_privilege_kiosk_runs_as_the_installer_user_and_failure_shows_the_log_path():
    unit = (SYSTEM / "seclegion-kiosk.service").read_text()
    assert f"User={INSTALLER}" in unit
    assert "OnFailure=seclegion-kiosk-error.service" in unit
    assert "Restart=no" in unit
    assert "PAMName=seclegion-kiosk" in unit and (AIROOTFS / "etc" / "pam.d" / "seclegion-kiosk").is_file()
    run = (KIOSK / "run").read_text()
    assert live_lines(run)[-1] == "exit 1"  # even a clean cage exit is a failure
    err = (KIOSK / "error").read_text()
    assert "LOG=/var/log/seclegion/kiosk.log" in err
    assert re.search(r"Log: %s.*\$LOG", err) and "/dev/tty1" in err


def test_privilege_kiosk_session_pam_stack_cannot_authenticate():
    pam = live_lines((AIROOTFS / "etc" / "pam.d" / "seclegion-kiosk").read_text())
    assert "auth     required pam_deny.so" in pam
    assert not [ln for ln in pam if ln.startswith("auth") and "permit" in ln]


def test_privilege_live_hypridle_is_dpms_only_no_lock():
    conf = (AIROOTFS / "home" / LIVE_USER / ".config" / "hypr" / "hypridle.conf").read_text()
    assert lock_hits(conf) == []
    assert "dpms off" in conf
    perms = (PROFILE / "profiledef.sh").read_text()
    assert f'["/home/{LIVE_USER}/.config/hypr/hypridle.conf"]="1000:1000:640"' in perms


def test_privilege_negative_a_lock_command_in_hypridle_is_caught():
    assert lock_hits("general {\n    lock_cmd = hyprlock\n}\n") != []
    assert lock_hits("listener {\n    on-timeout = loginctl lock-session\n}\n") != []
    assert lock_hits("listener {\n    on-timeout = hyprctl dispatch dpms off\n}\n") == []


def test_privilege_executables_are_listed_in_profiledef():
    perms = (PROFILE / "profiledef.sh").read_text()
    for script in sorted(KIOSK.iterdir()):
        path = "/" + script.relative_to(AIROOTFS).as_posix()
        assert f'["{path}"]="0:0:755"' in perms, path  # git does not keep the exec bit here


def test_privilege_new_files_carry_spdx_headers_or_a_reuse_annotation():
    reuse = (REPO / "REUSE.toml").read_text()
    for name in ("etc/passwd", "etc/shadow", "etc/group", "etc/gshadow"):
        assert f'"iso/profile/airootfs/{name}"' in reuse, name  # no comment syntax: annotation
    for p, t in text_files():
        r = rel(p)
        if r in ("etc/passwd", "etc/shadow", "etc/group", "etc/gshadow"):
            continue
        if re.search(r"seclegion", r) and not r.endswith(".css"):
            assert SPDX_MIT in t[:300], r


@pytest.mark.parametrize("name", ["install", "live", "rescue"])
def test_privilege_target_keeps_the_mode_marker_the_vm_gate_reads(name):
    text = (SYSTEM / f"seclegion-{name}.target").read_text()
    assert f"Wants=seclegion-mode@{name}.service" in text
    assert "systemd.unit" in text and "M1 stub" not in text


# --- the installer kiosk: GUI, pkexec and the polkit rule (spec A3) -------------------------------

INSTALL_PROGRAM = "/usr/bin/seclegion-install"
RULE_SRC = AIROOTFS / "usr" / "share" / "seclegion" / "install" / "50-seclegion-installer.rules"
RULE_DEST = "/run/polkit-1/rules.d/50-seclegion-installer.rules"
RULE_UNIT = "seclegion-kiosk-polkit.service"


LOGIND_IDS = ["org.freedesktop.login1.power-off", "org.freedesktop.login1.power-off-multiple-sessions",
              "org.freedesktop.login1.reboot", "org.freedesktop.login1.reboot-multiple-sessions"]


def rule_problems(text: str) -> list[str]:
    """Violations of 'this user may pkexec this program and reboot/power off, nothing else'."""
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    problems = []
    if code.count("polkit.addRule(") != 2 or "polkit.addAdminRule(" in code:
        problems.append("must hold exactly two addRule")
    if len(re.findall(r"polkit\.Result\.\w+", code)) != 2 or code.count("polkit.Result.YES") != 2:
        problems.append("must return exactly two results, both YES")
    literals = sorted(re.findall(r'"([^"]*)"', code))
    want = sorted(["org.freedesktop.policykit.exec", "program", INSTALL_PROGRAM, INSTALLER, INSTALLER,
                   *LOGIND_IDS])
    if literals != want:
        problems.append(f"string literals are {literals}, must be {want}")
    for needle in ('action.id == "org.freedesktop.policykit.exec"',
                   f'action.lookup("program") == "{INSTALL_PROGRAM}"', f'subject.user == "{INSTALLER}"'):
        if needle not in code:
            problems.append(f"missing condition {needle}")
    for i in LOGIND_IDS:
        if f'action.id == "{i}"' not in code:
            problems.append(f"missing logind id {i}")
    if code.count(f'subject.user == "{INSTALLER}"') != 2:
        problems.append("both rules must name the installer user")
    if code.count("&&") != 3:  # exec rule: two; logind rule: one (the ids are OR-ed inside parentheses)
        problems.append("conditions must be AND-ed")
    if code.count("||") != 3:
        problems.append("only the four logind ids may be OR-ed")
    return problems


def test_privilege_negative_a_wider_polkit_rule_is_caught():
    good = RULE_SRC.read_text()
    assert rule_problems(good.replace(INSTALL_PROGRAM, "/usr/bin/bash")) != []
    assert rule_problems(good.replace(f'subject.user == "{INSTALLER}"', 'subject.user == "root"')) != []
    assert rule_problems(good.replace("&&\n        subject.user", "||\n        subject.user")) != []
    assert rule_problems(good.replace('action.id == "org.freedesktop.policykit.exec" &&',
                                      'action.id.indexOf("org.freedesktop") == 0 &&')) != []
    assert rule_problems(good + good) != []
    assert rule_problems(good.replace("org.freedesktop.login1.reboot\"", "org.freedesktop.udisks2.x\"")) != []
    extra = good + good.replace("org.freedesktop.login1.power-off", "org.freedesktop.udisks2.x")
    assert rule_problems(extra) != []
    assert rule_problems(good.replace("polkit.Result.YES", "polkit.Result.AUTH_ADMIN")) != []


def test_privilege_polkit_rule_grants_exactly_exec_and_the_four_login1_ids():
    code = "\n".join(ln for ln in RULE_SRC.read_text().splitlines() if not ln.lstrip().startswith("//"))
    ids = re.findall(r'action\.id == "([^"]+)"', code)
    assert sorted(ids) == sorted(["org.freedesktop.policykit.exec", *LOGIND_IDS])
    assert "udisks2" not in code and "org.freedesktop.systemd1" not in code


def test_privilege_polkit_rule_exists_only_under_the_install_target():
    # nothing ships a rule where polkitd reads it: the one source file sits outside every polkit directory
    rules = sorted(rel(p) for p in AIROOTFS.rglob("*") if p.is_file() and p.suffix == ".rules")
    assert rules == [rel(RULE_SRC)]
    assert not [rel(p) for p in AIROOTFS.rglob("*") if "polkit-1" in p.as_posix()]
    # only the rule unit copies it, into /run (cleared by every boot), and only the install target wants it
    units = unit_files()
    users = [rel(p) for p, t in units if "50-seclegion-installer.rules" in t]
    assert users == [f"etc/systemd/system/{RULE_UNIT}"]
    assert pulled_in_by(units, RULE_UNIT) == ["etc/systemd/system/seclegion-install.target"]
    unit = (SYSTEM / RULE_UNIT).read_text()
    src = "/" + RULE_SRC.relative_to(AIROOTFS).as_posix()
    assert f"ExecStart=/usr/bin/install -D -m 0644 {src} {RULE_DEST}" in unit
    assert "polkit-1" not in "\n".join(ln.replace(RULE_DEST, "") for ln in live_lines(unit))
    assert "Type=oneshot" in unit and "[Install]" not in unit
    for other in ("live", "rescue"):
        assert RULE_UNIT not in (SYSTEM / f"seclegion-{other}.target").read_text()
    assert not [rel(p) for p in AIROOTFS.rglob("*") if p.is_symlink() and "polkit" in p.name]


def test_privilege_polkit_rule_is_written_and_loaded_before_the_kiosk_starts():
    unit = (SYSTEM / RULE_UNIT).read_text()
    assert "Before=seclegion-kiosk.service" in unit
    assert "ExecStart=-/usr/bin/systemctl try-restart polkit.service" in unit  # a polkitd that started first
    kiosk = (SYSTEM / "seclegion-kiosk.service").read_text()
    assert re.search(rf"^After=.*\b{re.escape(RULE_UNIT)}", kiosk, re.M)
    assert f"User={INSTALLER}" in kiosk


def test_privilege_kiosk_starts_the_installer_gui_in_kiosk_mode_and_any_exit_fails():
    run = live_lines((KIOSK / "run").read_text())
    cage = [ln for ln in run if ln.startswith("cage ")]
    assert len(cage) == 1
    assert cage[0].startswith(
        "cage -- /usr/share/seclegion/kiosk/scale /usr/bin/seclegion-installer-gui --kiosk --log ")
    assert "placeholder" not in (KIOSK / "run").read_text()
    assert not (KIOSK / "placeholder").exists()
    assert run[-1] == "exit 1"
    # the log is in the unit's StateDirectory: the no-shell user cannot write /var/log
    assert "StateDirectory=seclegion-installer" in (SYSTEM / "seclegion-kiosk.service").read_text()
    assert "${STATE_DIRECTORY:-/var/lib/seclegion-installer}/install.log" in cage[0]


def test_privilege_installer_user_gains_nothing_but_the_one_pkexec_rule():
    # still no sudo rule, no group with privilege, no shell (the tests above), and no other polkit rule
    for p, t in text_files():
        assert not re.search(rf"{INSTALLER}.*(NOPASSWD|ALL=)", t), rel(p)
    assert not [rel(p) for p, t in text_files() if "polkit.Result" in t and p != RULE_SRC]


JS_HARNESS = """
const rules = [];
const polkit = { Result: { YES: "yes" }, addRule(f) { rules.push(f); } };
eval(new TextDecoder().decode(imports.gi.GLib.file_get_contents(ARGV[0])[1]));
const ask = (id, program, user) =>
    String(rules[0]({ id, lookup: (k) => (k === "program" ? program : undefined) }, { user }));
const exec = "org.freedesktop.policykit.exec";
print(JSON.stringify([
    ask(exec, "/usr/bin/seclegion-install", "seclegion-installer"),
    ask(exec, "/usr/bin/id", "seclegion-installer"),
    ask(exec, "/usr/bin/seclegion-install", "root"),
    ask(exec, "/usr/bin/seclegion-install", "seclegion-live"),
    ask("org.freedesktop.login1.reboot", "/usr/bin/seclegion-install", "seclegion-installer"),
]));
"""


def test_privilege_polkit_rule_evaluates_to_yes_for_exactly_one_case(tmp_path):
    gjs = shutil.which("gjs")
    if not gjs:
        pytest.skip("gjs (SpiderMonkey, the engine polkit's rules run in) is not installed")
    harness = tmp_path / "eval.js"
    harness.write_text(JS_HARNESS)
    r = subprocess.run([gjs, str(harness), str(RULE_SRC)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["yes", "undefined", "undefined", "undefined", "undefined"]
