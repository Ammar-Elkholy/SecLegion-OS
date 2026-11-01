# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""G69 ai_pipe / ai_cors, plus: the key is never in the generated yaml or any output, the picker lists
only entries that exist, the waybar pill hides when nothing is configured, Super+A is bound."""

import io
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ai" / "aichat"))
import seclegion_ai_pick as pick  # noqa: E402
import seclegion_aichat as wrap  # noqa: E402

CANARY = "sk-canary-" + "91c4d7e0b3a5" + "QRST"
ON = {"enabled": True, "installed": True, "listening": True, "models": ["llama3.2:3b", "nomic-embed-text"]}
OFF = {"enabled": False, "installed": False, "listening": False, "models": []}
TOML = (
    '[[provider]]\nname = "OpenAI"\nbase_url = "https://api.openai.com/v1"\n'
    'model = "gpt-x"\nauth = "bearer"\n'
    '[[provider]]\nname = "Anthropic"\nbase_url = "https://api.anthropic.com/v1"\nmodel = "claude-x"\n'
    'auth = "x-api-key"\n'
)


def home(tmp_path, toml=TOML):
    h = tmp_path / "home"
    (h / "seclegion").mkdir(parents=True, exist_ok=True)
    if toml is not None:
        (h / "seclegion" / "ai.toml").write_text(toml)
    return {
        "XDG_CONFIG_HOME": str(h),
        "HOME": str(tmp_path),
        "PATH": os.defpath,
        "SECLEGION_AICHAT_BIN": "/bin/true",
    }


def run(tmp_path, args, state, tty=None, isatty=False, toml=TOML, secrets=None):
    env = home(tmp_path, toml)
    launched = []
    asked = []
    secrets = {"OpenAI": CANARY, "Anthropic": CANARY} if secrets is None else secrets

    def get(c):
        asked.append(c)
        return secrets.get(c)

    rc = wrap.main(
        args,
        env=env,
        stdin_isatty=isatty,
        open_tty=lambda: tty,
        state_fn=lambda: state,
        launch=lambda cmd, penv: launched.append((cmd, penv)) or 0,
        get_secret=get,
        roles_src=REPO / "ai" / "aichat" / "roles",
    )
    return rc, launched, asked, env


class Tty(io.StringIO):
    def __init__(self, answer):
        super().__init__(answer)
        self.out = []

    def write(self, s):
        self.out.append(s)

    def close(self):  # keep readable after `with`
        pass


# --- G69 ai_pipe -----------------------------------------------------------------------------------------


def test_ai_pipe_non_tty_cloud_refused(tmp_path, capsys):
    rc, launched, asked, _ = run(tmp_path, ["-m", "OpenAI:gpt-x", "hi"], ON, tty=None)
    assert rc == 1 and launched == [] and asked == []  # refused before the key is even read
    assert "never sent to cloud" in capsys.readouterr().err


def test_ai_pipe_default_cloud_model_refused(tmp_path):
    rc, launched, _, _ = run(tmp_path, ["hi"], OFF, tty=None)  # runtime off: the default is a cloud model
    assert rc == 1 and launched == []


def test_ai_pipe_local_allowed(tmp_path):
    rc, launched, asked, _ = run(tmp_path, ["hi"], ON, tty=None)
    assert rc == 0 and asked == []
    cmd, penv = launched[0]
    assert cmd[1:3] == ["-m", "ollama:llama3.2:3b"]
    assert not any(CANARY in v for v in penv.values())


def test_ai_pipe_cloud_needs_tty_confirmation(tmp_path):
    rc, launched, _, _ = run(tmp_path, ["-m", "OpenAI:gpt-x"], ON, tty=Tty("n\n"))
    assert rc == 1 and launched == []
    rc, launched, _, _ = run(tmp_path, ["-m", "OpenAI:gpt-x"], ON, tty=Tty("y\n"))
    assert rc == 0 and launched[0][1]["OPENAI_API_KEY"] == CANARY


def test_ai_pipe_interactive_cloud_needs_no_confirmation(tmp_path):
    rc, launched, _, _ = run(tmp_path, ["-m", "Anthropic:claude-x"], ON, isatty=True)
    assert rc == 0 and launched[0][1]["ANTHROPIC_API_KEY"] == CANARY


def test_ai_pipe_unknown_client_is_cloud(tmp_path):
    rc, launched, _, _ = run(tmp_path, ["-m", "somemodel"], ON, tty=None)
    assert rc == 1 and launched == []


def test_ai_pipe_subprocess_no_terminal(tmp_path):
    """The real script, no controlling terminal (new session) and piped stdin: refused, aichat never runs."""
    fake = tmp_path / "aichat"
    fake.write_text(f"#!/bin/sh\ntouch {tmp_path}/RAN\n")
    fake.chmod(0o755)
    env = home(tmp_path) | {"SECLEGION_AICHAT_BIN": str(fake), "PATH": f"{tmp_path}:{os.defpath}"}
    r = subprocess.run(
        [sys.executable, str(REPO / "ai/aichat/seclegion_aichat.py"), "-m", "OpenAI:gpt-x"],
        input="secret data",
        capture_output=True,
        text=True,
        env=env,
        start_new_session=True,
    )
    assert r.returncode == 1 and "never sent to cloud" in r.stderr
    assert not (tmp_path / "RAN").exists()


# --- the key never lands in the yaml or any output ------------------------------------------------------


def test_ai_keys_not_in_yaml_or_output(tmp_path, capsys):
    rc, launched, _, env = run(tmp_path, ["-m", "OpenAI:gpt-x"], ON, isatty=True)
    cfg = Path(env["XDG_CONFIG_HOME"]) / "aichat" / "config.yaml"
    text = cfg.read_text()
    assert CANARY not in text and "api_key" not in text
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    out = capsys.readouterr()
    assert CANARY not in out.out + out.err
    for p in Path(env["XDG_CONFIG_HOME"]).rglob("*"):
        if p.is_file():
            assert CANARY not in p.read_text()
    # only the one needed key reaches the process env
    penv = launched[0][1]
    assert [k for k in penv if k.endswith("_API_KEY")] == ["OPENAI_API_KEY"]


def test_ai_config_clients_and_roles(tmp_path):
    rc, _, _, env = run(tmp_path, ["config"], ON)
    base = Path(env["XDG_CONFIG_HOME"]) / "aichat"
    y = (base / "config.yaml").read_text()
    assert "name: ollama" in y and 'api_base: "http://127.0.0.1:11434/v1"' in y
    assert 'rag_embedding_model: "ollama:nomic-embed-text"' in y
    assert "type: claude" in y and "name: OpenAI" in y
    assert "serve_addr" not in y
    for r in ("S+A.md", "tutor.md", "docs-RAG.md"):
        assert (base / "roles" / r).is_file()
    # runtime off: no local client, providers only
    run(tmp_path, ["config"], OFF)
    y = (base / "config.yaml").read_text()
    assert "name: ollama" not in y and "name: OpenAI" in y
    run(tmp_path, ["config"], OFF, toml="")
    assert (base / "config.yaml").read_text().rstrip().endswith("clients: []")


# --- G69 ai_cors -----------------------------------------------------------------------------------------


def test_ai_cors_serve_mode_not_shipped(tmp_path, capsys):
    """aichat has no CORS control, so serve mode is not shipped: the wrapper rejects it, the yaml has no
    serve_addr, and the picker offers no browser chat."""
    for a in (["--serve"], ["--serve", "0.0.0.0:8000"], ["--serve=127.0.0.1:8000"]):
        rc, launched, _, _ = run(tmp_path, a, ON, isatty=True)
        assert rc == 1 and launched == []
        assert "serve mode is not shipped" in capsys.readouterr().err
    run(tmp_path, ["config"], ON)
    assert "serve_addr" not in (Path(home(tmp_path)["XDG_CONFIG_HOME"]) / "aichat/config.yaml").read_text()
    assert "--serve" not in (REPO / "ai/aichat/seclegion_ai_pick.py").read_text().replace('"--serve"', "")


# --- picker ---------------------------------------------------------------------------------------------


def fake_bins(tmp_path, names):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    for n in names:
        (d / n).write_text("#!/bin/sh\n")
        (d / n).chmod(0o755)
    return str(d)


def test_ai_picker_lists_only_existing(tmp_path):
    env = home(tmp_path)
    env["PATH"] = fake_bins(tmp_path, ["aichat", "seclegion-ai-center"])
    labels = [lab for lab, _ in pick.entries(env, ON)]
    assert labels == [
        "Local: llama3.2:3b",
        "Cloud: OpenAI (gpt-x)",
        "Cloud: Anthropic (claude-x)",
        "AI Center",
    ]
    # runtime off: no local entries
    assert [lab for lab, _ in pick.entries(env, OFF)] == labels[1:]
    # nothing configured: only the AI Center
    env = home(tmp_path, "")
    env["PATH"] = fake_bins(tmp_path, ["aichat", "seclegion-ai-center"])
    assert [lab for lab, _ in pick.entries(env, OFF)] == ["AI Center"]
    # aichat not installed: no chat entries at all
    env["PATH"] = str(tmp_path / "bin2")
    (tmp_path / "bin2").mkdir()
    assert pick.entries(env, ON) == []


# --- waybar pill ----------------------------------------------------------------------------------------


def pill(tmp_path, state, toml):
    fake = tmp_path / "fake-ai"
    fake.write_text(f"#!/bin/sh\necho '{json.dumps(state)}'\n")
    fake.chmod(0o755)
    env = home(tmp_path, toml) | {"SL_AI_BIN": str(fake)}
    r = subprocess.run([str(REPO / "desktop/waybar/seclegion-ai")], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stderr == ""
    return json.loads(r.stdout)


def test_ai_pill_hidden_when_nothing_configured(tmp_path):
    j = pill(tmp_path, OFF, None)
    assert j["text"] == "" and j["class"] == "hidden"


def test_ai_pill_states(tmp_path):
    j = pill(tmp_path, ON, None)
    assert j["class"] == "active" and "2" in j["text"]
    assert pill(tmp_path, OFF, TOML)["class"] == "off"
    assert pill(tmp_path, OFF, TOML)["tooltip"].endswith("2 cloud provider(s) configured")


def test_ai_pill_module_in_bar():
    cfg = (REPO / "desktop/waybar/config.jsonc").read_text()
    cfg = re.sub(r"^\s*//.*$", "", cfg, flags=re.M)
    m = json.loads(cfg)["custom/sl-ai"]
    assert "host/bin/seclegion-ai" in m["exec"] and m["on-click"] == "seclegion-ai-center"
    assert "custom/sl-ai" in json.loads(cfg)["modules-right"]


# --- Super+A --------------------------------------------------------------------------------------------


def test_ai_bind_super_a_present_without_collisions():
    keys = (REPO / "desktop/hypr/seclegion-keys.lua").read_text()
    assert 'hl.bind("SUPER + A", hl.dsp.exec_cmd("seclegion-ai-pick")' in keys
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/seclegion-keys-lint"),
            str(REPO / "tests/keys/fixtures/owner-keybinds.lua"),
            str(REPO / "desktop/hypr/seclegion-keys.lua"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout


def test_ai_packaging_optdepends_aichat_not_depends():
    pk = (REPO / "pkgs/seclegion-ai/PKGBUILD").read_text()
    assert re.search(r"optdepends=\(.*?'aichat:", pk, re.S)
    assert not re.search(r"^depends=\([^)]*aichat", pk, re.M)
    assert "ai/aichat" in (REPO / "pkgs/seclegion-ai/source.list").read_text().split()
