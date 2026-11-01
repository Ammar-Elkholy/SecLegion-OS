# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The VS Code and Brave launchers read the user's *-flags.conf, so the skel Wayland flag takes effect."""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CASES = [("seclegion-vscode-fetch/vscode.PKGBUILD", "code", "/opt/vscode/bin/code", "code-flags.conf"),
         ("seclegion-brave-fetch/brave.PKGBUILD", "brave", "/opt/brave/brave-browser", "brave-flags.conf")]


def wrapper(pkgbuild, binary):
    text = (REPO / "pkgs" / pkgbuild).read_text()
    m = re.search(rf'cat > "\$pkgdir/usr/bin/{binary}" <<\'EOF\'\n(.*?)\nEOF\n', text, re.S)
    assert m, f"no /usr/bin/{binary} wrapper in {pkgbuild}"
    return m.group(1)


@pytest.mark.parametrize("pkgbuild,binary,target,conf", CASES)
def test_vendor_wrapper_passes_flags_conf_lines(tmp_path, pkgbuild, binary, target, conf):
    script = wrapper(pkgbuild, binary).replace(f"exec {target} ", "printf '%s\\n' ")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / conf).write_text("# comment\n--ozone-platform-hint=auto\n\n--enable-x\n")
    out = subprocess.run(["bash", "-c", script, "wrapper", "file.txt"], capture_output=True, text=True,
                         env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, check=True).stdout.split("\n")
    assert out[:3] == ["--ozone-platform-hint=auto", "--enable-x", "file.txt"]
    assert "--no-sandbox" not in wrapper(pkgbuild, binary)
