# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""AI Center logic: providers config (names, URLs, model ids only), masked keys, runtime status,
explicit connection test. No GTK. Keys live in the secret store and nowhere else."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
AUTH_STYLES = ("bearer", "x-api-key")
PRESETS = {
    "Anthropic": {"base_url": "https://api.anthropic.com/v1", "auth": "x-api-key"},
    "OpenAI": {"base_url": "https://api.openai.com/v1", "auth": "bearer"},
}


class CenterError(Exception):
    pass


def config_path(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".config")
    return Path(base) / "seclegion" / "ai.toml"


def mask(key):
    """Display form of a key: only the last 4 characters (and none for a short key)."""
    if not key:
        return ""
    return "…" + key[-4:] if len(key) > 8 else "…••••"


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    auth: str = "bearer"


def check_url(url):
    u = urllib.parse.urlparse(url)
    loop = u.hostname in ("127.0.0.1", "localhost", "::1")
    if not u.hostname or u.scheme not in ("https", "http") or (u.scheme == "http" and not loop):
        raise CenterError("base URL must be https (http only for loopback)")
    if u.username or u.password or u.query:
        raise CenterError("base URL must not carry credentials or a query")


def load_providers(path):
    try:
        data = tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        return []
    return [
        Provider(p["name"], p["base_url"], p.get("model", ""), p.get("auth", "bearer"))
        for p in data.get("provider", [])
    ]


def save_providers(path, providers):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q = json.dumps  # a JSON string is a valid TOML basic string
    lines = ["# SecLegion AI Center: provider names, URLs and model ids. API keys are in the Secret Service."]
    for p in providers:
        lines += [
            "",
            "[[provider]]",
            f"name = {q(p.name)}",
            f"base_url = {q(p.base_url)}",
            f"model = {q(p.model)}",
            f"auth = {q(p.auth)}",
        ]
    path.write_text("\n".join(lines) + "\n")


def run(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, ""
    return p.returncode, p.stdout


def http_get(url, headers, timeout=10):
    """Return the HTTP status (an HTTP error status is a result, not an exception)."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (scheme checked by check_url)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class Center:
    def __init__(self, store, path=None, runner=run, http=http_get):
        self.store, self.path, self.runner, self.http = store, Path(path or config_path()), runner, http

    def runtime(self):
        """(status lines, installed models) from seclegion-ai; never raises."""
        rc, out = self.runner(["seclegion-ai", "status"])
        if rc == 127:
            return ["seclegion-ai is not installed"], []
        lines = [ln for ln in out.splitlines() if ln.strip()]
        models = []
        for ln in lines:
            if ln.startswith("models: ") and "none" not in ln and "not running" not in ln:
                models = [m.strip() for m in ln[len("models: ") :].split(",") if m.strip()]
        return lines, models

    def providers(self):
        return load_providers(self.path)

    def get(self, name):
        for p in self.providers():
            if p.name == name:
                return p
        raise CenterError(f"no provider {name}")

    def add(self, name, base_url, model, key=None, auth="bearer"):
        if not NAME_RE.match(name):
            raise CenterError("provider name: letters, digits, . _ - only")
        if auth not in AUTH_STYLES:
            raise CenterError("auth must be bearer or x-api-key")
        check_url(base_url)
        rest = [p for p in self.providers() if p.name != name]
        save_providers(self.path, [*rest, Provider(name, base_url.rstrip("/"), model.strip(), auth)])
        if key:
            self.store.set(name, key.strip())

    def set_key(self, name, key):
        self.get(name)
        self.store.set(name, key.strip())

    def remove(self, name):
        save_providers(self.path, [p for p in self.providers() if p.name != name])
        self.store.delete(name)

    def masked(self, name):
        k = self.store.get(name)
        return mask(k) if k else "no key"

    def test_connection(self, name):
        """Send the key to the provider's /models endpoint. Called only from an explicit click.

        Returns (ok, message); the message never contains the key.
        """
        p = self.get(name)
        key = self.store.get(name)
        if not key:
            raise CenterError(f"{name}: no API key stored")
        check_url(p.base_url)
        if p.auth == "x-api-key":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": f"Bearer {key}"}
        try:
            status = self.http(p.base_url + "/models", headers)
        except OSError as e:
            raise CenterError(f"{name}: could not connect ({type(e).__name__})") from None
        ok = 200 <= status < 300
        return ok, f"{name}: HTTP {status}" + ("" if ok else " (key rejected or endpoint wrong)")
