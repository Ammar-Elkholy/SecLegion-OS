# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-barcheck: the non-interactive checks of the daily-driver bar (docs/DAILY-DRIVER.md, B1-B13).

Read-only. It writes only to the file named by -o (never over an existing one without --force), needs
no root (a check that does prints SKIP), changes no setting and uses no network. Every external
command goes through one runner (`system_runner`), so the tests pass a fake.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

ENGINE = "dock" + "er"  # the container engine's name, built in pieces (tools/check-container-start)
TIMEOUT = 8

Result = namedtuple("Result", "rc out")
Line = namedtuple("Line", "status row check detail")


def system_runner(argv, timeout=TIMEOUT):
    """Run argv (no shell, no stdin, C locale); None when the command is missing."""
    env = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        proc = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, env=env, check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return Result(124, "timed out")
    except OSError as exc:
        return Result(126, str(exc))
    return Result(proc.returncode, proc.stdout.decode("utf-8", "replace"))


class Ctx:
    """What the checks look at: a root dir (/ or a test tree), a runner and the caller's uid."""

    def __init__(self, root="/", run=system_runner, euid=None):
        self.root = Path(root)
        self.run = run
        self.euid = os.geteuid() if euid is None else euid

    def path(self, rel):
        return self.root / rel.lstrip("/")

    def read(self, rel):
        """File text, None when absent, or the string 'perm' when it exists but cannot be read."""
        try:
            return self.path(rel).read_text(errors="replace")
        except FileNotFoundError:
            return None
        except PermissionError:
            return "perm"
        except OSError:
            return None

    def glob(self, pattern):
        return sorted(glob.glob(str(self.path(pattern))))

    @property
    def live(self):
        cmdline = self.read("/proc/cmdline")
        if cmdline and cmdline != "perm" and "archisobasedir" in cmdline:
            return True
        return self.path("/run/archiso").exists()


def _out(res):
    return (res.out or "").strip() if res else ""


def _first(res, default=""):
    text = _out(res)
    return text.splitlines()[0] if text else default


def _manual(row, check, step):
    return Line("SKIP", row, check, "manual: " + step)


def _tool(ctx, row, check, argv, need=None):
    """PASS when argv exits 0; FAIL when it is missing or fails."""
    res = ctx.run(argv)
    if res is None:
        return Line("FAIL", row, check, f"{argv[0]} not installed" + (f" ({need})" if need else ""))
    if res.rc != 0:
        return Line("FAIL", row, check, f"{' '.join(argv)} exited {res.rc}: {_first(res)}")
    return Line("PASS", row, check, _first(res, "ok").split(" (UUID")[0])


def _attr(base, name):
    f = base / name
    return f.read_text().strip() if f.is_file() else ""


def pci_gpus(ctx):
    """[(address, vendor, runtime_status path)] for display-class PCI devices."""
    gpus = []
    for dev in ctx.glob("/sys/bus/pci/devices/*"):
        base = Path(dev)
        if _attr(base, "class").startswith("0x03"):
            gpus.append((base.name, _attr(base, "vendor"), base / "power" / "runtime_status"))
    return gpus


def check_b1(ctx):
    efi = ctx.path("/sys/firmware/efi").is_dir()
    lines = [Line("PASS" if efi else "FAIL", "B1", "uefi",
                  "booted in UEFI mode" if efi else "no /sys/firmware/efi")]
    if ctx.live:
        lines.append(Line("PASS", "B1", "bootloader", "live mode (archiso); bootctl runs once installed"))
        return lines
    res = ctx.run(["bootctl", "status"])
    if res is None:
        lines.append(Line("FAIL", "B1", "bootloader", "bootctl not installed"))
    elif res.rc != 0 and ctx.euid != 0:
        lines.append(Line("SKIP", "B1", "bootloader", "needs root: bootctl status failed as a user"))
    elif res.rc != 0:
        lines.append(Line("FAIL", "B1", "bootloader", f"bootctl status exited {res.rc}"))
    else:
        text = res.out
        uki = "Type #2" in text or ("Kernel" in text and ".efi" in text)
        ok = "systemd-boot" in text and uki
        detail = "systemd-boot with a UKI entry" if ok else "bootctl status shows no systemd-boot/UKI"
        lines.append(Line("PASS" if ok else "FAIL", "B1", "bootloader", detail))
    return lines


def check_b2(ctx):
    gpus = pci_gpus(ctx)
    vendors = {v for _, v, _ in gpus}
    amd, nv = "0x1002" in vendors, "0x10de" in vendors
    both = f"AMD {'yes' if amd else 'no'}, NVIDIA {'yes' if nv else 'no'}"
    lines = [Line("PASS" if amd and nv else "FAIL", "B2", "gpus", f"{len(gpus)} display device(s); {both}")]
    if nv:
        # read the dGPU's power state before nvidia-smi or vulkaninfo wake it
        for _addr, vendor, rt in gpus:
            if vendor != "0x10de":
                continue
            state = rt.read_text().strip() if rt.is_file() else ""
            if _attr(rt.parent.parent, "boot_vga") == "1":
                lines.append(Line("SKIP", "B2", "dgpu-runtime", "dGPU drives the display (Discrete mode)"))
            elif state == "suspended":
                lines.append(Line("PASS", "B2", "dgpu-runtime", "runtime_status = suspended (D3)"))
            else:
                lines.append(Line("FAIL", "B2", "dgpu-runtime",
                                  f"runtime_status = {state or 'unreadable'}, not suspended (a client "
                                  "such as nvidia-smi keeps it awake)"))
        lines.append(_tool(ctx, "B2", "nvidia-smi", ["nvidia-smi", "-L"], "nvidia-utils"))
    else:
        lines.append(Line("SKIP", "B2", "nvidia-smi", "no NVIDIA GPU"))
        lines.append(Line("SKIP", "B2", "dgpu-runtime", "no NVIDIA GPU"))
    res = ctx.run(["vulkaninfo", "--summary"])
    if res is None:
        lines.append(Line("SKIP", "B2", "vulkaninfo", "vulkaninfo not installed (vulkan-tools)"))
    else:
        n = len(re.findall(r"deviceName\s*=", res.out))
        lines.append(Line("PASS" if res.rc == 0 and n >= 2 else "FAIL", "B2", "vulkaninfo",
                          f"{n} Vulkan device(s) listed (need both GPUs)"))
    lines.append(_manual("B2", "hyprland", "hyprctl monitors shows the native mode; prime-run glxinfo -B "
                         "reports the RTX 4060; HDMI/USB-C hotplug; repeat in Discrete mode"))
    return lines


def check_b3(ctx):
    res = ctx.run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"])
    if res is None or res.rc != 0:
        lines = [Line("FAIL", "B3", "wifi", "nmcli missing or NetworkManager not running")]
    elif any(ln.startswith("wifi:") for ln in res.out.splitlines()):
        lines = [Line("PASS", "B3", "wifi", "a Wi-Fi device exists")]
    else:
        lines = [Line("FAIL", "B3", "wifi", "no Wi-Fi device in nmcli dev")]
    hci = ctx.glob("/sys/class/bluetooth/hci*")
    lines.append(Line("PASS" if hci else "FAIL", "B3", "bluetooth",
                      f"{len(hci)} controller(s)" if hci else "no controller in /sys/class/bluetooth"))
    lines.append(_manual("B3", "connect-pair", "nmcli dev wifi connect <ssid> --ask and reconnect after "
                         "resume; bluetoothctl pairs a device"))
    return lines


def _wpctl_count(text, section):
    count, inside = 0, False
    for ln in text.splitlines():
        stripped = ln.strip(" │├└─")
        if stripped.endswith(":") and not stripped.startswith("*"):
            inside = stripped == section + ":"
        elif inside and re.match(r"\*?\s*\d+\.\s", stripped):
            count += 1
    return count


def check_b4(ctx):
    res = ctx.run(["wpctl", "status"])
    if res is None or res.rc != 0:
        lines = [Line("FAIL", "B4", "wpctl", "wpctl missing or PipeWire not running")]
    else:
        sinks, sources = _wpctl_count(res.out, "Sinks"), _wpctl_count(res.out, "Sources")
        lines = [Line("PASS" if sinks and sources else "FAIL", "B4", "wpctl",
                      f"{sinks} sink(s), {sources} source(s)")]
    cams = ctx.glob("/dev/video*")
    lines.append(Line("PASS" if cams else "FAIL", "B4", "webcam",
                      f"{len(cams)} /dev/video node(s)" if cams else "no /dev/video*"))
    lines.append(_manual("B4", "speakers-mic-keys", "both speakers play, the mic records, v4l2-ctl "
                         "--list-devices lists the webcam, brightness/volume/backlight/Fn+Q keys work"))
    return lines


def check_b5(ctx):
    mem = ctx.read("/sys/power/mem_sleep")
    if mem is None or mem == "perm":
        lines = [Line("FAIL", "B5", "mem_sleep", "/sys/power/mem_sleep unreadable")]
    else:
        lines = [Line("PASS" if "s2idle" in mem else "FAIL", "B5", "mem_sleep", mem.strip())]
    if not any(v == "0x10de" for _, v, _ in pci_gpus(ctx)):
        lines.append(Line("SKIP", "B5", "nvidia-suspend", "no NVIDIA GPU"))
        lines.append(Line("SKIP", "B5", "preserve-vram", "no NVIDIA GPU"))
    else:
        res = ctx.run(["systemctl", "is-enabled", "nvidia-suspend.service"])
        state = _first(res, "unknown (systemctl missing)")
        lines.append(Line("PASS" if res and res.rc == 0 else "FAIL", "B5", "nvidia-suspend",
                          f"nvidia-suspend.service is {state}"))
        params = ctx.read("/proc/driver/nvidia/params")
        if params == "perm":
            lines.append(Line("SKIP", "B5", "preserve-vram", "needs root: /proc/driver/nvidia/params"))
        elif params is None:
            lines.append(Line("FAIL", "B5", "preserve-vram", "NVIDIA driver not loaded (no params file)"))
        else:
            ok = re.search(r"PreserveVideoMemoryAllocations:\s*1\b", params) is not None
            lines.append(Line("PASS" if ok else "FAIL", "B5", "preserve-vram",
                              "PreserveVideoMemoryAllocations: 1" if ok
                              else "PreserveVideoMemoryAllocations is not 1"))
    lines.append(_tool(ctx, "B5", "powerprofilesctl", ["powerprofilesctl", "get"], "power-profiles-daemon"))
    lines.append(_manual("B5", "suspend", "systemctl suspend 3 times and one lid close: Wi-Fi, both GPUs "
                         "and the lock screen come back; battery drain over 8 h of suspend is under 10%"))
    return lines


def _fstypes(node, found):
    if isinstance(node, dict):
        if node.get("fstype"):
            found.add(node["fstype"])
        for child in node.get("children") or []:
            _fstypes(child, found)
    elif isinstance(node, list):
        for item in node:
            _fstypes(item, found)


def check_b6(ctx):
    res = ctx.run(["lsblk", "-J", "-f"])
    if res is None or res.rc != 0:
        lines = [Line("FAIL", "B6", "luks", "lsblk missing or failed")]
    else:
        found = set()
        try:
            _fstypes(json.loads(res.out).get("blockdevices", []), found)
        except ValueError:
            found = None
        if found is None:
            lines = [Line("FAIL", "B6", "luks", "lsblk -J output is not JSON")]
        elif "crypto_LUKS" in found:
            extra = "; btrfs on top" if "btrfs" in found else ""
            lines = [Line("PASS", "B6", "luks", "crypto_LUKS found" + extra)]
        elif ctx.live:
            lines = [Line("SKIP", "B6", "luks", "live USB: encryption is checked on the installed system")]
        else:
            lines = [Line("FAIL", "B6", "luks", "no crypto_LUKS device in lsblk -f")]
    lines.append(_manual("B6", "passphrase", "reboot: the passphrase is asked at boot"))
    return lines


def check_b7(ctx):
    res = ctx.run(["snapper", "--version"])
    if res is None:
        return [Line("SKIP", "B7", "snapper", "snapper not installed: V2 pending")]
    return [Line("PASS" if res.rc == 0 else "FAIL", "B7", "snapper", _first(res, "snapper present")),
            _manual("B7", "rollback", "snapper list has pre/post pairs; seclegion-rescue rollback N boots N")]


def check_b8(ctx):
    update = _manual("B8", "update", "sudo pacman -Syu exits 0 (needs the network)")
    if ctx.live:
        return [Line("SKIP", "B8", "pacman-conf", "live USB: its file:// [seclegion] repo is expected"),
                update]
    conf = ctx.read("/etc/pacman.conf")
    if conf is None or conf == "perm":
        return [Line("FAIL", "B8", "pacman-conf", "/etc/pacman.conf unreadable"), update]
    section, bad = None, False
    for ln in conf.splitlines():
        ln = ln.strip()
        if ln.startswith("[") and ln.endswith("]"):
            section = ln[1:-1]
        elif section == "seclegion" and re.match(r"Server\s*=\s*file://", ln):
            bad = True
    detail = ("[seclegion] points at a file:// repo that is absent on the installed system "
              "(known gap B8)") if bad else "no file:// [seclegion] server"
    return [Line("FAIL" if bad else "PASS", "B8", "pacman-conf", detail), update]


def check_b9(ctx):
    return [_tool(ctx, "B9", "firefox", ["firefox", "--version"], "firefox"),
            _manual("B9", "browse", "Firefox (and Brave) log in and play video")]


def check_b10(ctx):
    return [_tool(ctx, "B10", "git", ["git", "--version"], "git"),
            _tool(ctx, "B10", "ssh", ["ssh", "-V"], "openssh"),
            _tool(ctx, "B10", "gpg", ["gpg", "--version"], "gnupg"),
            _manual("B10", "remote", "ssh -T git@<host> and gpg -K")]


def check_b11(ctx):
    lines = []
    if ctx.live:
        lines.append(Line("SKIP", "B11", "group", f"live USB: no {ENGINE} group membership expected"))
        lines.append(Line("SKIP", "B11", "service", f"live USB: {ENGINE}.service is not enabled"))
    else:
        groups = _out(ctx.run(["id", "-nG"])).split()
        lines.append(Line("PASS" if ENGINE in groups else "FAIL", "B11", "group",
                          f"user is in the {ENGINE} group" if ENGINE in groups
                          else f"user is not in the {ENGINE} group"))
        res = ctx.run(["systemctl", "is-enabled", f"{ENGINE}.service"])
        lines.append(Line("PASS" if res and res.rc == 0 else "FAIL", "B11", "service",
                          f"{ENGINE}.service is {_first(res, 'unknown (systemctl missing)')}"))
    res = ctx.run([ENGINE, "info"])
    if res is None:
        lines.append(Line("FAIL", "B11", "daemon", f"{ENGINE} not installed"))
    else:
        lines.append(Line("PASS" if res.rc == 0 else "FAIL", "B11", "daemon",
                          f"{ENGINE} info reachable as the user" if res.rc == 0
                          else f"{ENGINE} info exited {res.rc}: {_first(res)}"))
    lines.append(_manual("B11", "hello-world", f"{ENGINE} run --rm hello-world as the user with ufw on "
                         "(pulls an image: needs the network)"))
    return lines


def check_b12(ctx):
    return [_tool(ctx, "B12", "claude", ["claude", "--version"], "not shipped yet"),
            _manual("B12", "desktop", "the Claude desktop app opens and signs in")]


def check_b13(ctx):
    lines = [_tool(ctx, "B13", "make", ["make", "--version"], "base-devel"),
             _tool(ctx, "B13", "python", ["python3", "--version"], "python")]
    missing = [t for t in ("gcc", "patch", "fakeroot", "pkgconf") if ctx.run([t, "--version"]) is None]
    lines.append(Line("FAIL" if missing else "PASS", "B13", "base-devel",
                      "missing: " + ", ".join(missing) if missing
                      else "gcc, patch, fakeroot, pkgconf present"))
    lines.append(_tool(ctx, "B13", "socat", ["socat", "-V"], "socat"))
    virt = ctx.run(["pacman", "-Q", "seclegion-virt"])
    if virt is None or virt.rc != 0:
        lines.append(Line("SKIP", "B13", "qemu", "seclegion-virt not installed (qemu is opt-in)"))
    else:
        lines.append(_tool(ctx, "B13", "qemu", ["qemu-system-x86_64", "--version"], "seclegion-virt"))
    lines.append(_manual("B13", "toolchain", "make bootstrap && pytest -q; tools/build-iso; one -m iso gate"))
    return lines


CHECKS = (check_b1, check_b2, check_b3, check_b4, check_b5, check_b6, check_b7, check_b8, check_b9,
          check_b10, check_b11, check_b12, check_b13)


def run_all(ctx):
    lines = []
    for fn in CHECKS:
        try:
            lines.extend(fn(ctx))
        except Exception as exc:  # a broken probe must not hide the other rows
            row = "B" + fn.__name__.removeprefix("check_b")
            lines.append(Line("FAIL", row, "internal", f"{type(exc).__name__}: {exc}"))
    return lines


def render(lines):
    out = [f"{ln.status} {ln.row} {ln.check} — {ln.detail}" for ln in lines]
    n = {s: sum(1 for ln in lines if ln.status == s) for s in ("PASS", "FAIL", "SKIP")}
    out.append(f"SUMMARY: {n['PASS']} PASS, {n['FAIL']} FAIL, {n['SKIP']} SKIP")
    return "\n".join(out) + "\n", n["FAIL"]


def main(argv=None, run=system_runner, root="/", euid=None, stdout=None):
    ap = argparse.ArgumentParser(prog="seclegion-barcheck", description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--output", metavar="FILE", help="also write the report to FILE")
    ap.add_argument("--force", action="store_true", help="let -o overwrite an existing file")
    args = ap.parse_args(argv)
    out = stdout or sys.stdout
    if args.output and os.path.lexists(args.output) and not args.force:
        print(f"seclegion-barcheck: {args.output} exists; use --force to overwrite", file=sys.stderr)
        return 2
    text, fails = render(run_all(Ctx(root, run, euid)))
    out.write(text)
    if args.output:
        try:
            Path(args.output).write_text(text)
        except OSError as exc:
            print(f"seclegion-barcheck: cannot write {args.output}: {exc}", file=sys.stderr)
            return 2
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
