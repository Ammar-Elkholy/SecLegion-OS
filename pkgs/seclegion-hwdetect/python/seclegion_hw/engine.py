# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Facts + TOML rules -> plan.

A rule file holds `[[rule]]` tables:

    [[rule]]
    id = "unique-id"
    claims_gpu = true            # optional: display devices this rule matched are handled
    [rule.when]                  # every key must hold (AND); omitted = always
    pci_vendor = "10de"          # pci_* keys are tested together against ONE PCI device
    [rule.add]                   # what a match contributes
    packages = ["mesa"]
    kernel_params = ["quiet"]
    services = ["x.service"]     # systemd units to enable on the installed system
    udev_rules = ["KERNEL==..."]  # lines for /etc/udev/rules.d/61-seclegion-gpu.rules
    warnings = ["text"]          # shown as warnings
    messages = ["text"]          # informational
    [rule.add.env]               # KEY = "value"; two rules may not set one key to different values
    [rule.add.settings]          # desktop settings (dotted keys), merged the same way
    [[rule.add.boot_entries]]    # id, title, params

`when` keys: pci_vendor, pci_device, pci_subsystem_vendor, pci_subsystem_device (hex, str or list),
pci_class (hex prefix, str or list), boot_vga (bool), nvidia ("open"|"legacy"|"unknown"),
nvidia_family; virt (str or list; "none" = bare metal), virtual (bool), cpu_vendor, cpu_model (regex),
dmi (table: field = regex), kernel ("stock"|"lts"|"other"), hybrid (bool), touchpad (bool),
unclaimed_gpu (true; such rules run after all others, on display devices no claims_gpu rule took).

Strings in warnings, messages and env values may use {pci_id}, {pci_addr}, {nvidia_family}, {virt},
{kernel}, {igpu_card}, {dgpu_card}, {igpu_addr}, {dgpu_addr};
a rule with pci_* keys produces one string per matched device.

Rule files: `rules.d/*.toml` in name order, then the EXTRA_RULE_FILES next to rules.d (gaming.toml,
added by a later job) and any `--rules` files/dirs given on the command line.
"""

import re
import tomllib
from collections import defaultdict
from pathlib import Path

from . import edid, system

PLAN_SCHEMA = 1
PCI_ADDR = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]")
EXTRA_RULE_FILES = ("gaming.toml",)
PCI_KEYS = {
    "pci_vendor": "vendor",
    "pci_device": "device",
    "pci_subsystem_vendor": "subsystem_vendor",
    "pci_subsystem_device": "subsystem_device",
    "pci_class": "class",
    "boot_vga": "boot_vga",
    "nvidia": "nvidia",
    "nvidia_family": "nvidia_family",
}
GLOBAL_KEYS = {
    "virt", "virtual", "cpu_vendor", "cpu_model", "dmi", "kernel", "hybrid", "touchpad", "unclaimed_gpu",
}
ADD_KEYS = {
    "packages", "kernel_params", "services", "udev_rules", "warnings", "messages", "env", "settings",
    "boot_entries",
}
RULE_KEYS = {"id", "description", "claims_gpu", "when", "add"}
INTEL_AMD = ("8086", "1002")


class RulesError(ValueError):
    pass


def load_nvidia_table(path):
    """{device id (lowercase hex): (family, driver)}; the first section listing an ID wins."""
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    table = {}
    for section in data.get("section", []):
        for ident in section["ids"]:
            table.setdefault(ident.lower(), (section["family"], section["driver"]))
    return table


def collect(root, nvidia_table):
    """Gather the facts rules match on."""
    pci = system.read_pci(root)
    for dev in pci:
        dev["pci_id"] = f"{dev['vendor']}:{dev['device']}"
        dev["nvidia"] = dev["nvidia_family"] = None
        if dev["vendor"] == "10de" and dev["class"].startswith("03"):
            family, driver = nvidia_table.get(dev["device"], ("unknown", None))
            dev["nvidia_family"] = family
            dev["nvidia"] = "open" if driver == "nvidia-open" else ("legacy" if driver else "unknown")
    gpus = [d for d in pci if d["class"].startswith("03")]
    igpus = [d for d in gpus if d["vendor"] in INTEL_AMD]
    nvidia = [d for d in gpus if d["vendor"] == "10de"]
    hybrid = bool(igpus and nvidia)
    dmi = system.read_dmi(root)
    cpu = system.read_cpu(root)
    osrelease = system.read_text(Path(root) / "proc/sys/kernel/osrelease")

    # Aquamarine splits AQ_DRM_DEVICES on ':', so the cards are udev symlinks (the plan's udev_rules)
    # with no colon in them, not the by-path names.
    def card(dev, name):
        return f"/dev/dri/seclegion-{name}" if dev and hybrid else ""

    def addr(dev):
        if not (dev and hybrid):
            return ""
        if not PCI_ADDR.fullmatch(dev["addr"]):
            raise RulesError(f"unexpected PCI address {dev['addr']!r}")
        return dev["addr"]

    return {
        "pci": pci,
        "gpus": gpus,
        "cpu": cpu,
        "dmi": dmi,
        "laptop": dmi.get("chassis_type", "") in system.LAPTOP_CHASSIS,
        "virt": system.detect_virt(dmi, cpu),
        "kernel_release": osrelease,
        "kernel": system.kernel_flavor(osrelease),
        "touchpad": system.has_touchpad(root),
        "displays": edid.read_displays(root),
        "hybrid": hybrid,
        "igpu_card": card(igpus[0] if igpus else None, "igpu"),
        "dgpu_card": card(nvidia[0] if nvidia else None, "dgpu"),
        "igpu_addr": addr(igpus[0] if igpus else None),
        "dgpu_addr": addr(nvidia[0] if nvidia else None),
    }


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _pci_ok(dev, when):
    for key, field in PCI_KEYS.items():
        if key not in when:
            continue
        want, have = when[key], dev.get(field)
        if key == "pci_class":
            if not any(dev["class"].startswith(p.lower()) for p in _as_list(want)):
                return False
        elif isinstance(want, bool):
            if have is not want:
                return False
        elif have is None or str(have).lower() not in {str(w).lower() for w in _as_list(want)}:
            return False
    return True


def _global_ok(facts, when):
    checks = {
        "virt": lambda v: facts["virt"] in _as_list(v),
        "virtual": lambda v: (facts["virt"] != "none") is v,
        "cpu_vendor": lambda v: facts["cpu"]["vendor"] in _as_list(v),
        "cpu_model": lambda v: re.search(v, facts["cpu"]["model"]) is not None,
        "kernel": lambda v: facts["kernel"] in _as_list(v),
        "hybrid": lambda v: facts["hybrid"] is v,
        "touchpad": lambda v: facts["touchpad"] is v,
        "dmi": lambda v: all(
            re.search(rx, facts["dmi"].get(field, ""), re.IGNORECASE) for field, rx in v.items()
        ),
    }
    return all(check(when[key]) for key, check in checks.items() if key in when)


def validate(rule, source):
    rid = rule.get("id", "?")
    where = f"{source}: rule {rid}"
    if "id" not in rule:
        raise RulesError(f"{source}: rule without id")
    for key in set(rule) - RULE_KEYS:
        raise RulesError(f"{where}: unknown key {key!r}")
    for key in set(rule.get("when", {})) - set(PCI_KEYS) - GLOBAL_KEYS:
        raise RulesError(f"{where}: unknown condition {key!r}")
    for key in set(rule.get("add", {})) - ADD_KEYS:
        raise RulesError(f"{where}: unknown action {key!r}")


def load_rules(paths):
    """Load rule files (given as files or directories of *.toml); returns the rules in order."""
    rules, seen = [], {}
    for path in paths:
        path = Path(path)
        files = sorted(path.glob("*.toml")) if path.is_dir() else [path]
        for file in files:
            try:
                with open(file, "rb") as handle:
                    data = tomllib.load(handle)
            except (OSError, tomllib.TOMLDecodeError) as err:
                raise RulesError(f"{file}: {err}") from err
            for rule in data.get("rule", []):
                validate(rule, file)
                if rule["id"] in seen:
                    raise RulesError(f"{file}: duplicate rule id {rule['id']!r} (also in {seen[rule['id']]})")
                seen[rule["id"]] = file
                rules.append(rule)
    return rules


def default_rule_paths(hw_dir, extra=()):
    hw_dir = Path(hw_dir)
    paths = [hw_dir / "rules.d"]
    paths += [hw_dir / name for name in EXTRA_RULE_FILES if (hw_dir / name).is_file()]
    return paths + [Path(p) for p in extra]


def _matches(rule, facts, pool):
    """Devices (or [None] for a device-less rule) the rule matched; None when it does not apply."""
    when = rule.get("when", {})
    if not _global_ok(facts, when):
        return None
    if any(key in when for key in PCI_KEYS) or "unclaimed_gpu" in when:
        found = [d for d in pool if _pci_ok(d, when)]
        return found or None
    return [None]


class _Merge:
    def __init__(self):
        self.packages, self.kernel_params, self.warnings, self.messages = [], [], [], []
        self.boot_entries, self.env, self.settings, self.applied = [], {}, {}, []
        self.services, self.udev_rules = [], []
        self._owner = {}

    def extend(self, target, items):
        for item in items:
            if item not in target:
                target.append(item)

    def put(self, target, kind, key, value, rid):
        if key in target and target[key] != value:
            raise RulesError(f"rules {self._owner[kind, key]} and {rid} set {kind} {key!r} differently")
        target[key] = value
        self._owner[kind, key] = rid


def evaluate(facts, rules):
    """Run `rules` over `facts`; returns the plan dict."""
    merged, claimed = _Merge(), set()
    all_pci = facts["pci"]
    phases = (
        [r for r in rules if "unclaimed_gpu" not in r.get("when", {})],
        [r for r in rules if "unclaimed_gpu" in r.get("when", {})],
    )
    for phase, group in enumerate(phases):
        for rule in group:
            pool = all_pci
            if phase == 1:
                pool = [d for d in facts["gpus"] if d["addr"] not in claimed]
                if not pool:
                    continue
            devices = _matches(rule, facts, pool)
            if devices is None:
                continue
            if rule.get("claims_gpu"):
                claimed |= {d["addr"] for d in devices if d and d["class"].startswith("03")}
            _apply(rule, devices, facts, merged)
    return {
        "schema": PLAN_SCHEMA,
        "packages": merged.packages,
        "kernel_params": merged.kernel_params,
        "services": merged.services,
        "udev_rules": merged.udev_rules,
        "env": merged.env,
        "settings": {**merged.settings, **_display_settings(facts)},
        "warnings": merged.warnings,
        "messages": merged.messages,
        "boot_entries": merged.boot_entries,
        "facts": summarise(facts),
        "rules_applied": merged.applied,
    }


def _context(facts, dev):
    ctx = defaultdict(str, virt=facts["virt"], kernel=facts["kernel"])
    ctx.update(igpu_card=facts["igpu_card"], dgpu_card=facts["dgpu_card"])
    ctx.update(igpu_addr=facts["igpu_addr"], dgpu_addr=facts["dgpu_addr"])
    if dev:
        ctx.update(pci_id=dev["pci_id"], pci_addr=dev["addr"], nvidia_family=dev["nvidia_family"] or "")
    return ctx


def _apply(rule, devices, facts, merged):
    add = rule.get("add", {})
    rid = rule["id"]
    merged.applied.append(rid)
    merged.extend(merged.packages, add.get("packages", []))
    merged.extend(merged.kernel_params, add.get("kernel_params", []))
    merged.extend(merged.services, add.get("services", []))
    for entry in add.get("boot_entries", []):
        if entry["id"] not in {e["id"] for e in merged.boot_entries}:
            merged.boot_entries.append(entry)
    for dev in devices:
        ctx = _context(facts, dev)
        merged.extend(merged.warnings, [s.format_map(ctx) for s in add.get("warnings", [])])
        merged.extend(merged.messages, [s.format_map(ctx) for s in add.get("messages", [])])
        merged.extend(merged.udev_rules, [s.format_map(ctx) for s in add.get("udev_rules", [])])
        for key, value in add.get("env", {}).items():
            merged.put(merged.env, "env", key, value.format_map(ctx), rid)
    for key, value in add.get("settings", {}).items():
        merged.put(merged.settings, "setting", key, value, rid)


def _display_settings(facts):
    displays = [d for d in facts["displays"] if d["scale"] != 1.0]
    if not displays:
        return {}
    return {
        "display.scale": facts["displays"][0]["scale"],
        "display.output_scales": {d["connector"]: d["scale"] for d in facts["displays"]},
    }


def summarise(facts):
    """The facts block of the plan: what was detected, without anything identifying."""
    return {
        "cpu_vendor": facts["cpu"]["vendor"],
        "virt": facts["virt"],
        "kernel": facts["kernel"],
        "laptop": facts["laptop"],
        "touchpad": facts["touchpad"],
        "hybrid": facts["hybrid"],
        "gpus": [
            {
                "addr": d["addr"],
                "pci_id": d["pci_id"],
                "class": d["class"],
                "boot_vga": d["boot_vga"],
                "nvidia_family": d["nvidia_family"],
            }
            for d in facts["gpus"]
        ],
        "displays": [
            {k: d[k] for k in ("connector", "width_px", "height_px", "dpi", "scale")}
            for d in facts["displays"]
        ],
    }
