# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Welcome model: which buttons exist, what each runs, once-only state, vendor-fetch pending parsing.

Pure Python, no GTK: tests import this without a display. The view only renders `visible_buttons()`
and calls `launch()`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PENDING = Path("/var/lib/seclegion/vendor-fetch-pending")
DUAL_BOOT_DOC = "/usr/share/doc/seclegion/dual-boot.md"
CATALOG_DIR = "/usr/share/seclegion/catalog"
TERMINAL = "kitty"  # the terminal the desktop ships (iso/packages/desktop.list) and its other launchers use
FETCHERS = {"seclegion-vscode-fetch": "Visual Studio Code", "seclegion-brave-fetch": "Brave",
            "seclegion-claude-fetch": "Claude Code"}


@dataclass(frozen=True)
class Button:
    id: str
    label: str
    description: str
    argv: tuple[str, ...]  # the full command, terminal wrapper included
    vendor: str | None = None  # the fetcher name when this is a vendor-install button


def state_dir(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_STATE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".local/state")
    return Path(base) / "seclegion"


def done_path(env=None) -> Path:
    return state_dir(env) / "welcome.done"


def vendor_marker(fetcher: str, env=None) -> Path:
    return state_dir(env) / f"{fetcher}.done"


def should_autostart(env=None) -> bool:
    """Autostart shows the window only until the done marker exists."""
    return not done_path(env).exists()


def mark_done(env=None) -> None:
    p = done_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("done\n")


def parse_pending(text: str) -> list[str]:
    """Fetcher names listed in the pending file; unknown names are ignored (never run)."""
    return [w for w in text.split() if w in FETCHERS]


def read_pending(path: Path = PENDING) -> list[str]:
    try:
        return parse_pending(path.read_text())
    except OSError:
        return []


def in_terminal(title: str, *cmd: str) -> tuple[str, ...]:
    return (TERMINAL, "--title", title, *cmd)


def vendor_button(fetcher: str) -> Button:
    name = FETCHERS[fetcher]
    return Button(
        "install-" + fetcher.removeprefix("seclegion-").removesuffix("-fetch"),
        f"Install {name}",
        f"Downloads {name} on this machine and builds a package (asks for your sudo password).",
        in_terminal(f"Install {name}", "seclegion-welcome", "--fetch", fetcher),
        vendor=fetcher,
    )


STATIC_TOP = (
    Button("keys", "Keybindings", "The Super+F1 cheat sheet.", ("seclegion-keys",)),
    Button("settings", "Settings", "Power, display, sound, network and appearance.", ("seclegion-settings",)),
)
STATIC_BOTTOM = (
    Button(
        "updates",
        "Updates",
        "Update the system in a terminal.",
        in_terminal("SecLegion Update", "seclegion-update"),
    ),
    Button(
        "dual-boot",
        "Dual-boot guide",
        "How to install SecLegion next to another system.",
        in_terminal("Dual-boot guide", "less", DUAL_BOOT_DOC),
    ),
    Button(
        "tools",
        "Security tools",
        "List the security tools in the catalog.",
        in_terminal("Security tools", "seclegion-tools", "--catalog", CATALOG_DIR, "list"),
    ),
)


def all_buttons() -> list[Button]:
    return [*STATIC_TOP, *(vendor_button(f) for f in FETCHERS), *STATIC_BOTTOM]


def visible_buttons(pending: list[str], env=None) -> list[Button]:
    """Vendor buttons show only while the fetcher is pending and this user has no done marker."""
    out = list(STATIC_TOP)
    out += [vendor_button(f) for f in FETCHERS if f in pending and not vendor_marker(f, env).exists()]
    return out + list(STATIC_BOTTOM)


def launch(button: Button, popen=subprocess.Popen) -> None:
    """Start the button's command detached from the window."""
    popen(list(button.argv), start_new_session=True)


def run_fetch(fetcher: str, env=None, geteuid=os.geteuid, run=subprocess.call, out=sys.stdout) -> int:
    """Run inside the terminal: the fetcher as the user, then the per-user done marker on success.

    Refuses root: the fetchers run makepkg, which must not run as root, and they ask for sudo themselves.
    """
    if geteuid() == 0:
        print("seclegion-welcome: refusing to run a vendor fetcher as root; run it as your user.", file=out)
        return 1
    if fetcher not in FETCHERS:
        print(f"seclegion-welcome: unknown fetcher {fetcher}", file=out)
        return 2
    rc = run([fetcher])
    if rc == 0:
        m = vendor_marker(fetcher, env)
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("done\n")
    return rc
