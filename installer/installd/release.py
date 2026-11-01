# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Release switch (RL1a): a release ISO disables every DEV-only installer behaviour.

Release mode is on when SECLEGION_RELEASE=1 or the marker file /etc/seclegion/release exists
(a release build writes the marker into the image). In release mode:
  - facts.gather reports dev_build=False whatever the caller asked for
  - --force-install-mode, --dev, --facts and SECLEGION_POST_SKIP_MISSING are refused
    (--facts matters most: the install kiosk user runs seclegion-install as root through pkexec, and
    made-up facts would defeat the host-damage guards)
"""

import os

MARKER = "/etc/seclegion/release"


def is_release(env=None, marker=MARKER):
    env = os.environ if env is None else env
    return env.get("SECLEGION_RELEASE") == "1" or os.path.exists(marker)


def dev_violations(force_install_mode=False, dev=False, env=None, marker=MARKER, facts=False):
    """Names of the DEV-only switches in use that a release build must refuse ([] outside release mode)."""
    env = os.environ if env is None else env
    if not is_release(env, marker):
        return []
    bad = []
    if force_install_mode:
        bad.append("--force-install-mode")
    if dev:
        bad.append("--dev")
    if facts:
        bad.append("--facts")
    if env.get("SECLEGION_POST_SKIP_MISSING"):
        bad.append("SECLEGION_POST_SKIP_MISSING")
    return bad
