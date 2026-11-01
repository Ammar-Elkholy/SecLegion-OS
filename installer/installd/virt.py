# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Opt-in virtualisation set: hints virt: true -> seclegion-virt package + its setup command.

Nothing here installs or runs; post.py appends the package and issues the setup command in the
target only when hints carry virt: true.
"""

PACKAGES = ["seclegion-virt"]


def virt_packages(virt):
    """Extra packages for the opt-in virt set; [] unless virt is exactly True."""
    return list(PACKAGES) if virt is True else []


def setup_argv(virt, user):
    """The in-target command (run via arch-chroot) that sets virt up; None unless virt is True."""
    return ["seclegion-virt-setup", "--user", user] if virt is True else None
