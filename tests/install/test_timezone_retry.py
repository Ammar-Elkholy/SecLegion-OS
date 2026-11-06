# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G2 time zone page and G4 retry re-gathers the disk facts. Pure model tests, no GTK."""

import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))
sys.path.insert(0, os.path.join(ROOT, "installer", "installd"))
sys.path.insert(0, HERE)
import configurator as c  # noqa: E402
from model import DISK_CHANGED, Model  # noqa: E402
from pages import p8_review  # noqa: E402
from pages.p16_timezone import load_zones  # noqa: E402
from test_gui_pages_a import VDA  # noqa: E402
from test_plan import load_facts  # noqa: E402

ZONES = ["Africa/Cairo", "Europe/Berlin", "Asia/Tokyo"]


def zone_model():
    m = Model(load_facts())
    m.pages["timezone"]._zones = list(ZONES)
    return m


def test_timezone_default_is_utc_for_english_and_cairo_for_arabic():
    m = zone_model()
    p = m.pages["timezone"]
    assert p.fragment() == {"timezone": "UTC"} and p.can_next()
    m.pages["language"].set_language("ar")
    assert p.fragment() == {"timezone": "Africa/Cairo"} and p.can_next()


def test_timezone_explicit_pick_wins_over_the_language_default():
    m = zone_model()
    p = m.pages["timezone"]
    p.set_zone("Asia/Tokyo")
    m.pages["language"].set_language("ar")
    assert p.fragment() == {"timezone": "Asia/Tokyo"}
    p.set_zone("Nowhere/Land")
    assert not p.can_next() and p.error()


def test_timezone_search_filters_the_list():
    p = zone_model().pages["timezone"]
    assert p.matching("cairo") == ["Africa/Cairo"]
    assert p.matching("") == ZONES


def test_timezone_zones_come_from_the_system_tzdata():
    zones = load_zones()
    assert "UTC" in zones and "Africa/Cairo" in zones and "Europe/Berlin" in zones
    assert all("/" in z or z == "UTC" for z in zones)


def test_timezone_walk_fallback_without_tzdata_zi(tmp_path):
    (tmp_path / "Africa").mkdir()
    (tmp_path / "Africa" / "Cairo").write_text("x")
    (tmp_path / "Etc").mkdir()
    (tmp_path / "Etc" / "GMT").write_text("x")
    assert load_zones(str(tmp_path)) == ["Africa/Cairo", "UTC"]


def test_timezone_validate_refuses_an_unknown_zone():
    f = load_facts()
    base = dict(disk=VDA, username="u", password="p", confirm="QEMU HARDDISK")
    c.validate(c.Answers(timezone="Africa/Cairo", **base), f)
    for bad in ("Mars/Olympus", "../etc/passwd", "/etc/passwd", "Africa", ""):
        with pytest.raises(c.Refusal) as e:
            c.validate(c.Answers(timezone=bad, **base), f)
        assert e.value.code == "bad_timezone", bad


def test_timezone_follows_language_in_the_flow_and_the_answers():
    m = zone_model()
    keys = [p.key for p in m.visible()]
    assert keys[:4] == ["welcome", "language", "timezone", "disk"]
    assert m.answers()["timezone"] == "UTC"


def test_timezone_review_row_edits_the_timezone_page():
    m = zone_model()
    m.pages["timezone"].set_zone("Europe/Berlin")
    rows = {r[0]: r for r in p8_review.summary_rows(m.pages["review"])}
    assert rows["Time zone"][1] == "Europe/Berlin" and rows["Time zone"][3] == "timezone"
    assert "timezone" in [p.key for p in m.visible()]


# ---- G4: retry re-gathers the facts ------------------------------------------------------------

def failed_model(refresh):
    m = Model(load_facts(), refresh_facts=refresh)
    m.pages["disk"].set_disk(VDA)
    m.install_failed()
    return m


def vda(facts):
    return next(d for d in facts["lsblk"]["blockdevices"] if d["name"] == "vda")


def test_retry_lands_on_the_disk_page_when_the_disk_changed():
    fresh = copy.deepcopy(load_facts())
    vda(fresh)["size"] = int(vda(fresh)["size"]) // 2
    m = failed_model(lambda: fresh)
    m.retry_from_review()
    assert m.current.key == "disk" and not m.failed
    assert m.pages["disk"].message == DISK_CHANGED and m.pages["disk"].disk is None
    assert m.facts is fresh


def test_retry_lands_on_the_disk_page_when_the_disk_is_gone():
    def refresh():
        f = copy.deepcopy(load_facts())
        f["lsblk"]["blockdevices"] = [d for d in f["lsblk"]["blockdevices"] if d["name"] != "vda"]
        return f

    m = failed_model(refresh)
    m.retry_from_review()
    assert m.current.key == "disk" and m.pages["disk"].message == DISK_CHANGED


def test_retry_lands_on_review_when_the_facts_are_unchanged():
    calls = []
    m = failed_model(lambda: calls.append(1) or load_facts())
    m.retry_from_review()
    assert calls == [1] and m.current.key == "review" and not m.pages["disk"].message
    assert m.pages["disk"].disk == VDA


def test_retry_without_refresh_facts_behaves_as_before():
    m = failed_model(None)
    old = m.facts
    m.retry_from_review()
    assert m.current.key == "review" and m.facts is old and not m.pages["disk"].message


def test_retry_partition_mode_checks_the_partition():
    with open(os.path.join(HERE, "fixtures", "facts_partitions.json")) as f:
        base = json.load(f)

    def build(refresh):
        m = Model(copy.deepcopy(base), refresh_facts=refresh)
        m.pages["disk"].set_disk("/dev/nvme0n1")
        m.pages["disk"].set_partition("/dev/nvme0n1p5")
        m.install_failed()
        return m

    m = build(lambda: copy.deepcopy(base))
    m.retry_from_review()
    assert m.current.key == "review"

    def gone():
        f = copy.deepcopy(base)
        d = f["lsblk"]["blockdevices"][0]
        d["children"] = [p for p in d["children"] if p["path"] != "/dev/nvme0n1p5"]
        return f

    m = build(gone)
    m.retry_from_review()
    assert m.current.key == "disk" and m.pages["disk"].partition is None

    def resized():
        f = copy.deepcopy(base)
        for p in f["lsblk"]["blockdevices"][0]["children"]:
            if p["path"] == "/dev/nvme0n1p5":
                p["size"] = int(p["size"]) - (1 << 30)
        return f

    m = build(resized)
    m.retry_from_review()
    assert m.current.key == "disk" and m.pages["disk"].message == DISK_CHANGED


def test_rescan_button_refreshes_the_facts_and_redraws():
    fresh = copy.deepcopy(load_facts())
    vda(fresh)["size"] = int(vda(fresh)["size"]) * 2
    m = Model(load_facts(), refresh_facts=lambda: fresh)
    drawn = []
    m.on_render = lambda: drawn.append(1)
    m.rescan_disks()
    assert m.facts is fresh and drawn == [1]


def test_rescan_button_without_refresh_facts_only_redraws():
    m = Model(load_facts())
    drawn = []
    m.on_render = lambda: drawn.append(1)
    old = m.facts
    m.rescan_disks()
    assert m.facts is old and drawn == [1]
