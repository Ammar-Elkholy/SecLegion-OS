# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer theme: libadwaita colour overrides and step classes, all from desktop/theme/tokens.toml."""

import os
import pathlib
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLED_TOKENS = "/usr/share/seclegion/installer/tokens.toml"
REPO_TOKENS = os.path.join(HERE, "..", "..", "..", "desktop", "theme", "tokens.toml")


def tokens_path():
    return INSTALLED_TOKENS if os.path.exists(INSTALLED_TOKENS) else os.path.normpath(REPO_TOKENS)


def load_css(path=None):
    c = tomllib.loads(pathlib.Path(path or tokens_path()).read_text())["colors"]
    defs = {
        "accent_bg_color": c["accent"], "accent_color": c["accent"], "accent_fg_color": c["bg"],
        "window_bg_color": c["bg"], "window_fg_color": c["text"], "view_bg_color": c["surface"],
        "card_bg_color": c["surface"], "headerbar_bg_color": c["surface"],
        "sidebar_bg_color": c["surface"], "error_color": c["err"], "success_color": c["ok"],
        "warning_color": c["warn"],
    }
    css = "".join(f"@define-color {k} {v};\n" for k, v in defs.items())
    # libadwaita 1.x reads :root variables; @define-color alone leaves its own defaults in place
    css += ":root {\n" + "".join(f"  --{k.replace('_', '-')}: {v};\n" for k, v in defs.items()) + "}\n"
    css += f"window.background {{ background-color: {c['bg']}; color: {c['text']}; }}\n"
    css += f"headerbar {{ background-color: {c['surface']}; color: {c['text']}; }}\n"
    css += f"button.suggested-action {{ background-color: {c['accent']}; color: {c['bg']}; }}\n"
    css += f".step-done {{ color: {c['ok']}; }}\n"
    css += f".step-current {{ color: {c['accent']}; font-weight: bold; }}\n"
    css += f".step-todo {{ color: {c['muted']}; }}\n"
    css += f".sidebar-title {{ color: {c['text']}; font-weight: bold; font-size: 120%; }}\n"
    return css
