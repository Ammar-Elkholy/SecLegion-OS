# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""W1 / G51 (static half): the key matrix of every shipped bind, its QMP sequences and its oracles.

No VM: tests/lib/keymatrix.py builds the matrix, these tests pin it. The VM half sends the matrix to an
installed guest in us and ara and checks each oracle.
"""

import json
import re

import pytest

from tests.lib import keymatrix as km
from tests.lib import qmp

HERE = km.ROOT / "tests/desktop"


def planted(*lines, with_shipped=False):
    """Matrix of a planted Lua source (plus the shipped binds when asked)."""
    binds = km.parse_binds("\n".join(lines) + "\n", "planted.lua")
    return km.build((km.shipped_binds() if with_shipped else []) + binds)


def bind(keys, action='hl.dsp.exec_cmd("true")', desc="planted"):
    return f'hl.bind("{keys}", {action}, {{ description = "{desc}" }})'


@pytest.fixture(scope="module")
def matrix():
    return km.shipped_matrix()


def shipped_bind_lines():
    n = 0
    for path in km.SHIPPED:
        n += len(re.findall(r"^\s*hl\.bind\(", path.read_text(encoding="utf-8"), re.M))
    return n


# ---- the shipped binds ------------------------------------------------------------------------------

def test_keymatrix_every_shipped_bind_appears_exactly_once_per_layout(matrix):
    expect = shipped_bind_lines()
    assert expect > 70   # the keys file plus the three skel launch binds
    for layout in km.LAYOUTS:
        ids = matrix.ids(layout)
        assert len(ids) == expect, layout
        assert len(set(ids)) == len(ids), layout
    assert len(matrix.entries) == expect * len(km.LAYOUTS)


def test_keymatrix_reads_binds_through_the_lint_parser():
    lint = km.lint()
    for path in km.SHIPPED:
        theirs = lint.parse_file(str(path))
        ours = km.parse_binds(path.read_text(encoding="utf-8"), path.name)
        assert [(b.norm, b.description) for b in ours] == [(n, d) for n, _, _, d in theirs]


def test_keymatrix_us_and_ara_both_produce_a_full_matrix(matrix):
    us, ara = matrix.layout("us"), matrix.layout("ara")
    assert [e.id for e in us] == [e.id for e in ara]
    for e in us + ara:
        assert e.oracle.kind and e.oracle.probe, e.id
        if e.key.lower() in km.HW_KEYS:
            continue   # no qcode: test_keymatrix_hardware_keys_share_an_action_with_a_reachable_bind
        assert e.chords and all(chord for chord in e.chords), e.id
        assert e.reachable, (e.layout, e.id, e.reason)


def test_keymatrix_shipped_binds_are_all_reachable_on_both_layouts(matrix):
    # Hyprland resolves keysym binds through the first layout (resolve_binds_by_sym is off in the shipped
    # config) and code:N binds are physical: nothing the install ships is lost under ara.
    assert [e for e in matrix.unreachable() if e.key.lower() not in km.HW_KEYS] == []
    config = (km.ROOT / "desktop/hypr/seclegion-host.lua").read_text(encoding="utf-8")
    assert "resolve_binds_by_sym" not in config


def test_keymatrix_hardware_keys_share_an_action_with_a_reachable_bind(matrix):
    # XF86Display (issue 14) cannot be sent over QMP; the VM half checks its action through the
    # reachable bind that runs the same command (Super+Shift+P).
    hw = [e for e in matrix.entries if e.key.lower() in km.HW_KEYS]
    assert {e.key for e in hw} == {"XF86Display"}
    for e in hw:
        assert not e.reachable and "no qcode" in e.reason, e.id
        twins = [o for o in matrix.layout(e.layout) if o.reachable and o.oracle == e.oracle]
        assert twins, e.id
    assert km.physical("XF86Display", "ara")[0] is None
    with pytest.raises(KeyError):
        km.physical("XF86Project", "us")


def test_keymatrix_keycode_binds_are_the_same_physical_keys_on_us_and_ara(matrix):
    n = 0
    for us, ara in zip(matrix.layout("us"), matrix.layout("ara"), strict=True):
        if us.key.startswith("code:"):
            n += 1
            assert us.chords == ara.chords, us.id
    assert n == 26   # S8: 26 code: binds


def test_keymatrix_known_sequences(matrix):
    by = {e.id: e for e in matrix.layout("ara")}
    assert by["SUPER+ALT+code:10"].chords == (("meta_l", "alt", "1"),)
    assert by["SUPER+ALT+SHIFT+code:19"].chords == (("meta_l", "alt", "shift", "0"),)
    assert by["SUPER+code:60"].chords == (("meta_l", "dot"),)
    assert by["SUPER+CTRL+Left"].chords == (("meta_l", "ctrl", "left"),)
    assert by["ALT+Print"].chords == (("alt", "print"),)
    assert by["SUPER+slash"].chords == (("meta_l", "slash"),)
    assert by["SUPER+Return"].chords == (("meta_l", "ret"),)


def test_keymatrix_every_qcode_is_one_qmp_knows():
    emitted = {q for e in km.shipped_matrix().entries for c in (*e.chords, *e.leave) for q in c}
    # the punctuation names tests/lib/qmp.py types with must be the names used here
    assert set(qmp._QCODES.values()) - set("1234567890") <= set(km.XKB_QCODES.values())
    assert emitted <= set(km.XKB_QCODES.values()) | set(km.MOD_QCODES.values())
    assert "%" not in "".join(emitted)   # the QMP typer cannot type %; binds are qcodes, never text


def test_keymatrix_submap_binds_enter_first_and_leave_after(matrix):
    by = {e.id: e for e in matrix.layout("us")}
    enter = ("meta_l", "alt", "r")
    assert by["SUPER+ALT+R"].chords == (enter,) and by["SUPER+ALT+R"].leave == (("esc",),)
    left = by["resize:CTRL+left"]
    assert left.chords == (enter, ("ctrl", "left")) and left.leave == (("esc",),)
    assert by["resize:Escape"].chords == (enter, ("esc",)) and by["resize:Escape"].leave == ()
    assert by["resize:Return"].leave == ()


def test_keymatrix_oracle_classes_of_the_shipped_binds(matrix):
    kinds = {e.id: e.oracle for e in matrix.layout("us")}
    assert dict(kinds["SUPER+ALT+code:10"].expect) == {"id": 11}
    assert kinds["SUPER+ALT+code:10"].kind == "workspace-active"
    assert kinds["SUPER+code:60"].kind == "workspace-empty"
    assert dict(kinds["SUPER+CTRL+Right"].expect) == {"delta": 1}
    assert dict(kinds["SUPER+ALT+code:60"].expect) == {"target": "empty", "follow": False}
    assert dict(kinds["SUPER+ALT+SHIFT+code:12"].expect) == {"target": 13, "follow": True}
    assert dict(kinds["SUPER+CTRL+code:11"].expect) == {"pct": 70}
    assert dict(kinds["resize:SHIFT+up"].expect) == {"dx": 0, "dy": -10}
    assert kinds["resize:c"].kind == "window-centered"
    assert kinds["resize:f"].kind == "float-toggled"
    assert kinds["SUPER+ALT+R"].kind == "submap-enter"
    assert kinds["resize:Escape"].kind == "submap-reset"
    assert dict(kinds["SUPER+CTRL+N"].expect) == {"command": "seclegion-night-light toggle",
                                                  "argv0": "seclegion-night-light"}
    assert dict(kinds["SUPER+SHIFT+T"].expect)["argv0"] == "seclegion-theme-pick"
    assert {o.needs for o in kinds.values()} == {"none", "window", "floating-window"}


def test_keymatrix_the_s8_runtime_capture_is_a_subset_of_the_matrix(matrix):
    # S8: runtime binds are matched by description; every bind of the real capture must be in the matrix.
    capture = json.loads((HERE / "fixtures/s8-nested-binds.json").read_text(encoding="utf-8"))
    ours = {e.description for e in matrix.layout("us")}
    missing = {b["description"].removeprefix("seclegion-keys: ") for b in capture} - {
        d.removeprefix("seclegion-keys: ") for d in ours}
    assert not missing


# ---- planted binds ----------------------------------------------------------------------------------

def test_keymatrix_planted_unknown_key_fails_naming_the_bind():
    with pytest.raises(km.KeyMatrixError) as err:
        planted(bind("SUPER + F13", desc="planted unknown key"))
    assert "planted unknown key" in str(err.value) and "unknown key 'F13'" in str(err.value)
    with pytest.raises(km.KeyMatrixError, match="unknown key 'code:999'"):
        planted(bind("SUPER + code:999"))


def test_keymatrix_planted_bind_with_no_oracle_fails_naming_the_bind():
    with pytest.raises(km.KeyMatrixError) as err:
        planted(bind("SUPER + F5", "hl.dsp.window.kill()", "planted no oracle"))
    assert "planted no oracle" in str(err.value) and "no oracle" in str(err.value)
    # a known class with an argument it cannot observe is also an error
    for action in ('hl.dsp.focus({ workspace = "previous" })', "hl.dsp.exec_cmd(os.getenv(\"X\"))",
                   'hl.dsp.window.float({ action = "enable" })', "function() end"):
        with pytest.raises(km.KeyMatrixError, match="no oracle"):
            planted(bind("SUPER + F5", action))


def test_keymatrix_planted_duplicate_bind_fails_even_by_another_spelling():
    with pytest.raises(km.KeyMatrixError, match="bound twice"):
        planted(bind("SUPER + 1"), bind("SUPER + code:10"))
    with pytest.raises(km.KeyMatrixError, match="bound twice"):   # against a shipped bind
        planted(bind("SUPER + Return"), with_shipped=True)


def test_keymatrix_planted_submap_bind_without_a_way_in_fails():
    src = ('hl.define_submap("orphan", function()\n' + "    " + bind("x") + "\nend)")
    with pytest.raises(km.KeyMatrixError, match="no bind enters submap 'orphan'"):
        planted(src)


def test_keymatrix_planted_submap_with_no_way_out_fails():
    with pytest.raises(km.KeyMatrixError, match="no bind leaves submap 'trap'"):
        planted(bind("SUPER + F5", 'hl.dsp.submap("trap")'),
                'hl.define_submap("trap", function()\n    ' + bind("x") + "\nend)")


def test_keymatrix_a_bind_the_layout_cannot_reach_is_reported_not_dropped():
    src = [bind("SUPER + T", desc="latin letter"), bind("SUPER + arabic_1", desc="arabic digit"),
           bind("SUPER + F1", desc="function key"), bind("SUPER + code:11", desc="keycode")]
    default = km.build(km.parse_binds("\n".join(src), "planted.lua"))
    # default (resolved through the first layout, us): an Arabic keysym is on neither layout's path
    assert [(e.layout, e.description) for e in default.unreachable()] == [
        ("us", "arabic digit"), ("ara", "arabic digit")]
    assert "arabic_1 is not on the us layout" in default.unreachable("ara")[0].reason
    assert len(default.layout("ara")) == len(src)
    # resolve_binds_by_sym = true: the active layout resolves keysyms, so Latin letters vanish on ara
    by_sym = km.build(km.parse_binds("\n".join(src), "planted.lua"), resolve_binds_by_sym=True)
    got = {(e.layout, e.description) for e in by_sym.unreachable()}
    assert got == {("us", "arabic digit"), ("ara", "latin letter")}
    assert len(by_sym.layout("ara")) == len(src) and len(by_sym.layout("us")) == len(src)
    ara = {e.description: e for e in by_sym.layout("ara")}
    assert ara["keycode"].reachable and ara["function key"].reachable and ara["arabic digit"].reachable
    assert ara["arabic digit"].chords == (("meta_l", "1"),)
    assert "keysym T is not on the ara layout" in ara["latin letter"].reason


def test_keymatrix_shipped_keysym_binds_are_the_ones_ara_would_lose_by_sym():
    m = km.shipped_matrix(resolve_binds_by_sym=True)
    assert [e for e in m.unreachable("us") if e.key.lower() not in km.HW_KEYS] == []
    lost = [e for e in m.unreachable("ara") if e.key.lower() not in km.HW_KEYS]
    assert lost and all(not e.key.startswith("code:") for e in lost)
    letters = {e.id for e in lost}
    assert "SUPER+SHIFT+T" in letters and "SUPER+slash" in letters and "SUPER+D" in letters
    assert "SUPER+F1" not in letters and "SUPER+Return" not in letters and "ALT+Print" not in letters
    assert "SUPER+CTRL+Left" not in letters
    # a submap bind whose entering bind is lost is lost too
    assert any(e.submap and "enters submap" in e.reason for e in lost)
    assert len(m.layout("ara")) == len(km.shipped_matrix().layout("ara"))


def test_keymatrix_every_dispatcher_of_the_shipped_binds_has_an_oracle_entry():
    for b in km.shipped_binds():
        assert b.dispatcher in km.ORACLES, (b.where, b.description, b.dispatcher)


# ---- sending ----------------------------------------------------------------------------------------

class FakeQmp:
    def __init__(self):
        self.sent = []

    def send_key(self, *qcodes):
        self.sent.append(qcodes)


def test_keymatrix_send_entry_sends_every_chord_over_qmp_in_order(matrix):
    by = {e.id: e for e in matrix.layout("ara")}
    q, pauses = FakeQmp(), []
    km.send_entry(q, by["resize:CTRL+left"], pause=0.5, sleep=pauses.append)
    assert q.sent == [("meta_l", "alt", "r"), ("ctrl", "left"), ("esc",)] and pauses == [0.5] * 3
    q = FakeQmp()
    km.send_entry(q, by["SUPER+ALT+SHIFT+code:10"], sleep=lambda _: None)
    assert q.sent == [("meta_l", "alt", "shift", "1")]


def test_keymatrix_send_entry_refuses_an_unreachable_entry():
    m = km.build(km.parse_binds(bind("SUPER + arabic_1") + "\n", "planted.lua"))
    with pytest.raises(ValueError, match="unreachable"):
        km.send_entry(FakeQmp(), m.unreachable("us")[0])
