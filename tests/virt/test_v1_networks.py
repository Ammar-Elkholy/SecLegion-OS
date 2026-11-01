# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""V1 static checks: libvirt network XML, seclegion-virt-setup, post.py opt-in (m10 = the gate's -k)."""

import importlib.machinery
import importlib.util
import os
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(REPO, "pkgs", "seclegion-virt")
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
sys.path.insert(0, os.path.join(REPO, "tests", "install"))
import post  # noqa: E402
import test_post as tp  # noqa: E402
import virt  # noqa: E402


def load_setup():
    path = os.path.join(PKG, "seclegion-virt-setup")
    loader = importlib.machinery.SourceFileLoader("seclegion_virt_setup", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def net(name):
    return ET.parse(os.path.join(PKG, f"{name}.xml")).getroot()


def run_setup(root, user="ammar"):
    mod, calls = load_setup(), []

    def run(argv):
        calls.append(argv)
        return 0

    return mod, mod.setup(str(root), user, run, share=PKG), calls


def test_m10_isolated_xml_has_no_route_out_and_no_dns():
    r = net("seclegion-isolated")
    assert r.find("forward") is None
    assert r.find("dns").get("enable") == "no"
    assert r.find("ip/dhcp/range") is not None
    assert r.find("ip").get("address").startswith("10.66.0.")
    assert r.find("bridge").get("name") == "virbr1"


def test_m10_default_xml_is_nat_with_dhcp():
    r = net("default")
    assert r.find("forward").get("mode") == "nat"
    assert r.find("ip").get("address") == "192.168.122.1"
    assert r.find("ip/dhcp/range") is not None
    assert r.find("dns") is None  # libvirt's dnsmasq serves DNS by default
    assert r.find("bridge").get("name") == "virbr0"


def test_m10_setup_is_idempotent(tmp_path):
    _, first, _ = run_setup(tmp_path)
    _, second, _ = run_setup(tmp_path)
    assert first == ["default", "seclegion-isolated"] and second == []
    nets = tmp_path / "etc/libvirt/qemu/networks"
    assert (nets / "autostart/default.xml").is_symlink()
    assert (nets / "autostart/seclegion-isolated.xml").is_symlink()
    conf = (tmp_path / "etc/libvirt/network.conf").read_text()
    assert conf.count('firewall_backend = "nftables"') == 1


def test_m10_setup_live_defines_only_absent_networks(tmp_path):
    mod, calls = load_setup(), []

    def run(argv):
        calls.append(argv)
        return 0 if argv == ["virsh", "net-info", "default"] else 1

    mod.setup(str(tmp_path), None, run, share=PKG, live=True)
    defines = [c for c in calls if c[:2] == ["virsh", "net-define"]]
    assert len(defines) == 1 and defines[0][2].endswith("seclegion-isolated.xml")
    assert ["virsh", "net-autostart", "seclegion-isolated"] in calls
    assert ["virsh", "net-autostart", "default"] not in calls


def test_m10_socket_group_and_ufw_rules_exact(tmp_path):
    mod, _, calls = run_setup(tmp_path)
    assert ["systemctl", "--root", str(tmp_path), "enable", "libvirtd.socket"] in calls
    assert ["usermod", "-aG", "libvirt", "ammar"] in calls
    assert not any("libvirtd.service" in " ".join(c) for c in calls)
    ufw = [c[1:] for c in calls if c[0] == "ufw"]
    assert ufw == [
        ["allow", "in", "on", "virbr0", "to", "any", "port", "67", "proto", "udp"],
        ["allow", "in", "on", "virbr0", "to", "any", "port", "53", "proto", "udp"],
        ["allow", "in", "on", "virbr0", "to", "any", "port", "53", "proto", "tcp"],
        ["route", "allow", "in", "on", "virbr0"],
    ]
    ufw_text = " ".join(" ".join(c) for c in calls if c[0] == "ufw")
    assert "virbr1" not in ufw_text and "isolated" not in ufw_text


def test_m10_network_conf_replaces_existing_key():
    mod = load_setup()
    assert mod.set_conf_key('#firewall_backend = "iptables"\n', "firewall_backend", "nftables") == (
        'firewall_backend = "nftables"\n'
    )
    assert mod.set_conf_key("", "firewall_backend", "nftables") == 'firewall_backend = "nftables"\n'


def post_run(tmp_path, hints):
    root, creds = tp.make_root(tmp_path)
    cmds = []
    p = post.Post(str(root), cmds.append, creds_dir=str(creds), hints=hints)
    p.steps()
    return cmds


def test_m10_post_installs_virt_only_with_hint(tmp_path):
    off = post_run(tmp_path / "a", tp.HINTS)
    on = post_run(tmp_path / "b", {**tp.HINTS, "virt": True})
    assert not any("seclegion-virt" in " ".join(c) for c in off)
    pac = [c for c in on if c[-1:] and "seclegion-virt" in c and "pacman" in c]
    assert pac, "pacman install must include seclegion-virt"
    chroot = next(c[1] for c in on if c[0] == "arch-chroot")
    assert ["arch-chroot", chroot, "seclegion-virt-setup", "--user", "ammar"] in on
    assert virt.virt_packages("yes") == [] and virt.setup_argv(False, "u") is None


def test_m10_virt_deps_are_in_offline_lists():
    import re

    text = open(os.path.join(PKG, "PKGBUILD")).read()
    deps = re.search(r"^depends=\((.*?)\)", text, re.M | re.S).group(1).replace("'", "").split()
    have = set()
    for n in ("base", "desktop", "cache", "live"):
        for line in open(os.path.join(REPO, "iso", "packages", f"{n}.list")):
            have.add(line.split("#")[0].strip())
    for d in ("libvirt", "qemu-desktop", "virt-manager", "dnsmasq", "edk2-ovmf", "swtpm"):
        assert d in deps and d in have, d
