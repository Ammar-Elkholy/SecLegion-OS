# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 3: disk + mode. Owns disk, mode, luks. Eligibility reuses configurator.validate (mode erase),
so the page never offers a disk the review step would refuse."""

import configurator as cfg

from .base import Page

MODES = {"erase": "Erase the whole disk",
         "alongside": "Install alongside an existing system (use free space)"}


def _model_name(disk):
    return (disk.get("model") or disk.get("name") or "").strip()


def disk_problem(disk_id, mode, facts):
    """Refusal for disk_id under mode via configurator.validate (confirm filled in), else None."""
    try:
        disk = cfg.find_disk(cfg.Answers(disk=disk_id, username="x", password="x"), facts)
        a = cfg.Answers(disk=disk_id, username="x", password="x", mode=mode, confirm=_model_name(disk))
        cfg.validate(a, facts, defer_unreadable=True)  # the root-side run in seclegion-install checks
    except cfg.Refusal as r:
        return r
    return None


def list_disks(facts):
    """[{id, path, label, size, problem, code}] for every disk; id is the by-id link when one exists."""
    by_path = {}
    for link, path in sorted(facts.get("by_id", {}).items()):
        by_path.setdefault(path, link)
    out = []
    for d in facts["lsblk"]["blockdevices"]:
        if d.get("type") != "disk":
            continue
        disk_id = by_path.get(d["path"], d["path"])
        prob = disk_problem(disk_id, "erase", facts)
        gib = int(d["size"]) / (1 << 30)
        out.append({"id": disk_id, "path": d["path"], "size": int(d["size"]),
                    "label": f"{_model_name(d)} ({gib:.0f} GiB) {d['path']}",
                    "problem": prob.message if prob else None, "code": prob.code if prob else None})
    return out


class DiskPage(Page):
    key = "disk"
    title = "Disk"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.disk = None
        self.mode = "erase"
        self._luks = None  # None = default for the mode (D11: on for erase)

    @property
    def luks(self):
        return self._luks if self._luks is not None else self.mode == "erase"

    def set_disk(self, disk_id):
        self.disk = disk_id

    def set_mode(self, mode):
        self.mode = mode
        self._luks = None

    def set_luks(self, on):
        self._luks = bool(on)

    def disks(self):
        return list_disks(self.ctx.facts)

    def error(self):
        if self.mode not in MODES:
            return "Choose how to install."
        if not self.disk:
            return "Choose a disk."
        prob = disk_problem(self.disk, "erase", self.ctx.facts)
        if prob:
            return f"This disk cannot be used: {prob.message}."
        return None

    def fragment(self):
        return {"disk": self.disk, "mode": self.mode, "luks": self.luks}


def widget(page):
    from view_util import choice_group, page_box, switch_row

    box = page_box(page.title)
    disks = page.disks()
    labels = {d["id"]: d["label"] + (f" - unavailable: {d['problem']}" if d["problem"] else "")
              for d in disks}
    box.append(choice_group("Install to", labels, page.disk, page.set_disk,
                            disabled=[d["id"] for d in disks if d["problem"]]))
    box.append(choice_group("Mode", MODES, page.mode, page.set_mode))
    box.append(switch_row("Encrypt the disk (LUKS2)", page.luks, page.set_luks))
    return box
