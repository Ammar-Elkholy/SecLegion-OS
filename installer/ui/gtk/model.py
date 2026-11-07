# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Installer GUI state machine (U2/U4). Pure Python: pages are model fragments, merged into the same
answers dict the CLI uses (configurator.Answers). Flow: welcome, language, timezone, disk, [alongside,
manual], [encryption], user, hardware, tiers, review, progress, finished.
error (10) replaces progress when the
install fails; kiosk_error (14) and about (15) are shown on their own."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages import (  # noqa: E402
    p1_welcome,
    p2_language,
    p3_disk,
    p4_alongside,
    p5_manual,
    p6_encryption,
    p7_user,
    p8_review,
    p9_progress,
    p10_error,
    p11_hardware,
    p12_tiers,
    p13_finished,
    p14_kiosk_error,
    p15_about,
    p16_timezone,
)

DISK_CHANGED = "The disk changed during the failed install; choose again."


class Model:
    def __init__(self, facts, refresh_facts=None):
        self.facts = facts
        self.refresh_facts = refresh_facts  # callable returning fresh facts; None = no rescan
        self.pages = {p.key: p for p in (
            p1_welcome.WelcomePage(self), p2_language.LanguagePage(self), p3_disk.DiskPage(self),
            p4_alongside.AlongsidePage(self), p5_manual.ManualPage(self),
            p6_encryption.EncryptionPage(self), p7_user.UserPage(self), p8_review.ReviewPage(self),
            p9_progress.ProgressPage(self), p10_error.ErrorPage(self),
            p11_hardware.HardwarePage(self), p12_tiers.TiersPage(self),
            p13_finished.FinishedPage(self), p14_kiosk_error.KioskErrorPage(self),
            p15_about.AboutPage(self), p16_timezone.TimezonePage(self))}
        self.index = 0
        self.failed = False  # install ran and failed: current page is "error"
        self.on_change = lambda: None  # the app hooks this to refresh Next
        self.on_render = lambda: None  # the app hooks this to redraw the page (goto, language change)
        self.manual = False  # user opened page 5 from page 4

    @property
    def disk_id(self):
        return self.pages["disk"].disk

    def visible(self):
        keys = ["welcome", "language", "timezone", "disk"]
        if self.pages["disk"].mode == "alongside" and not self.pages["disk"].shrink_on:
            keys.append("alongside")  # shrinking has no free gap to preview; its choices carry the checks
            if self.manual:
                keys.append("manual")
        if self.pages["disk"].fragment().get("luks"):
            keys.append("encryption")
        keys += ["user", "hardware", "tiers", "review", "progress", "finished"]
        return [self.pages[k] for k in keys]

    @property
    def current(self):
        if self.failed:
            return self.pages["error"]
        return self.visible()[self.index]

    def hints(self):
        """Non-secret post hints (gaming/virt), only for toggled-on tiers."""
        return self.pages["tiers"].hints()

    def install_failed(self):
        self.failed = True

    def retry_from_review(self):
        """Error page Back: return to the review page, ready to run again."""
        self.failed = False
        if self.rescan():
            self.index = [p.key for p in self.visible()].index("disk")
            return
        self.index = [p.key for p in self.visible()].index("review")

    def _target(self, facts):
        """What the install depends on: the chosen disk's size and (partition mode) the partition's size.
        None when the disk or the partition is gone."""
        disk_page = self.pages["disk"]
        path = disk_page.disk_path(facts)
        node = next((d for d in (facts.get("lsblk") or {}).get("blockdevices", [])
                     if d.get("type") == "disk" and path in (d.get("path"), d.get("name"))), None)
        if node is None:
            return None
        if disk_page.mode == "alongside" and disk_page.shrink_on:
            part = next((p for p in node.get("children") or [] if p.get("path") == disk_page.shrink_path),
                        None)
            return None if part is None else (node.get("size"), part.get("size"))
        if disk_page.mode != "partition":
            return (node.get("size"),)
        part = next((p for p in node.get("children") or [] if p.get("path") == disk_page.partition), None)
        return None if part is None else (node.get("size"), part.get("size"))

    def rescan(self):
        """Re-gather the facts (when refresh_facts is set). True when the chosen disk or partition is gone or
        resized: the disk page is then reset with a message and the caller shows it."""
        if not self.refresh_facts or not self.pages["disk"].disk:
            if self.refresh_facts:
                self.facts = self.refresh_facts()
            return False
        before = self._target(self.facts)
        self.facts = self.refresh_facts()
        if self._target(self.facts) == before and before is not None:
            return False
        self.pages["disk"].reset(DISK_CHANGED)
        return True

    def rescan_disks(self):
        """The disk page's Rescan button: refresh and redraw."""
        self.rescan()
        self.on_render()
        self.on_change()

    def can_next(self):
        return self.current.can_next()

    def error(self):
        return self.current.error()

    def next(self):
        if not self.can_next():
            return False
        if self.index + 1 < len(self.visible()):
            self.index += 1
        return True

    def back(self):
        self.index = max(0, self.index - 1)

    def goto(self, key):
        """Jump to a visible page (the review page's Edit buttons). False when `key` is not visible."""
        keys = [p.key for p in self.visible()]
        if key not in keys:
            return False
        self.failed = False
        self.index = keys.index(key)
        self.on_render()
        return True

    def open_manual(self):
        self.manual = True

    def answers(self):
        """Merged fragments of the visible pages: the configurator's answers dict."""
        out = {}
        for p in self.visible():
            out.update(p.fragment())
        return out
