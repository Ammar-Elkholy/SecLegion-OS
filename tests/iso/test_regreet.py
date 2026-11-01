# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r12 L1: ReGreet's style sheet reaches /etc/greetd/regreet.css inside the ISO only.

mkarchiso copies iso/profile/airootfs/ into the image root, so
iso/profile/airootfs/etc/greetd/regreet.css becomes /etc/greetd/regreet.css in the image.
It must be the theme engine's default export byte for byte (no hand edits, no colour
of its own), and no host tool may know about it: the display manager on the live host is
never touched. Static checks; no ISO, QEMU or root needed.
"""

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "desktop" / "theme"))

from seclegion_theme import engine  # noqa: E402

AIROOTFS = REPO / "iso" / "profile" / "airootfs"
ISO_COPY = AIROOTFS / "etc" / "greetd" / "regreet.css"
# every script and recipe that runs on (or installs onto) the host
HOST_SIDE = [REPO / "Makefile", *sorted(p for p in (REPO / "tools").iterdir() if p.is_file())]
HOST_SIDE.append(REPO / "tests" / "host" / "test-apply-rollback.sh")


def default_export(dest: Path) -> Path:
    return engine.export_default(dest) / "regreet.css"


def test_regreet_iso_path_is_the_image_etc_greetd():
    assert ISO_COPY.relative_to(AIROOTFS).as_posix() == "etc/greetd/regreet.css"
    assert ISO_COPY.is_file() and not ISO_COPY.is_symlink()  # a link would dangle inside the image


def test_regreet_iso_copy_is_the_engine_default_export():
    with tempfile.TemporaryDirectory() as d:
        want = default_export(Path(d)).read_text()
    assert ISO_COPY.read_text() == want, (
        "regenerate: tools/seclegion-theme export-default desktop/theme/default, then copy regreet.css"
    )
    assert (REPO / "desktop" / "theme" / "default" / "regreet.css").read_text() == want


def test_regreet_iso_copy_has_no_colour_of_its_own():
    css = re.sub(r"/\*.*?\*/", "", ISO_COPY.read_text(), flags=re.S)
    rules = re.sub(r"@define-color\s+\S+\s+#[0-9a-f]{6};", "", css)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rules)
    # REUSE-IgnoreStart
    assert ISO_COPY.read_text().startswith("/* SPDX-License-Identifier: MIT */\n")
    # REUSE-IgnoreEnd


def test_regreet_negative_host_tools_never_touch_greetd():
    """Nothing that runs on the host mentions greetd, regreet or the display manager."""
    pat = re.compile(r"greetd|regreet|display-manager|sddm|gdm|lightdm", re.I)
    hits = [
        f"{p.relative_to(REPO)}:{n}"
        for p in HOST_SIDE
        if p.exists()
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
        if pat.search(line)
    ]
    assert hits == []


def test_regreet_negative_a_stray_host_reference_is_caught():
    """The scan above is not vacuous: it flags a line that installs the sheet on the host."""
    pat = re.compile(r"greetd|regreet|display-manager|sddm|gdm|lightdm", re.I)
    assert pat.search("install -m644 regreet.css /etc/greetd/regreet.css")
    assert not pat.search("tools/seclegion-host apply gtk")


def test_regreet_is_not_a_host_component():
    host = (REPO / "tools" / "seclegion-host").read_text()
    comps = re.search(r"^COMPONENTS=\((.*?)\)", host, re.M).group(1).split()
    assert "regreet" not in comps and "greetd" not in comps
