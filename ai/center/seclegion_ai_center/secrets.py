# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""API-key storage: the Secret Service (gnome-keyring) only, through the libsecret secret-tool CLI.

Attribute schema: xdg:schema=org.seclegion.ai, provider=<name>. The key goes to secret-tool on stdin
(never argv, never a file) and comes back on stdout; it is not logged and not placed in any environment.
MemoryStore is the in-memory stand-in used by tests behind the same three methods.
"""

from __future__ import annotations

import os
import subprocess

SCHEMA = "org.seclegion.ai"


class SecretError(Exception):
    pass


class MemoryStore:
    def __init__(self):
        self._d: dict[str, str] = {}

    def get(self, provider):
        return self._d.get(provider)

    def set(self, provider, key):
        self._d[provider] = key

    def delete(self, provider):
        self._d.pop(provider, None)


class SecretToolStore:
    def __init__(self, program="secret-tool", env=None):
        self.program = program
        self.env = dict(os.environ if env is None else env)

    def _run(self, argv, stdin=None):
        try:
            return subprocess.run(
                [self.program, *argv], input=stdin, capture_output=True, text=True, env=self.env, check=False
            )
        except FileNotFoundError as e:
            raise SecretError("secret-tool is not installed (libsecret)") from e

    @staticmethod
    def _attrs(provider):
        return ["xdg:schema", SCHEMA, "provider", provider]

    def get(self, provider):
        p = self._run(["lookup", *self._attrs(provider)])
        return p.stdout if p.returncode == 0 and p.stdout else None

    def set(self, provider, key):
        p = self._run(["store", f"--label=SecLegion AI: {provider}", *self._attrs(provider)], stdin=key)
        if p.returncode != 0:
            raise SecretError("could not store the key in the Secret Service (is the keyring unlocked?)")

    def delete(self, provider):
        self._run(["clear", *self._attrs(provider)])
