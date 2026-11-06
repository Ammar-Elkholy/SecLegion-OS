# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""U4: installer GUI pages 6-15 (pure models always; GTK render only under Broadway, else skipped)."""

import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(ROOT, "installer", "installd"))
sys.path.insert(0, HERE)
import configurator as c  # noqa: E402
from model import Model  # noqa: E402
from pages import p6_encryption, p11_hardware, p15_about  # noqa: E402
from test_gui_pages_a import VDA, _free_display  # noqa: E402
from test_plan import load_facts  # noqa: E402

PW = "hunter2-Secret!"
PP = "correct horse battery"
DISK_NAME = "QEMU HARDDISK"


@pytest.fixture(autouse=True)
def _no_release(monkeypatch):
    monkeypatch.delenv("SECLEGION_RELEASE", raising=False)
    import release
    monkeypatch.setattr(release, "MARKER", "/nonexistent/seclegion-release")
    monkeypatch.setattr(release.is_release, "__defaults__", (None, "/nonexistent/seclegion-release"))


def filled(passphrase="", facts=None):
    m = Model(facts or load_facts())
    m.pages["disk"].set_disk(VDA)
    u = m.pages["user"]
    u.set_username("ammar")
    u.set_password(PW)
    u.set_confirm(PW)
    m.pages["encryption"].set_passphrase(passphrase)
    m.pages["encryption"].set_confirm(passphrase)
    return m


def fake_installer(tmp_path, body):
    p = tmp_path / "fake-install"
    p.write_text("#!/usr/bin/python3\nimport os, sys\n" + textwrap.dedent(body))
    p.chmod(0o755)
    return str(p)


ECHO = """
    print("argv:", " ".join(sys.argv[1:]), flush=True)
    path = sys.argv[sys.argv.index("--answers") + 1]
    print("mode:", oct(os.stat(path).st_mode & 0o777), "dirmode:",
          oct(os.stat(os.path.dirname(path)).st_mode & 0o777), flush=True)
    print("SECLEGION-INSTALL-OK")
"""


def progress(m, tmp_path, body=ECHO):
    p = m.pages["progress"]
    p.installer = [fake_installer(tmp_path, body)]
    p.run_dir = str(tmp_path)
    p.log_path = str(tmp_path / "install.log")
    return p


# ---- page 6 / 7 ----------------------------------------------------------------

def test_gui_pages_b_encryption_empty_defaults_to_user_password():
    m = filled()
    enc = m.pages["encryption"]
    assert enc.can_next() and enc.fragment() == {}
    a = c.Answers.from_dict({**m.answers(), "confirm": DISK_NAME})
    assert a.passphrase == PW
    enc.set_passphrase(PP)
    assert not enc.can_next() and "do not match" in enc.error()
    enc.set_confirm(PP)
    assert enc.can_next() and enc.fragment() == {"luks_passphrase": PP}
    assert c.Answers.from_dict(m.answers()).passphrase == PP
    assert "Too short" in p6_encryption.strength("abc") and "empty" in p6_encryption.strength("")
    assert p6_encryption.strength("Tr0ub4dor&3-horse-staple") == "Strong."


def test_gui_pages_b_encryption_page_only_when_luks():
    m = Model(load_facts())
    m.pages["disk"].set_disk(VDA)
    assert "encryption" in [p.key for p in m.visible()]
    m.pages["disk"].set_luks(False)
    assert "encryption" not in [p.key for p in m.visible()]


def test_gui_pages_b_user_page_rules():
    u = Model(load_facts()).pages["user"]
    assert not u.can_next()
    u.set_username("Bad Name")
    assert "Username" in u.error()
    u.set_username("ammar")
    u.set_hostname("-bad")
    assert "Hostname" in u.error()
    u.set_hostname("legion")
    assert u.error() == "Choose a password."
    u.set_password("x")
    u.set_confirm("y")
    assert "do not match" in u.error()
    u.set_confirm("x")
    assert u.can_next()
    assert u.fragment() == {"username": "ammar", "password": "x", "hostname": "legion"}


# ---- page 8 review ------------------------------------------------------------

def test_gui_pages_b_review_requires_exact_typed_name():
    m = filled()
    r = m.pages["review"]
    assert r.expected() == DISK_NAME
    assert not r.can_next() and DISK_NAME in r.error()
    for wrong in ("qemu harddisk", DISK_NAME + " ", "QEMU", ""):
        r.set_typed(wrong)
        assert not r.can_next(), wrong
    r.set_typed(DISK_NAME)
    assert r.can_next() and r.error() is None
    assert r.fragment() == {"confirm": DISK_NAME}
    assert m.answers()["confirm"] == DISK_NAME
    c.validate(c.Answers.from_dict(m.answers()), m.facts)


def test_gui_pages_b_review_shows_exact_dry_run_and_no_secret():
    m = filled(PP)
    r = m.pages["review"]
    text = r.commands()
    cfg, _ = c.build_config(c.Answers.from_dict({**m.answers(), "confirm": DISK_NAME}), m.facts)
    lines = []
    c.dry_run(cfg, c.Answers.from_dict({**m.answers(), "confirm": DISK_NAME}), "/run/seclegion-install",
              out=lines.append)
    assert text == "\n".join(lines)
    assert "Would run: archinstall --config /run/seclegion-install/user_configuration.json" in text
    assert PW not in text and PP not in text


def test_gui_pages_b_review_surfaces_refusal():
    f = load_facts()
    f["root_disk"] = f["by_id"][VDA] if VDA in f.get("by_id", {}) else "/dev/vda"
    m = filled(facts=f)
    r = m.pages["review"]
    r.set_typed(DISK_NAME)
    assert not r.can_next()
    assert r.refusal().code == "root_disk"
    assert r.error() == "disk holds the running root filesystem"


def test_gui_pages_b_review_dev_option_hidden_in_release(monkeypatch):
    r = filled().pages["review"]
    assert r.dev_options() == ["dev"]
    r.set_dev(True)
    assert r.dev_flags() == ["--dev"]
    monkeypatch.setenv("SECLEGION_RELEASE", "1")
    assert r.dev_options() == [] and r.dev_flags() == []
    r.set_dev(True)
    assert not r.dev and r.dev_flags() == []


# ---- page 9 progress ----------------------------------------------------------

def test_gui_pages_b_progress_never_leaks_password_and_cleans_up(tmp_path):
    m = filled(PP)
    m.pages["review"].set_typed(DISK_NAME)
    p = progress(m, tmp_path)
    seen = []
    assert p.run(seen.append) is True
    assert p.ok and p.done and seen == p.lines
    blob = "\n".join(p.lines) + open(p.log_path).read()
    assert PW not in blob and PP not in blob
    assert "--answers" in p.lines[0] and "mode: 0o600 dirmode: 0o700" in blob
    assert "SECLEGION-INSTALL-OK" in p.lines
    assert not os.path.exists(p.answers_path) and not os.path.exists(os.path.dirname(p.answers_path))
    assert stat.S_IMODE(os.stat(p.log_path).st_mode) == 0o600
    assert "--hints" not in p.lines[0] and "--dev" not in p.lines[0]


def test_gui_pages_b_progress_scrubs_a_leaking_child(tmp_path):
    m = filled(PP)
    p = progress(m, tmp_path, """
        import json
        d = json.load(open(sys.argv[sys.argv.index("--answers") + 1]))
        print("oops " + d["password"] + " and " + d["luks_passphrase"], flush=True)
        sys.exit(1)
    """)
    assert p.run() is False and not p.ok
    blob = "\n".join(p.lines) + open(p.log_path).read()
    assert PW not in blob and PP not in blob and "oops *** and ***" in blob
    assert not os.path.exists(p.answers_path)


def test_gui_pages_b_progress_failure_leads_to_error_page_and_back_to_review(tmp_path):
    m = filled()
    p = progress(m, tmp_path, 'print("boom"); sys.exit(3)')
    assert p.run() is False
    m.install_failed()
    assert m.current.key == "error"
    assert p.log_path in m.current.text() and "boom" in m.current.text()
    m.retry_from_review()
    assert m.current.key == "review"


def test_gui_pages_b_progress_ok_mark_without_exit0_is_failure(tmp_path):
    m = filled()
    p = progress(m, tmp_path, 'print("SECLEGION-INSTALL-OK"); sys.exit(1)')
    assert p.run() is False


def test_gui_pages_b_progress_missing_installer_reports_not_raises(tmp_path):
    m = filled()
    p = progress(m, tmp_path)
    p.installer = [str(tmp_path / "nope")]
    assert p.run() is False and "cannot start installer" in p.lines[0]


# ---- pages 11-15 --------------------------------------------------------------

def test_gui_pages_b_tiers_hints_only_when_toggled(tmp_path):
    m = filled()
    t = m.pages["tiers"]
    assert (t.gaming, t.virt) == (False, False) and m.hints() == {}
    p = progress(m, tmp_path)
    p.run()
    assert "--hints" not in p.lines[0]
    t.set_gaming(True)
    assert m.hints() == {"gaming": True}
    t.set_virt(True)
    assert m.hints() == {"gaming": True, "virt": True}
    p.run()
    assert "--hints" in p.lines[0]
    assert "gaming" not in m.answers() and "virt" not in m.answers()


def test_gui_pages_b_hardware_summary():
    assert "unavailable" in p11_hardware.summarize(None)
    msg = "NVIDIA GPU: using the open kernel module"
    plan = {"messages": [msg], "packages": ["nvidia-open-dkms"]}
    s = p11_hardware.summarize(plan)
    assert s.splitlines()[0] == msg and "nvidia-open-dkms" in s
    assert "open-source drivers" in p11_hardware.summarize({"packages": []})
    page = filled().pages["hardware"]
    page.loader = lambda: plan
    assert msg in page.text()


def test_gui_pages_b_finished_reboots_only_on_click():
    m = filled()
    calls = []
    page = m.pages["finished"]
    assert calls == []  # building the page / the flow never reboots
    page.reboot(runner=lambda argv, check: calls.append((argv, check)))
    assert calls == [(["systemctl", "reboot"], False)]


def test_gui_pages_b_flow_order_and_kiosk_and_about():
    m = filled()
    assert [p.key for p in m.visible()] == [
        "welcome", "language", "timezone", "disk", "encryption", "user", "hardware", "tiers", "review",
        "progress", "finished"]
    k = m.pages["kiosk_error"]
    k.log = "/var/log/x.log"
    assert "/var/log/x.log" in k.text() and not k.can_next()
    assert "free software" in p15_about.licence_text(tool="/nonexistent")
    assert p15_about.licence_text(tool=os.path.join(ROOT, "tools", "licence-check"),
                                  runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, "LIC", ""))


def test_gui_pages_b_progress_runs_the_installer_directly_by_default():
    p = filled().pages["progress"]
    assert p.installer == ["seclegion-install"]
    assert p.argv("/run/x/answers.json")[:3] == ["seclegion-install", "--answers", "/run/x/answers.json"]


def test_gui_pages_b_kiosk_progress_runs_exactly_pkexec_seclegion_install():
    # the install kiosk user has no sudo: root comes only from pkexec of the one program the polkit rule names
    p = filled().pages["progress"]
    p.use_pkexec()
    assert p.installer == ["pkexec", "/usr/bin/seclegion-install"]
    answers = "/run/user/1001/seclegion-gui-x/answers.json"
    argv = p.argv(answers)
    assert argv[:4] == ["pkexec", "/usr/bin/seclegion-install", "--answers", answers]
    assert os.path.isabs(argv[3])  # pkexec clears the environment and the cwd: the answers path is absolute


def test_gui_pages_b_kiosk_flag_reaches_the_progress_page():
    gui = open(os.path.join(ROOT, "installer", "ui", "seclegion-installer-gui")).read()
    assert '"--kiosk"' in gui and "kiosk=a.kiosk" in gui
    app = open(os.path.join(ROOT, "installer", "ui", "gtk", "app.py")).read()
    assert 'if self.kiosk:\n            model.pages["progress"].use_pkexec()' in app


def test_gui_pages_b_ui_never_touches_disks_or_archinstall():
    src = ""
    for base in (os.path.join(ROOT, "installer", "ui", "gtk"), os.path.join(ROOT, "installer", "ui")):
        for root, _, files in os.walk(base):
            for n in files:
                if n.endswith(".py") or n == "seclegion-installer-gui":
                    src += open(os.path.join(root, n)).read()
    for word in ("import archinstall", "os.system", "sgdisk", "parted", "wipefs", "mkfs", "cryptsetup"):
        assert word not in src, word


# ---- Broadway render ----------------------------------------------------------

def test_gui_pages_b_render_under_broadway(tmp_path):
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
        r = subprocess.run([py, os.path.join(HERE, "gui_render_probe_b.py")], env=env,
                           capture_output=True, text=True, timeout=60)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert list(got) == ["encryption", "user", "review", "progress", "error", "hardware", "tiers",
                         "finished"]
    assert got["review"] == {"confirm": ""}
    assert got["user"]["username"] == "ammar"
