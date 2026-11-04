# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 4: alongside preview + the dual-boot guide (U3). Shown only for mode alongside. Blocks Next on
bitlocker / hibernated Windows partitions it could probe, using winguide's own refusal text. Partitions the
kiosk user cannot read are only noted; seclegion-install checks them as root."""

import configurator as cfg
import winguide

from .base import Page
from .p3_disk import disk_problem

GUIDE = {
    "bitlocker": ["Boot Windows.", "Open Manage BitLocker and suspend protection (or decrypt the drive).",
                  "Shut Windows down, then restart the installer."],
    "windows_hibernated": ["Boot Windows.", "Disable Fast Startup (Power Options), or shut down with "
                           "shutdown /s /t 0.", "Restart the installer."],
    "windows_unreadable": ["Boot Windows, shut it down fully, then restart the installer."],
}


def partition_refusal(disk, facts):
    """First winguide refusal over the disk's partitions. A Windows (ntfs/bitlocker) partition with
    no probe result is "unreadable" (the kiosk user cannot read raw partitions): not a refusal here, the page
    says it is checked when installing. seclegion-install re-probes as root and refuses there."""
    probes = facts.get("probes") or {}
    for part in disk.get("children") or []:
        res = probes.get(part.get("path"))
        if res is None and (part.get("fstype") or "").lower() in ("ntfs", "bitlocker"):
            res = "unreadable"
        if res == "unreadable":
            continue
        blocked = winguide.refusal_for(res)
        if blocked:
            return blocked
    return None


def unchecked_partitions(disk, facts):
    """Windows (ntfs/bitlocker) partitions this process could not probe: checked as root when installing."""
    probes = facts.get("probes") or {}
    return [p["path"] for p in disk.get("children") or []
            if (p.get("fstype") or "").lower() in ("ntfs", "bitlocker")
            and probes.get(p.get("path"), "unreadable") == "unreadable"]


class AlongsidePage(Page):
    key = "alongside"
    title = "Install alongside"

    def disk(self):
        return cfg.find_disk(cfg.Answers(disk=self.ctx.disk_id, username="x", password="x"),
                             self.ctx.facts)

    def gaps(self):
        return cfg.free_gaps(self.disk())

    def refusal(self):
        """(code, message) blocking this page, or None."""
        blocked = partition_refusal(self.disk(), self.ctx.facts)
        if blocked:
            return blocked
        prob = disk_problem(self.ctx.disk_id, "alongside", self.ctx.facts)
        return (prob.code, prob.message) if prob else None

    UNCHECKED_NOTE = ("Windows partitions on this disk will be checked for BitLocker and hibernation "
                      "when installing.")

    def unchecked(self):
        return unchecked_partitions(self.disk(), self.ctx.facts)

    def guide(self):
        r = self.refusal()
        return GUIDE.get(r[0], []) if r else []

    def error(self):
        r = self.refusal()
        return f"{r[1]}." if r else None

    def preview(self):
        """Text lines: each gap, the largest marked as the one that will be used."""
        gaps = self.gaps()
        best = max(gaps, key=lambda g: g[1], default=None)
        return [f"Free space {g[1] / (1 << 30):.1f} GiB at {g[0] / (1 << 30):.1f} GiB"
                + ("  <- will be used" if g == best else "") for g in gaps] or ["No free space on this disk."]


def widget(page):
    import gi

    gi.require_version("Adw", "1")
    from diskmap import DiskMap
    from gi.repository import Adw
    from view_util import page_box

    box = page_box(page.title)
    disk = page.disk()
    layout = Adw.PreferencesGroup(title="Disk layout",
                                  description=(disk.get("model") or disk.get("name") or "").strip())
    maprow = Adw.PreferencesRow(activatable=False, selectable=False, focusable=False)
    dmap = DiskMap(disk)
    for side in ("top", "bottom", "start", "end"):
        getattr(dmap, f"set_margin_{side}")(10)
    maprow.set_child(dmap)
    layout.add(maprow)
    box.append(layout)
    space = Adw.PreferencesGroup(title="Free space", description="The installer uses the largest gap.")
    for line in page.preview():
        gap = line.endswith("will be used")
        title = line.replace("  <- will be used", "")
        row = Adw.ActionRow(title=title, use_markup=False,
                            subtitle="Will be used for SecLegion OS" if gap else "")
        space.add(row)
    box.append(space)
    if page.unchecked():
        note = Adw.PreferencesGroup()
        note.add(Adw.ActionRow(title=page.UNCHECKED_NOTE, use_markup=False, title_lines=0))
        box.append(note)
    r = page.refusal()
    if r:
        guide = Adw.PreferencesGroup(title="Blocked", description=f"{r[1]}.")
        guide.add_css_class("error")
        for i, step in enumerate(page.guide(), 1):
            guide.add(Adw.ActionRow(title=step, use_markup=False, title_lines=0, subtitle=f"Step {i}"))
        box.append(guide)
    return box
