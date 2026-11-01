# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Locate OVMF firmware on the host and make a per-run copy of the VARS store."""

import os
import shutil

# (code, vars) candidates, most specific first. 4M images are the current Arch layout.
CANDIDATES = (
    ("/usr/share/edk2/x64/OVMF_CODE.4m.fd", "/usr/share/edk2/x64/OVMF_VARS.4m.fd"),
    ("/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd", "/usr/share/edk2-ovmf/x64/OVMF_VARS.4m.fd"),
    ("/usr/share/OVMF/x64/OVMF_CODE.4m.fd", "/usr/share/OVMF/x64/OVMF_VARS.4m.fd"),
    ("/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_VARS_4M.fd"),
    ("/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_VARS.fd"),
    ("/usr/share/edk2/ovmf/OVMF_CODE.fd", "/usr/share/edk2/ovmf/OVMF_VARS.fd"),
)


class OvmfNotFound(RuntimeError):
    """OVMF is not installed where we looked. Never assume it is there."""


def find_ovmf(candidates=CANDIDATES):
    """Return (code_path, vars_template_path) or raise OvmfNotFound listing what was tried."""
    for code, vars_template in candidates:
        if os.path.isfile(code) and os.path.isfile(vars_template):
            return code, vars_template
    tried = ", ".join(code for code, _ in candidates)
    raise OvmfNotFound(
        "OVMF (edk2-ovmf) firmware not found on this host; looked for: " + tried
        + ". Install the edk2-ovmf package (owner action, no root for agents)."
    )


def fresh_vars(vars_template, destination):
    """Copy the pristine VARS template to a per-run file so runs never share NVRAM state."""
    shutil.copyfile(vars_template, destination)
    os.chmod(destination, 0o600)
    return destination
