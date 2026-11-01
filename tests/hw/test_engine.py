# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Rule engine behaviour: match keys, the extra-rules hook, errors, EDID scaling."""

import pytest
from conftest import HW
from seclegion_hw import edid, engine
from seclegion_hw.detect import build_plan


def write_rules(tmp_path, text, name="extra.toml"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_cpu_and_dmi_rules_match(tmp_path):
    rules = write_rules(
        tmp_path,
        '[[rule]]\nid = "amd-board"\n[rule.when]\ncpu_vendor = "AuthenticAMD"\ncpu_model = "Ryzen 7"\n'
        '[rule.when.dmi]\nsys_vendor = "micro-star"\n[rule.add]\nkernel_params = ["amd_pstate=active"]\n',
    )
    assert "amd_pstate=active" in build_plan(HW / "fixtures/amd/root", HW, [rules])["kernel_params"]
    assert "amd_pstate=active" not in build_plan(HW / "fixtures/intel/root", HW, [rules])["kernel_params"]


def test_boot_vga_and_class_prefix_match(tmp_path):
    rules = write_rules(
        tmp_path,
        '[[rule]]\nid = "primary"\n[rule.when]\npci_class = "0302"\nboot_vga = false\n[rule.add]\n'
        'packages = ["on-secondary-3d"]\n',
    )
    assert "on-secondary-3d" in build_plan(HW / "fixtures/intel-rtx4060/root", HW, [rules])["packages"]
    assert "on-secondary-3d" not in build_plan(HW / "fixtures/pascal/root", HW, [rules])["packages"]


def test_extra_rules_hook_loads_gaming_toml(tmp_path):
    hw = tmp_path / "hw"
    (hw / "rules.d").mkdir(parents=True)
    for name in ("nvidia-table.toml",):
        (hw / name).write_bytes((HW / name).read_bytes())
    for src in (HW / "rules.d").glob("*.toml"):
        (hw / "rules.d" / src.name).write_bytes(src.read_bytes())
    write_rules(hw, '[[rule]]\nid = "gaming-x"\n[rule.add]\npackages = ["gamemode"]\n', "gaming.toml")
    assert "gamemode" in build_plan(HW / "fixtures/amd/root", hw)["packages"]


def test_bad_rules_are_rejected(tmp_path):
    for body, why in (
        ('[[rule]]\nid = "a"\n[rule.when]\nvirtt = "qemu"\n', "unknown condition"),
        ('[[rule]]\nid = "a"\n[rule.add]\npackage = ["x"]\n', "unknown action"),
        ('[[rule]]\nid = "always-firmware"\n', "duplicate"),
    ):
        rules = write_rules(tmp_path, body)
        with pytest.raises(engine.RulesError, match=why):
            build_plan(HW / "fixtures/amd/root", HW, [rules])


def test_conflicting_env_is_an_error(tmp_path):
    rules = write_rules(
        tmp_path,
        '[[rule]]\nid = "a"\n[rule.add.env]\nX = "1"\n[[rule]]\nid = "b"\n[rule.add.env]\nX = "2"\n',
    )
    with pytest.raises(engine.RulesError, match="differently"):
        build_plan(HW / "fixtures/amd/root", HW, [rules])


def make_edid(width_px, width_mm, height_mm=200):
    blob = bytearray(128)
    blob[:8] = bytes([0, 255, 255, 255, 255, 255, 255, 0])
    blob[21], blob[22] = width_mm // 10, height_mm // 10
    blob[54], blob[55] = 0x01, 0x1D  # non-zero pixel clock: a detailed timing
    blob[56], blob[58] = width_px & 0xFF, (width_px >> 8) << 4
    blob[59], blob[61] = 0x80, 0x00
    blob[66], blob[67] = width_mm & 0xFF, height_mm & 0xFF
    blob[68] = ((width_mm >> 8) << 4) | (height_mm >> 8)
    return bytes(blob)


@pytest.mark.parametrize(
    ("width_px", "width_mm", "scale"),
    [(1920, 344, 1.0), (3840, 344, 2.0), (3840, 597, 1.5), (2560, 597, 1.0)],
)
def test_edid_scale(width_px, width_mm, scale):
    info = edid.parse_edid(make_edid(width_px, width_mm))
    assert edid.scale_for(info["dpi"]) == scale


def test_hidpi_from_edid_reaches_the_plan(fixture_root):
    root = fixture_root("intel")
    out = root / "sys/class/drm/card1-eDP-1"
    out.mkdir(parents=True)
    (out / "status").write_text("connected\n")
    (out / "edid").write_bytes(make_edid(3840, 344))
    plan = build_plan(root, HW)
    assert plan["settings"]["display.scale"] == 2.0
    assert plan["settings"]["display.output_scales"] == {"eDP-1": 2.0}


def test_garbage_edid_is_ignored():
    assert edid.parse_edid(b"\x00" * 128) is None
    assert edid.parse_edid(b"short") is None
