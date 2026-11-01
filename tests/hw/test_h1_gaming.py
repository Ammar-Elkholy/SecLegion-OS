# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""H1: nvidia_pkgs (hwdetect's NVIDIA choice seen through gaming.py), nvidia_kernel_pair, gaming opt-in."""

import re
import sys
import tomllib

import pytest
from conftest import HW, REPO
from seclegion_hw.detect import build_plan

sys.path.insert(0, str(REPO / "installer" / "installd"))
import gaming  # noqa: E402
import post  # noqa: E402

LISTS = REPO / "iso" / "packages"
MANIFEST = HW / "gaming.toml"


def names(path):
    out = set()
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.add(line)
    return out


def plan(fixture):
    return build_plan(HW / "fixtures" / fixture / "root", HW)


def test_nvidia_pkgs_open_driver_for_gtx1650_and_rtx4060():
    for fx in ("amd-gtx1650", "intel-rtx4060"):
        view = gaming.nvidia_view(plan(fx))
        assert view["modules"] == ["nvidia-open"], fx
        assert view["message"] is None


def test_nvidia_pkgs_lts_kernel_gets_the_lts_module():
    assert gaming.nvidia_view(plan("lts-kernel"))["modules"] == ["nvidia-open-lts"]


def test_nvidia_pkgs_pascal_uses_nouveau_with_a_human_message():
    p = plan("pascal")
    view = gaming.nvidia_view(p)
    assert view["modules"] == []
    assert {"mesa", "vulkan-nouveau"} <= set(p["packages"])
    assert "nouveau" in view["message"] and "older than Turing" in view["message"]


def test_nvidia_kernel_pair_manifest_matches_lists():
    pair = tomllib.loads(MANIFEST.read_text())["nvidia_kernel_pair"]
    assert pair == {"nvidia-open": "linux", "nvidia-open-lts": "linux-lts"}
    base, cache = names(LISTS / "base.list"), names(LISTS / "cache.list")
    for module, kernel in pair.items():
        assert module in cache, f"{module} missing from cache.list"
        assert kernel in base, f"{module} is cached but {kernel} is not in base.list"


def test_nvidia_kernel_pair_no_dkms_or_headers_required():
    everything = set()
    for n in ("base", "desktop", "cache", "live", "seclegion"):
        everything |= names(LISTS / f"{n}.list")
    assert not [p for p in everything if "dkms" in p or "headers" in p]


def test_nvidia_kernel_pair_plan_module_matches_installed_kernel():
    pair = tomllib.loads(MANIFEST.read_text())["nvidia_kernel_pair"]
    for fx, kernel in (("amd-gtx1650", "linux"), ("lts-kernel", "linux-lts")):
        (module,) = gaming.nvidia_view(plan(fx))["modules"]
        assert pair[module] == kernel


def test_gaming_manifest_matches_packages_d_and_keeps_multilib_apart():
    m = tomllib.loads(MANIFEST.read_text())
    assert names(REPO / "iso/packages.d/gaming.x86_64") == set(m["packages"]["official"])
    assert set(m["multilib"]["packages"]) == {"steam", "steam-devices"}
    allp = set(m["packages"]["official"]) | set(m["packages"]["seclegion"])
    assert not allp & set(m["multilib"]["packages"])
    assert not [p for p in allp if p.startswith("lib32-")]
    # everything official is in the offline cache, and seclegion-gaming is a real package dir
    assert set(m["packages"]["official"]) <= names(LISTS / "cache.list")
    for p in m["packages"]["seclegion"]:
        assert (REPO / "pkgs" / p / "PKGBUILD").exists()


def test_gaming_pkgbuild_depends_equal_the_official_set():
    text = (REPO / "pkgs/seclegion-gaming/PKGBUILD").read_text()
    deps = re.search(r"^depends=\((.*?)\)", text, re.M).group(1)
    got = {d.strip("'\"") for d in deps.split()}
    assert got == set(tomllib.loads(MANIFEST.read_text())["packages"]["official"])


def test_gaming_packages_only_when_opted_in():
    assert gaming.gaming_packages(None) == []
    assert gaming.gaming_packages(False) == []
    assert gaming.gaming_packages("yes") == []
    want = ["gamemode", "mangohud", "gamescope", "vulkan-tools", "seclegion-gaming"]
    assert gaming.gaming_packages(True) == want


@pytest.mark.parametrize("hints,expect", [({}, False), ({"gaming": False}, False), ({"gaming": True}, True)])
def test_gaming_post_installs_only_with_hint(tmp_path, hints, expect):
    root = tmp_path / "mnt"
    for d in ("etc/ufw", "etc/default", "var/log/archinstall"):
        (root / d).mkdir(parents=True)
    (root / "etc/pacman.conf").write_text("[options]\n\n[core]\nInclude = /x\n")
    (root / "usr/share/snapper/config-templates").mkdir(parents=True)
    (root / "usr/share/snapper/config-templates/default").write_text('SUBVOLUME="/"\nTIMELINE_CREATE="yes"\n')
    (root / "etc/conf.d").mkdir(parents=True)
    (root / "etc/conf.d/snapper").write_text('SNAPPER_CONFIGS=""\n')
    (root / "etc/ufw/ufw.conf").write_text("ENABLED=no\n")
    for rules in ("after.rules", "after6.rules"):
        (root / "etc/ufw" / rules).write_text("COMMIT\n")
    (root / "etc/default/ufw").write_text('DEFAULT_INPUT_POLICY="ACCEPT"\n')
    cmds = []
    post.Post(str(root), cmds.append, hints={"username": "u", **hints}).steps()
    install = next(c for c in cmds if c[:4] == ["arch-chroot", str(root), "pacman", "-S"])
    assert ("seclegion-gaming" in install) is expect
    assert ("gamemode" in install) is expect
    assert "steam" not in install  # multilib packages are not in the offline cache (D-H1)


def test_gaming_multilib_packages_only_when_opted_in():
    assert gaming.multilib_packages(None) == []
    assert gaming.multilib_packages(False) == []
    assert gaming.multilib_packages(True) == ["steam", "steam-devices"]
