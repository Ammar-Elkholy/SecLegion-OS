#!/usr/bin/python3 -I
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-ai: control the local AI runtime (ollama). OFF by default, no telemetry, no cloud.

  seclegion-ai status                 enabled? listener on 127.0.0.1:11434? installed models
  seclegion-ai enable | disable       install ollama on request (official Arch repo), enable/disable its unit
  seclegion-ai pull NAME [--yes] [--allow-uncatalogued]
  seclegion-ai list | remove NAME

Pulling needs consent: --yes, or typing the model name at an interactive prompt. Cloud-backed models
(a tag ending in "cloud") are always refused. After a pull the weights blob digest (the sha256 in the
FROM line of `ollama show NAME --modelfile`) must equal the catalog digest, else the model is removed.
Every external command goes through `runner`, so tests inject a fake.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

UNIT = "ollama.service"
PORT = 11434
CATALOG = Path(os.environ.get("SECLEGION_AI_CATALOG", "/usr/share/seclegion/ai/catalog.toml"))
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FIELDS = ("name", "tag", "digest", "licence", "size_mb", "ram_mb")


class Abort(Exception):
    pass


def run(argv):
    """Default runner: (returncode, stdout). A missing program is returncode 127."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, ""
    return p.returncode, p.stdout


def is_cloud(name):
    return name.lower().rsplit(":", 1)[-1].endswith("cloud") or name.lower().endswith("-cloud")


def lint_catalog(data):
    """Return the problems of a parsed catalog (empty list = clean)."""
    problems, seen = [], set()
    models = data.get("model")
    if not isinstance(models, list) or not models:
        return ["no [[model]] entries"]
    for i, m in enumerate(models):
        who = m.get("name", f"entry {i}")
        for f in FIELDS:
            if m.get(f) in (None, ""):
                problems.append(f"{who}: missing {f}")
        if m.get("digest") and not DIGEST_RE.match(str(m["digest"])):
            problems.append(f"{who}: digest is not sha256:<64 hex>")
        for f in ("size_mb", "ram_mb"):
            if f in m and (not isinstance(m[f], int) or m[f] <= 0):
                problems.append(f"{who}: {f} must be a positive integer")
        if is_cloud(str(m.get("tag", ""))) or is_cloud(str(m.get("name", ""))):
            problems.append(f"{who}: cloud-backed models are not allowed")
        for f in ("name", "tag"):
            if m.get(f) in seen:
                problems.append(f"{who}: duplicate {f} {m[f]}")
            seen.add(m.get(f))
    return problems


def load_catalog(path=None):
    with open(path or CATALOG, "rb") as f:
        data = tomllib.load(f)
    problems = lint_catalog(data)
    if problems:
        raise Abort("catalog is invalid: " + "; ".join(problems))
    return data["model"]


def find_model(catalog, name):
    return next((m for m in catalog if name in (m["name"], m["tag"])), None)


def mem_available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise Abort("cannot read MemAvailable from /proc/meminfo")


def blob_digest(modelfile):
    m = re.search(r"^FROM\s+\S*sha256-([0-9a-f]{64})\s*$", modelfile, re.M)
    return f"sha256:{m.group(1)}" if m else None


class Cli:
    def __init__(self, runner=run, catalog=None, mem=mem_available_mb, ask=input, interactive=None, out=None):
        self.runner, self._catalog, self.mem, self.ask = runner, catalog, mem, ask
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.out = out or sys.stdout

    def say(self, text=""):
        print(text, file=self.out)

    def catalog(self):
        if self._catalog is None:
            self._catalog = load_catalog()
        return self._catalog

    def sh(self, argv, check=True):
        rc, out = self.runner(argv)
        if check and rc != 0:
            raise Abort(f"{' '.join(argv)} failed (exit {rc})")
        return rc, out

    def priv(self, argv):
        return argv if os.geteuid() == 0 else ["sudo", *argv]

    def installed(self):
        return self.runner(["pacman", "-Q", "ollama"])[0] == 0

    def enabled(self):
        return self.runner(["systemctl", "is-enabled", UNIT])[1].strip() == "enabled"

    def listening(self):
        rc, out = self.runner(["ss", "-H", "-ltn", f"sport = :{PORT}"])
        return rc == 0 and bool(out.strip())

    def confirm(self, question, yes):
        if yes:
            return True
        if not self.interactive:
            return False
        return self.ask(f"{question} [y/N] ").strip().lower() in ("y", "yes")

    def models(self):
        rc, out = self.runner(["ollama", "list"])
        if rc != 0:
            return []
        return [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip()]

    # commands

    def status(self, args):
        on, up = self.enabled(), self.listening()
        if getattr(args, "json", False):
            names = self.models() if up else []
            self.say(
                json.dumps(
                    {"enabled": on, "installed": self.installed(), "listening": up, "models": names}
                )
            )
            return 0
        self.say(f"AI runtime: {'enabled' if on else 'disabled'}")
        self.say(f"ollama package: {'installed' if self.installed() else 'not installed'}")
        self.say(f"listener on 127.0.0.1:{PORT}: {'yes' if up else 'no'}")
        if up:
            names = self.models()
            self.say("models: " + (", ".join(names) if names else "none"))
        else:
            self.say("models: runtime not running")
        return 0

    def enable(self, args):
        if not self.installed():
            if not self.confirm(
                "ollama is not installed. Install it from the official Arch repository "
                "(about 15 MiB download, 61 MiB installed; needs network)?",
                args.yes,
            ):
                raise Abort("ollama is not installed and installing was not confirmed")
            self.sh(self.priv(["pacman", "-S", "--needed", "--noconfirm", "ollama"]))
        self.sh(self.priv(["systemctl", "enable", "--now", UNIT]))
        self.say(f"AI runtime enabled (listens on 127.0.0.1:{PORT} only). No model yet: seclegion-ai pull")
        return 0

    def disable(self, args):
        self.sh(self.priv(["systemctl", "disable", "--now", UNIT]))
        self.say("AI runtime disabled; models stay on disk.")
        return 0

    def list(self, args):
        if not self.listening():
            raise Abort("the AI runtime is not running (seclegion-ai enable)")
        for n in self.models():
            self.say(n)
        return 0

    def remove(self, args):
        if not self.listening():
            raise Abort("the AI runtime is not running (seclegion-ai enable)")
        self.sh(["ollama", "rm", args.name])
        self.say(f"removed {args.name}")
        return 0

    def pull(self, args):
        name = args.name
        if is_cloud(name):
            raise Abort(f"refused: {name} is a cloud-backed model (prompts would leave this machine)")
        entry = find_model(self.catalog(), name)
        if entry is None and not args.allow_uncatalogued:
            raise Abort(
                f"refused: {name} is not in the catalog (--allow-uncatalogued overrides; "
                "its contents cannot be verified)"
            )
        if entry is not None and is_cloud(entry["tag"]):
            raise Abort(f"refused: {name} is cloud-backed")
        self.consent(name, entry, args.yes)
        if entry is not None:
            have = self.mem()
            if entry["ram_mb"] > have:
                raise Abort(
                    f"refused: {entry['name']} needs about {entry['ram_mb']} MiB of RAM but only "
                    f"{have} MiB is available"
                )
        if not self.listening():
            raise Abort("the AI runtime is not running (seclegion-ai enable)")
        tag = entry["tag"] if entry else name
        self.sh(["ollama", "pull", tag])
        if entry is None:
            self.say(f"pulled {tag} (uncatalogued: digest not verified)")
            return 0
        _, modelfile = self.sh(["ollama", "show", tag, "--modelfile"])
        got = blob_digest(modelfile)
        if got != entry["digest"]:
            self.runner(["ollama", "rm", tag])
            raise Abort(f"digest mismatch for {tag}: expected {entry['digest']}, got {got}; model removed")
        self.say(f"pulled {tag}, digest verified ({got})")
        return 0

    def consent(self, name, entry, yes):
        if yes:
            return
        if not self.interactive:
            raise Abort(f"refused: pulling {name} needs consent: re-run with --yes, or run it in a terminal")
        if entry:
            self.say(f"{entry['name']}: about {entry['size_mb']} MiB download, licence {entry['licence']}.")
        self.say("The download comes from the ollama registry over the network.")
        if self.ask(f"Type the model name ({name}) to confirm: ").strip() != name:
            raise Abort("refused: confirmation did not match")


def main(argv=None, **kw):
    ap = argparse.ArgumentParser(prog="seclegion-ai", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("disable", "list"):
        sub.add_parser(c)
    sub.add_parser("status").add_argument("--json", action="store_true", help="machine-readable state")
    sub.add_parser("enable").add_argument("--yes", action="store_true", help="confirm installing ollama")
    p = sub.add_parser("pull")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true", help="consent to the download")
    p.add_argument("--allow-uncatalogued", action="store_true")
    sub.add_parser("remove").add_argument("name")
    args = ap.parse_args(argv)
    cli = Cli(**kw)
    try:
        return getattr(cli, args.cmd)(args)
    except Abort as e:
        print(f"seclegion-ai: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
