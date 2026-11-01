# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tools/seclegion-root-apply, run as a subprocess against a temp /etc (SL_ETC), a temp backup dir
(SL_ROOT_STATE), a temp zoneinfo (SL_ZONEINFO) and PATH stubs for systemctl, systemd-tmpfiles,
logger, timedatectl and ufw that log their argv. Nothing real is touched."""

import os
import re
import stat
import subprocess
import unittest
import xml.etree.ElementTree as ET

import _bootstrap  # noqa: F401
from stubs import FIXTURES, HERE, StubCase, snapshot

TOOL = HERE.parents[2] / "tools" / "seclegion-root-apply"
POLICY = HERE.parent / "org.seclegion.settings.policy"
PKG = HERE.parents[2] / "pkgs" / "seclegion-settings"
LID = "systemd/logind.conf.d/50-seclegion-lid.conf"


class RootApplyCase(StubCase):
    def setUp(self):
        super().setUp()
        self.rstate = self.tmp / "rootstate"
        self.rbin = self.tmp / "rbin"
        self.rbin.mkdir()
        self.log = self.tmp / "calls"
        for n in ("systemctl", "systemd-tmpfiles", "logger", "timedatectl", "ufw", "sshd", "snapper"):
            self.stub(n)
        self.zoneinfo = self.tmp / "zoneinfo"
        (self.zoneinfo / "Europe").mkdir(parents=True)
        (self.zoneinfo / "Europe/Berlin").write_bytes(b"TZif2")
        self.env = {
            "PATH": f"{self.rbin}:/usr/bin:/bin",
            "SL_ETC": str(self.etc),
            "SL_ROOT_STATE": str(self.rstate),
            "SL_SYSFS": str(FIXTURES / "sysfs-full"),
            "SL_ZONEINFO": str(self.zoneinfo),
            "HOME": str(self.home),
        }

    def stub(self, n, rc=0):
        p = self.rbin / n
        p.write_text(
            f'#!/bin/sh\nprintf "%s" "{n}" >> "{self.log}"; '
            f'for a in "$@"; do printf " [%s]" "$a" >> "{self.log}"; done; echo >> "{self.log}"\n'
            f"exit {rc}\n"
        )
        p.chmod(0o755)

    def run_tool(self, *args, env=None):
        return subprocess.run([str(TOOL), *args], env=env or self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


class Apply(RootApplyCase):
    def test_lid_written_atomically_with_hup_and_log(self):
        cp = self.run_tool("power.lid_ac", "lock")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        text = (self.etc / LID).read_text()
        self.assertIn("HandleLidSwitchExternalPower=lock\n", text)
        self.assertNotIn("sl-preview", text)
        self.assertIn(text, cp.stdout)  # the exact text is printed
        self.assertEqual(stat.S_IMODE((self.etc / LID).stat().st_mode), 0o644)
        self.assertEqual([p.name for p in (self.etc / LID).parent.iterdir()], ["50-seclegion-lid.conf"])
        c = self.calls()
        self.assertEqual(c[0], "systemctl [kill] [-s] [HUP] [systemd-logind]")
        self.assertTrue(c[1].startswith("logger [-t] [seclegion-root-apply]"))
        self.assertFalse(any("restart" in x for x in c))

    def test_backup_of_existing_file(self):
        self.run_tool("power.lid_ac", "lock")
        before = (self.etc / LID).read_text()
        self.run_tool("power.lid_battery", "ignore")
        baks = list(self.rstate.glob("50-seclegion-lid.conf.*.bak"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(baks[0].read_text(), before)
        self.assertEqual(stat.S_IMODE(baks[0].stat().st_mode), 0o600)
        self.assertIn("HandleLidSwitch=ignore", (self.etc / LID).read_text())
        self.assertIn("HandleLidSwitchExternalPower=lock", (self.etc / LID).read_text())  # kept

    def test_tmpfiles_row_applies_the_file(self):
        cp = self.run_tool("power.charge_limit", "80")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        t = (self.etc / "tmpfiles.d/50-seclegion-charge-limit.conf").read_text()
        self.assertRegex(t, r"w /sys/class/power_supply/BAT0/charge_control_end_threshold - - - - 80\n")
        self.assertTrue(self.calls()[0].startswith("systemd-tmpfiles [--create]"))

    def test_dry_run_writes_nothing_and_needs_no_override(self):
        cp = self.run_tool("--dry-run", "power.power_button", "suspend")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("HandlePowerKey=suspend", cp.stdout)
        self.assertEqual(snapshot(self.etc), {})
        self.assertFalse(self.rstate.exists())
        self.assertEqual(self.calls(), [])
        env = {"PATH": self.env["PATH"], "SL_SYSFS": self.env["SL_SYSFS"], "HOME": self.env["HOME"]}
        cp = self.run_tool("--dry-run", "power.power_button", "suspend", env=env)  # real /etc is only read
        self.assertEqual(cp.returncode, 0, cp.stderr)

    @unittest.skipIf(os.geteuid() == 0, "needs a non-root user")
    def test_refuses_without_root_or_override(self):
        env = {k: v for k, v in self.env.items() if not k.startswith("SL_ETC") and k != "SL_ROOT_STATE"}
        cp = self.run_tool("power.power_button", "suspend", env=env)
        self.assertEqual(cp.returncode, 3)
        self.assertIn("run as root", cp.stderr)


class Refusals(RootApplyCase):
    def test_allowlist_rejects_unlisted_ids(self):
        for sid in (
            "power.alert_low",
            "power.profile",
            "idle.lock_after",
            "../../etc/passwd",
            "about.kernel",
        ):
            with self.subTest(sid):
                cp = self.run_tool(sid, "10")
                self.assertNotEqual(cp.returncode, 0)
                self.assertRegex(
                    cp.stderr, r"is not a privileged setting this tool may apply|invalid|unknown"
                )
                if sid in ("power.alert_low", "power.profile", "idle.lock_after", "about.kernel"):
                    self.assertIn("not a privileged setting this tool may apply", cp.stderr)
        self.assertEqual(snapshot(self.etc), {})
        self.assertEqual(self.calls(), [])

    def test_values_validated_against_the_row(self):
        for sid, bad in (
            ("power.lid_ac", "explode"),
            ("power.lid_ac", "ignore; touch /tmp/x"),
            ("power.charge_limit", "101"),
            ("power.charge_limit", "59"),
            ("power.charge_limit", "80; id"),
            ("power.suspend_mode", "mem"),
        ):
            with self.subTest(id=sid, value=bad):
                cp = self.run_tool(sid, bad)
                self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertEqual(snapshot(self.etc), {})
        self.assertEqual(self.calls(), [])

    def test_symlink_target_refused(self):
        d = self.etc / "systemd/logind.conf.d"
        d.mkdir(parents=True)
        victim = self.tmp / "victim"
        victim.write_text("keep\n")
        (d / "50-seclegion-lid.conf").symlink_to(victim)
        cp = self.run_tool("power.lid_ac", "lock")
        self.assertEqual(cp.returncode, 3)
        self.assertIn("symlink", cp.stderr)
        self.assertEqual(victim.read_text(), "keep\n")
        self.assertEqual(self.calls(), [])

    def test_symlinked_parent_refused(self):
        (self.tmp / "elsewhere").mkdir()
        (self.etc / "systemd").mkdir()
        (self.etc / "systemd/logind.conf.d").symlink_to(self.tmp / "elsewhere")
        cp = self.run_tool("power.lid_ac", "lock")
        self.assertEqual(cp.returncode, 3, cp.stderr)
        self.assertEqual(list((self.tmp / "elsewhere").iterdir()), [])


FOUR = ("region.timezone", "security.ssh_enable", "security.firewall", "updates.snapshot_keep")
UNITS = "[sshd.service] [sshd.socket] [sshd@.service] [sshd-unix-local.socket]"


class RootReady(unittest.TestCase):
    def test_the_four_rows_are_root_ready(self):  # G2
        from seclegion_settings.backend import registry

        for sid in FOUR:
            with self.subTest(sid):
                s = registry.get(sid)
                self.assertTrue(registry.root_ready(s))
                self.assertIn("Needs root: asks for the administrator password.", s.description)
        self.assertEqual([s.id for s in registry.SETTINGS if s.privileged and not registry.root_ready(s)], [])

    def test_sshd_units_match_the_installer(self):
        import ast

        from seclegion_settings.backend import writers

        tree = ast.parse((HERE.parents[2] / "installer/installd/post.py").read_text())
        (node,) = [n for n in tree.body if isinstance(n, ast.Assign)
                   and [getattr(t, "id", None) for t in n.targets] == ["SSHD_MASKED"]]
        self.assertEqual(writers.SSHD_UNITS, ast.literal_eval(node.value))


class Commands(RootApplyCase):
    def test_timezone_runs_timedatectl(self):
        cp = self.run_tool("region.timezone", "Europe/Berlin")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        c = self.calls()
        self.assertEqual(c[0], "timedatectl [set-timezone] [Europe/Berlin]")
        self.assertTrue(c[1].startswith("logger [-t] [seclegion-root-apply]"))
        self.assertEqual(len(c), 2)
        self.assertEqual(snapshot(self.etc), {})

    def test_timezone_refused_before_any_command(self):  # G3
        (self.tmp / "outside").write_text("x")
        (self.zoneinfo / "Evil").symlink_to(self.tmp / "outside")  # a file, but outside zoneinfo
        for bad in ("../etc/passwd", "/etc/x", "Nope/Zone", "Europe/../../etc/passwd", "Evil", "Europe"):
            with self.subTest(bad):
                cp = self.run_tool("region.timezone", bad)
                self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(snapshot(self.etc), {})

    def test_ssh_on_unmasks_then_enables(self):
        cp = self.run_tool("security.ssh_enable", "on")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(self.calls()[:2], [f"systemctl [unmask] {UNITS}",
                                            "systemctl [enable] [--now] [sshd.service]"])

    def test_ssh_off_disables_then_masks(self):
        cp = self.run_tool("security.ssh_enable", "off")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(self.calls()[:2], ["systemctl [disable] [--now] [sshd.service]",
                                            f"systemctl [mask] {UNITS}"])

    def test_firewall_on_and_off(self):
        self.assertEqual(self.run_tool("security.firewall", "on").returncode, 0)
        self.assertEqual(self.calls()[0], "ufw [--force] [enable]")
        self.assertEqual(self.run_tool("security.firewall", "off").returncode, 0)
        self.assertEqual(self.calls()[2], "ufw [disable]")
        self.assertEqual(len(self.calls()), 4)  # each followed by its logger line

    def test_bad_values_run_nothing(self):
        for sid, bad in (("security.firewall", "maybe"), ("security.ssh_enable", "on; id")):
            with self.subTest(sid):
                self.assertEqual(self.run_tool(sid, bad).returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_dry_run_runs_nothing(self):
        cp = self.run_tool("--dry-run", "security.ssh_enable", "on")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("would run: /usr/bin/systemctl enable --now sshd.service", cp.stdout)
        self.assertEqual(self.calls(), [])

    def test_failing_tool_is_reported_and_stops(self):
        self.stub("systemctl", rc=1)
        cp = self.run_tool("security.ssh_enable", "on")
        self.assertEqual(cp.returncode, 5, cp.stderr)
        self.assertEqual(cp.stderr.strip().splitlines()[-1],
                         "seclegion-root-apply: the system refused the change (exit 1)")
        self.assertEqual(self.calls(), [f"systemctl [unmask] {UNITS}"])  # no enable, no log line

    def test_never_the_real_binary_under_a_test_override(self):  # negative
        (self.rbin / "ufw").unlink()  # PATH still has /usr/bin
        cp = self.run_tool("security.firewall", "on")
        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertEqual(self.calls(), [])


class SnapperConfig(RootApplyCase):
    CONFIG = ('# snapper\nSUBVOLUME="/"\nNUMBER_LIMIT="10"\nNUMBER_LIMIT_IMPORTANT="10"\n'
              'TIMELINE_CREATE="no"\n')

    def test_edits_only_number_limit(self):
        f = self.etc / "snapper/configs/root"
        f.parent.mkdir(parents=True)
        f.write_text(self.CONFIG)
        cp = self.run_tool("updates.snapshot_keep", "4")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(f.read_text(), self.CONFIG.replace('NUMBER_LIMIT="10"\n', 'NUMBER_LIMIT="4"\n'))
        c = self.calls()
        self.assertEqual(len(c), 1)  # the log line only: no tmpfiles, no logind reload
        self.assertTrue(c[0].startswith("logger [-t] [seclegion-root-apply]"))

    def test_refused_without_a_config(self):
        cp = self.run_tool("updates.snapshot_keep", "4")
        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertEqual(snapshot(self.etc), {})
        self.assertEqual(self.calls(), [])


class NoShell(unittest.TestCase):
    def test_source_never_uses_a_shell(self):
        src = (HERE.parent / "seclegion_settings/backend/rootapply.py").read_text()
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        for bad in ("shell=True", "os.system", "os.popen", 'check_output("'):
            self.assertNotIn(bad, code)
        self.assertEqual(len(re.findall(r"subprocess\.run\(\[", code)), 1)  # argv list only


if __name__ == "__main__":
    unittest.main()


class Policy(unittest.TestCase):
    def test_policy_exec_path(self):
        from seclegion_settings.backend import registry

        root = ET.parse(POLICY).getroot()  # a local, tracked file
        (action,) = root.findall("action")
        self.assertEqual(action.get("id"), registry.POLKIT_ACTION)
        self.assertEqual(action.get("id"), "org.seclegion.settings.root-apply")
        d = action.find("defaults")
        self.assertEqual(
            {k: d.findtext(k) for k in ("allow_any", "allow_inactive", "allow_active")},
            {"allow_any": "no", "allow_inactive": "no", "allow_active": "auth_admin_keep"},
        )
        ann = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(ann, {"org.freedesktop.policykit.exec.path": "/usr/bin/seclegion-root-apply"})
        self.assertEqual(registry.ROOT_APPLY, "/usr/bin/seclegion-root-apply")
        build = (PKG / "PKGBUILD").read_text()
        self.assertRegex(build, r"depends=\([^)]*'polkit'")
        self.assertIn('"$pkgdir/usr/share/polkit-1/actions/org.seclegion.settings.policy"', build)
        self.assertIn('"$srcdir/tools/$t" "$pkgdir/usr/bin/$t"', build)  # root-apply at the exec.path
        self.assertIn("desktop/settings/org.seclegion.settings.policy", (PKG / "source.list").read_text())
