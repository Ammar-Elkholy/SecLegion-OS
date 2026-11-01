# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Read the hardware facts from sysfs/procfs under a root (`/`, or a fixture dir with the same layout).

Only an allowlist of DMI fields is read. Serials, UUIDs, MAC addresses and hostnames are never
copied into the returned facts (hwreport reads them separately, only to scrub them).
"""

import re
from pathlib import Path

DMI_FIELDS = (
    "sys_vendor",
    "product_name",
    "product_version",
    "board_vendor",
    "board_name",
    "bios_vendor",
    "bios_version",
    "bios_date",
    "chassis_type",
)
LAPTOP_CHASSIS = {"8", "9", "10", "11", "14", "30", "31", "32"}
# (field, regex) pairs checked in order against the DMI strings; first hit names the hypervisor.
VIRT_DMI = (
    ("sys_vendor", r"^QEMU", "qemu"),
    ("product_name", r"\bKVM\b|Standard PC \(", "qemu"),
    ("sys_vendor", r"VMware", "vmware"),
    ("sys_vendor", r"innotek|Oracle Corporation", "virtualbox"),
    ("product_name", r"VirtualBox", "virtualbox"),
    ("product_name", r"Virtual Machine", "hyperv"),
)


def read_text(path, default=""):
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return default


def _hex(value):
    value = value.strip().lower()
    return value[2:] if value.startswith("0x") else value


def read_pci(root):
    """PCI devices under root/sys/bus/pci/devices. Real sysfs names contain no underscore; fixtures use
    it for the colons some filesystems (exfat, ntfs) cannot hold."""
    devices = []
    base = Path(root) / "sys/bus/pci/devices"
    for entry in sorted(base.iterdir()) if base.is_dir() else []:
        vendor, device = _hex(read_text(entry / "vendor")), _hex(read_text(entry / "device"))
        if not vendor or not device:
            continue
        devices.append(
            {
                "addr": entry.name.replace("_", ":"),  # fixture dirs spell 0000:00:02.0 as 0000_00_02.0
                "vendor": vendor,
                "device": device,
                "class": _hex(read_text(entry / "class")).zfill(6),
                "subsystem_vendor": _hex(read_text(entry / "subsystem_vendor")),
                "subsystem_device": _hex(read_text(entry / "subsystem_device")),
                "boot_vga": read_text(entry / "boot_vga") == "1",
            }
        )
    return devices


def read_dmi(root):
    base = Path(root) / "sys/class/dmi/id"
    return {name: read_text(base / name) for name in DMI_FIELDS if read_text(base / name)}


def read_cpu(root):
    vendor = model = ""
    hypervisor = False
    for line in read_text(Path(root) / "proc/cpuinfo").splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "vendor_id" and not vendor:
            vendor = value
        elif key == "model name" and not model:
            model = value
        elif key == "flags" and "hypervisor" in value.split():
            hypervisor = True
        if vendor and model and hypervisor:
            break
    return {"vendor": vendor, "model": model, "hypervisor_flag": hypervisor}


def detect_virt(dmi, cpu):
    for field, pattern, name in VIRT_DMI:
        if re.search(pattern, dmi.get(field, ""), re.IGNORECASE):
            return name
    return "other" if cpu["hypervisor_flag"] else "none"


def kernel_flavor(osrelease):
    """stock = Arch `linux`, lts = `linux-lts`, anything else (zen, hardened, rt, custom) = other."""
    if re.search(r"-arch\d+-\d+$", osrelease):
        return "stock"
    if osrelease.endswith("-lts"):
        return "lts"
    return "other"


def has_touchpad(root):
    text = read_text(Path(root) / "proc/bus/input/devices")
    return any("N: Name=" in line and "touchpad" in line.lower() for line in text.splitlines())
