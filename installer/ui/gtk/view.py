# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""GTK4 view for pages 1-5: build_widget(page) returns the page's Gtk widget."""

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

BUILDERS = {"welcome": p1_welcome.widget, "language": p2_language.widget, "disk": p3_disk.widget,
            "alongside": p4_alongside.widget, "manual": p5_manual.widget,
            "encryption": p6_encryption.widget, "user": p7_user.widget, "review": p8_review.widget,
            "progress": p9_progress.widget, "error": p10_error.widget,
            "hardware": p11_hardware.widget, "tiers": p12_tiers.widget,
            "finished": p13_finished.widget, "kiosk_error": p14_kiosk_error.widget,
            "about": p15_about.widget, "timezone": p16_timezone.widget}


def build_widget(page):
    return BUILDERS[page.key](page)
