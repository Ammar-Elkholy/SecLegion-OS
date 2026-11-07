# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Keyboard layouts: the XKB list parser, the console keymap, the xkb switch string, and where they land
(configurator refusal, greetd XKB variables, Hyprland kb-layout.lua)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import configurator as c  # noqa: E402
import keymaps  # noqa: E402
import post  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "keymaps")
LST = os.path.join(FIX, "base.lst")
MAP = os.path.join(FIX, "kbd-model-map")


@pytest.fixture(autouse=True)
def fixture_lists(monkeypatch):
    monkeypatch.setattr(keymaps, "BASE_LST", LST)
    monkeypatch.setattr(keymaps, "KBD_MODEL_MAP", MAP)


def test_parser_reads_layouts_and_variants():
    got = keymaps.xkb_layouts(LST)
    assert len(got) == 8 + 4  # eight layouts, four variants; the model and option sections are skipped
    assert ("us", "", "English (US)") in got
    assert ("de", "nodeadkeys", "German (no dead keys)") in got
    assert ("ara", "azerty", "Arabic (AZERTY)") in got
    assert not any(lo == "pc105" or lo == "grp" for lo, _v, _d in got)


def test_real_list_is_at_least_the_fixture_when_installed():
    if not os.path.isfile("/usr/share/X11/xkb/rules/base.lst"):
        pytest.skip("no xkeyboard-config on this host")
    assert len(keymaps.xkb_layouts("/usr/share/X11/xkb/rules/base.lst")) >= len(keymaps.xkb_layouts(LST))


def test_common_layouts_come_first_then_alphabetical():
    got = keymaps.ordered(keymaps.xkb_layouts(LST))
    assert [e[0] for e in got[:3]] == ["us", "us", "gb"]
    assert got[0][1] == ""  # the base layout before its variants
    tail = [e[2].lower() for e in got if e[0] not in keymaps.COMMON]
    assert tail == sorted(tail)


@pytest.mark.parametrize("layout,variant,want", [
    ("fr", "", "fr"), ("de", "", "de"), ("de", "nodeadkeys", "de-latin1-nodeadkeys"),
    ("fr", "oss", "fr"),  # a variant the map lacks falls back to the base layout's keymap
    ("ara", "", "us"),  # no Arabic console font: US keys on the console
    ("zz9", "", "us"), ("nope", "x", "us"),
])
def test_console_keymap(layout, variant, want):
    assert keymaps.console_keymap(layout, variant, MAP) == want


def test_console_keymap_without_the_map_file_is_us():
    assert keymaps.console_keymap("fr", "", "/nonexistent/kbd-model-map") == "us"


@pytest.mark.parametrize("layout,variant,want", [
    ("us", "", ("us", "")), ("us", "intl", ("us", "intl")),
    ("ara", "", ("us,ara", "")), ("ara", "azerty", ("us,ara", ",azerty")),
    ("fr", "", ("fr,us", "")), ("de", "nodeadkeys", ("de,us", "nodeadkeys,")),
])
def test_xkb_spec_always_keeps_us(layout, variant, want):
    assert keymaps.xkb_spec(layout, variant) == want


def answers(**kw):
    kw.setdefault("disk", "/dev/vda")
    kw.setdefault("username", "tester")
    kw.setdefault("password", "pw")
    return c.Answers(**kw)


def test_configurator_rejects_an_unknown_xkb_layout():
    facts = {"install_mode": True}
    with pytest.raises(c.Refusal) as err:
        c.validate(answers(xkb_layout="zz"), facts)
    assert err.value.code == "bad_keyboard"
    with pytest.raises(c.Refusal) as err:
        c.validate(answers(xkb_layout="de", xkb_variant="bogus"), facts)
    assert err.value.code == "bad_keyboard"


def test_configurator_accepts_the_listed_layouts_and_hints_carry_them():
    a = answers(keyboard="de-latin1-nodeadkeys", xkb_layout="de", xkb_variant="nodeadkeys")
    assert keymaps.known(a.xkb_layout, a.xkb_variant)
    hints = c.post_hints(a)
    assert hints["xkb_layout"] == "de" and hints["xkb_variant"] == "nodeadkeys"


def test_xkb_for_hints():
    assert post.xkb_for({}) is None
    assert post.xkb_for({"xkb_layout": "us"}) is None
    assert post.xkb_for({"keyboard_extra": ["ara"]}) == ("us,ara", "")  # older hints
    assert post.xkb_for({"xkb_layout": "ara", "keyboard_extra": ["ara"]}) == ("us,ara", "")
    assert post.xkb_for({"xkb_layout": "fr"}) == ("fr,us", "")
    with pytest.raises(post.PostError):
        post.xkb_for({"xkb_layout": "fr;rm"})


def test_greetd_command_gets_the_xkb_variables():
    cmd = post.greetd_config(("fr,us", "oss,"))
    assert "XKB_DEFAULT_LAYOUT=fr,us" in cmd and "XKB_DEFAULT_VARIANT=oss," in cmd
    assert "XKB_DEFAULT_OPTIONS=grp:alt_shift_toggle" in cmd
    plain = post.greetd_config(None)
    assert "XKB" not in plain
    single = post.greetd_config(("us", "intl"))
    assert "XKB_DEFAULT_LAYOUT=us XKB_DEFAULT_VARIANT=intl" in single and "XKB_DEFAULT_OPTIONS" not in single


def test_hyprland_kb_layout_lua():
    lua = post.kb_layout_lua(("fr,us", "oss,"))
    assert 'kb_layout = "fr,us"' in lua and 'kb_variant = "oss,"' in lua
    assert 'kb_options = "grp:alt_shift_toggle"' in lua
    assert 'kb_variant' not in post.kb_layout_lua(("us,ara", ""))
    assert 'kb_options' not in post.kb_layout_lua(("us", "intl"))
