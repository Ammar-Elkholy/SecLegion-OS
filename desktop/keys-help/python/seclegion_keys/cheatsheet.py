# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-keys: keybinding cheat sheet.

Sources: the repo's Lua bind files (parsed statically, never executed) and, when a
Hyprland instance runs, `hyprctl binds -j` (the only hyprctl call this module makes;
it never dispatches, sets keywords or reloads). Display only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

INSTALLED_KEYS = "/usr/share/seclegion/hypr/seclegion-keys.lua"
PREFIX = "seclegion-keys: "
KEYCODES = {"code:60": "."}
KEYCODES.update({f"code:{10 + i}": d for i, d in enumerate("1234567890")})
MODBITS = ((1, "SHIFT"), (4, "CTRL"), (8, "ALT"), (64, "SUPER"))
MODALIAS = {"CONTROL": "CTRL", "MOD4": "SUPER", "WIN": "SUPER", "MOD1": "ALT"}
DESC_RE = re.compile(r"description\s*=\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')")


def _scan_string(s, i):
    """s[i] is a quote; return the index after the closing quote."""
    q = s[i]
    i += 1
    while i < len(s) and s[i] != q:
        i += 2 if s[i] == "\\" else 1
    return i + 1


def _split_call(s, start):
    """s[start] is '('; return (top-level argument strings, index after ')')."""
    depth, args, cur, i = 0, [], start + 1, start + 1
    while i < len(s):
        c = s[i]
        if c in "\"'":
            i = _scan_string(s, i)
            continue
        if s.startswith("--", i):
            nl = s.find("\n", i)
            i = len(s) if nl < 0 else nl
            continue
        if c in "({[":
            depth += 1
        elif c in ")}]":
            if depth == 0:
                args.append(s[cur:i].strip())
                return args, i + 1
            depth -= 1
        elif c == "," and depth == 0:
            args.append(s[cur:i].strip())
            cur = i + 1
        i += 1
    return args, len(s)


def _literal(expr):
    expr = expr.strip()
    if len(expr) >= 2 and expr[0] in "\"'" and _scan_string(expr, 0) == len(expr):
        return expr[1:-1]
    return None


def _split_keys(keys):
    parts = [p.strip() for p in keys.split("+")]
    return {MODALIAS.get(p.upper(), p.upper()) for p in parts[:-1] if p}, parts[-1]


def _sig(mods, key, submap):
    key = key.lower()
    return frozenset(mods), KEYCODES.get(key, key).lower(), submap


def human_keys(mods, key):
    k = KEYCODES.get(key.lower(), key)
    if len(k) == 1:
        k = k.upper()
    order = [m for m in ("SUPER", "CTRL", "ALT", "SHIFT") if m in mods]
    return " + ".join(order + sorted(set(mods) - set(order)) + [k])


def _category(dispatcher, desc, submap):
    if submap:
        return "Resize mode" if submap == "resize" else "Submap: " + submap
    d = (dispatcher + " " + desc).lower()
    if "exec" in dispatcher:
        return "Launch"
    if "workspace" in d or "focus" in d:
        return "Workspaces"
    if "window" in d or "resize" in d or "float" in d:
        return "Windows"
    return "Other"


def command_available(cmd):
    """The first word of an exec command resolves to an executable (PATH, or a path)."""
    words = cmd.split()
    if not words:
        return False
    tok = os.path.expanduser(words[0])
    if "/" in tok:
        return os.path.isfile(tok) and os.access(tok, os.X_OK)
    return shutil.which(tok) is not None


def _entry(mods, key, dispatcher, command, desc, submap, available, source):
    if desc.startswith(PREFIX):
        desc = desc[len(PREFIX):]
    return {
        "keys": human_keys(mods, key),
        "dispatcher": dispatcher,
        "command": command,
        "description": desc,
        "category": _category(dispatcher, desc, submap),
        "available": bool(available),
        "source": source,
        "submap": submap,
        "_sig": _sig(mods, key, submap),
    }


def parse_lua(text):
    """Static parse of hl.bind(...) calls, including those inside hl.define_submap(name, ...)."""
    out, submaps, i = [], [], 0
    pat = re.compile(r"hl\.(bind|define_submap)\(")
    while True:
        m = pat.search(text, i)
        if not m:
            break
        args, end = _split_call(text, m.end() - 1)
        if m.group(1) == "define_submap":
            name = _literal(args[0]) if args else None
            if name:
                submaps.append((name, end))
            i = m.end()
            continue
        i = end
        submaps = [s for s in submaps if s[1] > m.start()]
        keys = _literal(args[0]) if args else None
        if keys is None or len(args) < 2:
            continue
        mods, key = _split_keys(keys)
        action = args[1]
        dm = DESC_RE.search(args[2]) if len(args) > 2 else None
        desc = dm.group(1)[1:-1] if dm else ""
        if action.startswith("function"):
            disp, cmd, avail = "lua function", "", True
        else:
            disp = action.split("(")[0].replace("hl.dsp.", "")
            cmd = action[action.find("(") + 1:action.rfind(")")].strip() if "(" in action else ""
            avail = True
            if disp == "exec_cmd":
                lit = _literal(cmd)
                if lit is not None:
                    cmd, avail = lit, command_available(lit)
        out.append(_entry(mods, key, disp, cmd, desc, submaps[-1][0] if submaps else "", avail, "static"))
    return out


def parse_files(paths):
    res = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                res += parse_lua(f.read())
        except OSError:
            pass
    return res


def default_bind_files():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.join(here, "..", "..", "..", "hypr", "seclegion-keys.lua")
    return [p for p in (INSTALLED_KEYS, repo) if os.path.isfile(p)][:1]


def runtime_binds():
    """Read `hyprctl binds -j` (read only). [] when there is no running instance."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or not shutil.which("hyprctl"):
        return []
    try:
        r = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, timeout=5, check=True)
        data = json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return data if isinstance(data, list) else []


def runtime_entry(b):
    mm = int(b.get("modmask", 0) or 0)
    mods = {n for bit, n in MODBITS if mm & bit}
    key = b.get("key") or ("code:{}".format(b["keycode"]) if b.get("keycode") else "")
    disp, cmd = b.get("dispatcher", ""), b.get("arg", "")
    avail = command_available(cmd) if disp == "exec" else True
    return _entry(mods, key, disp, cmd, b.get("description", ""), b.get("submap", ""), avail, "runtime")


def merge(static, runtime):
    res, seen = list(static), {e["_sig"] for e in static}
    # Lua binds come back from `binds -j` with key "" and keycode 0 (spike S8), so a runtime copy of a
    # static bind is matched by its description and submap instead of its key.
    by_desc = {(e["description"], e["submap"]) for e in static if e["description"]}
    for b in runtime:
        e = runtime_entry(b)
        if not b.get("key") and not b.get("keycode") and (e["description"], e["submap"]) in by_desc:
            continue
        if e["_sig"] not in seen:
            seen.add(e["_sig"])
            res.append(e)
    return res


def public(binds):
    return [{k: v for k, v in b.items() if k != "_sig"} for b in binds]


def collect(files=None, use_runtime=True):
    static = parse_files(files if files is not None else default_bind_files())
    return public(merge(static, runtime_binds() if use_runtime else []))


def format_lines(binds):
    w = max([len(b["keys"]) for b in binds] or [0])
    return [f'{b["keys"]:<{w}}  {b["description"] or b["command"] or b["dispatcher"]}'
            f'{"" if b["available"] else "  (unavailable)"}  [{b["category"]}]' for b in binds]


def show(lines):
    """Searchable list through rofi (the launcher the desktop uses); stdout otherwise. Display only."""
    has_display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")
    if shutil.which("rofi") and has_display and not sys.stdout.isatty():
        subprocess.run(["rofi", "-dmenu", "-i", "-p", "keys", "-no-custom"],
                       input="\n".join(lines), text=True, stdout=subprocess.DEVNULL)
    else:
        print("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="seclegion-keys", description="SecLegion keybinding cheat sheet")
    ap.add_argument("--json", action="store_true", help="print every bind as JSON")
    ap.add_argument("--list", action="store_true", help="plain text to stdout (no launcher)")
    ap.add_argument("--file", action="append", help="Lua bind file (default: the installed one)")
    args = ap.parse_args(argv)
    binds = collect(args.file)
    if args.json:
        print(json.dumps(binds, indent=2))
    elif args.list:
        print("\n".join(format_lines(binds)))
    else:
        show(format_lines(binds))
    return 0
