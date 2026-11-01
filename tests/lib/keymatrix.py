# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The key matrix: every bind the installed system ships, as QMP key sequences, with an oracle each.

Static half of plan item W1 (G51). No VM runs here. The VM half sends `Entry.chords` with
`send_entry()` to a logged-in Hyprland guest and checks `Entry.oracle` there.

Source of truth. The binds are the ones the installed system ships: desktop/hypr/seclegion-keys.lua
(installed to /usr/share/seclegion/hypr) and the skel hyprland.lua. They are read with the parser of
tools/seclegion-keys-lint (its tokenizer and evaluator, loaded from the tool file), the same one the bind
lints use. The only addition is `_Eval`, which also keeps the tokens of each bind's action so the
oracle can tell an exec from a workspace dispatch; there is no second key parser.

QMP sends physical keys (qcodes). The guest's xkb layout maps them to keysyms, so what a bind needs
depends on how Hyprland resolves it (spike S8, docs/spec/v1/s8-s9.md: the key is taken from the Lua
source, never from `hyprctl binds -j`, which reports key "" and keycode 0 for Lua binds):
  - `code:N` binds are physical: the same qcodes on us and ara (xkb keycode N = evdev N-8).
  - keysym binds are resolved to a physical key through a layout. Hyprland's default
    (`resolve_binds_by_sym = false`, which the shipped config does not change) resolves them through the
    first layout of kb_layout = "us,ara", so they are the same physical keys on ara. With
    `resolve_binds_by_sym=True` the active layout is used and a Latin keysym is not on ara at all: such an
    entry is kept in the matrix with reachable=False and a reason (reported, never dropped).
  That default is an assumption the VM half confirms (press the key under ara, check the oracle).

QMP limits. The QMP typer in tests/lib/qmp.py cannot type `%` (no qcode path to it); that is why binds are
sent as qcodes here and never as typed text. Modifiers go in the same send-key as the key (pressed
together, released together).

A bind with no oracle class, a key that is on no layout table, a duplicate bind, or a submap bind with no way
into the submap is an error (KeyMatrixError naming each bind), not a skip.
"""
import dataclasses
import importlib.machinery
import importlib.util
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
LINT = ROOT / "tools/seclegion-keys-lint"
KEYS_LUA = ROOT / "desktop/hypr/seclegion-keys.lua"
SKEL_LUA = ROOT / "pkgs/seclegion-dotfiles/skel/.config/hypr/hyprland.lua"
SHIPPED = (KEYS_LUA, SKEL_LUA)
LAYOUTS = ("us", "ara")   # kb_layout = "us,ara"; us is the first layout

# Modifier -> QEMU qcode (the canonical names tools/seclegion-keys-lint folds aliases to).
MOD_ORDER = ("SUPER", "CTRL", "ALT", "SHIFT")
MOD_QCODES = {"SUPER": "meta_l", "CTRL": "ctrl", "ALT": "alt", "SHIFT": "shift"}

# xkb keycode (evdev + 8) -> QEMU qcode, for every physical key a bind can use.
XKB_QCODES = {9: "esc", 20: "minus", 21: "equal", 22: "backspace", 23: "tab", 34: "bracket_left",
              35: "bracket_right", 36: "ret", 47: "semicolon", 48: "apostrophe", 49: "grave_accent",
              51: "backslash", 59: "comma", 60: "dot", 61: "slash", 65: "spc", 95: "f11", 96: "f12",
              107: "print", 110: "home", 111: "up", 112: "pgup", 113: "left", 114: "right", 115: "end",
              116: "down", 117: "pgdn", 118: "insert", 119: "delete"}
XKB_QCODES.update({10 + i: d for i, d in enumerate("1234567890")})
XKB_QCODES.update({24 + i: c for i, c in enumerate("qwertyuiop")})
XKB_QCODES.update({38 + i: c for i, c in enumerate("asdfghjkl")})
XKB_QCODES.update({52 + i: c for i, c in enumerate("zxcvbnm")})
XKB_QCODES.update({67 + i: f"f{1 + i}" for i in range(10)})

# keysym (lower case) -> xkb keycode, per layout. Function and navigation keys sit on the same physical
# key under every layout. The ara table holds only what tools/seclegion-keys-lint knows about ara (its
# KEYCODES table): the Arabic-Indic digits on the number row and zain on the period key.
_COMMON = {"escape": 9, "tab": 23, "backspace": 22, "return": 36, "space": 65, "print": 107, "home": 110,
           "up": 111, "prior": 112, "left": 113, "right": 114, "end": 115, "down": 116, "next": 117,
           "insert": 118, "delete": 119}
_COMMON.update({f"f{1 + i}": 67 + i for i in range(10)} | {"f11": 95, "f12": 96})
LAYOUT_KEYSYMS = {
    "us": _COMMON | {c: 24 + i for i, c in enumerate("qwertyuiop")}
    | {c: 38 + i for i, c in enumerate("asdfghjkl")} | {c: 52 + i for i, c in enumerate("zxcvbnm")}
    | {d: 10 + i for i, d in enumerate("1234567890")}
    | {"minus": 20, "equal": 21, "bracketleft": 34, "bracketright": 35, "semicolon": 47, "apostrophe": 48,
       "grave": 49, "backslash": 51, "comma": 59, "period": 60, "slash": 61},
    "ara": _COMMON | {f"arabic_{d}": 10 + i for i, d in enumerate("1234567890")}
    | {"arabic_zain": 60, "period": 60},
}

# Hardware keys: the same physical key on every layout, but QEMU has no qcode for them (QMP send-key
# cannot press them), keysym (lower case) -> xkb keycode. Their entries are unreachable with a reason;
# each must run the same action as a reachable bind (tests/desktop/test_m7_keymatrix.py), which the VM
# half presses instead.
HW_KEYS = {"xf86display": 235}   # KEY_SWITCHVIDEOMODE (Fn+F7 on many laptops)


class KeyMatrixError(Exception):
    """Every problem found, one per line, each naming its bind."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


class _NoOracle(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Oracle:
    """The observable effect the VM half checks after sending a bind."""
    kind: str       # the effect class, one of the ORACLES values below
    expect: tuple   # ((name, value), ...) the expected effect
    probe: str      # how to observe it in the guest
    needs: str      # the state to set up first: "none", "window" or "floating-window"


@dataclasses.dataclass(frozen=True)
class Entry:
    layout: str
    id: str                 # "SUPER+ALT+code:10", prefixed "<submap>:" inside a submap; unique per layout
    description: str
    source: str             # file name and line of the bind
    submap: str
    mods: tuple
    key: str
    chords: tuple           # the send-key calls in order, ((qcode, ...), ...); a submap bind is preceded
                            # by the chord that enters its submap
    leave: tuple            # chords sent after it to leave the submap again, () when none is needed
    oracle: Oracle
    reachable: bool
    reason: str             # why not, when reachable is False


@dataclasses.dataclass(frozen=True)
class Bind:
    mods: tuple
    key: str
    submap: str
    description: str
    where: str
    dispatcher: str   # "exec_cmd", "focus", "window.move", "function:winsize", ...
    args: tuple       # ((name, value), ...); a lone string argument is ("arg", value)
    norm: tuple       # the lint's (mods, keycodes, submap): what it compares binds by


class Matrix:
    def __init__(self, entries):
        self.entries = tuple(entries)

    def layout(self, layout):
        return [e for e in self.entries if e.layout == layout]

    def unreachable(self, layout=None):
        return [e for e in self.entries if not e.reachable and layout in (None, e.layout)]

    def ids(self, layout):
        return [e.id for e in self.layout(layout)]


_lint = None


def lint():
    """tools/seclegion-keys-lint loaded as a module (it has no .py name)."""
    global _lint
    if _lint is None:
        loader = importlib.machinery.SourceFileLoader("seclegion_keys_lint", str(LINT))
        _lint = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(_lint)
    return _lint


def _make_eval():
    class _Eval(lint().Eval):
        """The lint's evaluator, also keeping the action tokens of each hl.bind call."""

        def __init__(self, toks, path):
            super().__init__(toks, path)
            self.actions = []

        def bind(self, i, line):
            j = super().bind(i, line)
            depth, k = 1, i + 4   # i+3 is the "(" of hl.bind(
            start = None
            while k < len(self.t) and depth:
                kind, val, _ = self.t[k]
                if kind == "op" and val in ("(", "{", "["):
                    depth += 1
                elif kind == "op" and val in (")", "}", "]"):
                    depth -= 1
                elif kind == "op" and val == "," and depth == 1:
                    if start is None:
                        start = k + 1
                    else:
                        break
                k += 1
            end = k if depth else k - 1
            self.actions.append(self.t[start:end] if start is not None else [])
            return j
    return _Eval


def _action(tokens):
    """(dispatcher, args) from the second hl.bind argument, e.g. hl.dsp.window.move({ workspace = 11 })."""
    vals = [v if k in ("name", "op") else None for k, v, _ in tokens]
    if vals[:1] == ["function"]:
        for n, (kind, val, _) in enumerate(tokens):
            if kind == "name" and val == "winsize" and vals[n + 1:n + 2] == ["("]:
                if tokens[n + 2][0] == "num" and isinstance(tokens[n + 2][1], int):
                    return "function:winsize", (("pct", tokens[n + 2][1]),)
        return "function", ()
    if vals[:4] != ["hl", ".", "dsp", "."]:
        return "unknown", ()
    n, name = 4, []
    while n < len(tokens) and vals[n] != "(":
        if vals[n] != ".":
            name.append(str(tokens[n][1]))
        n += 1
    body = tokens[n + 1:]
    if body and body[0][0] == "str":
        return ".".join(name), (("arg", body[0][1]),)
    args = []
    for m, (kind, val, _) in enumerate(body[:-2]):
        if kind == "name" and body[m + 1][:2] == ("op", "="):
            neg = body[m + 2][:2] == ("op", "-")
            vk, vv, _ = body[m + 2 + neg]
            if vk == "num":
                args.append((val, -vv if neg else vv))
            elif vk == "str":
                args.append((val, vv))
            elif vk == "name" and vv in ("true", "false"):
                args.append((val, vv == "true"))
    return ".".join(name), tuple(args)


def parse_binds(text, name):
    """Every hl.bind of one Lua source, through the lint's parser."""
    ev = _make_eval()(lint().tokenize(text, name), name)
    ev.run(0, len(ev.t))
    out = []
    for (norm, raw, line, desc), tokens in zip(ev.binds, ev.actions, strict=True):
        mods = tuple(sorted(norm[0], key=MOD_ORDER.index))
        key = [p.strip() for p in raw.split("+")][-1] or "plus"
        dispatcher, args = _action(tokens)
        out.append(Bind(mods, key, norm[2], desc, f"{name}:{line}", dispatcher, args, norm))
    return out


def shipped_binds(paths=SHIPPED):
    out = []
    for p in paths:
        p = pathlib.Path(p)
        out += parse_binds(p.read_text(encoding="utf-8"), p.name)
    return out


# ---- the oracle table: one line per bind class (keyed by dispatcher) -----------------------------------

def _o(kind, probe, needs="none", **expect):
    return Oracle(kind, tuple(expect.items()), probe, needs)


def _exec(a):
    cmd = a.get("arg")
    if not isinstance(cmd, str) or not cmd.strip():
        raise _NoOracle("exec_cmd without a literal command")
    return _o("exec-process", "a process whose command line contains the command appears (pgrep -f)",
              command=cmd, argv0=cmd.split()[0].rsplit("/", 1)[-1])


def _focus(a):
    ws = a.get("workspace")
    if isinstance(ws, int):
        return _o("workspace-active", "hyprctl activeworkspace -j: .id", id=ws)
    if ws == "empty":
        return _o("workspace-empty", "hyprctl activeworkspace -j: .windows == 0 and .id changed", windows=0)
    if ws in ("e-1", "e+1"):
        return _o("workspace-relative", "hyprctl activeworkspace -j: .id moved to the neighbour",
                  delta=int(ws[1:]))
    raise _NoOracle(f"focus workspace {ws!r}")


def _move(a):
    ws = a.get("workspace")
    if not (isinstance(ws, int) or ws == "empty"):
        raise _NoOracle(f"window.move workspace {ws!r}")
    return _o("window-workspace", "hyprctl clients -j: the window's .workspace.id; activeworkspace follows "
              "only when follow is true", "window", target=ws, follow=a.get("follow", True))


def _submap(a):
    name = a.get("arg")
    if name == "reset":
        return _o("submap-reset", "hyprctl submap: empty", submap="")
    if isinstance(name, str) and name:
        return _o("submap-enter", "hyprctl submap: the submap name", submap=name)
    raise _NoOracle("submap without a literal name")


def _resize(a):
    if a.get("relative") is True and "x" in a and "y" in a:
        return _o("window-resize-relative", "hyprctl activewindow -j: .size changed by (x, y)",
                  "floating-window", dx=a["x"], dy=a["y"])
    raise _NoOracle("absolute window.resize")


def _center(a):
    return _o("window-centered", "hyprctl activewindow -j: .at and .size centre on the monitor",
              "floating-window")


def _float(a):
    if a.get("action") == "toggle":
        return _o("float-toggled", "hyprctl activewindow -j: .floating flipped", "window")
    raise _NoOracle(f"window.float action {a.get('action')!r}")


def _winsize(a):
    return _o("window-size-percent", "hyprctl activewindow -j: .floating, .size = pct % of the monitor "
              "(hyprctl monitors -j), centred", "window", pct=a["pct"])


ORACLES = {
    "exec_cmd": _exec,
    "focus": _focus,
    "window.move": _move,
    "submap": _submap,
    "window.resize": _resize,
    "window.center": _center,
    "window.float": _float,
    "function:winsize": _winsize,
}


def oracle_for(bind):
    """The Oracle of one bind; raises _NoOracle when its class has no entry."""
    make = ORACLES.get(bind.dispatcher)
    if make is None:
        raise _NoOracle(f"no oracle class for {bind.dispatcher}")
    return make(dict(bind.args))


# ---- the matrix ----------------------------------------------------------------------------------------

def bind_id(bind):
    return (f"{bind.submap}:" if bind.submap else "") + "+".join([*bind.mods, bind.key])


def physical(key, layout, resolve_binds_by_sym=False):
    """(xkb keycode, "") for the physical key of a bind key, or (None, why not) when it is not reachable.
    Raises KeyError when the key is on no layout table at all."""
    k = key.lower()
    if k.startswith("code:"):
        code = int(k[5:])
        if code not in XKB_QCODES:
            raise KeyError(key)
        return code, ""
    if k in HW_KEYS:
        return None, f"hardware key {key} (xkb {HW_KEYS[k]}): QEMU has no qcode for it"
    if not any(k in t for t in LAYOUT_KEYSYMS.values()):
        raise KeyError(key)
    resolver = layout if resolve_binds_by_sym else LAYOUTS[0]
    if k in LAYOUT_KEYSYMS[resolver]:
        return LAYOUT_KEYSYMS[resolver][k], ""
    return None, f"keysym {key} is not on the {resolver} layout (resolved through {resolver})"


def _chord(bind, code):
    return (*(MOD_QCODES[m] for m in bind.mods), XKB_QCODES[code])


def build(binds, layouts=LAYOUTS, resolve_binds_by_sym=False):
    """The Matrix of `binds` for `layouts`; KeyMatrixError lists every bind that cannot be placed."""
    problems, oracles, unknown = [], {}, set()
    for n, b in enumerate(binds):
        who = f"{b.where} {bind_id(b)} ({b.description})"
        twice = next((a.where for a in binds[:n] if lint().clash(a.norm, b.norm)), None)
        if twice:
            problems.append(f"{who}: bound twice (also {twice})")
        for m in b.mods:
            if m not in MOD_QCODES:
                problems.append(f"{who}: modifier {m} has no qcode")
        try:
            oracles[bind_id(b)] = oracle_for(b)
        except _NoOracle as e:
            problems.append(f"{who}: no oracle ({e})")
        try:
            physical(b.key, layouts[0])
        except KeyError:
            unknown.add(bind_id(b))
            problems.append(f"{who}: unknown key {b.key!r} (on no layout table)")
    binds = [b for b in binds if bind_id(b) not in unknown]
    entering = {dict(b.args)["arg"]: b for b in binds if _enters(b)}
    leaving = {b.submap: b for b in binds if b.submap and _is_reset(b)}
    entries = []
    for layout in layouts:
        phys = {bind_id(b): physical(b.key, layout, resolve_binds_by_sym) for b in binds}
        for b in binds:
            why = phys[bind_id(b)][1]
            chords, tail = [], ()
            if b.submap:
                eb = entering.get(b.submap)
                if eb is None:
                    problems.append(f"{b.where} {bind_id(b)} ({b.description}): no bind enters submap "
                                    f"{b.submap!r}")
                    continue
                chords.append(_chord(eb, phys))
                why = why or ("" if _chord(eb, phys) else f"the bind that enters submap {b.submap!r} is "
                              f"unreachable: {phys[bind_id(eb)][1]}")
            chords.append(_chord(b, phys))
            sub = b.submap or (dict(b.args)["arg"] if _enters(b) else "")
            if sub and not _is_reset(b):   # the bind leaves us inside a submap: add the way out
                lb = leaving.get(sub)
                if lb is None:
                    problems.append(f"{b.where} {bind_id(b)} ({b.description}): no bind leaves submap "
                                    f"{sub!r}")
                    continue
                tail = (_chord(lb, phys),)
                why = why or ("" if tail[0] else f"the bind that leaves submap {sub!r} is unreachable")
            entries.append(Entry(layout, bind_id(b), b.description, b.where, b.submap, b.mods, b.key,
                                 tuple(c for c in chords if c), tuple(c for c in tail if c),
                                 oracles.get(bind_id(b)), not why, why))
    if problems:
        raise KeyMatrixError(problems)
    return Matrix(entries)


def _chord(b, phys):
    """The send-key qcodes of one bind (modifiers first), None when its key is unreachable."""
    code = phys[bind_id(b)][0]
    if code is None:
        return None
    return (*(MOD_QCODES[m] for m in b.mods if m in MOD_QCODES), XKB_QCODES[code])


def _is_reset(b):
    return b.dispatcher == "submap" and dict(b.args).get("arg") == "reset"


def _enters(b):
    return b.dispatcher == "submap" and not b.submap and not _is_reset(b) and "arg" in dict(b.args)


def shipped_matrix(resolve_binds_by_sym=False):
    return build(shipped_binds(), LAYOUTS, resolve_binds_by_sym)


def send_entry(qmp, entry, pause=0.3, sleep=time.sleep):
    """Send an entry over QMP: one send-key per chord, then the chords that leave a submap."""
    if not entry.reachable:
        raise ValueError(f"{entry.id} is unreachable on {entry.layout}: {entry.reason}")
    for chord in (*entry.chords, *entry.leave):
        qmp.send_key(*chord)
        sleep(pause)
