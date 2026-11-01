# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Registry completeness (G1), round trips and goldens (G2), capabilities (G3), dry-run (G4),
hypridle ordering and AC guard (G5), real-host read-only run (G6).

Nothing here touches the real home, sysfs or tools except the G6 test, which only reads.
"""

import contextlib
import dataclasses
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from seclegion_settings.backend import capabilities, cli, registry, render
from seclegion_settings.backend.env import (
    AuthCancelled,
    CommandFailed,
    Ctx,
    InvalidValue,
    NotAuthorized,
    Refused,
    WriteResult,
)
from stubs import FIXTURES, HERE, TOOLS, StubCase, make_bin, snapshot

ROOT = HERE.parents[2]
LAUNCHER = ROOT / "tools" / "seclegion-set"


def run_cli(environ, *argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv), environ=environ)
        except SystemExit as e:  # argparse usage errors
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


# One new value per user-level row, different from every default.
ROUND_TRIP = {
    "power.profile": "performance",
    "power.lid_ignore": "on",
    "power.conservation_mode": "on",
    "power.alert_low": "20",
    "power.alert_critical": "5",
    "idle.lock_after": "3",
    "idle.screen_off_after": "never",
    "idle.suspend_battery": "30",
    "idle.suspend_ac": "60",
    "idle.lock_before_sleep": "off",
    "display.brightness": "35",
    "display.kbd_brightness": "66",
    "display.nightlight": "on",
    "display.nightlight_temp": "4000",
    "display.layout": "mirror",
    "sound.volume": "25",
    "sound.mute": "on",
    "sound.mic_mute": "on",
    "network.wifi": "off",
    "network.airplane": "on",
    "network.bluetooth": "off",
    "notifications.dnd": "on",
    "power.autolock": "30m",
    "apps.file_manager": "thunar2.desktop",
    "apps.browser": "brave-browser.desktop",
    "apps.terminal": "kitty.desktop",
    "appearance.theme": "seclegion-teal",
    "appearance.auto": "on",
    "appearance.theme_mode": "auto",
    "appearance.contrast": "high",
    "bluetooth.power": "on",  # network.bluetooth (above) leaves it off first
    "storage.low_disk": "80",
    "input.repeat_rate": "40",
    "input.repeat_delay": "300",
    "input.tap_to_click": "off",
    "input.natural_scroll": "on",
    "input.disable_while_typing": "off",
    "region.clock_format": "12h",
}


class RegistryTests(unittest.TestCase):
    def test_every_row_complete(self):  # G1
        self.assertGreater(len(registry.SETTINGS), 30)
        ids = [s.id for s in registry.SETTINGS]
        self.assertEqual(len(ids), len(set(ids)))
        for s in registry.SETTINGS:
            with self.subTest(s.id):
                self.assertTrue(callable(s.reader))
                self.assertTrue(callable(s.writer))
                self.assertTrue(s.label.strip())
                self.assertTrue(s.description.strip())
                self.assertTrue(s.file or s.command, "needs a file or command description")
                self.assertIn(s.kind, registry.KINDS)
                self.assertIn(s.page, registry.PAGES)
                if s.kind == "choice":
                    self.assertTrue(s.choices)
                if s.kind == "range":
                    self.assertIsNotNone(s.minimum)
                    self.assertIsNotNone(s.maximum)

    def test_round_trip_table_covers_every_user_row(self):
        user = {s.id for s in registry.SETTINGS if not s.privileged and not s.readonly and s.kind != "action"}
        self.assertEqual(user, set(ROUND_TRIP))

    def test_cli_exposes_registry_rows(self):
        env = {"PATH": "", "SL_HOME": "/nonexistent", "SL_SYSFS": "/nonexistent"}
        rc, out, _ = run_cli(env, "list", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual([r["id"] for r in json.loads(out)], [s.id for s in registry.SETTINGS])


class RoundTripTests(StubCase):
    def test_round_trip_every_user_row(self):  # G2
        for sid, new in ROUND_TRIP.items():
            with self.subTest(sid):
                s = registry.get(sid)
                ctx = self.ctx()
                before, err = registry.read_value(s, ctx)
                self.assertEqual(err, "")
                res = registry.write(s, ctx, new)
                self.assertTrue(res.files or res.commands, "a write must list what it did")
                after, err = registry.read_value(s, self.ctx())
                self.assertEqual(err, "")
                self.assertEqual(after, s.coerce(new))
                self.assertNotEqual(before, after)

    def test_write_result_lists_exactly(self):
        res = registry.write(registry.get("sound.volume"), self.ctx(), "25")
        self.assertEqual(res.commands, [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "25%"]])
        self.assertEqual(res.files, [])
        self.assertTrue(res.applied_live)
        res = registry.write(registry.get("idle.lock_after"), self.ctx(), "3")
        self.assertEqual(res.files, ["~/.config/seclegion/idle.conf"])
        self.assertEqual(res.commands, [])
        self.assertFalse(res.applied_live)

    def test_nightlight_live_commands(self):
        registry.write(registry.get("display.nightlight_temp"), self.ctx(), "4200")  # off: file only
        self.assertEqual(self.mutations(), [])
        registry.write(registry.get("display.nightlight"), self.ctx(), "on")
        registry.write(registry.get("display.nightlight"), self.ctx(), "off")
        self.assertEqual(
            self.mutations(), ["hyprctl hyprsunset temperature 4200", "hyprctl hyprsunset identity"]
        )

    def test_theme_manager_rows_run_seclegion_theme(self):
        self.assertEqual(
            registry.read_value(registry.get("appearance.theme"), self.ctx())[0], "seclegion-dark"
        )
        registry.write(registry.get("appearance.theme"), self.ctx(), "wallpaper:0123abcd")
        registry.write(registry.get("appearance.auto"), self.ctx(), "on")
        registry.write(registry.get("appearance.reset"), self.ctx(), "run")
        self.assertEqual(
            self.mutations(),
            [
                "seclegion-theme apply --theme wallpaper:0123abcd",
                "seclegion-theme auto on",
                "seclegion-theme reset",
            ],
        )
        self.assertEqual(
            registry.read_value(registry.get("appearance.theme"), self.ctx())[0], "seclegion-dark"
        )
        for bad in ("../x", "nope", "wallpaper:xyz"):
            with self.assertRaises(InvalidValue):
                registry.write(registry.get("appearance.theme"), self.ctx(), bad)
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("appearance.reset"), self.ctx(), "now")
        self.assertEqual(len(self.mutations()), 3)

    def test_theme_goes_through_seclegion_theme_only(self):
        registry.write(registry.get("appearance.theme_mode"), self.ctx(), "auto")
        registry.write(registry.get("appearance.contrast"), self.ctx(), "high")
        self.assertEqual(self.stub_state()["theme_mode"], "auto")
        self.assertEqual(self.stub_state()["theme_contrast"], "high")
        self.assertEqual(
            self.mutations(),
            [
                "seclegion-theme apply --mode auto --contrast normal",
                "seclegion-theme apply --mode auto --contrast high",
            ],
        )
        self.assertEqual(list(self.home.rglob("*")), [], "the backend writes no colour files")

    def test_idle_goldens(self):
        registry.write(registry.get("idle.lock_after"), self.ctx(), "5")  # default values rendered
        idle = self.home / ".config/seclegion/idle.conf"
        self.assertEqual(idle.read_text(), self.golden("idle-default.conf"))
        for sid, v in (
            ("idle.lock_after", "3"),
            ("idle.screen_off_after", "5"),
            ("idle.suspend_battery", "10"),
            ("idle.suspend_ac", "30"),
            ("idle.lock_before_sleep", "off"),
        ):
            registry.write(registry.get(sid), self.ctx(), v)
        self.assertEqual(
            (self.home / ".config/seclegion/idle.conf").read_text(),
            self.golden("idle-ac30-nolock-before-sleep.conf"),
        )

    def test_user_state_goldens(self):
        registry.write(registry.get("power.alert_critical"), self.ctx(), "10")
        registry.write(registry.get("power.alert_low"), self.ctx(), "20")
        cfg = self.home / ".config/seclegion"
        self.assertEqual((cfg / "battery.toml").read_text(), self.golden("battery.toml"))
        registry.write(registry.get("display.nightlight_temp"), self.ctx(), "4000")
        registry.write(registry.get("display.nightlight"), self.ctx(), "on")
        self.assertEqual((cfg / "nightlight.toml").read_text(), self.golden("nightlight.toml"))

    def test_cross_field_rules(self):
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("power.alert_critical"), self.ctx(), "20")  # not below low=15
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("idle.screen_off_after"), self.ctx(), "3")  # before lock=5
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("idle.lock_after"), self.ctx(), "15")  # at/after screen off=10
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("sound.volume"), self.ctx(), "101")
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("apps.browser"), self.ctx(), "../evil;rm.desktop")
        self.assertEqual(list(self.home.rglob("*")), [])


UNIT = ".config/systemd/user/seclegion-lid-inhibit.service"


class LidIgnoreTests(StubCase):
    def test_on_writes_unit_and_enables(self):
        s = registry.get("power.lid_ignore")
        self.assertIs(registry.read_value(s, self.ctx())[0], False)
        res = registry.write(s, self.ctx(), "on")
        self.assertEqual((self.home / UNIT).read_text(), self.golden("seclegion-lid-inhibit.service"))
        self.assertEqual(
            self.mutations(),
            ["systemctl --user daemon-reload", "systemctl --user enable --now seclegion-lid-inhibit.service"],
        )
        self.assertTrue(res.applied_live)
        self.assertIs(registry.read_value(s, self.ctx())[0], True)

    def test_off_disables(self):
        s = registry.get("power.lid_ignore")
        registry.write(s, self.ctx(), "on")
        registry.write(s, self.ctx(), "off")
        self.assertEqual(self.mutations()[-1], "systemctl --user disable --now seclegion-lid-inhibit.service")
        self.assertIs(registry.read_value(s, self.ctx())[0], False)

    def test_dry_run_writes_nothing(self):
        res = registry.write(registry.get("power.lid_ignore"), self.ctx(dry_run=True), "on")
        self.assertEqual(list(self.home.rglob("*")), [])
        self.assertEqual(self.mutations(), [])
        self.assertIn("handle-lid-switch", res.texts["~/" + UNIT])

    def test_logind_rows_point_at_the_toggle(self):
        # issue 18: the rows now write through the password prompt; no command is shown any more
        for sid in ("power.lid_battery", "power.lid_ac", "power.lid_docked"):
            d = registry.get(sid).description
            self.assertIn("use the toggle above", d)
            self.assertIn("administrator password", d)
            self.assertNotIn("sudo", d)


class PrivilegedTests(StubCase):
    PRIV = [s.id for s in registry.SETTINGS if s.privileged]

    def test_set_refuses_and_writes_nothing(self):
        for sid in self.PRIV:
            with self.subTest(sid):
                s = registry.get(sid)
                val = {"toggle": "on", "text": "Europe/Berlin"}.get(s.kind) or (
                    s.choices[0] if s.choices else str(s.minimum))
                rc, _, err = run_cli(self.environ, "set", sid, val)
                self.assertEqual(rc, 3, err)
        self.assertEqual(list(self.etc.rglob("*")), [])
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_dry_run_shows_exact_text(self):
        cases = {
            ("power.lid_ac", "lock"): ("/etc/systemd/logind.conf.d/50-seclegion-lid.conf", "logind-lid.conf"),
            ("power.power_button", "suspend"): (
                "/etc/systemd/logind.conf.d/50-seclegion-power.conf",
                "logind-power.conf",
            ),
            ("power.charge_limit", "80"): (
                "/etc/tmpfiles.d/50-seclegion-charge-limit.conf",
                "charge-limit.conf",
            ),
        }
        for (sid, v), (path, golden) in cases.items():
            with self.subTest(sid):
                res = registry.write(registry.get(sid), self.ctx(dry_run=True), v)
                self.assertEqual(res.files, [path])
                self.assertEqual(res.texts[path], self.golden(golden))
                self.assertFalse(res.applied_live)

    def test_preview_header_marks_text_as_preview(self):
        for t in (
            render.render_logind_power("suspend"),
            render.render_charge_limit("BAT0", 80),
            render.render_sleep_mode("deep"),
        ):
            # REUSE-IgnoreStart
            self.assertTrue(t.startswith("# SPDX-License-Identifier: MIT\n# sl-preview:"), t)
            # REUSE-IgnoreEnd

    def test_crafted_etc_file_cannot_inject_into_preview(self):
        d = self.etc / "systemd" / "logind.conf.d"
        d.mkdir(parents=True)
        (d / "50-seclegion-lid.conf").write_text(
            "HandleLidSwitch=suspend\nHandleLidSwitchExternalPower=ignore\nExecStart=/bin/evil\n"
            "HandleLidSwitchDocked=x\n[Service]\n"
        )
        res = registry.write(registry.get("power.lid_battery"), self.ctx(dry_run=True), "lock")
        text = res.texts["/etc/systemd/logind.conf.d/50-seclegion-lid.conf"]
        self.assertIn("HandleLidSwitchDocked=ignore", text)  # the bad value fell back to its default
        self.assertNotIn("evil", text)
        with self.assertRaises(ValueError):
            render.render_logind_lid("suspend", "lock\n[Service]", "ignore")

    def test_battery_name_validated(self):
        for bad in ("BAT0\nw /etc/passwd", "../BAT0", "CMB0", ""):
            with self.subTest(bad), self.assertRaises(ValueError):
                render.render_charge_limit(bad, 80)

    def test_explain_output(self):
        rc, out, _ = run_cli(self.environ, "explain", "power.lid_ac", "lock")
        self.assertEqual(rc, 0)
        for needle in (
            "id: power.lid_ac",
            "current value: suspend",
            "needs privilege: yes",
            "applies live: no",
            "HandleLidSwitchExternalPower=lock",
            "50-seclegion-lid.conf",
        ):
            self.assertIn(needle, out)
        rc, out, _ = run_cli(self.environ, "explain", "sound.volume")
        self.assertIn("applies live: yes", out)
        self.assertIn("needs privilege: no", out)
        self.assertIn("would run: wpctl set-volume @DEFAULT_AUDIO_SINK@ 40%", out)


CONSERVATION = "bus/platform/drivers/ideapad_acpi/VPC2004_00/conservation_mode"


class PkexecTests(StubCase):
    """Privileged writes run `pkexec /usr/bin/seclegion-root-apply <id> <value>`; a stub pkexec
    (SL_PKEXEC) records its argv and exits with a chosen status. Nothing here asks for a password."""

    def pkexec(self, rc=0, stderr=""):
        self.argv_log = self.tmp / "pkexec.argv"
        p = self.tmp / "pkexec"
        p.write_text(f'#!/bin/sh\nfor a in "$@"; do printf \'%s\\n\' "$a"; done > "{self.argv_log}"\n'
                     f"printf '%s\\n' '{stderr}' >&2\nexit {rc}\n")
        p.chmod(0o755)
        self.environ["SL_PKEXEC"] = str(p)
        return str(p)

    def called(self):
        return self.argv_log.read_text().splitlines() if self.argv_log.exists() else None

    def test_pkexec_argv(self):
        stub = self.pkexec(0)
        before = (snapshot(self.etc), snapshot(self.home))
        res = registry.write(registry.get("power.lid_ac"), self.ctx(), "lock")
        self.assertEqual(self.called(), ["/usr/bin/seclegion-root-apply", "power.lid_ac", "lock"])
        self.assertEqual(res.commands, [[stub, "/usr/bin/seclegion-root-apply", "power.lid_ac", "lock"]])
        self.assertEqual(res.files, ["/etc/systemd/logind.conf.d/50-seclegion-lid.conf"])
        self.assertTrue(res.applied_live)
        self.assertFalse(res.dry_run)
        self.assertEqual((snapshot(self.etc), snapshot(self.home)), before)  # root-apply writes, not us
        self.assertEqual(registry.root_argv(Ctx({}), "power.charge_limit", "80"),
                         ["/usr/bin/pkexec", "/usr/bin/seclegion-root-apply", "power.charge_limit", "80"])

    def test_pkexec_argv_for_a_command_row(self):
        stub = self.pkexec(0)
        res = registry.write(registry.get("security.firewall"), self.ctx(), "on")
        self.assertEqual(self.called(), ["/usr/bin/seclegion-root-apply", "security.firewall", "on"])
        self.assertEqual(res.commands, [[stub, "/usr/bin/seclegion-root-apply", "security.firewall", "on"]])
        self.assertEqual(res.files, [])
        self.assertEqual(self.mutations(), [])  # root-apply runs ufw, not us

    def test_unknown_time_zone_refused_before_pkexec(self):
        self.pkexec(0)
        self.environ["SL_ZONEINFO"] = str(self.tmp)  # an empty zoneinfo
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("region.timezone"), self.ctx(), "Nope/Zone")
        self.assertIsNone(self.called())

    def _refused(self, rc, exc):
        self.pkexec(rc, "Error executing command as another user: Not authorized")
        before = (snapshot(self.etc), snapshot(self.home))
        with self.assertRaises(exc) as cm:
            registry.write(registry.get("power.charge_limit"), self.ctx(), "80")
        msg = str(cm.exception)
        self.assertEqual(self.called(), ["/usr/bin/seclegion-root-apply", "power.charge_limit", "80"])
        for word in ("pkexec", "seclegion-root-apply", "sudo", "/usr/bin", "Error executing"):
            self.assertNotIn(word, msg)
        self.assertIn("not changed", msg)
        self.assertEqual((snapshot(self.etc), snapshot(self.home)), before)
        self.assertEqual(self.mutations(), [])
        return cm.exception

    def test_pkexec_126_is_auth_cancelled(self):
        e = self._refused(126, AuthCancelled)
        self.assertNotIsInstance(e, NotAuthorized)
        self.assertIn("password", str(e))

    def test_pkexec_127_is_not_authorized(self):
        e = self._refused(127, NotAuthorized)
        self.assertNotIsInstance(e, AuthCancelled)
        self.assertIn("may not", str(e))

    def test_hostile_id_refused_before_pkexec(self):
        self.pkexec(0)
        lid = registry.get("power.lid_ac")
        for sid in ("power.lid_ac;reboot", "power.lid_ac $(id)", "power.lid_ac\nx", "power.alert_low",
                    "../../etc/passwd", "power.lid_ac`id`"):
            with self.subTest(sid):
                with self.assertRaises(Refused):
                    registry.write(dataclasses.replace(lid, id=sid), self.ctx(), "lock")
        no_writer = mock.patch.object(registry.W, "ROOT_WRITERS", frozenset())
        with no_writer, self.assertRaises(Refused):  # privileged, no root writer: no password prompt
            registry.write(registry.get("updates.snapshot_keep"), self.ctx(), "10")
        with self.assertRaises(InvalidValue):  # the value is validated before the prompt too
            registry.write(lid, self.ctx(), "lock; reboot")
        self.assertIsNone(self.called())

    def test_sandboxed_ctx_never_runs_the_real_pkexec(self):
        with mock.patch("subprocess.run") as run, self.assertRaises(Refused):
            registry.write(registry.get("power.lid_ac"), self.ctx(), "lock")
        run.assert_not_called()

    def test_other_failure_is_command_failed_and_stays_untouched(self):
        self.pkexec(3, "seclegion-root-apply: refusing to replace x: it is a symlink")
        with self.assertRaises(CommandFailed) as cm:
            registry.write(registry.get("power.suspend_mode"), self.ctx(), "deep")
        self.assertIn("refusing to replace x", str(cm.exception))
        self.assertEqual(snapshot(self.etc), {})


class ConservationTests(StubCase):
    """ideapad_laptop conservation_mode: read, write through the backend, hide when absent."""

    def file(self) -> Path:
        return self.sysfs / CONSERVATION

    def test_conservation_mode_reads_the_file(self):
        s = registry.get("power.conservation_mode")
        self.file().write_text("0\n")
        self.assertEqual(registry.read_value(s, self.ctx()), (False, ""))
        self.file().write_text("1\n")
        self.assertEqual(registry.read_value(s, self.ctx()), (True, ""))
        self.file().write_text("2\n")
        value, err = registry.read_value(s, self.ctx())
        self.assertIsNone(value)
        self.assertIn("unreadable", err)

    def test_conservation_mode_write_puts_1_and_0_in_the_file(self):
        s = registry.get("power.conservation_mode")
        res = registry.write(s, self.ctx(), "on")
        self.assertEqual(self.file().read_text(), "1\n")
        self.assertEqual(res.files, [str(self.file())])
        self.assertTrue(res.applied_live)
        registry.write(s, self.ctx(), "off")
        self.assertEqual(self.file().read_text(), "0\n")
        self.assertFalse(s.privileged)  # the udev rule, not a root helper, opens the file to wheel

    def test_conservation_mode_dry_run_leaves_the_file(self):
        rc, out, err = run_cli(self.environ, "set", "power.conservation_mode", "on", "--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertIn("would", out)
        self.assertEqual(self.file().read_text(), "0\n")

    @unittest.skipIf(os.geteuid() == 0, "root ignores the file mode")
    def test_conservation_mode_unwritable_file_is_a_clear_error(self):
        self.file().chmod(0o444)
        with self.assertRaises(CommandFailed) as cm:
            registry.write(registry.get("power.conservation_mode"), self.ctx(), "on")
        self.assertIn("wheel", str(cm.exception))
        self.assertEqual(self.file().read_text(), "0\n")

    def test_conservation_mode_refuses_a_path_outside_sysfs(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.write_text("0\n")
        with self.assertRaises(Refused):
            self.ctx().write_sysfs(WriteResult(), elsewhere, "1\n")
        self.assertEqual(elsewhere.read_text(), "0\n")


class CapabilityTests(StubCase):
    SYSFS = "sysfs-nobat"

    def test_conservation_mode_hidden_without_the_file(self):
        rc, out, _ = run_cli(self.environ, "list", "--json")
        row = {r["id"]: r for r in json.loads(out)}["power.conservation_mode"]
        self.assertFalse(row["visible"])
        self.assertIn("Lenovo IdeaPad and Legion only", row["reason"])
        rc, _, err = run_cli(self.environ, "get", "power.conservation_mode")
        self.assertEqual(rc, 4)
        rc, _, _ = run_cli(self.environ, "set", "power.conservation_mode", "on")
        self.assertEqual(rc, 4)

    def test_charge_limit_hidden_with_reason(self):  # G3
        rc, out, _ = run_cli(self.environ, "list", "--json")
        rows = {r["id"]: r for r in json.loads(out)}
        cl = rows["power.charge_limit"]
        self.assertFalse(cl["visible"])
        self.assertEqual(cl["reason"], "Not supported on this hardware: no charge threshold file")
        rc, _, err = run_cli(self.environ, "get", "power.charge_limit")
        self.assertEqual(rc, 4)
        self.assertIn("no charge threshold file", err)
        rc, _, _ = run_cli(self.environ, "set", "power.charge_limit", "80", "--dry-run")
        self.assertEqual(rc, 4)
        self.assertTrue(rows["power.suspend_mode"]["visible"])

    def test_bare_machine_never_errors(self):
        env = {
            "PATH": str(self.tmp / "empty"),
            "SL_HOME": str(self.home),
            "SL_SYSFS": str(self.tmp / "nosys"),
            "SL_ETC": str(self.etc),
        }
        rc, out, err = run_cli(env, "list", "--json")
        self.assertEqual(rc, 0, err)
        rows = {r["id"]: r for r in json.loads(out)}
        for sid in (
            "power.profile",
            "display.brightness",
            "sound.volume",
            "network.wifi",
            "power.suspend_mode",
            "power.conservation_mode",
            "power.lid_battery",
            "display.kbd_brightness",
            "network.bluetooth",
        ):
            self.assertFalse(rows[sid]["visible"], sid)
            self.assertTrue(rows[sid]["reason"], sid)
        rc, _, _ = run_cli(env, "list")
        self.assertEqual(rc, 0)

    def test_sleep_modes_need_both(self):
        (self.tmp / "sys1" / "power").mkdir(parents=True)
        (self.tmp / "sys1" / "power" / "mem_sleep").write_text("[s2idle]\n")
        c = capabilities.detect(Ctx({**self.environ, "SL_SYSFS": str(self.tmp / "sys1")}))
        self.assertFalse(c["sleep_modes"].ok)

    def test_kbd_backlight_found(self):
        self.assertEqual(capabilities.kbd_backlight_device(self.ctx()), "asus_kbd_backlight")


class DryRunTests(StubCase):
    def test_dry_run_changes_nothing(self):  # G4
        zi = self.tmp / "zoneinfo"  # the root rows preview against a time zone and a snapper config
        (zi / "Europe").mkdir(parents=True)
        (zi / "Europe/Berlin").write_bytes(b"TZif2")
        self.environ["SL_ZONEINFO"] = str(zi)
        (self.etc / "snapper/configs").mkdir(parents=True)
        (self.etc / "snapper/configs/root").write_text('NUMBER_LIMIT="10"\n')
        before, etc_before = snapshot(self.home), snapshot(self.etc)
        state_before = self.stub_state()
        for s in registry.SETTINGS:
            if s.readonly:
                continue
            val = ROUND_TRIP.get(s.id) or {"region.timezone": "Europe/Berlin"}.get(s.id) or (
                "run"
                if s.kind == "action"
                else "on"
                if s.kind == "toggle"
                else s.choices[-1]
                if s.choices
                else str(s.minimum)
            )
            with self.subTest(s.id):
                rc, out, err = run_cli(self.environ, "set", s.id, val, "--dry-run")
                self.assertEqual(rc, 0, err)
                self.assertIn("would", out)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(snapshot(self.etc), etc_before)
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.stub_state(), state_before)

    def test_dry_run_lists_files_and_commands(self):
        rc, out, _ = run_cli(self.environ, "set", "idle.lock_after", "3", "--dry-run", "--json")
        d = json.loads(out)
        self.assertEqual(d["files"], ["~/.config/seclegion/idle.conf"])
        self.assertTrue(d["dry_run"])
        self.assertIn("timeout = 180", d["texts"]["~/.config/seclegion/idle.conf"])

    def test_write_outside_home_refused(self):
        ctx = self.ctx()
        with self.assertRaises(Refused):
            ctx.write_file(WriteResult(), self.tmp / "outside.txt", "x")


class IdleRenderTests(unittest.TestCase):
    def _timeouts(self, text):
        return [int(m) for m in re.findall(r"timeout = (\d+)", text)]

    def test_order_lock_dpms_suspend(self):  # G5
        text = render.render_idle(render.IdleState(suspend_ac=30))
        cmds = re.findall(r"on-timeout = (.*)", text)
        self.assertIn("loginctl lock-session", cmds[0])
        self.assertIn("dpms", cmds[1])
        self.assertIn("systemctl suspend", cmds[2])
        t = self._timeouts(text)
        self.assertEqual(t, sorted(t))
        self.assertLess(t[0], t[1])
        self.assertLess(t[1], t[2])

    def test_rejects_lock_after_dpms(self):  # G5
        for bad in (
            render.IdleState(lock=15, screen_off=10),
            render.IdleState(lock=10, screen_off=10),
            render.IdleState(screen_off=30, suspend_battery=15),
            render.IdleState(screen_off=15, suspend_battery=10, suspend_ac=None),
            render.IdleState(lock=5, screen_off=None, suspend_battery=5),
        ):
            with self.subTest(bad), self.assertRaises(ValueError):
                render.render_idle(bad)

    def test_never_values_are_skipped_not_compared(self):
        text = render.render_idle(render.IdleState(lock=None, screen_off=10, suspend_battery=None))
        self.assertNotIn("on-timeout = loginctl lock-session", text)
        self.assertEqual(self._timeouts(text), [600])

    def test_ac_guard_present(self):  # G5
        text = render.render_idle(render.IdleState(suspend_ac=30))
        bat = re.search(r"timeout = 900\n\s+on-timeout = (.*)", text).group(1)
        ac = re.search(r"timeout = 1800\n\s+on-timeout = (.*)", text).group(1)
        for c in (bat, ac):
            self.assertIn("/sys/class/power_supply/AC*/online", c)
        self.assertIn("|| systemctl suspend", bat)  # battery listener: suspend only when NOT on AC
        self.assertIn("&& systemctl suspend", ac)
        self.assertNotRegex(text, r"on-timeout = systemctl suspend")  # never an unguarded suspend

    def test_default_has_no_ac_suspend(self):
        text = render.render_idle(render.IdleState())
        self.assertEqual(text.count("systemctl suspend"), 1)
        self.assertIn("grep -qx 1 || systemctl suspend", text)

    def test_state_header_round_trips(self):
        st = render.IdleState(
            lock=None, screen_off=15, suspend_battery=30, suspend_ac=60, lock_before_sleep=False
        )
        self.assertEqual(render.parse_idle_state(render.render_idle(st)), st)

    def test_dpms_dispatch_form(self):
        text = render.render_idle(render.IdleState())
        self.assertNotIn("UNVERIFIED", text)
        self.assertIn('hl.dsp.dpms({action="off"})', text)
        self.assertNotIn("$", text)  # hyprlang would treat $x as a variable


class CraftedStateTests(StubCase):
    LINES = (
        "lock=-5 screen_off=0 suspend_battery=+1 suspend_ac=\u0669",
        "lock=99999999999999999999 screen_off=10 suspend_battery=15 suspend_ac=never",
    )

    def test_crafted_sl_state_falls_back_to_defaults(self):
        cfg = self.home / ".config" / "seclegion"
        cfg.mkdir(parents=True)
        for line in self.LINES:
            with self.subTest(line):
                (cfg / "idle.conf").write_text(f"# sl-state: {line} lock_before_sleep=on\n", encoding="utf-8")
                rc, out, _ = run_cli(self.environ, "get", "idle.lock_after")
                self.assertEqual((rc, out.strip()), (0, "5"))
                rc, out, _ = run_cli(self.environ, "get", "idle.suspend_battery")
                self.assertEqual((rc, out.strip()), (0, "15"))
                rc, _, err = run_cli(self.environ, "set", "idle.lock_before_sleep", "off")
                self.assertEqual(rc, 0, err)
                text = (cfg / "idle.conf").read_text()
                self.assertEqual(
                    sorted(int(t) for t in re.findall(r"^    timeout = (.*)$", text, re.M)), [300, 600, 900]
                )


class NoBatteryTests(StubCase):
    def setUp(self):
        super().setUp()
        sysfs = self.tmp / "sysfs-nobattery"
        shutil.copytree(FIXTURES / "sysfs-full", sysfs)
        shutil.rmtree(sysfs / "class" / "power_supply" / "BAT0")
        self.environ["SL_SYSFS"] = str(sysfs)

    def test_no_battery_hides_suspend_on_battery_and_emits_no_listener(self):
        rc, out, _ = run_cli(self.environ, "list", "--json")
        rows = {r["id"]: r for r in json.loads(out)}
        self.assertFalse(rows["idle.suspend_battery"]["visible"])
        self.assertIn("no battery", rows["idle.suspend_battery"]["reason"])
        rc, _, _ = run_cli(self.environ, "set", "idle.suspend_battery", "30")
        self.assertEqual(rc, 4)
        rc, _, err = run_cli(self.environ, "set", "idle.lock_after", "3")
        self.assertEqual(rc, 0, err)
        text = (self.home / ".config/seclegion/idle.conf").read_text()
        self.assertNotIn("systemctl suspend", text)
        self.assertEqual(len(re.findall(r"^listener \{", text, re.M)), 2)

    def test_with_battery_listener_is_present(self):
        run_cli(self.environ | {"SL_SYSFS": str(FIXTURES / "sysfs-full")}, "set", "idle.lock_after", "3")
        self.assertIn("systemctl suspend", (self.home / ".config/seclegion/idle.conf").read_text())


class AcGuardTests(unittest.TestCase):
    def _on_ac(self, supplies):
        with tempfile.TemporaryDirectory(prefix="sl-ps-test-") as d:
            for name, (typ, online) in supplies.items():
                (Path(d) / name).mkdir()
                (Path(d) / name / "type").write_text(typ + "\n")
                (Path(d) / name / "online").write_text(online + "\n")
            test = render.ON_AC_TEST.replace("/sys/class/power_supply", d)
            return subprocess.run(["sh", "-c", test], capture_output=True).returncode == 0

    def test_usb_c_supply_counts_as_ac(self):
        self.assertTrue(self._on_ac({"ucsi-source-psy-USBC000:001": ("USB", "1")}))

    def test_other_cases(self):
        self.assertTrue(self._on_ac({"ADP0": ("Mains", "1")}))
        self.assertTrue(self._on_ac({"foo": ("Mains", "1")}))
        self.assertFalse(self._on_ac({"ucsi-source-psy-USBC000:001": ("USB", "0"), "ADP0": ("Mains", "0")}))
        self.assertFalse(self._on_ac({"BAT0": ("Battery", "1")}))
        self.assertFalse(self._on_ac({}))


class WriteSafetyTests(StubCase):
    def test_config_dir_is_a_file_exits_5_without_traceback(self):
        (self.home / ".config").mkdir()
        (self.home / ".config" / "seclegion").write_text("not a directory")
        rc, out, err = run_cli(self.environ, "set", "idle.lock_after", "3")
        self.assertEqual(rc, 5)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("command failed", err)

    def test_symlinked_config_dir_outside_home_refused(self):
        outside = self.tmp / "elsewhere"
        outside.mkdir()
        (self.home / ".config").mkdir()
        (self.home / ".config" / "seclegion").symlink_to(outside)
        rc, _, err = run_cli(self.environ, "set", "idle.lock_after", "3")
        self.assertEqual(rc, 3, err)
        self.assertEqual(list(outside.iterdir()), [])

    def test_root_refused(self):
        with mock.patch("os.geteuid", return_value=0), self.assertRaises(Refused):
            self.ctx().write_file(WriteResult(), self.home / "x.txt", "x")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_existing_mode_preserved_and_new_file_is_0644(self):
        ctx = self.ctx()
        f = self.home / "a.txt"
        ctx.write_file(WriteResult(), f, "one")
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o644)
        f.chmod(0o600)
        ctx.write_file(WriteResult(), f, "two")
        self.assertEqual((f.read_text(), stat.S_IMODE(f.stat().st_mode)), ("two", 0o600))

    def test_temp_file_is_fsynced_before_replace(self):
        calls = []
        real_fsync, real_replace = os.fsync, os.replace
        with (
            mock.patch("os.fsync", side_effect=lambda fd: (calls.append("fsync"), real_fsync(fd))[1]),
            mock.patch(
                "os.replace", side_effect=lambda a, b: (calls.append("replace"), real_replace(a, b))[1]
            ),
        ):
            self.ctx().write_file(WriteResult(), self.home / "b.txt", "x")
        self.assertEqual(calls[:2], ["fsync", "replace"])


class FindThemeCliTests(StubCase):
    """The host-installed layout is host/settings/{python/seclegion_settings,seclegion-theme}."""

    def installed(self, with_launcher: bool) -> Path:
        base = self.tmp / "host" / "settings"
        shutil.copytree(
            ROOT / "desktop" / "settings" / "seclegion_settings",
            base / "python" / "seclegion_settings",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        if with_launcher:
            (base / "seclegion-theme").write_text("#!/bin/sh\n")
        return base

    def find(self, base: Path) -> str:
        empty = self.tmp / "empty-path"
        empty.mkdir(exist_ok=True)
        code = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from seclegion_settings.backend import capabilities\n"
            "from seclegion_settings.backend.env import Ctx\n"
            "print(capabilities.find_theme_cli(Ctx({'PATH': sys.argv[2]})))\n"
        )
        r = subprocess.run(
            [sys.executable, "-I", "-c", code, str(base / "python"), str(empty)],
            capture_output=True,
            text=True,
            check=True,
        )
        return r.stdout.strip()

    def test_sibling_launcher_of_the_installed_python_dir(self):
        base = self.installed(True)
        self.assertEqual(self.find(base), str(base / "seclegion-theme"))

    def test_none_without_a_launcher_anywhere(self):
        self.assertEqual(self.find(self.installed(False)), "None")


class AutolockTests(StubCase):
    def no_cli_env(self) -> dict:
        """The stub PATH without seclegion-autolock."""
        b = self.tmp / "bin-nocli"
        make_bin(b, tuple(t for t in TOOLS if t != "seclegion-autolock"))
        return {**self.environ, "PATH": str(b)}

    def test_write_calls_the_cli_and_reads_it_back(self):
        res = registry.write(registry.get("power.autolock"), self.ctx(), "never")
        self.assertEqual(res.commands, [["seclegion-autolock", "set", "never"]])
        self.assertEqual(res.files, [])
        self.assertTrue(res.applied_live)
        self.assertEqual(self.mutations(), ["seclegion-autolock set never"])
        self.assertEqual(registry.read_value(registry.get("power.autolock"), self.ctx()), ("never", ""))

    def test_bad_value_refused_before_any_call(self):
        rc, _, err = run_cli(self.environ, "set", "power.autolock", "5s")
        self.assertNotEqual(rc, 0)
        self.assertIn("is not one of default, 15m, 30m, 60m, never", err)
        self.assertEqual(self.mutations(), [])

    def test_hidden_without_the_cli(self):
        bare = self.no_cli_env()
        rows = {r["id"]: r for r in json.loads(run_cli(bare, "list", "--json")[1])}
        self.assertFalse(rows["power.autolock"]["visible"])
        self.assertIn("the automatic lock is not set up", rows["power.autolock"]["reason"])
        rc, _, err = run_cli(bare, "set", "power.autolock", "never")
        self.assertEqual(rc, 4)
        self.assertIn("automatic lock is not set up", err)

    def test_found_in_local_bin_when_not_on_path(self):
        bare = self.no_cli_env()
        lb = self.home / ".local" / "bin"
        lb.mkdir(parents=True)
        (lb / "seclegion-autolock").write_text(
            f'#!/bin/sh\nexec "{sys.executable}" -I "{HERE / "stub_tool.py"}" seclegion-autolock "$@"\n'
        )
        (lb / "seclegion-autolock").chmod(0o755)
        ctx = Ctx(bare)
        self.assertEqual(capabilities.find_autolock_cli(ctx), str(lb / "seclegion-autolock"))
        self.assertEqual(registry.read_value(registry.get("power.autolock"), ctx), ("default", ""))
        res = registry.write(registry.get("power.autolock"), ctx, "60m")
        self.assertEqual(res.commands, [[str(lb / "seclegion-autolock"), "set", "60m"]])
        self.assertEqual(registry.read_value(registry.get("power.autolock"), Ctx(bare)), ("60m", ""))


class RealHostReadOnlyTests(unittest.TestCase):
    def test_list_on_real_host_is_read_only(self):  # G6
        cfg = Path.home() / ".config" / "seclegion"
        before = snapshot(cfg) if cfg.exists() else None
        # No session signature and an empty runtime dir: hyprctl (about.hyprland, the display rows)
        # finds no instance socket, so nothing reaches the live compositor.
        with tempfile.TemporaryDirectory() as run:
            os.chmod(run, 0o700)
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("SL_") and k != "HYPRLAND_INSTANCE_SIGNATURE"}
            env["XDG_RUNTIME_DIR"] = run
            cp = subprocess.run([str(LAUNCHER), "list"], capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("power.profile", cp.stdout)
        after = snapshot(cfg) if cfg.exists() else None
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
