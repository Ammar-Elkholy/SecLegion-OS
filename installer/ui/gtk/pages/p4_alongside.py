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
    from view_util import page_box, text_label

    box = page_box(page.title)
    for line in page.preview():
        box.append(text_label(line))
    if page.unchecked():
        box.append(text_label(page.UNCHECKED_NOTE))
    r = page.refusal()
    if r:
        box.append(text_label(f"Blocked: {r[1]}", css="error"))
        for i, step in enumerate(page.guide(), 1):
            box.append(text_label(f"{i}. {step}"))
    return box
