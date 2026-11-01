# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-set: list | get | set | explain. No daemon; one short run per call.

Exit status: 0 ok, 1 unknown setting, 2 invalid value or usage, 3 refused (read-only or
privileged), 4 unavailable on this machine, 5 a command failed.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import registry
from .env import CommandFailed, Ctx, SettingError, WriteResult

_CONTROLS = dict.fromkeys([*range(0x20), *range(0x7F, 0xA0)])
_KEEP = {ord("\n"): "\n"}


def _clean(text) -> str:
    """Strip terminal control bytes from anything echoed (keeps newlines for multi-line text)."""
    return str(text).translate({k: v for k, v in _CONTROLS.items() if k not in _KEEP} | _KEEP)


def _line(text) -> str:
    return str(text).translate(_CONTROLS)


def _fmt(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _raw(value) -> str | None:
    """A current value as the text `set` would accept."""
    if value is None:
        return None
    return _fmt(value)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seclegion-set", description="SecLegion Settings from the shell")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="list settings and their current values")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--page", choices=registry.PAGES)
    g = sub.add_parser("get", help="print one value")
    g.add_argument("id")
    g.add_argument("--json", action="store_true")
    s = sub.add_parser("set", help="change a setting")
    s.add_argument("id")
    s.add_argument("value")
    s.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    s.add_argument("--json", action="store_true")
    e = sub.add_parser("explain", help="show what a setting reads, writes and runs")
    e.add_argument("id")
    e.add_argument("value", nargs="?")
    e.add_argument("--json", action="store_true")
    return p


def _list(ctx: Ctx, args) -> int:
    rows = registry.rows(ctx, args.page)
    if args.json:
        print(json.dumps([r.as_dict() for r in rows], indent=2, sort_keys=True))
        return 0
    page = None
    for r in rows:
        s = r.setting
        if s.page != page:
            page = s.page
            print(f"\n{registry.PAGE_LABELS[page]}")
        if not r.visible:
            tail = f"hidden: {r.reason}"
        else:
            numeric = isinstance(r.value, int) and not isinstance(r.value, bool)
            tail = _fmt(r.value) + (f" {s.unit}" if numeric and s.unit else "")
            if r.error:
                tail += f"  (unreadable: {r.error})"
            if s.privileged:
                tail += "  [needs root: asks for the password]"
        print(_line(f"  {s.id:<28} {s.label:<36} {tail}"))
    return 0


def _get(ctx: Ctx, args) -> int:
    s = registry.get(args.id)
    r = registry.row(s, ctx)
    if not r.visible:
        print(f"seclegion-set: {_line(s.id)}: {_line(r.reason)}", file=sys.stderr)
        return 4
    if r.error:
        print(f"seclegion-set: {_line(s.id)}: unreadable: {_line(r.error)}", file=sys.stderr)
        return 5
    print(json.dumps({"id": s.id, "value": r.value}) if args.json else _line(_fmt(r.value)))
    return 0


def _print_result(res: WriteResult, as_json: bool, setting_id: str) -> None:
    if as_json:
        print(json.dumps({"id": setting_id, **res.as_dict()}, indent=2, sort_keys=True))
        return
    verb = "would" if res.dry_run else "did"
    print(f"{setting_id}: {verb} {'apply live' if res.applied_live else 'not apply live'}")
    for f in res.files:
        print(_line(f"  file: {f}"))
        if res.dry_run and f in res.texts:
            print(_clean("    | " + res.texts[f].rstrip("\n").replace("\n", "\n    | ")))
    for c in res.commands:
        print(_line("  command: " + " ".join(c)))
    for n in res.notes:
        print(_line(f"  note: {n}"))


def _set(ctx: Ctx, args) -> int:
    s = registry.get(args.id)
    ctx.dry_run = args.dry_run
    res = registry.write(s, ctx, args.value)
    res.dry_run = ctx.dry_run
    _print_result(res, args.json, s.id)
    return 0


def _explain(ctx: Ctx, args) -> int:
    s = registry.get(args.id)
    r = registry.row(s, ctx)
    ctx.dry_run = True
    plan = None
    err = ""
    if r.visible:
        raw = args.value if args.value is not None else _raw(r.value)
        if s.readonly:
            err = "read-only"
        elif raw is None:
            err = "current value unreadable; give a value to preview"
        else:
            try:
                plan = registry.write(s, ctx, raw)
            except SettingError as e:
                err = str(e)
    info = {
        "id": s.id, "label": s.label, "page": s.page,
        "visible": r.visible, "reason": r.reason,
        "value": r.value, "read_error": r.error,
        "file": s.file, "command": s.command,
        "privileged": s.privileged,
        "applies_live": bool(plan.applied_live) if plan else False,
        "files": plan.files if plan else [],
        "commands": plan.commands if plan else [],
        "texts": plan.texts if plan else {},
        "preview_error": err,
        "description": s.description,
    }
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    out = [f"id: {s.id}", f"label: {s.label}"]
    if not r.visible:
        out.append(f"hidden: {r.reason}")
    out.append(f"current value: {_fmt(r.value)}" + (f" ({r.error})" if r.error else ""))
    out.append(f"file: {s.file or '-'}")
    out.append(f"command: {s.command or '-'}")
    priv = "yes (asks for the administrator password)" if s.privileged else "no"
    out.append(f"needs privilege: {priv}")
    out.append(f"applies live: {'yes' if info['applies_live'] else 'no'}")
    if err:
        out.append(f"preview: {err}")
    for f, t in info["texts"].items():
        out.append(f"text of {f}:")
        out.append("    | " + t.rstrip("\n").replace("\n", "\n    | "))
    for c in info["commands"]:
        out.append("would run: " + " ".join(c))
    print(_clean("\n".join(out)))
    return 0


def main(argv: list[str] | None = None, environ: dict | None = None) -> int:
    args = _parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    ctx = Ctx(environ)
    try:
        return {"list": _list, "get": _get, "set": _set, "explain": _explain}[args.cmd](ctx, args)
    except SettingError as e:
        print(f"seclegion-set: {_line(e)}", file=sys.stderr)
        return e.code
    except OSError as e:  # e.g. ~/.config/seclegion is a file, or the disk is full
        where = f" ({e.filename})" if e.filename else ""
        print(f"seclegion-set: command failed: {_line(e.strerror or e)}{where}", file=sys.stderr)
        return CommandFailed.code
