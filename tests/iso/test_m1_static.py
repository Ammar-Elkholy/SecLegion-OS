# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r13 J1a (G1, G2): the ISO profile and the GRUB menu, checked statically.

No ISO, QEMU or root needed. The VM gates (default boot, modes, memtest) are J1c.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILE = REPO / "iso" / "profile"
GRUB_FILES = [PROFILE / "grub" / "grub.cfg", PROFILE / "grub" / "loopback.cfg"]
PROFILEDEF = PROFILE / "profiledef.sh"

BRAND_RE = re.compile(r"arch ?linux|syslinux", re.IGNORECASE)


def top_level_entries(text: str) -> list[tuple[str, str, str]]:
    """(kind, title, body) of each menuentry/submenu at brace depth 0, in order."""
    found = []
    depth = 0
    for m in re.finditer(r"[{}]", text):
        if m.group() == "{":
            if depth == 0:
                head = text[text.rfind("\n", 0, m.start()) + 1 : m.start()]
                hm = re.match(r"\s*(menuentry|submenu)\s+(?:'([^']*)'|\"([^\"]*)\")", head)
                if hm:
                    found.append([hm.group(1), hm.group(2) or hm.group(3), m.end()])
            depth += 1
        else:
            depth -= 1
            if depth == 0 and found and len(found[-1]) == 3:
                found[-1].append(text[found[-1][2] : m.start()])
    assert depth == 0
    return [(k, t, b) for k, t, _, b in found]


def entry_id(text: str, title: str) -> str:
    m = re.search(r"(?:menuentry|submenu)\s+'" + re.escape(title) + r"'[^{]*--id\s+'([^']+)'", text)
    assert m, title
    return m.group(1)


def brand_hits(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if BRAND_RE.search(ln)]


def setting(text: str, name: str) -> str:
    m = re.search(rf"^\s*(?:set\s+)?{name}=\"?([^\s\"]+)", text, re.MULTILINE)
    assert m, name
    return m.group(1)


@pytest.mark.parametrize("cfg", GRUB_FILES, ids=lambda p: p.name)
def test_six_entries_install_default_timeout(cfg):
    text = cfg.read_text()
    entries = top_level_entries(text)
    assert [t for _, t, _ in entries] == [
        "Install SecLegion OS",
        "Try SecLegion OS (Live)",
        "Rescue",
        "Memory Test (Memtest86+)",
        "UEFI Firmware Settings",
        "Safe Graphics",
    ]
    assert entry_id(text, entries[0][1]) == "seclegion-install"
    assert setting(text, "default") == "seclegion-install"
    assert int(setting(text, "timeout")) >= 10
    assert setting(text, "timeout_style") == "menu"


@pytest.mark.parametrize("cfg", GRUB_FILES, ids=lambda p: p.name)
def test_each_entry_sets_its_mode_and_target(cfg):
    entries = top_level_entries(cfg.read_text())
    by_title = {t: (k, b) for k, t, b in entries}
    modes = (("Install SecLegion OS", "install"), ("Try SecLegion OS (Live)", "live"), ("Rescue", "rescue"))
    for title, mode in modes:
        _, body = by_title[title]
        assert f"seclegion.mode={mode} " in body
        assert f"systemd.unit=seclegion-{mode}.target" in body
        assert len(re.findall(r"^\s*linux\s", body, re.MULTILINE)) == 1
    kind, body = by_title["Safe Graphics"]
    assert kind == "submenu"
    sub = top_level_entries(body)
    assert [t for _, t, _ in sub] == ["Install (safe graphics)", "Live (safe graphics)"]
    for (_, _, sbody), mode in zip(sub, ("install", "live"), strict=True):
        assert "nomodeset" in sbody
        assert f"seclegion.mode={mode} " in sbody
        assert f"systemd.unit=seclegion-{mode}.target" in sbody
    assert "fwsetup" in by_title["UEFI Firmware Settings"][1]
    assert "memtest86+" in by_title["Memory Test (Memtest86+)"][1]


def test_serial_kept_and_theme_is_conditional():
    text = (PROFILE / "grub" / "grub.cfg").read_text()
    assert re.search(r"^\s*if serial --unit=0 --speed=115200", text, re.MULTILINE)
    assert "terminal_output --append serial" in text
    assert "console=ttyS0,115200" in text
    # the theme is loaded only inside a file-exists guard
    guard_re = r'if \[ -f "\$\{prefix\}/themes/seclegion/theme\.txt" \]; then(.*?)\n    else'
    guard = re.search(guard_re, text, re.DOTALL)
    assert guard, "theme guard missing"
    assert 'set theme="${prefix}/themes/seclegion/theme.txt"' in guard.group(1)
    assert text.count("set theme=") == 1


def test_profiledef():
    text = PROFILEDEF.read_text()
    assert 'iso_name="seclegion"' in text
    assert re.search(r'^iso_label="SECLEGION_\$\(date .*\+%Y%m\)"$', text, re.MULTILINE)
    assert "bootmodes=('uefi.grub')" in text
    assert "DEV BUILD" in text
    assert 'install_dir="seclegion"' in text


def test_stock_boot_dirs_removed():
    assert not (PROFILE / "syslinux").exists()
    assert not (PROFILE / "efiboot").exists()


def test_no_arch_branding_and_no_bios():
    """G2: the same scan as the plan's grep, plus no BIOS boot mode."""
    for f in (*GRUB_FILES, PROFILEDEF):
        assert brand_hits(f.read_text()) == [], f
    assert "bios." not in PROFILEDEF.read_text().split("bootmodes=")[1].split("\n")[0]
    for f in GRUB_FILES:
        assert 'grub_platform}" == \'pc\'' not in f.read_text()


def test_branding_scan_catches_a_planted_string():
    assert brand_hits("menuentry 'Arch Linux install medium' {") != []
    assert brand_hits("APPEND syslinux boot") != []
    assert brand_hits("menuentry 'Install SecLegion OS' {") == []


def test_spdx_headers():
    for f in (*GRUB_FILES, PROFILEDEF):
        head = "\n".join(f.read_text().splitlines()[:4])
        assert "SPDX-License-" + "Identifier: MIT" in head, f
        assert "SPDX-FileCopyright" + "Text" in head, f
