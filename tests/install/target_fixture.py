# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""A minimal clean installed-target tree for target_check tests (no root, no VM)."""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "installer", "installd"))
import post  # noqa: E402

FILES = {
    "etc/passwd": "root:x:0:0::/root:/bin/bash\nammar:x:1000:1000::/home/ammar:/bin/bash\n"
    "nobody:x:65534:65534::/:/usr/bin/nologin\n",
    "etc/shadow": "root:!*:19000::::::\nammar:$6$salt$hashhashhash:19000:0:99999:7:::\n"
    "nobody:!*:19000::::::\n",
    "etc/group": "root:x:0:\nwheel:x:998:ammar\nammar:x:1000:\n",
    "etc/sudoers": "root ALL=(ALL:ALL) ALL\n%wheel ALL=(ALL:ALL) ALL\n@includedir /etc/sudoers.d\n",
    "etc/pam.d/system-auth": "auth required pam_unix.so try_first_pass\n",
    "etc/mkinitcpio.conf": (
        "# HOOKS=(archiso)\nHOOKS=(base systemd autodetect modconf block filesystems fsck)\n"
    ),
    "etc/kernel/cmdline": "root=UUID=x rw quiet\n",
    "etc/os-release": 'NAME="SecLegion OS"\nID=seclegion\nID_LIKE=arch\n',
    "usr/lib/os-release": 'NAME="Arch Linux"\nID=arch\n',
    "etc/pacman.conf": "[options]\nSigLevel = Required DatabaseOptional\n\n[core]\n"
    "Include = /etc/pacman.d/mirrorlist\n\n[extra]\nInclude = /etc/pacman.d/mirrorlist\n\n"
    + post.DISABLED_SECLEGION,
    "var/lib/pacman/local/bash-5.2-1/desc": "%NAME%\nbash\n\n%VERSION%\n5.2-1\n",
    "etc/greetd/config.toml": '[default_session]\ncommand = "greeter"\n',
}
LIVE_ONLY = {"mkinitcpio-archiso", "grub", "nbd"}


def build_clean(root):
    root = str(root)
    for rel, text in FILES.items():
        write(root, rel, text)
    os.makedirs(os.path.join(root, "etc/sudoers.d"), exist_ok=True)
    os.makedirs(os.path.join(root, "etc/polkit-1/rules.d"), exist_ok=True)
    return root


def write(root, rel, text):
    p = os.path.join(str(root), rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)
