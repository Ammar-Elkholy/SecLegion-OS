# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""HiDPI for the install kiosk: scale the enabled output before the installer GUI starts.

cage runs kiosk/scale, which runs this and then execs the GUI. A 2560x1600 laptop panel draws the GTK
installer at 1x, so everything is tiny. This reads `wlr-randr --json`, picks the enabled output's current
mode width and sets `--scale` for it. It never fails: no wlr-randr, bad JSON or an error all exit 0, so the
kiosk always starts."""
import json
import subprocess
import sys

WLR_RANDR = "wlr-randr"


def scale_for(width):
    """Output scale for a panel `width` pixels wide; None keeps 1x."""
    if width >= 3840:
        return 2.0
    if width >= 2560:
        return 1.5
    return None


def pick_output(outputs):
    """(name, current mode width) of the first enabled output, or None."""
    for out in outputs:
        if not out.get("enabled", True):
            continue
        for mode in out.get("modes") or []:
            if mode.get("current"):
                return out["name"], int(mode["width"])
    return None


def main(run=subprocess.run):
    try:
        got = run([WLR_RANDR, "--json"], capture_output=True, text=True, timeout=10)
        picked = pick_output(json.loads(got.stdout)) if got.returncode == 0 else None
        scale = scale_for(picked[1]) if picked else None
        if scale:
            run([WLR_RANDR, "--output", picked[0], "--scale", str(scale)], capture_output=True, timeout=10)
            print(f"seclegion-kiosk: {picked[0]} {picked[1]} px wide, scale {scale}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass  # the kiosk starts at 1x
    return 0


if __name__ == "__main__":
    sys.exit(main())
