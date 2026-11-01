# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r13 J2c (G14 to G16): the new package-set ISO booted in each mode, checked from the inside.

Needs a built ISO (`make iso`, or SECLEGION_ISO) and QEMU/OVMF; without them the VM tests are
skipped (NOT RUN), never recorded as a PASS. The harness passes the system credential
`seclegion.selftest` as an SMBIOS OEM string; seclegion-selftest.service then prints one JSON
object per line on ttyS0 (usr/local/bin/seclegion-selftest: status only, never a hash). The host
side parses those lines; the checkers below are pure and also run on planted violations.
Image files only: QemuVM refuses /dev paths. OCR (SL_REQUIRE_OCR=1) confirms the error screen.

  -k units             G14 M2-units-{install,live,rescue}  exactly the units in
                       tests/expected-units/<mode>.txt
                       (SL_WRITE_EXPECTED=1 writes the observed set for review instead of comparing)
  -k install_isolation G15 M2-privilege    no live user, no autologin, no sudo in install mode
                       (+ live privilege)
  -k kiosk_killed      G16 M2-kiosk-error  killing the kiosk shows the error screen with the log path
  -k installer_kiosk   M2-installer        the install kiosk runs the GTK installer, pkexec of
                       seclegion-install works as seclegion-installer, Live/Rescue have no polkit rule
  -k lock              M2-lock             live mode: no lock, no locker; hypridle is DPMS only
  -k repos / -k cache  M2-repos, M2-cache  the image's pacman repos; the offline cache resolves and verifies
"""

import functools
import json
import os
import re
import shutil
import tempfile
import time

import pytest

import evidence
from tests.lib import bootgate
from tests.lib.bootgate import MODE_TIMEOUT, REPO, choose, wait_for_menu
from tests.lib.qemu import QemuVM

PREFIX = "SECLEGION-SELFTEST "
LIVE, INSTALLER = "seclegion-live", "seclegion-installer"
EXPECTED = os.path.join(REPO, "tests", "expected-units")
REQUIRE_OCR = os.environ.get("SL_REQUIRE_OCR") == "1"
ENTRY = {"install": bootgate.ENTRY_INSTALL, "live": bootgate.ENTRY_LIVE, "rescue": bootgate.ENTRY_RESCUE}
# Jobs that may stay queued offline: the time-sync chain and what is ordered after it (pacman-init and the
# keyring refresh); queued .timer and .target units (timers, multi-user.target, the mode target) wait
# behind it. seclegion-selftest decides "explained" from systemd's own ordering; this list is the
# test's independent bound, so a hung kiosk or greeter cannot hide behind it.
TIME_SYNC_JOBS = {
    "time-sync.target",
    "systemd-time-wait-sync.service",
    "pacman-init.service",
    "archlinux-keyring-wkd-sync.service",
    "archlinux-keyring-wkd-sync.timer",
}
CACHE_SET = ["firefox", "greetd", "hyprland", "linux"]
ARCHIVE = "https://archive.archlinux.org/repos/<date>/$repo/os/$arch"
SECLEGION_SERVER = "file:///opt/seclegion/cache/seclegion"  # the embedded signed [seclegion] repository
SIGLEVELS = ["SigLevel = Required DatabaseOptional", "SigLevel = Required DatabaseRequired"]


# --- parsing and pure checkers -------------------------------------------------------------------


def parse(text):
    """{section: report dict}. `units` parts are merged into one sorted list under "units"."""
    out, units = {}, []
    for line in evidence.ANSI_RE.sub("", text).splitlines():
        if PREFIX not in line:
            continue
        try:
            obj = json.loads(line.split(PREFIX, 1)[1])
        except ValueError:
            continue  # a console message interleaved into the line: the done marker tells
        if obj.get("section") == "units":
            units += obj["active"]
        else:
            out[obj["section"]] = obj
    out["units"] = sorted(units)
    return out


def expected_units(mode):
    with open(os.path.join(EXPECTED, f"{mode}.txt"), encoding="utf-8") as handle:
        return sorted(ln.strip() for ln in handle if ln.strip() and not ln.startswith("#"))


def check_units(report, expected):
    problems = []
    state = report.get("state", {})
    # Offline (net=none) the time-sync chain never finishes, so the system stays `starting` with only
    # those jobs queued; any other pending job, a failed unit or another state is a violation.
    system, pending = state.get("system"), state.get("pending_jobs", [])
    unexplained = state.get("unexplained_jobs")
    if system != "running":
        if system != "starting" or not pending or unexplained != []:
            problems.append(f"system {system!r}, pending jobs {pending}, unexplained: {unexplained}")
        else:
            stray = sorted(
                u for u in pending if u not in TIME_SYNC_JOBS and not u.endswith((".timer", ".target"))
            )
            if stray:
                problems.append(f"jobs outside the time-sync chain: {stray}")
    if state.get("failed"):
        problems.append(f"failed units {state.get('failed')}")
    active = report.get("units", [])
    if sorted(set(active) - set(expected)):
        problems.append(f"unexpected units: {sorted(set(active) - set(expected))}")
    if sorted(set(expected) - set(active)):
        problems.append(f"missing units: {sorted(set(expected) - set(active))}")
    return problems


def check_install_isolation(report):
    iso, priv = report.get("isolation", {}), report.get("privilege", {})
    problems = []
    if iso.get("live_user_processes"):
        problems.append(f"processes run as {LIVE}: {iso['live_user_processes']}")
    if LIVE in iso.get("session_users", []):
        problems.append(f"{LIVE} has a login session")
    if iso.get("autologin_processes"):
        problems.append(f"autologin: {iso['autologin_processes']}")
    for unit in ("greetd", "rescue_shell", "sshd"):
        if iso.get(unit) != "inactive":
            problems.append(f"{unit} is {iso.get(unit)!r} in install mode")
    if iso.get("kiosk") != "active" or iso.get("kiosk_user") != [INSTALLER]:
        problems.append(f"kiosk {iso.get('kiosk')!r} as {iso.get('kiosk_user')}")
    sudo = priv.get("sudo_n", {})
    for who in (INSTALLER, "nobody"):
        if sudo.get(who) in (0, None):
            problems.append(f"`sudo -n true` as {who} returned {sudo.get(who)!r}, it must fail")
    problems += check_no_empty_password(priv)
    return problems


def check_no_empty_password(priv):
    problems = [
        f"PAM accepts an empty password for {u}"
        for u, ok in priv.get("empty_password_login", {}).items()
        if ok
    ]
    if not priv.get("empty_password_login"):
        problems.append("no empty-password login attempt was recorded")
    if priv.get("nullok_files"):
        problems.append(f"nullok in {priv['nullok_files']}")
    return problems


def check_privilege(priv):
    acc, problems = priv.get("accounts", {}), []
    for name in ("root", LIVE, INSTALLER):
        if acc.get(name, {}).get("password") != "L":
            problems.append(
                f"{name} password status {acc.get(name, {}).get('password')!r}, wanted locked (L)"
            )
    if priv.get("uid_zero") != ["root"]:
        problems.append(f"uid 0 accounts: {priv.get('uid_zero')}")
    if not acc.get(INSTALLER, {}).get("shell", "").endswith("nologin"):
        problems.append(f"{INSTALLER} has a login shell")
    if priv.get("nopasswd_files") != ["10-seclegion-live"]:
        problems.append(f"passwordless sudo rules in {priv.get('nopasswd_files')}")
    sudo = priv.get("sudo_n", {})
    if sudo.get(LIVE) != 0:
        problems.append(f"live user `sudo -n true` returned {sudo.get(LIVE)!r}, wanted 0")
    if sudo.get(INSTALLER) in (0, None):
        problems.append(f"{INSTALLER} can sudo")
    return problems + check_no_empty_password(priv)


RULE_BASENAME = "50-seclegion-installer.rules"


def check_installer(inst, mode):
    """Install mode: the GUI runs and pkexec of seclegion-install works for the installer user (and of
    nothing else); the one polkit rule exists only there (spec A3)."""
    problems = []
    rules = [os.path.basename(p) for p in inst.get("rules_run", [])]
    if inst.get("rules_etc"):
        problems.append(f"polkit rules in /etc: {inst['rules_etc']}")
    if mode != "install":
        return problems + ([f"polkit rules in /run in {mode} mode: {rules}"] if rules else [])
    if rules != [RULE_BASENAME]:
        problems.append(f"polkit rules in /run: {rules}, wanted [{RULE_BASENAME!r}]")
    if inst.get("gui_running") is not True:
        problems.append("seclegion-installer-gui is not running as the installer user")
    if inst.get("pkexec_help_rc") != 0 or inst.get("pkexec_help_usage") is not True:
        problems.append(f"pkexec seclegion-install --help: rc {inst.get('pkexec_help_rc')}")
    if inst.get("pkexec_other_rc") in (0, None):
        problems.append("pkexec of another program was not refused")
    return problems


def check_lock(lock):
    problems = []
    if lock.get("locker_processes"):
        problems.append(f"locker running: {lock['locker_processes']}")
    if any(v != "no" for v in lock.get("locked_hints", {}).values()):
        problems.append(f"a session is locked: {lock['locked_hints']}")
    if lock.get("hypridle_conf_lock_lines") or not lock.get("hypridle_conf_dpms"):
        problems.append(f"hypridle.conf is not DPMS-only: {lock.get('hypridle_conf_lock_lines')}")
    return problems


def check_repos(repos):
    problems = []
    if repos.get("sections") != ["options", "core", "extra", "seclegion"]:
        problems.append(f"repositories {repos.get('sections')}")
    if repos.get("siglevels") != SIGLEVELS:
        problems.append(f"SigLevel {repos.get('siglevels')}")
    if repos.get("servers") != [SECLEGION_SERVER, ARCHIVE] or len(repos.get("archive_dates", [])) != 1:
        problems.append(f"servers {repos.get('servers')}")
    # openssh may be installed as a dependency (decisions.md M2-openssh); what must hold is no SSH server.
    state = repos.get("sshd_state")
    if (
        not isinstance(state, dict)
        or sorted(state) != ["sshd.service", "sshd.socket"]
        or any(v != "masked" for v in state.values())
    ):
        problems.append(f"sshd is not masked: {state}")
    if repos.get("ssh_host_keys") != []:
        problems.append(f"ssh host keys exist: {repos.get('ssh_host_keys')}")
    if repos.get("listening_22") is not False:
        problems.append(f"something listens on :22: {repos.get('listening_22')}")
    return problems


def check_cache(cache):
    problems = []
    if (
        not cache.get("packages")
        or cache.get("without_sig")
        or cache.get("sigs", 0) < cache.get("packages", 0)
    ):
        problems.append(f"cache {cache.get('packages')} packages, {cache.get('without_sig')} without .sig")
    if cache.get("database") is not True or cache.get("sync_rc") != 0 or cache.get("resolve_rc") != 0:
        problems.append(f"offline sync/resolve failed: {cache}")
    if cache.get("resolves") != CACHE_SET:
        problems.append(f"resolved {cache.get('resolves')}")
    if not cache.get("sig_verified") or not all(cache["sig_verified"].values()):
        problems.append(f"signature check: {cache.get('sig_verified')}")
    if cache.get("tampered_rejected") is not True:
        problems.append("a tampered package passed the signature check")
    return problems


# --- planted violations: every checker turns red (no VM) -------------------------------------------

GOOD_INSTALL = {
    "state": {
        "system": "starting",
        "failed": [],
        "pending_jobs": ["time-sync.target", "pacman-init.service", "multi-user.target", "shadow.timer"],
        "unexplained_jobs": [],
    },
    "units": ["a.service"],
    "isolation": {
        "live_user_processes": [],
        "session_users": [],
        "autologin_processes": [],
        "greetd": "inactive",
        "rescue_shell": "inactive",
        "sshd": "inactive",
        "kiosk": "active",
        "kiosk_user": [INSTALLER],
    },
    "privilege": {
        "sudo_n": {INSTALLER: 1, "nobody": 1, LIVE: 0},
        "empty_password_login": {"root": False},
        "nullok_files": [],
    },
}


GOOD_REPOS = {
    "sections": ["options", "core", "extra", "seclegion"],
    "siglevels": SIGLEVELS,
    "servers": [SECLEGION_SERVER, ARCHIVE],
    "archive_dates": ["2026/10/15"],
    "openssh_installed": False,
    "sshd_state": {"sshd.service": "masked", "sshd.socket": "masked"},
    "ssh_host_keys": [],
    "listening_22": False,
}


def planted(**overrides):
    report = json.loads(json.dumps(GOOD_INSTALL))
    for dotted, value in overrides.items():
        section, key = dotted.split("__")
        report[section][key] = value
    return report


def test_planted_extra_or_missing_unit_is_caught():
    assert check_units(planted(), ["a.service"]) == []
    assert "unexpected units" in " ".join(check_units(planted(), []))
    assert "missing units" in " ".join(check_units(planted(), ["a.service", "b.socket"]))
    assert check_units(planted(state__failed=["x.service"]), ["a.service"]) != []
    assert check_units(planted(state__system="running", state__pending_jobs=[]), ["a.service"]) == []
    # a stuck job that is not the time-sync chain (a hung kiosk), or a degraded/timed-out system, fails
    assert check_units(planted(state__unexplained_jobs=["seclegion-kiosk.service"]), ["a.service"]) != []
    assert check_units(planted(state__pending_jobs=["seclegion-kiosk.service"]), ["a.service"]) != []
    assert check_units(planted(state__system="timeout"), ["a.service"]) != []
    assert check_units(planted(state__system="degraded"), ["a.service"]) != []
    assert check_units(planted(state__system="starting", state__pending_jobs=[]), ["a.service"]) != []


@pytest.mark.parametrize(
    "override",
    [
        {"isolation__live_user_processes": ["Hyprland"]},
        {"isolation__session_users": [LIVE]},
        {"isolation__autologin_processes": ["agetty --autologin root"]},
        {"isolation__greetd": "active"},
        {"isolation__kiosk": "failed"},
        {"privilege__sudo_n": {INSTALLER: 0, "nobody": 1}},
        {"privilege__empty_password_login": {"root": True}},
        {"privilege__nullok_files": ["/etc/pam.d/system-auth"]},
    ],
)
def test_planted_install_isolation_violation_is_caught(override):
    assert check_install_isolation(planted()) == []
    assert check_install_isolation(planted(**override)) != []


def load_selftest():
    from importlib import machinery, util

    path = os.path.join(REPO, "iso", "profile", "airootfs", "usr", "local", "bin", "seclegion-selftest")
    loader = machinery.SourceFileLoader("seclegion_selftest", path)  # a plain script, no .py suffix
    module = util.module_from_spec(util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def test_selftest_explains_only_the_time_sync_chain():
    st = load_selftest()
    after_time_sync = {"pacman-init.service": "a.target\ntime-sync.target\nb.service\n"}
    st.run = lambda argv, **_: (0, after_time_sync.get(argv[-1], "a.target\nb.service\n"))
    for unit in (
        "time-sync.target",
        "systemd-time-wait-sync.service",
        "pacman-init.service",
        "multi-user.target",
        "shadow.timer",
        "seclegion-rescue.target",
    ):
        assert st.waits_for_time_sync(unit), unit
    for unit in ("seclegion-kiosk.service", "greetd.service", "sshd.socket"):
        assert not st.waits_for_time_sync(unit), unit


def test_selftest_cache_probe_creates_the_pacman_cachedir(tmp_path):
    """pacman exits 1 at once when --cachedir does not exist; that made the offline `-Sy` probe fail."""
    st = load_selftest()
    st.CACHE = str(tmp_path)
    seen = []

    def fake_run(argv, **_):
        if "--cachedir" in argv:
            seen.append(os.path.isdir(argv[argv.index("--cachedir") + 1]))
        return 0, ""

    st.run = fake_run
    st.cache()
    assert seen and all(seen), seen


def test_selftest_unit_is_not_ordered_after_the_time_sync_chain():
    """pacman-init waits for time-sync.target, which never completes offline: the selftest must not."""
    path = os.path.join(
        REPO, "iso", "profile", "airootfs", "etc", "systemd", "system", "seclegion-selftest.service"
    )
    with open(path, encoding="utf-8") as handle:
        deps = [ln for ln in handle if re.match(r"\s*(After|Requires|Wants|BindsTo)=", ln)]
    assert deps, "the unit has no ordering lines at all"
    assert not [ln for ln in deps if re.search(r"pacman-init|time-sync|time-set", ln)], deps


def test_planted_sshd_is_rejected_by_the_repos_judge():
    """Checkpoint A gate 2: the judge behind the M2-repos VM test fails a live image that has sshd enabled."""
    assert check_repos(GOOD_REPOS) == []
    enabled = {"sshd.service": "enabled", "sshd.socket": "masked"}
    planted_state = check_repos({**GOOD_REPOS, "sshd_state": enabled})
    assert any("sshd is not masked" in p for p in planted_state), planted_state
    both = check_repos({**GOOD_REPOS, "sshd_state": {"sshd.service": "enabled", "sshd.socket": "enabled"}})
    assert any("sshd is not masked" in p for p in both), both
    keys = check_repos({**GOOD_REPOS, "ssh_host_keys": ["/etc/ssh/ssh_host_ed25519_key"]})
    assert any("host keys" in p for p in keys), keys
    listening = check_repos({**GOOD_REPOS, "listening_22": True})
    assert any(":22" in p for p in listening), listening
    # the same facts as the selftest prints them on serial, parsed by the VM test's own parser
    sick = {
        **GOOD_REPOS,
        "section": "repos",
        "listening_22": True,
        "sshd_state": {"sshd.service": "enabled", "sshd.socket": "masked"},
    }
    parsed = parse(f"{PREFIX}{json.dumps(sick)}\n")["repos"]
    assert len(check_repos(parsed)) == 2, check_repos(parsed)


def test_planted_privilege_lock_repos_and_cache_violations_are_caught():
    assert (
        check_lock({"locker_processes": ["hyprlock"], "locked_hints": {}, "hypridle_conf_dpms": True}) != []
    )
    assert (
        check_lock({"locker_processes": [], "locked_hints": {"1": "yes"}, "hypridle_conf_dpms": True}) != []
    )
    assert check_repos({"sections": ["options", "core", "extra", "seclegion", "foo"]}) != []
    assert (
        check_repos(
            {
                "sections": ["options", "core", "extra", "seclegion"],
                "siglevels": ["SigLevel = Required DatabaseOptional", "SigLevel = Optional TrustAll"],
                "servers": [SECLEGION_SERVER, ARCHIVE],
                "archive_dates": ["2026/10/15"],
            }
        )
        != []
    )
    assert check_repos(GOOD_REPOS) == []
    # openssh installed is fine (decisions.md M2-openssh); an enabled sshd, a host key or a :22 listener
    # is not
    assert check_repos({**GOOD_REPOS, "openssh_installed": True}) == []
    enabled = {"sshd.service": "enabled", "sshd.socket": "masked"}
    assert check_repos({**GOOD_REPOS, "sshd_state": enabled}) != []
    static = {"sshd.service": "masked", "sshd.socket": "static"}
    assert check_repos({**GOOD_REPOS, "sshd_state": static}) != []
    assert check_repos({**GOOD_REPOS, "sshd_state": {"sshd.service": "masked"}}) != []
    assert check_repos({**GOOD_REPOS, "ssh_host_keys": ["/etc/ssh/ssh_host_ed25519_key"]}) != []
    assert check_repos({**GOOD_REPOS, "listening_22": True}) != []
    assert check_repos({k: v for k, v in GOOD_REPOS.items() if k != "listening_22"}) != []
    assert check_cache({"packages": 2, "sigs": 1, "without_sig": 1}) != []
    assert check_privilege({"accounts": {"root": {"password": "NP"}}}) != []


GOOD_INSTALLER = {
    "rules_run": ["/run/polkit-1/rules.d/" + RULE_BASENAME], "rules_etc": [], "gui_running": True,
    "pkexec_help_rc": 0, "pkexec_help_usage": True, "pkexec_other_rc": 127,
}


def test_m2_check_installer_accepts_the_designed_install_report_and_rejects_deviations():
    assert check_installer(GOOD_INSTALLER, "install") == []
    for bad in ({"gui_running": False}, {"pkexec_help_rc": 126}, {"pkexec_help_usage": False},
                {"pkexec_other_rc": 0}, {"rules_run": []}, {"rules_etc": ["/etc/polkit-1/rules.d/x.rules"]},
                {"rules_run": GOOD_INSTALLER["rules_run"] + ["/run/polkit-1/rules.d/60-other.rules"]}):
        assert check_installer({**GOOD_INSTALLER, **bad}, "install") != [], bad
    live = {"rules_run": [], "rules_etc": []}
    assert check_installer(live, "live") == [] and check_installer(live, "rescue") == []
    assert check_installer(GOOD_INSTALLER, "live") != []  # the rule must not exist outside the install target


# --- VM boots ------------------------------------------------------------------------------------


def finish(status, actual):
    if status == "NOT RUN":
        pytest.skip(f"NOT RUN: {actual}")
    assert status == "PASS", actual


@pytest.fixture(scope="module")
def scratch():
    root = "/var/tmp/seclegion-build/vm"  # image files only live here (plan r13 rules)
    os.makedirs(root, exist_ok=True)
    path = tempfile.mkdtemp(prefix="m2-", dir=root)
    yield path
    shutil.rmtree(path, ignore_errors=True)  # the directory this run created


class Boot:
    def __init__(self, text, screen, command):
        self.text, self.screen, self.command, self.report = text, screen, command, parse(text)


@functools.cache
def _boot(scratch_dir, iso, mode, action):
    workdir = os.path.join(scratch_dir, f"{mode}-{action}")
    with QemuVM(iso, workdir, credentials=[("seclegion.selftest", action)]) as vm:
        command = evidence.repo_relative(vm.command, REPO)
        wait_for_menu(vm)
        choose(vm, ENTRY[mode])
        vm.serial.wait_for(r'SECLEGION-SELFTEST \{"section": "done"', MODE_TIMEOUT)
        if action == "kill-kiosk" and "SECLEGION-KIOSK-ERROR" not in vm.serial.text():
            # the error unit prints its marker right after the kill, i.e. usually before "done":
            # wait_for searches from its cursor (already past "done"), so only wait if not yet seen
            vm.serial.wait_for(r"SECLEGION-KIOSK-ERROR", 60)
            time.sleep(3)  # let tty1 draw the error screen
        shot = bootgate.take_screen(vm)
        return Boot(vm.serial.text(), shot, command)


def boot(scratch, mode, action="report"):
    iso = bootgate.find_iso()
    return _boot(scratch, iso, mode, action)


def gate(test_id, expected, body, scratch_dir):
    """run_gate with the shared boots: body(result_dir) -> (actual, [Boot...]); logs are copied in."""

    def wrapped(result_dir, iso):
        actual, boots, ocr = body()
        text = "".join(
            (f"[entry {b_mode}]\n" if len(boots) > 1 else "") + b.text + "\n" for b_mode, b in boots
        )
        with open(os.path.join(result_dir, "serial.log"), "w", encoding="utf-8") as out:
            out.write(text)
        if boots[-1][1].screen and os.path.isfile(boots[-1][1].screen):
            shutil.copy(boots[-1][1].screen, os.path.join(result_dir, "screen.png"))
        return actual, boots[0][1].command, ocr

    finish(*bootgate.run_gate(test_id, expected, wrapped))


def no_problems(problems):
    assert problems == [], "; ".join(problems)


@pytest.mark.iso
@pytest.mark.parametrize("mode", ["install", "live", "rescue"])
def test_m2_units_each_mode_runs_exactly_its_expected_units(mode, scratch):
    def body():
        b = boot(scratch, mode)
        if os.environ.get("SL_WRITE_EXPECTED") == "1":
            with open(os.path.join(EXPECTED, f"{mode}.txt"), "w", encoding="utf-8") as out:
                out.write(
                    "# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors\n"
                    # REUSE-IgnoreStart
                    "# SPDX-License-Identifier: MIT\n# Active services and sockets after boot, "
                    # REUSE-IgnoreEnd
                    f"{mode} mode (observed by seclegion-selftest; reviewed by hand).\n"
                )
                out.write("\n".join(b.report["units"]) + "\n")
        no_problems(check_units(b.report, expected_units(mode)))
        return (
            f"{len(b.report['units'])} active services and sockets equal tests/expected-units/{mode}.txt",
            [(mode, b)],
            "n/a",
        )

    gate(
        f"M2-units-{mode}",
        f"{mode} mode: the active services and sockets equal "
        f"tests/expected-units/{mode}.txt, system running (or starting behind the offline time-sync chain "
        f"only), no failed unit",
        body,
        scratch,
    )


@pytest.mark.iso
def test_m2_install_isolation_and_live_privilege(scratch):
    def body():
        live, install = boot(scratch, "live"), boot(scratch, "install")
        no_problems(check_privilege(live.report["privilege"]))
        no_problems(check_install_isolation(install.report))
        return (
            "live: root/installer locked, passwordless sudo only for the live user, no nullok, no "
            "empty-password login; install: no live user, no autologin, `sudo -n true` fails",
            [("live", live), ("install", install)],
            "n/a",
        )

    gate(
        "M2-privilege",
        "live privilege as designed; install mode has no live user, no autologin and no sudo",
        body,
        scratch,
    )


@pytest.mark.iso
def test_m2_kiosk_killed_shows_the_error_screen(scratch):
    def body():
        b = boot(scratch, "install", "kill-kiosk")
        err = b.report.get("kiosk_error", {})
        assert err.get("killed") is True and err.get("error_unit") == "active" and err.get("log_exists"), err
        assert err.get("kiosk") != "active", err
        status, text = bootgate.ocr_status_of(b.screen)
        if status == "OK":
            assert "kiosk stopped" in text.lower().replace("\n", " "), (
                f"OCR lacks the error text: {text[:200]!r}"
            )
        elif REQUIRE_OCR:
            raise AssertionError(f"SL_REQUIRE_OCR=1 but OCR did not run: {status}")
        return (
            "cage killed: the kiosk unit failed, the error unit is active, the log exists and tty1 "
            "shows the error screen",
            [("install", b)],
            status,
        )

    gate("M2-kiosk-error", "a killed kiosk shows the error screen with the log path", body, scratch)


@pytest.mark.iso
def test_m2_installer_kiosk_gui_runs_and_pkexec_is_the_only_privilege(scratch):
    """Install: the GTK installer is up in the kiosk and `pkexec /usr/bin/seclegion-install --help` works as
    seclegion-installer; Live and Rescue have no polkit rule. Shares the boots of the units gates."""

    def body():
        boots = [(mode, boot(scratch, mode)) for mode in ("install", "live", "rescue")]
        for mode, b in boots:
            no_problems(check_installer(b.report.get("installer", {}), mode))
        no_problems(check_install_isolation(boots[0][1].report))
        return (
            "install: the GTK installer runs as seclegion-installer, pkexec runs only seclegion-install, one "
            "polkit rule in /run; live and rescue: no polkit rule",
            boots,
            "n/a",
        )

    gate(
        "M2-installer",
        "the install kiosk runs the GTK installer; pkexec of seclegion-install is its only privilege",
        body,
        scratch,
    )


@pytest.mark.iso
def test_m2_lock_live_mode_has_no_lock_and_dpms_only(scratch):
    def body():
        b = boot(scratch, "live")
        no_problems(check_lock(b.report["lock"]))
        return (
            (
                "no locker running, no session locked, hypridle.conf is DPMS only; "
                f"hypridle running: {b.report['lock'].get('hypridle_running')} (report only)"
            ),
            [("live", b)],
            "n/a",
        )

    gate("M2-lock", "live mode: no lock; hypridle configuration is DPMS only", body, scratch)


@pytest.mark.iso
def test_m2_repos_core_extra_archive_only_sshd_masked(scratch):
    def body():
        b = boot(scratch, "live")
        no_problems(check_repos(b.report["repos"]))
        return (
            "core and extra from one archive date, SigLevel Required DatabaseOptional, sshd masked, "
            "no host keys, nothing on :22",
            [("live", b)],
            "n/a",
        )

    gate(
        "M2-repos",
        "the image's pacman.conf: core/extra from the archive only, signatures required",
        body,
        scratch,
    )


@pytest.mark.iso
def test_m2_cache_resolves_offline_and_rejects_a_tampered_package(scratch):
    def body():
        b = boot(scratch, "live")
        no_problems(check_cache(b.report["cache"]))
        c = b.report["cache"]
        return (
            f"{c['packages']} cached packages all with .sig; offline resolve ok; signatures verify; "
            "tampered package rejected",
            [("live", b)],
            "n/a",
        )

    gate(
        "M2-cache",
        "the offline cache resolves with no network and keeps verifiable Arch signatures",
        body,
        scratch,
    )


def test_selftest_console_survives_a_getty_hangup(tmp_path):
    """serial-getty@ttyS0 starting mid-run hangs up a held fd; each line must reopen the console."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader(
        "sl_selftest", os.path.join(REPO, "iso/profile/airootfs/usr/local/bin/seclegion-selftest")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    out = tmp_path / "ttyS0"
    out.write_text("")
    console = mod.Console(str(out))
    console.emit("start", mode="rescue")
    out.unlink()  # the old open file is gone, like a hung-up tty: a held fd would write into the void
    out.write_text("")
    console.emit("done", mode="rescue")
    assert '"section": "done"' in out.read_text()
