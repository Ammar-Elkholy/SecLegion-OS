# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The sidebar: 17 deep-linkable pages (plan-r8 B3/B7). Pure Python, no gi import.

A page shows the registry rows whose `Setting.page` is its `registry_page`. A page with no
registry rows yet is still listed (and deep-linkable) and shows "Coming in a later update".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..backend import registry


@dataclass(frozen=True)
class Page:
    id: str            # deep-link id: `seclegion-settings --page ID`
    label: str
    icon: str          # symbolic icon name from the Adwaita theme
    group: str
    registry_page: str | None = None  # registry.PAGES id whose rows this page shows


SYSTEM, PERSONAL, MAINTENANCE = "SYSTEM", "PERSONAL", "MAINTENANCE"

PAGES: tuple[Page, ...] = (
    Page("power", "Power", "battery-full-symbolic", SYSTEM, "power"),
    Page("sleep", "Sleep", "weather-clear-night-symbolic", SYSTEM, "idle"),
    Page("display", "Display", "video-display-symbolic", SYSTEM, "display"),
    Page("sound", "Sound", "audio-volume-high-symbolic", SYSTEM, "sound"),
    Page("network", "Network", "network-wireless-symbolic", SYSTEM, "network"),
    Page("bluetooth", "Bluetooth", "bluetooth-active-symbolic", SYSTEM, "bluetooth"),
    Page("input", "Input", "input-keyboard-symbolic", SYSTEM, "input"),
    Page("appearance", "Appearance", "preferences-desktop-appearance-symbolic", PERSONAL, "appearance"),
    Page("notifications", "Notifications", "preferences-system-notifications-symbolic", PERSONAL,
         "notifications"),
    Page("apps", "Apps", "view-app-grid-symbolic", PERSONAL, "apps"),
    Page("region", "Region", "preferences-desktop-locale-symbolic", PERSONAL, "region"),
    Page("updates", "Updates", "software-update-available-symbolic", MAINTENANCE, "updates"),
    Page("storage", "Storage", "drive-harddisk-symbolic", MAINTENANCE, "storage"),
    Page("security", "Security", "security-high-symbolic", MAINTENANCE, "security"),
    Page("users", "Users", "system-users-symbolic", MAINTENANCE, "users"),
    Page("troubleshoot", "Troubleshoot", "applications-engineering-symbolic", MAINTENANCE, "troubleshoot"),
    Page("about", "About", "help-about-symbolic", MAINTENANCE, "about"),
)

BY_ID = {p.id: p for p in PAGES}
# Registry page ids are accepted as deep-link aliases (`--page idle` opens Sleep).
ALIASES = {p.registry_page: p.id for p in PAGES if p.registry_page and p.registry_page != p.id}


def resolve(page_id: str) -> Page | None:
    return BY_ID.get(ALIASES.get(page_id, page_id))


def settings_for(page: Page) -> list[registry.Setting]:
    if page.registry_page is None:
        return []
    return [s for s in registry.SETTINGS if s.page == page.registry_page]


def page_of(setting: registry.Setting) -> Page:
    return next(p for p in PAGES if p.registry_page == setting.page)


def search(text: str) -> list[registry.Setting]:
    """Registry rows whose id, label, description or keywords contain every word of `text`."""
    words = text.lower().split()
    if not words:
        return []
    out = []
    for s in registry.SETTINGS:
        hay = " ".join((s.id, s.label, s.description, *s.keywords, registry.PAGE_LABELS[s.page])).lower()
        if all(w in hay for w in words):
            out.append(s)
    return out
