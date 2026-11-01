#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-ai-pick: Super+A rofi picker (decision O11). Lists ONLY entries that exist:
local models (only while the runtime is enabled and running), configured providers (only when
aichat is installed to chat with them), and AI Center. `--list` prints the entries."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def providers(env):
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".config")
    try:
        data = tomllib.loads((Path(base) / "seclegion" / "ai.toml").read_text())
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []
    return [p for p in data.get("provider", []) if p.get("name") and p.get("model")]


def runtime(env):
    try:
        p = subprocess.run(
            ["seclegion-ai", "status", "--json"], capture_output=True, text=True, timeout=10, env=env
        )
        d = json.loads(p.stdout)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def entries(env, state=None):
    """[(label, argv)] in display order."""
    st = runtime(env) if state is None else state
    out = []
    if shutil.which("aichat", path=env.get("PATH")):
        if st.get("enabled") and st.get("listening"):
            out += [
                (f"Local: {m}", ["seclegion-aichat", "-m", f"ollama:{m}"])
                for m in st.get("models", [])
                if "embed" not in m
            ]
        out += [
            (f"Cloud: {p['name']} ({p['model']})", ["seclegion-aichat", "-m", f"{p['name']}:{p['model']}"])
            for p in providers(env)
        ]
    if shutil.which("seclegion-ai-center", path=env.get("PATH")):
        out.append(("AI Center", ["seclegion-ai-center"]))
    return out


def main(argv=None, env=None):
    args = sys.argv[1:] if argv is None else argv
    env = dict(os.environ if env is None else env)
    ents = entries(env)
    if args[:1] == ["--list"]:
        print("\n".join(label for label, _ in ents))
        return 0
    if not ents:
        return 0
    p = subprocess.run(
        ["rofi", "-dmenu", "-i", "-p", "AI"],
        input="\n".join(lab for lab, _ in ents),
        capture_output=True,
        text=True,
    )
    choice = p.stdout.strip()
    for label, cmd in ents:
        if label == choice:
            if cmd[0] == "seclegion-ai-center":
                os.execvp(cmd[0], cmd)
            os.execvp("kitty", ["kitty", "--title", "SecLegion AI", *cmd])
    return 0


if __name__ == "__main__":
    sys.exit(main())
