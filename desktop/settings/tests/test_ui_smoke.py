# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""GTK smoke test (plan-r8 T8 G1/G2): every page builds against the stub backend, every registry row
has a Details expander, writes go through the backend with Undo, privileged rows ask for the password
off-thread (a cancelled prompt reverts), a reader failure shows "Unavailable", and the theme loader
picks and reloads colors.css.

Needs a display: run under xvfb-run, GDK_BACKEND=broadway (with gtk4-broadwayd) or a nested
compositor. Without one every test is skipped, loudly. Nothing touches the real home: the window
gets a Ctx built from the stub environment (fake SL_HOME/SL_SYSFS/SL_ETC, PATH of stubs).

    python3 -m unittest desktop.settings.tests.test_ui_smoke
"""
import contextlib
import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _bootstrap  # noqa: E402,F401
from stubs import StubCase, snapshot  # noqa: E402

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GLib

    Adw.init()
    DISPLAY = Gdk.Display.get_default()
except (ImportError, ValueError) as e:  # no PyGObject or no GTK4/libadwaita typelibs
    DISPLAY, _GI_ERROR = None, e

from seclegion_settings.backend import registry  # noqa: E402

if DISPLAY is not None:
    from seclegion_settings.ui import app, offthread, theme, writeflow  # noqa: E402
    from seclegion_settings.ui import pages as P  # noqa: E402
    from seclegion_settings.ui.window import COMING, SettingsWindow  # noqa: E402
else:
    print("test_ui_smoke: SKIPPED, no display (use xvfb-run, GDK_BACKEND=broadway or a nested "
          "compositor)", file=sys.stderr)


def spin(seconds: float, until=lambda: False) -> None:
    ctx = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end and not until():
        ctx.iteration(False)
        time.sleep(0.01)


@unittest.skipIf(DISPLAY is None, "no display")
class UICase(StubCase):
    def setUp(self):
        super().setUp()
        # These tests read the result right after a widget call; the thread dispatch itself is
        # covered headless by tests/desktop/test_ui_thread.py.
        offthread.synchronous = True
        self.addCleanup(setattr, offthread, "synchronous", False)

    def window(self) -> "SettingsWindow":
        win = SettingsWindow(self.ctx())
        self.addCleanup(win.destroy)
        return win


class EveryPage(UICase):
    def test_every_page_builds_and_every_row_has_details(self):  # G1, G2
        win = self.window()
        win.build_all()
        self.assertEqual(sorted(win.built), sorted(p.id for p in P.PAGES))
        self.assertEqual(len(P.PAGES), 17)
        self.assertEqual(set(win.rows), {s.id for s in registry.SETTINGS})
        with_details = [sid for sid, r in win.rows.items()
                        if isinstance(r.widget, Adw.ExpanderRow) and r.widget.sl_details is not None]
        self.assertEqual(len(with_details), len(registry.SETTINGS))
        print("rows-with-details=ALL" if len(with_details) == len(registry.SETTINGS)
              else f"rows-with-details={len(with_details)}/{len(registry.SETTINGS)}")
        for p in P.PAGES:
            w = win.built[p.id]
            if not P.settings_for(p):
                self.assertIsInstance(w, Adw.StatusPage)
                self.assertEqual(w.get_description(), COMING)
            else:
                self.assertIsInstance(w, Adw.PreferencesPage)

    def test_details_show_file_and_exact_text(self):
        win = self.window()
        win.show_page("sleep")
        r = win.rows["idle.lock_after"]
        r.widget.set_expanded(True)
        text = r.details_text.get_label()
        self.assertIn("file: ~/.config/seclegion/idle.conf", text)
        self.assertIn("loginctl lock-session", text)
        self.assertEqual(r.details_live.get_label(), "no")

    def test_deep_links(self):
        win = self.window()
        for p in P.PAGES:
            self.assertTrue(win.show_page(p.id))
            self.assertEqual(win.stack.get_visible_child_name(), p.id)
        self.assertTrue(win.show_page("idle"))  # registry id alias
        self.assertEqual(win.stack.get_visible_child_name(), "sleep")
        self.assertFalse(win.show_page("nope"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(app.main(["--list-pages"]), 0)
        self.assertEqual([ln.split("\t")[0] for ln in out.getvalue().splitlines()], [p.id for p in P.PAGES])


class Writes(UICase):
    def test_profile_button_writes_toasts_and_undo(self):
        win = self.window()
        r = win.rows["power.profile"]  # the window opens on Power
        self.assertTrue(r.profile_buttons["balanced"].get_active())
        r.profile_buttons["performance"].set_active(True)
        self.assertEqual(self.stub_state()["ppd"], "performance")
        t = win.last_toast
        self.assertEqual(t.get_title(), "Saved. Applies now.")
        self.assertEqual(t.get_button_label(), "Undo")
        t.emit("button-clicked")
        self.assertEqual(self.stub_state()["ppd"], "balanced")
        self.assertTrue(r.profile_buttons["balanced"].get_active())
        self.assertEqual(win.last_toast.get_title(), "Restored the previous value.")

    def test_switch_writes_through_backend(self):
        win = self.window()
        win.show_page("network")
        sw = win.rows["network.wifi"].control
        self.assertTrue(sw.get_active())
        sw.set_active(False)
        self.assertIs(self.stub_state()["wifi"], False)
        self.assertIn("nmcli radio wifi off", self.mutations())

    def test_appearance_theme_picker_auto_and_reset(self):
        win = self.window()
        win.show_page("appearance")
        r = win.rows["appearance.theme"]
        self.assertEqual([t["id"] for t in r.themes], ["seclegion-dark", "seclegion-teal", "seclegion-cyan"])
        self.assertEqual(r.theme_dd.get_selected(), 0)
        self.assertTrue(r.swatch.get_visible())
        self.assertIn("#050f0e", r.swatch.get_label())  # the swatch shows the theme's colours
        r.theme_dd.set_selected(2)
        self.assertEqual(self.stub_state()["theme_id"], "seclegion-cyan")
        self.assertIn("seclegion-theme apply --theme seclegion-cyan", self.mutations())
        win.rows["appearance.auto"].control.set_active(True)
        self.assertEqual(self.stub_state()["theme_auto"], "on")
        win.rows["appearance.reset"].control.emit("clicked")
        self.assertEqual(self.stub_state()["theme_id"], "seclegion-dark")
        self.assertEqual(r.theme_dd.get_selected(), 0)

    def test_range_debounced_write_and_reset_to_default(self):
        win = self.window()
        r = win.rows["power.alert_low"]
        r.spin.set_value(20)
        self.assertFalse((self.home / ".config/seclegion/battery.toml").exists())  # debounced
        r.flush()
        self.assertIn("low = 20", (self.home / ".config/seclegion/battery.toml").read_text())
        self.assertEqual(win.last_toast.get_title(), "Saved.")
        self.assertEqual(r.default_raw(), "15")
        r.reset()
        self.assertIn("low = 15", (self.home / ".config/seclegion/battery.toml").read_text())

    def test_invalid_value_is_a_toast_not_a_crash(self):
        win = self.window()
        win.show_page("apps")
        r = win.rows["apps.terminal"]
        r.control.set_text("not a desktop id")
        r.control.emit("activate")
        self.assertIn("not a valid value", win.last_toast.get_title())
        self.assertFalse((self.home / ".config/xdg-terminals.list").exists())

    def test_privileged_row_cancelled_password_reverts(self):  # issue 18
        pk = self.tmp / "pkexec"
        pk.write_text("#!/bin/sh\nexit 126\n")
        pk.chmod(0o755)
        self.environ["SL_PKEXEC"] = str(pk)
        before_etc, before_home = snapshot(self.etc), snapshot(self.home)
        win = self.window()
        r = win.rows["power.lid_battery"]
        self.assertEqual(r.widget.get_subtitle(), r.s.description)
        stored = r.control.get_selected()
        self.assertFalse(hasattr(r, "copy_button"))
        r.control.set_selected(r.s.choices.index("lock"))
        self.assertEqual(win.last_toast.get_title(),
                         "Lid closed on battery: not changed. The password was not entered.")
        self.assertEqual(r.control.get_selected(), stored)  # back to the stored value
        self.assertFalse(r.spinner.get_visible())
        self.assertTrue(r.control.get_sensitive())
        self.assertIn("HandleLidSwitch=", r.details_text.get_label())
        self.assertEqual((snapshot(self.etc), snapshot(self.home)), (before_etc, before_home))
        self.assertEqual(self.mutations(), [])


class S1Pages(UICase):
    def test_empty_trash_asks_first_and_only_the_confirm_empties(self):
        files = self.home / ".local/share/Trash/files"
        files.mkdir(parents=True)
        (files / "a.bin").write_bytes(b"x")
        win = self.window()
        win.show_page("storage")
        r = win.rows["storage.empty_trash"]
        self.assertEqual(r.control.get_label(), "Empty trash")
        r.control.emit("clicked")
        dlg = r.confirm_dialog
        self.assertIsNotNone(dlg)
        self.assertEqual(self.mutations(), [])
        dlg.emit("response", "cancel")
        self.assertEqual([p.name for p in files.iterdir()], ["a.bin"])
        self.assertEqual(self.mutations(), [])
        dlg.emit("response", "run")
        self.assertEqual(list(files.iterdir()), [])
        self.assertEqual(win.last_toast.get_title(), "Empty trash: done.")

    def test_three_pages_show_rows_not_coming_soon(self):
        win = self.window()
        for pid in ("bluetooth", "storage", "updates"):
            self.assertIsInstance(win.build_page(P.BY_ID[pid]), Adw.PreferencesPage)
        snap = win.rows["updates.snapshot_keep"]
        self.assertEqual(snap.widget.get_subtitle(), registry.get("updates.snapshot_keep").description)
        self.assertIn("asks for the administrator password", snap.widget.get_subtitle())
        self.assertTrue(snap.control.get_sensitive())
        self.assertFalse(win.rows["storage.empty_trash"].open_button)


class S2Pages(UICase):
    def test_three_pages_show_rows_not_coming_soon(self):
        (self.etc / "localtime").symlink_to("../usr/share/zoneinfo/Europe/Berlin")
        win = self.window()
        for pid in ("input", "region", "troubleshoot"):
            self.assertIsInstance(win.build_page(P.BY_ID[pid]), Adw.PreferencesPage)
        self.assertEqual(win.rows["region.timezone"].widget.get_subtitle(),
                         registry.get("region.timezone").description)
        self.assertEqual(win.rows["troubleshoot.diagnostics"].control.get_label(), "Copy to clipboard")

    def test_copy_diagnostics_button_copies_and_toasts(self):
        win = self.window()
        win.show_page("troubleshoot")
        win.rows["troubleshoot.diagnostics"].control.emit("clicked")
        self.assertIn("SecLegion diagnostics", (self.state / "clipboard.txt").read_text())
        self.assertEqual(win.last_toast.get_title(), "Copy diagnostics: done.")


class S3Pages(UICase):
    def test_security_and_users_show_rows_not_coming_soon(self):
        win = self.window()
        for pid in ("security", "users"):
            self.assertIsInstance(win.build_page(P.BY_ID[pid]), Adw.PreferencesPage)
        for sid in ("security.ssh_enable", "security.firewall"):
            self.assertEqual(win.rows[sid].widget.get_subtitle(), registry.get(sid).description)
            self.assertNotEqual(win.rows[sid].widget.get_subtitle(), writeflow.NOT_YET)
        self.assertEqual(win.rows["users.password"].control.get_label(), "Open terminal and change password")


class ReaderFailure(UICase):
    def test_reader_failure_shows_unavailable_with_error(self):
        (self.bin / "powerprofilesctl").write_text("#!/bin/sh\necho 'ppd: boom' >&2\nexit 1\n")
        win = self.window()
        r = win.rows["power.profile"]
        self.assertEqual(r.widget.get_subtitle(), "Unavailable")
        self.assertIn("ppd: boom", r.details_value.get_label())
        self.assertIn("ppd: boom", r.details_text.get_label())
        self.assertFalse(any(b.get_sensitive() for b in r.profile_buttons.values()))


class MissingCapability(UICase):
    SYSFS = "sysfs-nobat"

    def test_unsupported_row_is_greyed_with_the_backend_reason(self):
        win = self.window()
        r = win.rows["power.charge_limit"]
        self.assertTrue(r.widget.get_subtitle().startswith("Not supported on this hardware"))
        self.assertTrue(r.widget.has_css_class("sl-unavailable"))
        self.assertFalse(r.control.get_visible())

    def test_conservation_toggle_is_greyed_with_its_reason_off_lenovo(self):
        r = self.window().rows["power.conservation_mode"]
        self.assertIn("Lenovo IdeaPad and Legion only", r.widget.get_subtitle())
        self.assertTrue(r.widget.has_css_class("sl-unavailable"))
        self.assertFalse(r.control.get_visible())


class SearchAndDetails(UICase):
    def test_search_filters_registry(self):
        win = self.window()
        found = [s.id for s in win.run_search("lid")]
        self.assertIn("power.lid_battery", found)
        self.assertNotIn("sound.volume", found)
        self.assertEqual(win.stack.get_visible_child_name(), "__search__")
        self.assertIn("display.nightlight", [s.id for s in win.run_search("hyprsunset")])  # keyword
        self.assertIn("sound.mute", [s.id for s in win.run_search("sound.mute")])          # id
        win.open_setting("idle.lock_after")
        self.assertEqual(win.stack.get_visible_child_name(), "sleep")
        self.assertTrue(win.rows["idle.lock_after"].widget.get_expanded())

    def test_show_details_everywhere(self):
        win = self.window()
        win.build_all()
        win.show_details_action.change_state(GLib.Variant.new_boolean(True))
        self.assertTrue(all(r.widget.get_expanded() for r in win.rows.values()))
        r = win.rows["sound.volume"]
        r.widget.set_expanded(False)
        self.assertTrue(r.widget.get_expanded())
        win.show_details_action.change_state(GLib.Variant.new_boolean(False))
        self.assertFalse(any(r.widget.get_expanded() for r in win.rows.values()))


class Theming(UICase):
    def test_colors_css_order_and_reload(self):
        env = dict(self.environ)
        self.assertEqual(theme.find_colors_css(env), theme.REPO_COLORS)  # no state theme, no package
        cur = self.home / ".local/state/seclegion/theme/current"
        cur.mkdir(parents=True)
        css = cur / "colors.css"
        css.write_text("@define-color sl_bg #000000;\n")
        th = theme.Theme(env)
        self.addCleanup(th.stop)
        self.assertEqual(th.colors_path, css)
        th.watch()
        n = th.reloads
        css.write_text("@define-color sl_bg #111111;\n")
        spin(5, lambda: th.reloads > n)
        self.assertGreater(th.reloads, n, "FileMonitor did not reload colors.css")
        th.stop()
        self.assertEqual(th._monitors, [])


if __name__ == "__main__":
    unittest.main()
