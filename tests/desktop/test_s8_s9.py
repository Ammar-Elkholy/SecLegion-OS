# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""S8/S9 spike: code:NN binds in `hyprctl binds -j` (0.56.2 nested capture), swaync margins, swayosd."""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KEYS_LUA = os.path.join(ROOT, "desktop", "hypr", "seclegion-keys.lua")
FIXTURE = os.path.join(HERE, "fixtures", "s8-nested-binds.json")
MOD = {"SHIFT": 1, "CTRL": 4, "CONTROL": 4, "ALT": 8, "SUPER": 64}
BIND = re.compile(r'^\s*hl\.bind\("([^"]+)",.*description = "([^"]*)" \}\)\s*$')


def _code_binds():
    out = []
    for line in open(KEYS_LUA, encoding="utf-8"):
        m = BIND.match(line)
        if m and "code:" in m.group(1):
            parts = [p.strip() for p in m.group(1).split("+")]
            mask = sum(MOD[p] for p in parts if p in MOD)
            out.append((mask, parts[-1], m.group(2)))
    return out


def _fixture():
    return json.load(open(FIXTURE, encoding="utf-8"))


def test_s8_every_code_bind_is_registered_with_the_right_modmask():
    binds = _fixture()
    expect = _code_binds()
    assert len(expect) == 26
    for mask, key, desc in expect:
        hits = [b for b in binds if b["description"] == desc and b["modmask"] == mask]
        assert len(hits) == 1, (key, desc, mask)


def test_s8_runtime_json_does_not_report_the_keycode():
    # Hyprland 0.56.2 Lua binds: code:NN comes back as key "" and keycode 0, so
    # consumers must take the key from the Lua source and match runtime binds by
    # description + modmask, never by key.
    binds = _fixture()
    descs = {d for _, _, d in _code_binds()}
    seen = 0
    for b in binds:
        if b["description"] in descs:
            seen += 1
            assert b["key"] == "" and b["keycode"] == 0
    assert seen == 26


def test_s8_description_prefix_identifies_ours():
    assert all(b["description"].startswith("seclegion-keys: ") for b in _fixture())


def test_s9_swaync_sets_only_control_center_margin_keys():
    cfg = json.load(open(os.path.join(ROOT, "desktop", "swaync", "config.json"), encoding="utf-8"))
    margins = {k for k in cfg if "margin" in k}
    # swaync 0.12.6 documents only these four (man swaync(5), configSchema.json)
    assert margins == {f"control-center-margin-{s}" for s in ("top", "right", "bottom", "left")}
    assert all(isinstance(cfg[k], int) for k in margins)
    css = open(os.path.join(ROOT, "desktop", "swaync", "style.css"), encoding="utf-8").read()
    assert "swaync has no popup-margin config key" in css
    assert re.search(r"\.floating-notifications\.background\s*\{[^}]*padding:\s*50px 20px 0 0", css)


def test_s9_osd_shim_does_not_depend_on_swayosd_custom_message():
    # swayosd-client 0.3.2 has --custom-message/--custom-icon/--custom-progress, but
    # the shipped OSD shim is dunstify-based and uses no swayosd flag.
    src = open(os.path.join(ROOT, "desktop", "osd", "seclegion-osd"), encoding="utf-8").read()
    assert "swayosd-client" not in src and "custom-message" not in src
