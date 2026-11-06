# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Evidence records: result.json read/write/validate and TESTING.md rendering.

Layout (spec/v1 section 7): evidence/<test-id>/<iso-sha256>/<UTC-timestamp>/result.json
plus the artifact files it lists (serial.log, screen.png). Every run gets a new
timestamp directory and a tracked result is never overwritten. The small artifacts are
committed with the result so a PASS stays re-verifiable from a fresh clone.

`validate` is a consistency check, not proof that a run happened: a result is only
accepted when its commit is a real ancestor of HEAD, its timestamp is sane and not before
that commit, its ISO hash matches the built ISO, the stored serial.log satisfies the
canonical patterns for its test, and every artifact re-hashes. A fabricated but consistent
serial.log on a real commit cannot be told from a real one without signing (accepted
residual, docs/decisions.md).
"""

import datetime
import hashlib
import json
import os
import re
import subprocess

import branding

SCHEMA_VERSION = 1
STATUSES = ("PASS", "FAIL", "NOT RUN")
CLASSES = ("AUTO", "PROBE", "HW-MANUAL")
NO_ISO = "NONE"  # iso_sha256 for a NOT RUN record where no ISO exists
REQUIRED_FIELDS = (
    "schema",
    "test_id",
    "status",
    "class",
    "commit",
    "iso_sha256",
    "env",
    "command",
    "expected",
    "serial_patterns",
    "actual",
    "exit_code",
    "artifacts",
    "timestamp",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DIRTY_SUFFIX = "-dirty"
# Same pattern as tests/lib/serial.py (kept equal by a unit test): the verifier cannot
# import tests/, and must strip exactly what the harness stripped when it matched.
ANSI_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\r")

# Canonical serial patterns per test_id. A PASS is accepted only when its recorded
# serial_patterns equal these exactly: the record cannot choose its own (weaker) oracle.
# tests/iso/test_m0_boot.py reads its patterns from here.
M0_BOOT_ENTRY = r"Install SecLegion OS"  # the default GRUB entry's title, drawn on serial
M0_BOOT_LOGIN = r"seclegion login:|root@seclegion"  # the ttyS0 getty prompt, or the autologin shell
# M1 (plan r13 J1c). Each "SECLEGION-MODE=<m>" line is echoed on ttyS0 by seclegion-mode@<m>.service.
M1_MENU_TITLES = [  # the six top-level entries, in menu order
    r"Install SecLegion OS",
    r"Try SecLegion OS \(Live\)",
    r"Rescue",
    r"Memory Test \(Memtest86\+\)",
    r"UEFI Firmware Settings",
    r"Safe Graphics",
]
# (entry, mode): install, live, rescue, then Safe Graphics install and live (same two modes)
M1_MODES = [
    ("install", "install"),
    ("live", "live"),
    ("rescue", "rescue"),
    ("safe-install", "install"),
    ("safe-live", "live"),
]
M1_MEMTEST_BANNER = r"Memtest86\+ v\d+\.\d+"  # the tool's own title bar, not the menu entry


def _st(section, mode, rest):
    """Pattern for one self test line: section and mode first, then `rest` somewhere after them."""
    return rf'SECLEGION-SELFTEST \{{"section": "{section}", "mode": "{mode}"[^\n]*?{rest}'


def m4_install_patterns(mode):
    """Install marker, install exit 0, clean target, [alongside: NTFS kept], greeter, SecLegion banner."""
    return [
        r"SECLEGION-INSTALL-OK",
        r"DL-INSTALL 0",
        r"DL-TARGET 0",
        *([r"NTFS-SHA256-UNCHANGED [0-9a-f]{64}"] if mode == "alongside" else []),
        *([r"PARTS-SHA256-UNCHANGED [0-9a-f]{64}"] if mode == "partition" else []),
        r"\[phase installed-boot\][\s\S]*?Started .*(?:greetd|[Gg]reeter)",
        r"\nSecLegion OS \S+ \(ttyS0\)",  # the getty banner from /etc/issue: our os-release, not Arch's
    ]


CANONICAL_SERIAL_PATTERNS = {
    "M0-boot": [M0_BOOT_ENTRY, M0_BOOT_LOGIN],
    "M1-menu": [*M1_MENU_TITLES, r"SECLEGION-MODE=install"],
    # tests/iso/test_m1_menu.py writes "[entry <name>]" before each boot's serial text.
    "M1-modes": [rf"\[entry {entry}\][\s\S]*?SECLEGION-MODE={mode}" for entry, mode in M1_MODES],
    "M1-memtest": [r"Memory Test \(Memtest86\+\)", M1_MEMTEST_BANNER],
    "M1-fwsetup": [r"UEFI Firmware Settings", r"Device Manager"],
    "M1-branding": [r"Install SecLegion OS", r"SECLEGION-MODE=install", r"seclegion login:"],
    "M1-theme-repro": [r"theme-repro: identical"],
    # M2 (plan r13 J2c). tests/iso/test_m2_targets.py boots a mode and reads the self test's JSON lines
    # (usr/local/bin/seclegion-selftest) from ttyS0; each line starts with SECLEGION-SELFTEST.
    **{
        f"M2-units-{m}": [
            rf"SECLEGION-MODE={m}",
            # "starting" only with no unexplained job: offline, the time-sync chain never finishes (the
            # judge in tests/iso/test_m2_targets.py bounds which jobs may be pending)
            _st("state", m,
                r'"system": "(?:running|starting)", "failed": \[\][^\n]*?"unexplained_jobs": \[\]'),
            _st("units", m, r'"part": 1, '),
            _st("done", m, ""),
        ]
        for m in ("install", "live", "rescue")
    },
    "M2-privilege": [
        r"\[entry live\]",
        _st(
            "privilege",
            "live",
            r'"root": \{"exists": true, "uid": 0, '
            r'"shell": "[^"]*", "password": "L"\}',
        ),
        r"\[entry install\]",
        _st("privilege", "install", ""),  # the selftest prints privilege before isolation
        _st("isolation", "install", r'"live_user_processes": \[\], '),
        _st("done", "install", ""),
    ],
    "M2-kiosk-error": [
        r"SECLEGION-MODE=install",
        # the error unit prints its marker before the selftest sees it active and prints kiosk_error
        r"SECLEGION-KIOSK-ERROR log=/var/log/seclegion/kiosk\.log",
        _st("kiosk_error", "install", r'"killed": true'),
    ],
    "M2-installer": [
        r"\[entry install\]",
        _st("installer", "install", r'"rules_run": \["[^"]*/50-seclegion-installer\.rules"\], '
            r'"rules_etc": \[\], "gui_running": true, "pkexec_help_rc": 0, "pkexec_help_usage": true, '
            r'"pkexec_other_rc": [1-9]'),
        r"\[entry live\]",
        _st("installer", "live", r'"rules_run": \[\], "rules_etc": \[\]'),
        r"\[entry rescue\]",
        _st("installer", "rescue", r'"rules_run": \[\], "rules_etc": \[\]'),
    ],
    "M2-lock": [
        r"SECLEGION-MODE=live",
        _st("lock", "live", r'"locker_processes": \[\], '),
        _st("done", "live", ""),
    ],
    "M2-live-desktop": [
        r"SECLEGION-MODE=live",
        _st(
            "desktop",
            "live",
            r'"hyprland_lua": true, "hyprland_lua_is_skel": true, "live_processes": '
            r'\["Hyprland", "waybar"\]',
        ),
        _st("done", "live", ""),
    ],
    "M2-repos": [
        r"SECLEGION-MODE=live",
        _st(  # one line: two patterns on it would need a second repos line (matched in order)
            "repos",
            "live",
            r'"sections": \["options", "core", "extra", "seclegion"\][^\n]*?'
            r'"sshd_state": \{"sshd\.service": "masked", '
            r'"sshd\.socket": "masked"\}, "ssh_host_keys": \[\], '
            r'"listening_22": false',
        ),
        _st("done", "live", ""),
    ],
    "M2-cache": [
        r"SECLEGION-MODE=live",
        _st(
            "cache",
            "live",
            r'"without_sig": 0, "database": true, "sync_rc": 0, '
            r'"resolve_rc": 0',
        ),
        _st("done", "live", ""),
    ],
    # S2 (checkpoint A gate 19). tests/iso/test_s2_host_repo.py types into the rescue shell and has it print
    # these markers on ttyS0: [seclegion] synced from a repo on the host, hello installed, hello queried.
    "S2-host-repo": [
        r"SECLEGION-MODE=rescue",
        r"S2-REPO-SYNC-OK",
        r"S2-REPO-INSTALL-OK",
        r"S2-REPO-QUERY hello",
    ],
    # M4 (checkpoint B). tests/install/test_i2_run.py writes "[phase <name>]" headers around the install
    # transcript (devloop.run outputs) and the installed disk's boot serial.
    "M4-erase": m4_install_patterns("erase"),
    "M4-luks": m4_install_patterns("luks"),
    "M4-alongside": m4_install_patterns("alongside"),
    "M4-partition": m4_install_patterns("partition"),
    "M4-offline": [
        r"\[phase install-command\][^\n]*\n[^\n]*-nic none",  # QEMU command of the install VM: no NIC
        r"SECLEGION-INSTALL-OK",
        r"DL-INSTALL 0",
    ],
    "M4-target-clean": [
        r"\[phase check\]\n0\n",  # find /mnt -name user_credentials.json | wc -l
        r"\[phase target-check\]\nDL-TARGET 0",  # target_check printed nothing before its marker
    ],
    "M4-mutation": [r"MUTANTS \d+ GREEN 0\b"],
    # checkpoint C
    # M5-fast (G47): tests/install/test_m5_fast.py appends the two M5-FAST lines after the install transcript,
    # only once the clock (QEMU launch to the installed greeter screendump) is < 900 s and OCR read "tester".
    "M5-fast": [
        *m4_install_patterns("erase"),
        r"M5-FAST elapsed_s=(?:[0-8]\d\d|\d{1,2}) limit_s=900\b",
        r"M5-FAST ocr=OK greeter screen names tester",
    ],
    # M5-diskfull (G49): "[phase install]" / "[phase after]" are the devloop.run outputs; DL-INSTALL 2 is the
    # configurator's refusal exit, then the three leftovers counts (pacman.conf cache, orig copy, /run creds).
    "M5-diskfull": [
        r"(?m)\[phase install\][\s\S]*?^refused: [^\n]*(?:disk_too_small|under 20 GiB)",
        r"DL-INSTALL 2\b",
        r"\[phase after\]\s+0\s+0\s+0\s",
    ],
    # M6-greeter (G41): the G41-*-RC<n> markers are printed by the guest's serial shell (split marker, so the
    # typed echo cannot match): <n> is the exit status of the probe, 0 = hyprland running / session file ok.
    "M6-greeter": [
        r"SECLEGION-INSTALL-OK",
        r"DL-INSTALL 0",
        r"\[phase installed-boot\][\s\S]*?Started .*(?:greetd|[Gg]reeter)",
        r"\[tester@\S+ ~\]\$ ",
        r"G41-BEFORE-RC1\b",  # no Hyprland before any greeter login
        r"G41-SESSIONFILE-RC0\b",  # exactly one session file, hyprland.desktop
        r"G41-WRONG-RC1\b",  # a wrong password starts nothing
        r"G41-ARA-RC1\b",  # the right keys on the ara group are the wrong password (toggle works)
        r"G41-RIGHT-RC0\b",  # toggled back to us, the right password starts Hyprland
        r"G41-OCR-OK\b",  # every greeter screen assertion ran (OCR) and held
    ],
    # W3 / V2 (installed-base gates). tests/install/test_m7a_defaults.py and test_m11_rollback.py boot an
    # overlay of the cached install (tests/lib/installed.py) and have the guest print one result line per
    # passed check (split, so the typed command never matches); the serial.log is that boot's console.
    "M7a-defaults": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM7A-UFW deny-incoming",
        r"\nM7A-SSHD masked inactive",
        r"\nM7A-BASELINE \d+",
    ],
    # tests/install/test_m7a_docker_ufw.py (D-DKR-1): the DOCKER-USER chain hands new connections to ufw.
    "M7a-docker-ufw": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM7A-DKR ufw active and service active",
        r"\nM7A-DKR4 ufw-user-forward before NEW drop",
        r"\nM7A-DKR6 (?:ufw-user-forward before NEW drop|chain absent)",
        r"\nM7A-DKRINFO tester without sudo",
    ],
    "M11-rollback": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM11-PAIR pre \d+ post \d+",
        r"\nM11-ROLLBACK to \d+",
        r"Started .*(?:greetd|[Gg]reeter)",  # the boot after the rollback
        r"\nM11-BACK \S+ restored with @broken",
    ],
    # CP-C VM (installed-base): M6 rows. tests/install/test_m6_target.py prints one result line per passed
    # check from the installed target's serial shell (split, so the typed command never matches).
    "M6-single-session": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM6-SINGLE no gnome gdm gnome-shell",
        r"\nM6-SINGLE wayland-sessions only hyprland",
    ],
    "M6-branding": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM6-BRANDING hits 0",
    ],
    "M6-roles": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM6-ROLES notifications one service file owner swaync",
        r"\nM6-ROLES polkit one agent installed",
        r"\nM6-ROLES secrets one provider installed",
        r"\nM6-ROLES every role package installed binary present",
    ],
    "M6-browsers": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM6-BROWSERS xdg default firefox",
        r"\nM6-BROWSERS flags ozone wayland sandbox on",
    ],
    # VG10 (installed-base): tests/install/test_m12_desktop_units.py, the 2026-10-31 desktop work.
    "M12-desktop-units": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nM12-PKGS wifi sysmon settings desktop branding libnm psutil installed",
        r"\nM12-HELPER root 755 polkit action registered",
        r"\nM12-ROOTAPPLY dry-run then real timezone set bad value refused",
        r"\nM12-SNAPPER config mode 644 readable",
        r"\nM12-UNITS displayd wallpaper enabled launchers executable",
        r"\nM12-IMPORTS wifi sysmon data modules import",
    ],
    # G39 (installed-base): tests/desktop/test_s6_userlua_vm.py, the user.lua override on a real session.
    "S6-userlua": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nS6-USERLUA user.lua written in the home of tester",
        r"\nS6-HYPRLAND started through the greeter and answers hyprctl",
        r"\nS6-BINDS SUPER L maps to the user command and the new bind is present",
        r"\nS6-OVERRIDE SUPER L created the marker and started no hyprlock",
        r"\nS6-NEWBIND SUPER F9 created the second marker",
    ],
    # G46 (installed-base): tests/desktop/test_s7_lock_vm.py, synthetic input under hyprlock.
    "S7-result": [
        r"Started .*(?:greetd|[Gg]reeter)",
        r"\nS7-HYPRLAND started through the greeter and answers hyprctl",
        r"\nS7-CONTROL a word typed over QMP reaches the focused client while unlocked",
        r"\nS7-LOCK SUPER L started hyprlock for tester",
        r"\nS7-LOCKED a word typed over QMP under the lock reached no client",
        r"\nS7-UNLOCK the tester password typed over QMP ended hyprlock",
        r"\nS7-AFTER a word typed over QMP reaches the client again after the unlock",
    ],
}
# The log a PASS is checked against, when it is not serial.log (the theme build has no console).
LOG_ARTIFACT = {"M1-theme-repro": "theme.log"}
# Patterns that must NOT appear in the log of a PASS (the negative half of a gate).
HASH_PATTERN = r"\$(?:y|7|6|5|2[abxy]?|1|sha\d+)\$[./0-9A-Za-z$,=-]{6,}"  # a crypt(3) password hash
M2_IDS = (
    "M2-units-install",
    "M2-units-live",
    "M2-units-rescue",
    "M2-privilege",
    "M2-kiosk-error",
    "M2-installer",
    "M2-lock",
    "M2-live-desktop",
    "M2-repos",
    "M2-cache",
)
M4_IDS = ("M4-erase", "M4-luks", "M4-alongside", "M4-partition", "M4-offline", "M4-target-clean",
          "M4-mutation")
# checkpoint C
M5_M6_IDS = ("M5-fast", "M5-diskfull", "M6-greeter")
# W3 / V2 (installed-base gates): the ids whose log must hold neither test secret.
W3_IDS = ("M7a-defaults", "M7a-docker-ufw", "M11-rollback")
# CP-C VM (installed-base): M6 rows
M6_TARGET_IDS = ("M6-single-session", "M6-branding", "M6-browsers", "M6-roles")
# VG10 (installed-base): the desktop units row
# S6-userlua and S7-result: same secrets (tests/desktop/test_s6_userlua_vm.py, test_s7_lock_vm.py)
M12_IDS = ("M12-desktop-units", "S6-userlua", "S7-result")
# The install test's secrets (tests/install/test_i2_run.py PASSWORD, LUKS_PASSPHRASE); a log that holds
# either leaked a secret to a serial console or transcript. Kept equal by a unit test.
M4_TEST_PASSWORD = "test-pass-1"
M4_TEST_LUKS_PASSPHRASE = "test-luks-2"
M6_TEST_WRONG_PASSWORD = "wrong-pass-9"  # test_d2_greeter_vm.py WRONG; kept equal by a unit test
FORBIDDEN_PATTERNS = {
    "M1-branding": [branding.BRAND_RE.pattern],
    **{t: [HASH_PATTERN] for t in M2_IDS},
    **{t: [re.escape(M4_TEST_PASSWORD), re.escape(M4_TEST_LUKS_PASSPHRASE)] for t in M4_IDS},
    # checkpoint C
    "M5-fast": [re.escape(M4_TEST_PASSWORD), re.escape(M4_TEST_LUKS_PASSPHRASE)],
    # a refused install never installs: no success marker, no traceback, no archinstall run, no secret
    "M5-diskfull": [re.escape(M4_TEST_PASSWORD), r"SECLEGION-INSTALL-OK", r"Traceback", r"archinstall"],
    "M6-greeter": [re.escape(M4_TEST_PASSWORD), re.escape(M6_TEST_WRONG_PASSWORD)],
    # W3 / V2 (installed-base gates)
    **{t: [re.escape(M4_TEST_PASSWORD), re.escape(M4_TEST_LUKS_PASSPHRASE)] for t in W3_IDS},
    # CP-C VM (installed-base): M6 rows
    **{t: [re.escape(M4_TEST_PASSWORD), re.escape(M4_TEST_LUKS_PASSPHRASE)] for t in M6_TARGET_IDS},
    **{t: [re.escape(M4_TEST_PASSWORD), re.escape(M4_TEST_LUKS_PASSPHRASE)] for t in M12_IDS},
}

TESTING_HEADER = """\
# TESTING

<!-- GENERATED by tools/gen-testing-md from evidence/*/*/*/result.json. DO NOT EDIT. -->
<!-- `tools/verify-evidence` regenerates this file and fails on any difference. -->

Every row is one `result.json`. `PASS` is only ever written by a test that ran;
`NOT RUN` means it did not. Evidence class: AUTO (VM, automatic), PROBE (VM, probe
copy), HW-MANUAL (real hardware, signed attestation).

"""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso():
    return datetime.datetime.now(datetime.UTC).strftime(TIMESTAMP_FORMAT)


def dir_stamp(timestamp):
    """2026-10-14T20:03:22Z -> 20261014T200322Z (the run directory name)."""
    return timestamp.replace("-", "").replace(":", "")


def git_env():
    """Environment without GIT_* so an outer hook or worktree cannot redirect git."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, env=git_env(), check=False
    )


def git_commit_id(repo):
    """HEAD sha, suffixed `-dirty` when tracked files differ or untracked files exist.

    evidence/ is excluded: it is the output of the run being recorded, not code under test.
    """
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if not head:
        return "unknown"
    status = git(repo, "status", "--porcelain", "--untracked-files=normal", "--", ".", ":(exclude)evidence")
    return head + DIRTY_SUFFIX if status.stdout.strip() or status.returncode else head


def repo_relative(argv, repo):
    """Join argv into one string with `<repo>/` prefixes removed (no host paths in evidence)."""
    prefix = os.path.abspath(repo).rstrip(os.sep) + os.sep
    return " ".join(arg.replace(prefix, "") for arg in argv)


def new_result_dir(evidence_root, test_id, iso_sha256):
    """Create a fresh run directory; returns (dir, timestamp). Never reuses a directory."""
    timestamp = now_iso()
    result_dir = os.path.join(evidence_root, test_id, iso_sha256, dir_stamp(timestamp))
    os.makedirs(os.path.dirname(result_dir), exist_ok=True)
    os.mkdir(result_dir)  # FileExistsError if a run already used this second
    return result_dir, timestamp


def write_result(evidence_root, record, artifact_names):
    """Hash the named artifacts (files already inside the run dir) and write result.json.

    `record` carries every REQUIRED_FIELDS key except `schema`, `artifacts`. The run dir is
    derived from record["timestamp"]; an existing result.json is never overwritten.
    Returns the run directory.
    """
    absent = [f for f in REQUIRED_FIELDS if f not in record and f not in ("schema", "artifacts")]
    if absent:
        raise ValueError(f"result record missing fields: {absent}")
    result_dir = os.path.join(
        evidence_root, record["test_id"], record["iso_sha256"], dir_stamp(record["timestamp"])
    )
    target = os.path.join(result_dir, "result.json")
    if os.path.exists(target):
        raise FileExistsError(f"refusing to overwrite existing evidence {target}")
    os.makedirs(result_dir, exist_ok=True)
    full = dict(record)
    full["schema"] = SCHEMA_VERSION
    full["artifacts"] = {name: sha256_file(os.path.join(result_dir, name)) for name in sorted(artifact_names)}
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(full, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result_dir


def load_results(evidence_root):
    """Return [(run_dir, parsed_dict, result_json_sha256)] sorted by path."""
    found = []
    if not os.path.isdir(evidence_root):
        return found
    for test_id in sorted(os.listdir(evidence_root)):
        for iso in _subdirs(os.path.join(evidence_root, test_id)):
            for stamp in _subdirs(os.path.join(evidence_root, test_id, iso)):
                run_dir = os.path.join(evidence_root, test_id, iso, stamp)
                path = os.path.join(run_dir, "result.json")
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as handle:
                        found.append((run_dir, json.load(handle), sha256_file(path)))
    return found


def _subdirs(path):
    if not os.path.isdir(path):
        return []
    return sorted(n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n)))


def iso_hashes_from_sums(path):
    """sha256 values of the *.iso entries in a SHA256SUMS file."""
    hashes = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            digest, _, name = line.strip().partition(" ")
            if SHA256_RE.match(digest) and name.lstrip(" *").endswith(".iso"):
                hashes.add(digest)
    return hashes


def check_commit(repo, commit, status):
    """Problems (without location prefix) with a recorded commit."""
    base = commit
    if isinstance(commit, str) and commit.endswith(DIRTY_SUFFIX):
        base = commit[: -len(DIRTY_SUFFIX)]
        if status == "PASS":
            return [f"PASS recorded on a dirty tree ({commit})"]
    if not isinstance(base, str) or not COMMIT_RE.match(base):
        return [f"commit {commit!r} is not a full 40-hex sha"]
    if git(repo, "cat-file", "-e", base + "^{commit}").returncode != 0:
        return [f"commit {base} does not exist in this repository"]
    ancestry = git(repo, "merge-base", "--is-ancestor", base, "HEAD").returncode
    if ancestry != 0:
        return [f"commit {base} is not an ancestor of HEAD"]
    return []


def commit_time(repo, commit):
    """Committer time of a commit as an aware UTC datetime, or None if unreadable."""
    out = git(repo, "show", "-s", "--format=%ct", commit + "^{commit}")
    try:
        return datetime.datetime.fromtimestamp(int(out.stdout.strip()), datetime.UTC)
    except ValueError:
        return None


def check_serial(run_dir, result):
    """Re-apply the canonical serial patterns, in order, to the stored serial.log."""
    patterns = result["serial_patterns"]
    if not patterns:
        return ["PASS without serial_patterns to re-check"]
    canonical = CANONICAL_SERIAL_PATTERNS.get(result["test_id"])
    if canonical is None:
        return [f"PASS for test {result['test_id']!r}, which has no canonical serial patterns"]
    if patterns != canonical:
        return [
            f"serial_patterns differ from the canonical patterns for {result['test_id']} "
            f"(recorded {patterns!r}); a run with a changed oracle cannot be a PASS"
        ]
    log_name = LOG_ARTIFACT.get(result["test_id"], "serial.log")
    if log_name not in result["artifacts"]:
        return [f"PASS without a {log_name} artifact"]
    path = os.path.join(run_dir, log_name)
    if not os.path.isfile(path):
        return []  # reported as a missing artifact
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = ANSI_RE.sub("", handle.read())
    cursor = 0
    for pattern in patterns:
        try:
            match = re.compile(pattern).search(text, cursor)
        except re.error as exc:
            return [f"serial pattern /{pattern}/ is not a valid regex: {exc}"]
        if not match:
            return [f"{log_name} does not match /{pattern}/ (expected for a PASS)"]
        cursor = match.end()
    for pattern in FORBIDDEN_PATTERNS.get(result["test_id"], []):
        hit = re.compile(pattern, re.IGNORECASE).search(text)
        if hit:
            return [f"{log_name} matches the forbidden /{pattern}/ at {hit.group()!r}"]
    return []


def validate(run_dir, result, repo=None, iso_hashes=None):
    """Return a list of problems with one result (empty = consistent).

    repo: repository to check commits against (None skips the commit check; only unit
    tests of unrelated rules do that). iso_hashes: set of acceptable ISO sha256 values
    for a PASS, or None when no ISO reference is available / the check is skipped.
    """
    problems = []
    where = run_dir
    missing = [f for f in REQUIRED_FIELDS if f not in result]
    if missing:
        return [f"{where}: missing fields {missing}"]
    if result["schema"] != SCHEMA_VERSION:
        problems.append(f"{where}: unsupported schema {result['schema']!r}")
    if result["status"] not in STATUSES:
        problems.append(f"{where}: bad status {result['status']!r}")
    if result["class"] not in CLASSES:
        problems.append(f"{where}: bad class {result['class']!r}")
    if not (SHA256_RE.match(str(result["iso_sha256"])) or result["iso_sha256"] == NO_ISO):
        problems.append(f"{where}: iso_sha256 is neither a sha256 nor {NO_ISO}")
    if not isinstance(result["serial_patterns"], list):
        return problems + [f"{where}: serial_patterns must be a list"]

    stamp = str(result["timestamp"])
    parsed = None
    if TIMESTAMP_RE.match(stamp):
        try:
            parsed = datetime.datetime.strptime(stamp, TIMESTAMP_FORMAT).replace(tzinfo=datetime.UTC)
        except ValueError:
            pass
    if parsed is None:
        problems.append(f"{where}: timestamp {stamp!r} is not ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ)")
    elif parsed > datetime.datetime.now(datetime.UTC):
        problems.append(f"{where}: timestamp {stamp} is in the future")
    parts = os.path.normpath(run_dir).split(os.sep)
    want = [result["test_id"], result["iso_sha256"], dir_stamp(stamp)]
    if parts[-3:] != want:
        problems.append(f"{where}: directory does not match test_id/iso_sha256/timestamp in result.json")

    if repo is not None:
        commit_problems = check_commit(repo, result["commit"], result["status"])
        problems += [f"{where}: {p}" for p in commit_problems]
        if not commit_problems and parsed is not None:
            committed = commit_time(repo, str(result["commit"]).removesuffix(DIRTY_SUFFIX))
            if committed is not None and parsed < committed:
                problems.append(
                    f"{where}: timestamp {stamp} is earlier than the commit's "
                    f"committer date {committed.strftime(TIMESTAMP_FORMAT)}"
                )
    if result["status"] == "PASS":
        if result["exit_code"] != 0:
            problems.append(f"{where}: PASS with exit_code {result['exit_code']!r}")
        if not result["artifacts"]:
            problems.append(f"{where}: PASS with no artifacts")
        if result["iso_sha256"] == NO_ISO:
            problems.append(f"{where}: PASS without an ISO")
        elif iso_hashes is not None and result["iso_sha256"] not in iso_hashes:
            problems.append(
                f"{where}: iso_sha256 {result['iso_sha256']} matches no known ISO (out/SHA256SUMS or --iso)"
            )
        if result["artifacts"]:
            problems += [f"{where}: {p}" for p in check_serial(run_dir, result)]
    if result["status"] == "NOT RUN" and result["artifacts"]:
        problems.append(f"{where}: NOT RUN must not list artifacts")
    for name, expected in sorted(result["artifacts"].items()):
        if os.path.basename(name) != name:
            problems.append(f"{where}: artifact name {name!r} escapes the run dir")
            continue
        path = os.path.join(run_dir, name)
        if not os.path.isfile(path):
            problems.append(f"{where}: artifact {name} is missing")
        elif sha256_file(path) != expected:
            problems.append(f"{where}: artifact {name} sha256 differs from result.json")
    return problems


def render_testing_md(results):
    """results: [(result_dir, parsed_dict, result_json_sha256)] -> TESTING.md text."""
    rows = []
    counts = {s: 0 for s in STATUSES}
    for _dir, res, digest in results:
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        rows.append(
            "| {test_id} | {status} | {cls} | `{iso}` | `{commit}` | {ts} | {n} | `{digest}` |".format(
                test_id=res["test_id"],
                status=res["status"],
                cls=res["class"],
                iso=str(res["iso_sha256"])[:12],
                commit=str(res["commit"])[:12],
                ts=res["timestamp"],
                n=len(res["artifacts"]),
                digest=digest[:12],
            )
        )
    text = TESTING_HEADER
    if not rows:
        return text + "No evidence recorded yet.\n"
    text += "Totals: " + ", ".join(f"{counts[s]} {s}" for s in STATUSES) + "\n\n"
    text += "| Test | Status | Class | ISO sha256 | Commit | Run (UTC) | Artifacts | result.json sha256 |\n"
    text += "|---|---|---|---|---|---|---|---|\n"
    return text + "\n".join(rows) + "\n"
