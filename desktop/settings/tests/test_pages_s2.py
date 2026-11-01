# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r12 S2: the Input, Region and Troubleshoot pages (backend rows, against the stub tools).

User rows write only under the fake HOME; the one root row (time zone) previews here, and
seclegion-root-apply runs the stub timedatectl. Nothing here touches the real home, /etc or a real tool.
"""

import json
import unittest

import _bootstrap  # noqa: F401
from seclegion_settings.backend import registry, render, rootapply
from seclegion_settings.backend.env import Ctx, InvalidValue, Refused, Unavailable
from stubs import StubCase, snapshot


def row(sid: str, ctx: Ctx):
    return registry.row(registry.get(sid), ctx)


def put(case: StubCase, sid: str, raw: str, dry_run: bool = False):
    return registry.write(registry.get(sid), case.ctx(dry_run=dry_run), raw)


class Gates(unittest.TestCase):
    def test_user_rows_never_write_outside_home(self):  # G3
        self.assertEqual([s.id for s in registry.SETTINGS if not s.privileged and s.file.startswith("/")], [])

    def test_every_root_row_says_so(self):  # G4
        self.assertEqual(
            [s.id for s in registry.SETTINGS if s.privileged and "Needs root" not in s.description], []
        )

    def test_the_three_pages_have_rows(self):
        self.assertLessEqual({"input", "region", "troubleshoot"}, {s.page for s in registry.SETTINGS})

    def test_input_rows_are_in_the_home_lua_file(self):  # G5
        for sid in ("repeat_rate", "repeat_delay", "tap_to_click", "natural_scroll", "disable_while_typing"):
            self.assertEqual(registry.get("input." + sid).file, "~/.config/seclegion/input.lua")


class InputTests(StubCase):
    def lua(self) -> str:
        return (self.home / ".config/seclegion/input.lua").read_text()

    def test_defaults_without_a_file(self):
        vals = {
            s: row("input." + s, self.ctx()).value
            for s in ("repeat_rate", "repeat_delay", "tap_to_click", "natural_scroll", "disable_while_typing")
        }
        self.assertEqual(
            vals,
            {
                "repeat_rate": 25,
                "repeat_delay": 600,
                "tap_to_click": True,
                "natural_scroll": False,
                "disable_while_typing": True,
            },
        )

    def test_write_renders_the_whole_file_and_round_trips(self):
        res = put(self, "input.repeat_rate", "40")
        self.assertEqual(res.files, ["~/.config/seclegion/input.lua"])
        self.assertEqual(self.lua(), render.render_input_lua({**render.INPUT_DEFAULTS, "repeat_rate": 40}))
        put(self, "input.natural_scroll", "on")
        put(self, "input.tap_to_click", "off")
        put(self, "input.repeat_delay", "300")
        put(self, "input.disable_while_typing", "off")
        text = self.lua()
        for want in (
            "repeat_rate = 40,",
            "repeat_delay = 300,",
            "tap_to_click = false,",
            "natural_scroll = true,",
            "disable_while_typing = false,",
        ):
            self.assertIn(want, text)
        self.assertEqual(row("input.repeat_rate", self.ctx()).value, 40)
        self.assertIs(row("input.natural_scroll", self.ctx()).value, True)
        self.assertIs(row("input.tap_to_click", self.ctx()).value, False)

    def test_write_never_reloads_or_runs_anything(self):
        put(self, "input.repeat_rate", "40")
        self.assertEqual(self.mutations(), [])
        self.assertFalse((self.state / "calls.log").exists())

    def test_dry_run_writes_nothing(self):
        res = put(self, "input.tap_to_click", "off", dry_run=True)
        self.assertIn("tap_to_click = false,", res.texts["~/.config/seclegion/input.lua"])
        self.assertEqual(snapshot(self.home), {})

    def test_out_of_range_refused_before_any_write(self):  # negative
        for sid, bad in (
            ("repeat_rate", "9"),
            ("repeat_rate", "81"),
            ("repeat_delay", "149"),
            ("repeat_delay", "1001"),
            ("repeat_rate", "1); os.exit(1) --"),
            ("tap_to_click", "maybe"),
        ):
            with self.subTest(f"{sid} {bad}"), self.assertRaises(InvalidValue):
                put(self, "input." + sid, bad)
        self.assertEqual(snapshot(self.home), {})

    def test_crafted_file_falls_back_to_defaults(self):
        d = self.home / ".config/seclegion"
        d.mkdir(parents=True)
        (d / "input.lua").write_text("repeat_rate = 99999,\n repeat_delay = abc,\n tap_to_click = 3,\n")
        self.assertEqual(row("input.repeat_rate", self.ctx()).value, 25)
        self.assertEqual(row("input.repeat_delay", self.ctx()).value, 600)
        self.assertIs(row("input.tap_to_click", self.ctx()).value, True)

    def test_symlinked_config_dir_cannot_carry_the_write_out_of_home(self):  # negative
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.home / ".config").mkdir()
        (self.home / ".config/seclegion").symlink_to(outside)
        with self.assertRaises(Refused):
            put(self, "input.repeat_rate", "40")
        self.assertEqual(list(outside.iterdir()), [])


class RegionTests(StubCase):
    def test_clock_default_and_write(self):
        self.assertEqual(row("region.clock_format", self.ctx()).value, "24h")
        res = put(self, "region.clock_format", "12h")
        self.assertEqual(res.files, ["~/.config/seclegion/clock.toml"])
        self.assertEqual(
            (self.home / ".config/seclegion/clock.toml").read_text(),
            # REUSE-IgnoreStart
            '# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n[clock]\nformat = "12h"\n',
            # REUSE-IgnoreEnd
        )
        self.assertEqual(row("region.clock_format", self.ctx()).value, "12h")

    def test_clock_rejects_other_values(self):
        with self.assertRaises(InvalidValue):
            put(self, "region.clock_format", "26h")
        self.assertEqual(snapshot(self.home), {})

    def test_locale_is_read_only_info(self):
        (self.etc / "locale.conf").write_text("LANG=de_DE.UTF-8\n")
        r = row("region.locale", self.ctx())
        self.assertEqual(r.value, "de_DE.UTF-8")
        with self.assertRaises(Refused):
            put(self, "region.locale", "C")

    def test_timezone_read_from_the_localtime_link(self):
        self.assertTrue(row("region.timezone", self.ctx()).error)
        (self.etc / "localtime").symlink_to("../usr/share/zoneinfo/Europe/Berlin")
        self.assertEqual(row("region.timezone", self.ctx()).value, "Europe/Berlin")

    def zoneinfo(self):
        z = self.tmp / "zoneinfo"
        (z / "Europe").mkdir(parents=True)
        (z / "Europe/Berlin").write_bytes(b"TZif2")
        self.environ["SL_ZONEINFO"] = str(z)

    def test_timezone_previews_timedatectl_and_runs_nothing(self):
        self.zoneinfo()
        s = registry.get("region.timezone")
        self.assertTrue(s.privileged)
        self.assertTrue(registry.root_ready(s))
        with self.assertRaises(Refused):  # sandboxed ctx: never the real pkexec
            put(self, "region.timezone", "Europe/Berlin")
        res = put(self, "region.timezone", "Europe/Berlin", dry_run=True)
        self.assertEqual(res.commands, [["/usr/bin/timedatectl", "set-timezone", "Europe/Berlin"]])
        self.assertEqual(res.files, [])
        self.assertEqual(list(self.etc.iterdir()), [])
        self.assertEqual(snapshot(self.home), {})
        self.assertEqual(self.mutations(), [])

    def test_timezone_rejects_paths(self):  # negative
        self.zoneinfo()
        for bad in ("../../etc/passwd", "/etc/shadow", "a b", "Europe/../x", "a/b/c/d", "Nope/Zone"):
            with self.subTest(bad), self.assertRaises(InvalidValue):
                put(self, "region.timezone", bad, dry_run=True)

    def test_root_apply_runs_timedatectl(self):
        self.zoneinfo()
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        self.assertEqual(rootapply.apply("region.timezone", "Europe/Berlin", True, env), 0)
        self.assertEqual(self.mutations(), [])  # dry run: nothing ran
        self.assertEqual(rootapply.apply("region.timezone", "Europe/Berlin", False, env), 0)
        self.assertEqual(self.mutations(), ["timedatectl set-timezone Europe/Berlin"])
        self.assertEqual(snapshot(self.etc), {})
        self.assertFalse((self.tmp / "rstate").exists())


class TroubleshootTests(StubCase):
    def test_restart_rows_run_systemctl_user_restart(self):
        for sid, unit in (("waybar", "waybar"), ("swaync", "swaync"), ("hypridle", "hypridle")):
            with self.subTest(sid):
                res = put(self, "troubleshoot.restart_" + sid, "run")
                self.assertEqual(res.commands, [["systemctl", "--user", "restart", unit + ".service"]])
        self.assertEqual(
            self.mutations(),
            [
                "systemctl --user restart waybar.service",
                "systemctl --user restart swaync.service",
                "systemctl --user restart hypridle.service",
            ],
        )

    def test_restart_dry_run_runs_nothing(self):
        put(self, "troubleshoot.restart_waybar", "run", dry_run=True)
        self.assertEqual(self.mutations(), [])

    def test_restart_needs_the_word_run(self):
        with self.assertRaises(InvalidValue):
            put(self, "troubleshoot.restart_waybar", "now")
        self.assertEqual(self.mutations(), [])

    def test_diagnostics_copy_is_redacted(self):
        user, host_ip = "ammar", "192.168.1.77"
        self.environ["USER"] = user
        (self.state / "state.json").write_text(
            json.dumps(
                {
                    "failed_units": f"swaync.service failed {user} {host_ip}",
                    "configerrors": (
                        f"{self.home}/.config/hypr/x.lua:3: bad; mac AA:BB:CC:DD:EE:FF; "
                        "fe80::1ff:fe23:4567:890a"
                    ),
                }
            )
        )
        res = put(self, "troubleshoot.diagnostics", "run")
        self.assertEqual(res.commands, [["wl-copy"]])
        clip = (self.state / "clipboard.txt").read_text()
        self.assertIn("SecLegion diagnostics", clip)
        self.assertIn("hyprland: 0.56.2", clip)
        self.assertIn("~/.config/hypr/x.lua:3", clip)
        self.assertIn("swaync.service failed <user> <ip>", clip)
        for leak in (str(self.home), user, host_ip, "AA:BB:CC:DD:EE:FF", "fe80::"):
            self.assertNotIn(leak, clip)

    def test_diagnostics_dry_run_copies_nothing(self):
        put(self, "troubleshoot.diagnostics", "run", dry_run=True)
        self.assertFalse((self.state / "clipboard.txt").exists())

    def test_diagnostics_hidden_without_wl_copy(self):
        (self.bin / "wl-copy").unlink()
        r = row("troubleshoot.diagnostics", self.ctx())
        self.assertFalse(r.visible)
        self.assertIn("wl-copy", r.reason)
        with self.assertRaises(Unavailable):
            put(self, "troubleshoot.diagnostics", "run")


class RedactTests(unittest.TestCase):
    def test_redact(self):
        out = render.redact(
            "/home/bob/x bob@lab 10.0.0.1 aa-bb-cc-dd-ee-ff lab ::1 12:34:56 bobby",
            home="/home/bob",
            user="bob",
            host="lab",
        )
        self.assertEqual(out, "~/x <user>@<host> <ip> <mac> <host> <ip> 12:34:56 bobby")


if __name__ == "__main__":
    unittest.main()
