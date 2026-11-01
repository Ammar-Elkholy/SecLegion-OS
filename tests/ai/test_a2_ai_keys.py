# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G68 ai_keys: an API key reaches the provider only on an explicit test, and is stored nowhere but the
secret store (not in config, any file under HOME, output, logging, subprocess env, or the UI string)."""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ai" / "center"))
from seclegion_ai_center import model  # noqa: E402
from seclegion_ai_center.secrets import MemoryStore  # noqa: E402

CANARY = "sk-canary-" + "7f3a9c1e5b2d4086a1c3" + "WXYZ"


class Stub:
    def __init__(self):
        self.seen = []
        seen = self.seen

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, dict(self.headers)))
                ok = (
                    self.headers.get("Authorization") == f"Bearer {CANARY}"
                    or self.headers.get("x-api-key") == CANARY
                )
                self.send_response(200 if ok else 401)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.close()


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return h


def files_under(root):
    return [p for p in Path(root).rglob("*") if p.is_file()]


def test_ai_keys_canary_reaches_stub_only_on_explicit_test_and_is_absent_elsewhere(
    home, stub, capsys, caplog
):
    caplog.set_level(logging.DEBUG)
    spawned_env = []
    real_run = subprocess.run

    def spy(*a, **k):
        spawned_env.append(k.get("env") or dict(os.environ))
        return real_run(*a, **k)

    store = MemoryStore()
    c = model.Center(store, runner=lambda argv: (127, ""))
    c.add("local-stub", stub.url, "m1", key=CANARY)
    assert stub.seen == [], "adding a provider must not contact it"
    c.runtime()
    ui = [c.masked("local-stub"), *(p.name + p.base_url + p.model for p in c.providers())]

    orig = subprocess.run
    subprocess.run = spy
    try:
        ok, msg = c.test_connection("local-stub")
    finally:
        subprocess.run = orig
    assert ok and "HTTP 200" in msg
    assert len(stub.seen) == 1
    assert stub.seen[0][1]["Authorization"] == f"Bearer {CANARY}"

    out = capsys.readouterr()
    haystacks = {
        "stdout": out.out,
        "stderr": out.err,
        "log": caplog.text,
        "message": msg,
        "ui": " ".join(ui),
        "env": "\n".join(f"{k}={v}" for e in spawned_env for k, v in {**e, **os.environ}.items()),
    }
    for p in files_under(home):
        haystacks[str(p)] = p.read_text(errors="replace")
    assert (home / ".config/seclegion/ai.toml").is_file()
    for where, text in haystacks.items():
        assert CANARY not in text, f"key leaked into {where}"
        assert CANARY[:-4] not in text, f"key prefix leaked into {where}"
    assert c.masked("local-stub") == "…WXYZ"


def test_ai_keys_rejected_key_reports_status_without_the_key(home, stub):
    store = MemoryStore()
    c = model.Center(store)
    c.add("local-stub", stub.url, "m1", key="wrong-key-0000")
    ok, msg = c.test_connection("local-stub")
    assert not ok and "401" in msg and "wrong-key" not in msg


def test_ai_keys_anthropic_style_header(home, stub):
    c = model.Center(MemoryStore())
    c.add("anth", stub.url, "m", key=CANARY, auth="x-api-key")
    assert c.test_connection("anth")[0]
    assert {k.lower(): v for k, v in stub.seen[0][1].items()}["x-api-key"] == CANARY


def test_ai_keys_mask_shows_last_four_only():
    assert model.mask(CANARY) == "…WXYZ"
    assert model.mask("short") == "…••••"
    assert model.mask("") == ""


def test_ai_keys_remote_http_and_credential_urls_refused(home):
    c = model.Center(MemoryStore())
    for bad in (
        "http://example.com/v1",
        "https://u:p@example.com/v1",
        "https://example.com/v1?k=1",
        "ftp://x",
    ):
        with pytest.raises(model.CenterError):
            c.add("p", bad, "m")
    assert not (home / ".config/seclegion/ai.toml").exists()


def test_ai_keys_remove_clears_secret_and_config(home, stub):
    s = MemoryStore()
    c = model.Center(s)
    c.add("local-stub", stub.url, "m", key=CANARY)
    c.remove("local-stub")
    assert s.get("local-stub") is None and c.providers() == []


def test_ai_keys_runtime_status_parsed():
    out = (
        "AI runtime: enabled\nollama package: installed\nlistener on 127.0.0.1:11434: yes\nmodels: a:1, b:2\n"
    )
    c = model.Center(MemoryStore(), runner=lambda argv: (0, out))
    lines, names = c.runtime()
    assert names == ["a:1", "b:2"] and "AI runtime: enabled" in lines


@pytest.mark.skipif(
    not (
        shutil.which("secret-tool")
        and shutil.which("dbus-run-session")
        and shutil.which("gnome-keyring-daemon")
    ),
    reason="secret-tool, dbus-run-session or gnome-keyring-daemon missing",
)
def test_ai_keys_real_secret_tool_roundtrip_in_throwaway_session():
    """Own private bus + keyring in a temp HOME: never the owner's keyring."""
    with tempfile.TemporaryDirectory() as td:
        env = {
            "PATH": os.environ["PATH"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": td,
            "XDG_DATA_HOME": td + "/data",
            "XDG_RUNTIME_DIR": td,
        }
        os.chmod(td, 0o700)
        name = "p" + uuid.uuid4().hex[:6]
        script = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from seclegion_ai_center.secrets import SecretToolStore\n"
            "s = SecretToolStore()\n"
            f"s.set('{name}', 'canary-roundtrip-1234')\n"
            f"print('GOT=' + str(s.get('{name}')))\n"
            f"s.delete('{name}')\n"
            f"print('AFTER=' + str(s.get('{name}')))\n"
        )
        cmd = (
            'echo "" | gnome-keyring-daemon --foreground --unlock --components=secrets '
            ">/dev/null 2>&1 & KP=$!; "
            "sleep 1; "
            f'"{sys.executable}" -c "$PY" "{REPO / "ai/center"}"; rc=$?; kill $KP 2>/dev/null; exit $rc'
        )
        try:
            p = subprocess.run(
                ["dbus-run-session", "--", "sh", "-c", cmd],
                env={**env, "PY": script},
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pytest.skip("throwaway keyring did not respond")
        if "GOT=" not in p.stdout:
            pytest.skip("throwaway Secret Service unavailable: " + p.stderr[-200:])
        assert "GOT=canary-roundtrip-1234" in p.stdout and "AFTER=None" in p.stdout
        assert not [f for f in files_under(td) if b"canary-roundtrip-1234" in f.read_bytes()]
