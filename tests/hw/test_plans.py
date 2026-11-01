# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G14: the shipped rules produce the expected plan for each hardware fixture."""

import json

import pytest
from conftest import FIXTURES, HW
from seclegion_hw.detect import build_plan


def plan_of(root):
    return build_plan(root, HW)


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_plan_matches_expected(name):
    expected = json.loads((HW / "fixtures" / name / "expected-plan.json").read_text())
    assert plan_of(HW / "fixtures" / name / "root") == expected


def test_all_fixtures_exist():
    on_disk = sorted(p.name for p in (HW / "fixtures").iterdir() if (p / "root").is_dir())
    assert on_disk == sorted(FIXTURES)


@pytest.mark.parametrize("name", FIXTURES)
def test_every_plan_has_always_packages_and_no_dkms(name):
    plan = plan_of(HW / "fixtures" / name / "root")
    for pkg in ("linux-firmware", "sof-firmware", "alsa-ucm-conf", "intel-ucode", "amd-ucode"):
        assert pkg in plan["packages"]
    assert not [p for p in plan["packages"] if "dkms" in p]
    assert set(plan) >= {"packages", "kernel_params", "env", "warnings", "boot_entries"}


def test_semantics_of_the_gpu_cases():
    intel_nv = plan_of(HW / "fixtures/intel-rtx4060/root")
    assert {"nvidia-open", "nvidia-prime", "switcheroo-control"} <= set(intel_nv["packages"])
    assert intel_nv["env"]["AQ_DRM_DEVICES"] == "/dev/dri/seclegion-igpu:/dev/dri/seclegion-dgpu"
    igpu_rule, dgpu_rule = intel_nv["udev_rules"]  # iGPU first
    assert 'KERNELS=="0000:00:02.0"' in igpu_rule and 'SYMLINK+="dri/seclegion-igpu"' in igpu_rule
    assert 'KERNELS=="0000:01:00.0"' in dgpu_rule and 'SYMLINK+="dri/seclegion-dgpu"' in dgpu_rule
    assert "GBM_BACKEND" not in intel_nv["env"]

    pascal = plan_of(HW / "fixtures/pascal/root")
    assert {"mesa", "vulkan-nouveau"} <= set(pascal["packages"])
    assert not [p for p in pascal["packages"] if p.startswith("nvidia")]
    assert pascal["messages"] and not pascal["warnings"]

    unknown = plan_of(HW / "fixtures/unknown-gpu/root")
    assert unknown["warnings"] and unknown["boot_entries"][0]["id"] == "safe-graphics"

    assert "nvidia-open-lts" in plan_of(HW / "fixtures/lts-kernel/root")["packages"]
    assert "nvidia-open" in plan_of(HW / "fixtures/amd-gtx1650/root")["packages"]
    assert "qemu-guest-agent" in plan_of(HW / "fixtures/vm/root")["packages"]


def test_nvidia_on_a_foreign_kernel_falls_back_to_generic(fixture_root):
    root = fixture_root("lts-kernel")
    (root / "proc/sys/kernel/osrelease").write_text("6.17.1-zen1-1-zen\n")
    plan = plan_of(root)
    assert not [p for p in plan["packages"] if p.startswith("nvidia")]
    assert plan["warnings"] and plan["boot_entries"]


def test_nvidia_device_missing_from_table_is_unknown(fixture_root):
    root = fixture_root("lts-kernel")
    dev = next((root / "sys/bus/pci/devices").glob("*09_00.0")) / "device"
    dev.write_text("0xfffe\n")
    plan = plan_of(root)
    assert plan["warnings"] and "10de:fffe" in plan["warnings"][0]
    assert not [p for p in plan["packages"] if p.startswith("nvidia")]


LEGION = "legion-slim5-16ahp9-"
SUSPEND_UNITS = ["nvidia-suspend.service", "nvidia-resume.service", "nvidia-hibernate.service"]


def test_legion_hybrid_mode_offloads_to_the_nvidia_gpu():
    plan = plan_of(HW / "fixtures" / (LEGION + "hybrid") / "root")
    assert [g["pci_id"] for g in plan["facts"]["gpus"]] == ["10de:28e0", "1002:1900"]
    assert plan["facts"]["hybrid"] is True
    assert {"nvidia-open", "nvidia-prime", "switcheroo-control", "vulkan-radeon"} <= set(plan["packages"])
    assert {"gpu-amd", "hybrid-offload", "hybrid-nvidia-prime"} <= set(plan["rules_applied"])
    assert plan["env"]["AQ_DRM_DEVICES"] == "/dev/dri/seclegion-igpu:/dev/dri/seclegion-dgpu"  # iGPU first
    igpu_rule, dgpu_rule = plan["udev_rules"]
    assert 'KERNELS=="0000:65:00.0"' in igpu_rule and 'KERNELS=="0000:01:00.0"' in dgpu_rule
    assert "GBM_BACKEND" not in plan["env"]


def test_legion_discrete_mode_is_nvidia_only_without_offload():
    plan = plan_of(HW / "fixtures" / (LEGION + "discrete") / "root")
    assert [g["pci_id"] for g in plan["facts"]["gpus"]] == ["10de:28e0"]
    assert plan["facts"]["hybrid"] is False
    assert "nvidia-open" in plan["packages"]
    assert not {"nvidia-prime", "switcheroo-control", "vulkan-radeon"} & set(plan["packages"])
    assert "hybrid-offload" not in plan["rules_applied"]
    assert "AQ_DRM_DEVICES" not in plan["env"]
    assert plan["env"]["GBM_BACKEND"] == "nvidia-drm"


@pytest.mark.parametrize("name", ["amd-gtx1650", "intel-rtx4060", "lts-kernel", LEGION + "hybrid",
                                  LEGION + "discrete"])
def test_nvidia_machines_preserve_vram_across_suspend(name):
    plan = plan_of(HW / "fixtures" / name / "root")
    assert "nvidia.NVreg_PreserveVideoMemoryAllocations=1" in plan["kernel_params"]
    assert plan["services"] == SUSPEND_UNITS


@pytest.mark.parametrize("name", ["intel", "amd", "pascal", "unknown-gpu", "vm"])
def test_machines_without_the_open_nvidia_driver_get_no_suspend_services(name):
    plan = plan_of(HW / "fixtures" / name / "root")
    assert plan["services"] == []
    assert not [p for p in plan["kernel_params"] if "NVreg" in p]


@pytest.mark.parametrize("name", FIXTURES)
def test_aq_drm_devices_has_no_colon_inside_a_path(name):
    """Aquamarine splits AQ_DRM_DEVICES on ':'; only the hybrid plans set it, with two colon-free paths."""
    plan = plan_of(HW / "fixtures" / name / "root")
    value = plan["env"].get("AQ_DRM_DEVICES")
    assert bool(value) == plan["facts"]["hybrid"] == bool(plan["udev_rules"])
    if value:
        assert value.count(":") == 1 and "by-path" not in value
        assert len(plan["udev_rules"]) == 2
