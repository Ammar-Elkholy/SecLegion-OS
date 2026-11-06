# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_gui_screens under system python3 with GDK_BACKEND=broadway: renders every installer page from
the test fixtures and saves numbered PNGs to $SCREENS (default <repo>/out/screens). Nothing is installed.
File names: NN-page-WxH-lang.png, W and H being the size Broadway really gave. The last stdout line is a
JSON summary: {"shots": [{"file", "page", "lang", "direction", "width", "height", "asked"}, ...]}."""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "installer", "ui", "gtk"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from app import InstallerWindow  # noqa: E402
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
from model import Model  # noqa: E402
from theme import load_css  # noqa: E402

if not Gtk.init_check():
    print("NO-DISPLAY")
    sys.exit(3)
Adw.init()
Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
css = Gtk.CssProvider()
css.load_from_string(load_css())
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                          Gtk.STYLE_PROVIDER_PRIORITY_USER)
OUT = os.environ.get("SCREENS") or os.path.join(ROOT, "out", "screens")
os.makedirs(OUT, exist_ok=True)
VDA = "/dev/disk/by-id/ata-QEMU_HARDDISK_vda"
NVME = "/dev/nvme0n1"
P5 = "/dev/nvme0n1p5"
FAKE_LOG = [
    "==> Partitioning /dev/vda",
    "==> Formatting btrfs, creating subvolumes @ @home @log @pkg @.snapshots",
    ":: Synchronizing package databases...",
    ":: Installing seclegion-base seclegion-desktop seclegion-theme (3)",
    "==> Installing the unified kernel image",
]
FAILED_LOG = FAKE_LOG + [
    "error: failed retrieving file 'seclegion-ai' from the offline repo",
    "ERROR: package installation failed (exit 1)",
]
SIZES = ((1280, 800), (800, 600))
app = Adw.Application(application_id="org.seclegion.InstallerScreens")
app.register(None)
ctx = GLib.MainContext.default()
shots = []


def pump(n=60):
    for _ in range(n):
        ctx.iteration(False)
        time.sleep(0.02)


def walk(w):
    yield w
    c = w.get_first_child()
    while c:
        yield from walk(c)
        c = c.get_next_sibling()


def facts(name):
    with open(os.path.join(HERE, "fixtures", name)) as f:
        return json.load(f)


def fill(m, disk):
    u = m.pages["user"]
    u.set_username("ammar")
    u.set_hostname("seclegion")
    u.set_password("screens-only")
    u.set_confirm("screens-only")
    m.pages["disk"].set_disk(disk)
    m.pages["hardware"].loader = lambda: {
        "messages": ["GPU: Intel integrated, drivers: mesa", "CPU: microcode intel-ucode"],
        "packages": ["mesa", "intel-ucode", "vulkan-intel"]}
    m.pages["progress"].lines = list(FAKE_LOG)
    m.pages["progress"].log_path = "/var/log/seclegion-installer.log"


def make(kind):
    if kind in ("partition", "review-partition"):
        m = Model(facts("facts_partitions.json"))
        fill(m, NVME)
        m.pages["disk"].set_partition(P5)
    elif kind == "alongside":
        m = Model(facts("facts_partitions.json"))
        fill(m, NVME)
        m.pages["disk"].set_mode("alongside")
    else:
        m = Model(facts("facts.json"))
        fill(m, VDA)
    if kind == "error":
        m.pages["progress"].lines = list(FAILED_LOG)
    return m


def snap(win, num, page, lang, asked):
    pump(60)
    w, h = win.get_width(), win.get_height()
    name = f"{num:02d}-{page}-{w}x{h}-{lang}.png"
    s = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(win).snapshot(s, w, h)
    win.get_native().get_renderer().render_texture(s.to_node(), None).save_to_png(os.path.join(OUT, name))
    shots.append({"file": name, "page": page, "lang": lang, "direction": win.get_direction().value_nick,
                  "width": w, "height": h, "asked": f"{asked[0]}x{asked[1]}"})


def pick_arabic(win, m):
    m.goto("language")
    pump()
    row = next(r for r in walk(win.holder)
               if isinstance(r, Adw.ActionRow) and r.get_title() == "العربية")
    row.get_activatable_widget().set_active(True)
    pump(40)  # the page redraw is an idle callback


def shoot(num, page, kind, key, size, lang="en"):
    Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
    m = make(kind)
    win = InstallerWindow(app, m, kiosk_error=(key == "kiosk_error"))
    win.set_default_size(*size)
    win.present()
    pump()
    if lang == "ar":
        pick_arabic(win, m)
    if key == "error":
        m.index = [p.key for p in m.visible()].index("progress")  # a real failure happens there
        m.install_failed()
        win.render()
    elif key == "about":
        win.activate_action("win.about", None)
        pump(80)
    elif key != "kiosk_error":
        m.goto(key)
    pump()
    snap(win, num, page, lang, size)
    win.destroy()
    Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
    pump(5)


# (number, name, scenario, page key, languages)
FLOW = (
    (1, "welcome", "erase", "welcome", ("en", "ar")),
    (2, "language", "erase", "language", ("en", "ar")),
    (3, "disk", "erase", "disk", ("en", "ar")),
    (4, "disk-partition", "partition", "disk", ("en",)),
    (5, "alongside", "alongside", "alongside", ("en",)),
    (6, "encryption", "erase", "encryption", ("en",)),
    (7, "user", "erase", "user", ("en",)),
    (8, "hardware", "erase", "hardware", ("en",)),
    (9, "extras", "erase", "tiers", ("en",)),
    (10, "review", "erase", "review", ("en", "ar")),
    (11, "review-partition", "review-partition", "review", ("en",)),
    (12, "progress", "erase", "progress", ("en",)),
    (13, "finished", "erase", "finished", ("en",)),
    (14, "error", "error", "error", ("en",)),
    (15, "kiosk-error", "erase", "kiosk_error", ("en",)),
    (16, "about", "erase", "about", ("en",)),
)
for size in SIZES:
    for num, page, kind, key, langs in FLOW:
        for lang in langs:
            shoot(num, page, kind, key, size, lang)
print(json.dumps({"out": OUT, "shots": shots}), flush=True)
os._exit(0)  # skip interpreter teardown: GTK objects can segfault there after the last window closes
