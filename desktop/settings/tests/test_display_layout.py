# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Display page (issues 14 and 18): the layout row runs the display menu, the outputs row lists the
connected displays. hyprctl and the display menu are both stubs (stub_tool.py); monitor layouts come
from fixtures/hyprctl/monitors-*.json. Nothing here can reach the live Hyprland.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import unittest

import _bootstrap  # noqa: F401
from seclegion_settings.backend import capabilities, readers, registry, writers
from seclegion_settings.backend.env import Ctx, Unavailable
from seclegion_settings.ui import writeflow
from stubs import FIXTURES, HERE, StubCase

MENU = HERE.parents[2] / "desktop" / "display" / "seclegion-display-menu"
MODES = ("laptop", "extend", "mirror", "external")
QUERY = ["hyprctl", "-j", "monitors", "all"]


def fixture(name):
    return json.loads((FIXTURES / "hyprctl" / f"monitors-{name}.json").read_text())


def load_menu():
    """The display menu as a module (its main() is behind __name__; loading runs nothing)."""
    loader = importlib.machinery.SourceFileLoader("sl_display_menu", str(MENU))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class DisplayCase(StubCase):
    def layout(self, name):
        (self.state / "state.json").write_text(json.dumps({"monitors": fixture(name)}))

    def menu_calls(self):
        return [c for c in self.calls() if c[0] == "seclegion-display-menu"]


class LayoutReader(DisplayCase):
    def test_reads_the_mode_from_one_hyprctl_call(self):
        for name, want in (("single", "laptop"), ("laptop", "laptop"), ("extend", "extend"),
                           ("mirror", "mirror"), ("external", "external")):
            with self.subTest(name):
                self.layout(name)
                (self.state / "calls.log").unlink(missing_ok=True)
                self.assertEqual(registry.read_value(registry.get("display.layout"), self.ctx()),
                                 (want, ""))
                self.assertEqual(self.calls(), [QUERY])
        self.assertEqual(self.mutations(), [])

    def test_outputs_one_line_each(self):
        self.layout("extend")
        self.assertEqual(registry.read_value(registry.get("display.outputs"), self.ctx()), (
            "eDP-1: 2560x1600@165Hz, scale 1.6\nHDMI-A-1: 1920x1080@59.95Hz, scale 1", ""))
        self.layout("laptop")
        value, _ = registry.read_value(registry.get("display.outputs"), self.ctx())
        self.assertEqual(value.splitlines()[1], "HDMI-A-1: 1920x1080@59.95Hz, scale 1, off")
        self.assertEqual(self.mutations(), [])

    def test_fallback_monitor_is_not_an_output(self):
        fb = dict(fixture("single")[0], name="FALLBACK", id=-1)
        (self.state / "state.json").write_text(json.dumps({"monitors": [*fixture("single"), fb]}))
        self.assertEqual(registry.read_value(registry.get("display.layout"), self.ctx()), ("laptop", ""))
        self.assertEqual(readers.display_outputs(self.ctx()).count("\n"), 0)


class LayoutWriter(DisplayCase):
    def test_writer_runs_the_menu_with_the_mode(self):
        s = registry.get("display.layout")
        menu = str(self.bin / "seclegion-display-menu")
        for mode in ("mirror", "external", "laptop", "extend"):
            with self.subTest(mode):
                res = registry.write(s, self.ctx(), mode)
                self.assertEqual(res.commands, [[menu, mode]])
                self.assertEqual(self.menu_calls()[-1], ["seclegion-display-menu", mode])  # the stub ran
                self.assertEqual(registry.read_value(s, self.ctx()), (mode, ""))
        self.assertEqual([c[1:] for c in self.menu_calls()], [[m] for m in ("mirror", "external",
                                                                            "laptop", "extend")])

    def test_dry_run_lists_the_command_and_runs_no_menu(self):
        res = registry.write(registry.get("display.layout"), self.ctx(dry_run=True), "mirror")
        self.assertEqual(res.commands, [[str(self.bin / "seclegion-display-menu"), "mirror"]])
        self.assertEqual(self.menu_calls(), [])

    def test_local_bin_menu_comes_first(self):
        lb = self.home / ".local" / "bin"
        lb.mkdir(parents=True)
        shutil.copy(self.bin / "seclegion-display-menu", lb / "seclegion-display-menu")
        res = registry.write(registry.get("display.layout"), self.ctx(), "mirror")
        self.assertEqual(res.commands, [[str(lb / "seclegion-display-menu"), "mirror"]])
        self.assertEqual(self.menu_calls(), [["seclegion-display-menu", "mirror"]])

    def test_single_output_refused_and_runs_nothing(self):
        self.layout("single")
        s = registry.get("display.layout")
        for mode in MODES:
            with self.subTest(mode):
                with self.assertRaises(Unavailable) as cm:
                    registry.write(s, self.ctx(), mode)
                self.assertEqual(str(cm.exception), "No second display is connected.")
                self.assertEqual(writeflow.failure(s, cm.exception), "No second display is connected.")
        self.assertEqual(self.menu_calls(), [])
        self.assertEqual({tuple(c) for c in self.calls()}, {tuple(QUERY)})  # only the read
        self.assertEqual(self.mutations(), [])

    def test_no_laptop_screen_refused(self):
        two = [dict(m, name=n) for m, n in zip(fixture("extend"), ("DP-1", "DP-2"), strict=True)]
        (self.state / "state.json").write_text(json.dumps({"monitors": two}))
        with self.assertRaises(Unavailable) as cm:
            registry.write(registry.get("display.layout"), self.ctx(), "mirror")
        self.assertEqual(str(cm.exception), writers.NO_LAPTOP_SCREEN)
        self.assertEqual(self.menu_calls(), [])


class LayoutCapability(DisplayCase):
    def test_hidden_without_a_hyprland_session(self):
        del self.environ["HYPRLAND_INSTANCE_SIGNATURE"]
        for sid in ("display.layout", "display.outputs"):
            st = registry.row(registry.get(sid), self.ctx())
            self.assertFalse(st.visible, sid)
            self.assertIn("Hyprland is not running", st.reason)
        self.assertEqual(self.calls(), [])

    def test_hidden_without_the_menu(self):
        os.unlink(self.bin / "seclegion-display-menu")
        st = registry.row(registry.get("display.layout"), self.ctx())
        self.assertFalse(st.visible)
        self.assertEqual(st.reason, "Not available: the display menu is not installed")
        self.assertTrue(registry.row(registry.get("display.outputs"), self.ctx()).visible)
        self.assertIsNone(capabilities.find_display_menu(self.ctx()))

    def test_choice_labels_match_the_menu(self):
        self.assertEqual(registry.CHOICE_LABELS["display.layout"], load_menu().MODES)
        self.assertEqual(registry.get("display.layout").choices, tuple(load_menu().MODES))


class MenuParity(unittest.TestCase):
    """The reader splits the outputs as the display menu does, and the menu itself has nothing to do
    on one output (so the writer's refusal never hides a working mode)."""

    def test_split_matches_the_menu(self):
        menu = load_menu()
        self.assertEqual(readers.INTERNAL_PREFIXES, menu.INTERNAL_PREFIXES)
        self.assertEqual(readers.FALLBACK, menu.FALLBACK)
        ctx = Ctx({})
        for name in ("single", "laptop", "extend", "mirror", "external"):
            ms = fixture(name)
            self.assertEqual(readers.split_monitors(ctx, ms), menu.split(ms), name)

    def test_menu_renders_nothing_on_one_output(self):
        menu = load_menu()
        for mode in MODES:
            self.assertEqual(menu.render(mode, fixture("single")), [], mode)


if __name__ == "__main__":
    unittest.main()
