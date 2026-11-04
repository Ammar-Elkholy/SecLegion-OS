# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""D2/D3: libadwaita page helpers and restyled pages. The pure parts (Model.goto, review rows, release
label) always run; the widget checks run in gui_pages_probe.py under Broadway, else skipped."""

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
import release  # noqa: E402
from model import Model  # noqa: E402
from pages import p8_review  # noqa: E402
from test_gui_pages_a import VDA, _free_display  # noqa: E402
from test_plan import load_facts  # noqa: E402


def filled():
    m = Model(load_facts())
    m.pages["disk"].set_disk(VDA)
    u = m.pages["user"]
    u.set_username("ammar")
    u.set_password("pw")
    u.set_confirm("pw")
    return m


def rows_by_title(m):
    return {r[0]: r for r in p8_review.summary_rows(m.pages["review"])}


def test_model_goto_jumps_to_a_visible_page_and_asks_for_a_redraw():
    m = filled()
    seen = []
    m.on_render = lambda: seen.append(m.current.key)
    m.index = len(m.visible()) - 2
    assert m.goto("user") is True
    assert m.current.key == "user" and seen == ["user"]
    m.install_failed()
    assert m.goto("disk") and not m.failed and m.current.key == "disk"


def test_model_goto_refuses_a_hidden_page_and_stays_put():
    m = filled()
    m.pages["disk"].set_luks(False)
    m.index = 3
    before = m.current.key
    assert m.goto("encryption") is False  # luks is off, so the page is not in the flow
    assert m.goto("nonsense") is False
    assert m.current.key == before


def test_review_summary_has_one_row_per_answer_and_each_edit_target_is_visible():
    m = filled()
    rows = p8_review.summary_rows(m.pages["review"])
    assert [r[0] for r in rows] == ["Disk", "Mode", "Encryption", "User", "Locale", "Extras"]
    assert {p.key for p in m.visible()} >= {r[3] for r in rows}
    by = rows_by_title(m)
    assert by["User"][1].startswith("ammar") and by["Locale"][1]
    assert by["Extras"][1] == "None"
    m.pages["tiers"].set_gaming(True)
    assert "Gaming" in rows_by_title(m)["Extras"][1]


def test_review_summary_encryption_row_edits_the_page_that_owns_the_choice():
    m = filled()
    m.pages["disk"].set_luks(False)
    assert rows_by_title(m)["Encryption"][1] == "Off" and rows_by_title(m)["Encryption"][3] == "disk"
    m.pages["disk"].set_luks(True)
    assert rows_by_title(m)["Encryption"][1] == "On (LUKS2)"
    assert rows_by_title(m)["Encryption"][3] == "encryption"


def test_release_build_label_names_the_channel():
    assert release.build_label(env={}, marker="/nonexistent/x") == "Development build"
    assert release.build_label(env={"SECLEGION_RELEASE": "1"}, marker="/nonexistent/x") == "Release build"


def test_gui_adw_pages_under_broadway(tmp_path):
    broadwayd = shutil.which("gtk4-broadwayd")
    py = "/usr/bin/python3"
    if not broadwayd or not os.path.exists(py):
        pytest.skip("gtk4-broadwayd or system python3 not available")
    if subprocess.run([py, "-c", "import gi; gi.require_version('Gtk','4.0');"
                       "gi.require_version('Adw','1')"], capture_output=True).returncode:
        pytest.skip("gi GTK4/libadwaita not importable by system python3")
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    n = _free_display()
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
    env.update(XDG_RUNTIME_DIR=str(run), GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{n}")
    daemon = subprocess.Popen([broadwayd, f":{n}"], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run([py, os.path.join(HERE, "gui_pages_probe.py")], env=env,
                           capture_output=True, text=True, timeout=120)
    finally:
        daemon.terminate()
        daemon.wait(10)
    if "NO-DISPLAY" in r.stdout:
        pytest.skip("Broadway display unavailable: " + r.stderr[-200:])
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    h = got["helpers"]
    assert h["page_box"] == {"type": "AdwClamp", "max": 760, "append_ok": True, "rows_in_boxed_list": True}
    assert h["switch"] == {"type": "AdwSwitchRow", "calls": [True, False], "follows_model": True}
    assert h["entry"] == {"type": "AdwEntryRow", "calls": ["a"]}
    assert h["secret"] == "AdwPasswordEntryRow"
    assert h["choice"] == {"type": "AdwPreferencesGroup", "rows": ["AdwActionRow"] * 3,
                           "grouped": True, "activatable": True, "disabled": [False, False, True],
                           "picked": ["b"]}
    assert h["status_icon"] == {"type": "AdwStatusPage", "icon": "emblem-ok-symbolic", "paintable": False}
    assert h["status_logo"] == {"type": "AdwStatusPage", "paintable": True}
    assert h["label_box"] == "AdwClamp"
    assert got["welcome"] == {"type": "AdwStatusPage", "title": "SecLegion OS", "paintable": True,
                              "body_has_build": True}
    assert got["rtl"] == {"ar_sidebar": "RTL", "ar_default": "RTL", "en_sidebar": "LTR",
                          "en_default": "LTR", "ar_selected_after_rerender": True}
    rv = got["review"]
    assert rv["titles"] == ["Disk", "Mode", "Encryption", "User", "Locale", "Extras"]
    assert rv["edit_buttons"] == 6
    assert rv["edit_jumps"] == ["disk", "disk", "encryption", "user", "language", "tiers"]
    assert rv["confirm_entry"] is True
    assert got["progress"] == {"type": "AdwStatusPage", "bar": True, "expander": "Details",
                               "expanded": False, "step": "line three", "log_updates": True}
    assert got["answers_unchanged"] is True
    assert got["types"] == {"encryption": "AdwClamp", "user": "AdwClamp", "error": "AdwStatusPage",
                            "hardware": "AdwClamp", "tiers": "AdwClamp", "finished": "AdwStatusPage",
                            "kiosk_error": "AdwStatusPage"}
