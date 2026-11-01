# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Run by test_sysmon_ui.py under a private Broadway display (never the live session): builds the
System Monitor window on fake data and prints one JSON line of what it saw. argv[1]: fake DRM root."""
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "desktop", "sysmon"))
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib  # noqa: E402

Adw.init()
if Gdk.Display.get_default() is None:
    print("NO-DISPLAY")
    sys.exit(0)

from seclegion_sysmon import procs  # noqa: E402
from seclegion_sysmon.gpu import GpuReader  # noqa: E402
from seclegion_sysmon.ui import theme  # noqa: E402
from seclegion_sysmon.ui.window import SysmonWindow  # noqa: E402

env = {"SL_DRM_ROOT": sys.argv[1], "SL_PSU_ROOT": sys.argv[1] + "-psu", "PATH": sys.argv[1] + "-bin"}
sent = []
table = [procs.Proc(4242, "mine", "me", 3.0, 10 << 20, True),
         procs.Proc(1, "systemd", "root", 0.1, 5 << 20, False)]


def spin(sec, until=lambda: False):
    ctx, end = GLib.MainContext.default(), time.monotonic() + sec
    while time.monotonic() < end and not until():
        ctx.iteration(False)
        time.sleep(0.01)


colors = theme.apply(dict(os.environ), Gdk.Display.get_default())
win = SysmonWindow(gpus=GpuReader(env), list_procs=lambda: table,
                   send=lambda pid, sig: sent.append((pid, sig)))
out = {"theme": colors is not None, "polling_before_map": win.polling}
win.present()
spin(3, lambda: win.polling)
out["polling_mapped"] = win.polling
out["cpu_label"] = win.cpu_row.sl_value.get_label()
win.show_page("gpu")
spin(5, lambda: bool(win.gpu_rows.rows))  # the page switch reads the GPUs off-thread
out["gpu"] = sorted((r.get_title(), r.get_subtitle()) for r in win.gpu_rows.rows.values())
win.show_page("processes")
win.refresh_procs()
out["rows"] = win.sort_model.get_n_items()
win.search.set_text("systemd")
spin(1, lambda: win.sort_model.get_n_items() == 1)
out["filtered"] = win.sort_model.get_n_items()
win.selection.set_selected(0)
out["other_user_end_enabled"] = win.end_btn.get_sensitive()
win.search.set_text("")
spin(1, lambda: win.sort_model.get_n_items() == 2)
out["first_by_cpu"] = win.sort_model.get_item(0).name
win.selection.set_selected(next(i for i in range(2) if win.sort_model.get_item(i).pid == 4242))
out["own_end_enabled"] = win.end_btn.get_sensitive()
win.end_btn.emit("clicked")
win.confirm_dialog.emit("response", "cancel")
out["sent_after_cancel"] = list(sent)
win.kill_btn.emit("clicked")
win.confirm_dialog.emit("response", "signal")
out["sent"] = [[p, int(s)] for p, s in sent]
out["sigkill"] = int(signal.SIGKILL)
win.set_visible(False)
spin(1, lambda: not win.polling)
out["polling_hidden"] = win.polling
win.destroy()
print(json.dumps(out))
