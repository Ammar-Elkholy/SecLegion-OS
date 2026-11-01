# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-theme command line."""

from __future__ import annotations

import argparse
import json
import sys

from . import auto, engine, manager, store
from .palette import ThemeError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seclegion-theme", description="SecLegion dynamic theming")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="derive a theme and apply it live")
    a.add_argument("--wallpaper", metavar="IMG")
    a.add_argument(
        "--theme", metavar="ID", help="a theme from `list` (not with --wallpaper, --mode or --accent)"
    )
    a.add_argument("--mode", choices=engine.MODES)
    a.add_argument("--accent", metavar="#HEX", help="auto mode only; hue is held in the SecLegion family")
    a.add_argument(
        "--contrast", choices=engine.CONTRASTS, help="default normal; with --theme, the current contrast"
    )
    a.add_argument("--no-hooks", action="store_true", help="write files only, no live reload")
    a.add_argument("-v", "--verbose", action="store_true")
    ls = sub.add_parser("list", help="the themes `apply --theme` accepts")
    ls.add_argument("--json", action="store_true")
    c = sub.add_parser("current", help="show the active theme")
    c.add_argument("--json", action="store_true")
    r = sub.add_parser("reset", help="back to SecLegion Dark (static tokens)")
    r.add_argument("--no-hooks", action="store_true")
    r.add_argument("-v", "--verbose", action="store_true")
    au = sub.add_parser("auto", help="re-theme whenever the wallpaper changes (on|off|status)")
    au.add_argument("state", choices=("on", "off", "status"))
    sub.add_parser("sync", help="apply the theme for the current wallpaper if auto is on and it changed")
    e = sub.add_parser("export-default", help="write the static default files to DIR")
    e.add_argument("dir")
    return p


# C0, DEL and C1 controls: a path or message must not move the cursor, clear
# the screen or fake extra lines on the user's terminal.
_CONTROLS = dict.fromkeys([*range(0x20), *range(0x7F, 0xA0)])


def _clean(text) -> str:
    return str(text).translate(_CONTROLS)


def _report(res: engine.Result, verbose: bool) -> None:
    for w in res.warnings:
        print(f"seclegion-theme: warning: {_clean(w)}", file=sys.stderr)
    for h in res.hook_results:
        if h.status in (
            "failed",
            "timeout",
            "kept",
            "adopted",
            "ok-backed-up",
        ):  # kept: a hand-edited file left alone; the last two moved or saved a user file
            print(f"seclegion-theme: hook {h.name}: {h.status} ({_clean(h.detail)})", file=sys.stderr)
        elif verbose:
            print(f"seclegion-theme: hook {h.name}: {h.status} {_clean(h.detail)}".rstrip(), file=sys.stderr)
    print(
        f"seclegion-theme: applied {res.name} mode={res.mode} "
        f"total={res.ms_total:.0f}ms matugen={res.ms_matugen:.0f}ms hooks={res.ms_hooks:.0f}ms"
    )


def _current_line(cur: dict) -> str:
    """One summary line; tolerant of keys missing from an older/edited file."""

    def get(d, key):
        v = d.get(key) if isinstance(d, dict) else None
        return v if isinstance(v, str) and v else "-"

    return _clean(
        f"mode={get(cur, 'mode')} contrast={get(cur, 'contrast')} "
        f"wallpaper={get(cur.get('source'), 'wallpaper')} accent={get(cur.get('tokens'), 'accent')}"
    )


def _apply_args(args) -> dict:
    """engine.apply_theme keywords for `apply`; --theme resolves before anything is written."""
    kw = {
        "wallpaper": args.wallpaper,
        "mode": args.mode or "auto",
        "accent": args.accent,
        "contrast": args.contrast or "normal",
        "run_hooks": not args.no_hooks,
    }
    if args.theme is not None:
        if args.wallpaper or args.mode or args.accent:
            raise ThemeError("--theme cannot be combined with --wallpaper, --mode or --accent")
        kw.update(manager.resolve(args.theme))
        kw["contrast"] = args.contrast or manager.current_contrast()
    return kw


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Paths may hold undecodable bytes (surrogateescape); print them escaped, never crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    try:
        if args.cmd == "apply":
            res = engine.apply_theme(**_apply_args(args))
            _report(res, args.verbose)
        elif args.cmd == "list":
            themes = manager.list_themes()
            if args.json:
                print(json.dumps(themes, indent=2, sort_keys=True))
            else:
                for t in themes:
                    print(_clean(f"{'*' if t['current'] else ' '} {t['id']:<22} {t['accent']}  {t['label']}"))
        elif args.cmd == "reset":
            res = engine.apply_theme(mode="default", run_hooks=not args.no_hooks)
            _report(res, args.verbose)
        elif args.cmd == "current":
            cur = store.read_current(store.state_root())
            if cur is None:
                print("seclegion-theme: no theme applied yet", file=sys.stderr)
                return 1
            if args.json:
                print(json.dumps(cur, indent=2, sort_keys=True))
            else:
                print(_current_line(cur))
        elif args.cmd == "auto":
            if args.state == "status":
                print("on" if auto.is_on() else "off")
            else:
                auto.set_auto(args.state == "on")
                print(f"seclegion-theme: auto theme {args.state}")
        elif args.cmd == "sync":
            print(_clean(auto.sync()))
        elif args.cmd == "export-default":
            print(_clean(engine.export_default(args.dir)))
    except ThemeError as e:
        print(f"seclegion-theme: error: {_clean(e)}", file=sys.stderr)
        return 2
    return 0
