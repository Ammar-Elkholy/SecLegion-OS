# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r12 S3: the Security and Users pages (backend rows, against the stub tools).

Nothing here writes outside the fake HOME or runs a real tool. The root rows (SSH server, firewall)
preview here; seclegion-root-apply runs the stub `systemctl` and `ufw`, which record every call.
"""

import json
import time
import unittest

import _bootstrap  # noqa: F401
from seclegion_settings.backend import registry, rootapply, writers
from seclegion_settings.backend.env import Ctx, InvalidValue, Refused, Unavailable
from stubs import StubCase, snapshot

ROOT_ROWS = ("security.ssh_enable", "security.firewall")


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

    def test_every_page_has_rows(self):  # G2
        from seclegion_settings.ui import pages

        self.assertEqual([p.id for p in pages.PAGES if not pages.settings_for(p)], [])

    def test_every_root_row_has_a_root_writer(self):  # the CLI and UI no longer have a preview-only path
        self.assertEqual([s.id for s in registry.SETTINGS if s.privileged and not registry.root_ready(s)], [])

    def test_ports_row_explains_with_a_home_path(self):  # G5
        self.assertTrue(registry.get("security.ports").file.startswith("~/.config/seclegion/"))


class SecurityTests(StubCase):
    def set_state(self, **kw):
        (self.state / "state.json").write_text(json.dumps(kw))

    def test_ports_split_by_reach(self):
        self.assertEqual(
            row("security.ports", self.ctx()).value,
            "open to the network: 22; this computer only: 53, 631, 8080",
        )

    def test_ports_when_nothing_listens(self):
        self.set_state(ss="State Recv-Q Send-Q Local Address:Port Peer Address:Port\n")
        self.assertEqual(row("security.ports", self.ctx()).value, "nothing is listening")

    def test_ports_ignore_junk_lines(self):
        self.set_state(ss="LISTEN 0 1 *:80 *:*\nLISTEN 0 1 weird\nLISTEN 0 1 x:notaport *\n")
        self.assertEqual(row("security.ports", self.ctx()).value, "open to the network: 80")

    def test_ports_row_is_read_only(self):
        with self.assertRaises(Refused):
            put(self, "security.ports", "22")

    def test_sshd_info_states(self):
        self.assertEqual(row("security.sshd", self.ctx()).value, "off")
        self.set_state(sshd="enabled")
        self.assertEqual(row("security.sshd", self.ctx()).value, "on, not running")
        self.set_state(sshd="enabled", sshd_active=True)
        self.assertEqual(row("security.sshd", self.ctx()).value, "on, running")
        self.set_state(sshd="masked")
        self.assertEqual(row("security.sshd", self.ctx()).value, "off (masked)")

    def test_rows_hidden_without_their_tool(self):
        (self.bin / "sshd").unlink()
        (self.bin / "ss").unlink()
        for sid, tool in (
            ("security.sshd", "sshd"),
            ("security.ssh_enable", "sshd"),
            ("security.ports", "ss"),
        ):
            r = row(sid, self.ctx())
            self.assertFalse(r.visible, sid)
            self.assertIn(tool, r.reason)

    def test_firewall_hidden_without_ufw(self):
        (self.bin / "ufw").unlink()
        self.assertFalse(row("security.firewall", self.ctx()).visible)

    def test_root_rows_read_their_state(self):
        self.assertIs(row("security.ssh_enable", self.ctx()).value, False)
        self.set_state(sshd="enabled", ufw="enabled")
        self.assertIs(row("security.ssh_enable", self.ctx()).value, True)
        self.assertIs(row("security.firewall", self.ctx()).value, True)

    def test_firewall_reads_ufw_switch_not_the_unit(self):
        self.set_state(ufw="enabled")  # `ufw disable` leaves ufw.service enabled
        (self.etc / "ufw").mkdir()
        (self.etc / "ufw" / "ufw.conf").write_text("# ufw\nENABLED=no\nLOGLEVEL=low\n")
        self.assertIs(row("security.firewall", self.ctx()).value, False)
        (self.etc / "ufw" / "ufw.conf").write_text("ENABLED=yes\n")
        self.assertIs(row("security.firewall", self.ctx()).value, True)

    def test_root_rows_preview_commands_and_run_nothing(self):  # negative
        sc, units = "/usr/bin/systemctl", list(writers.SSHD_UNITS)
        for sid, on, off in (
            (
                "security.ssh_enable",
                [[sc, "unmask", *units], [sc, "enable", "--now", "sshd.service"]],
                [[sc, "disable", "--now", "sshd.service"], [sc, "mask", *units]],
            ),
            ("security.firewall", [["/usr/bin/ufw", "--force", "enable"]], [["/usr/bin/ufw", "disable"]]),
        ):
            with self.subTest(sid):
                self.assertTrue(registry.get(sid).privileged)
                self.assertTrue(registry.root_ready(registry.get(sid)))
                with self.assertRaises(Refused):  # sandboxed ctx: never the real pkexec
                    put(self, sid, "on")
                self.assertEqual(put(self, sid, "on", dry_run=True).commands, on)
                res = put(self, sid, "off", dry_run=True)
                self.assertEqual(res.commands, off)
                self.assertEqual(res.notes, ["Needs root: asks for the administrator password."])
        self.assertEqual(self.mutations(), [])
        self.assertEqual(snapshot(self.home), {})
        self.assertEqual(snapshot(self.etc), {})

    def test_root_writers_never_run_even_called_directly(self):  # negative
        writers.ssh_enable(self.ctx(), True)
        writers.firewall(self.ctx(), True)
        self.assertEqual(self.mutations(), [])

    def test_root_rows_reject_bad_values(self):
        for sid in ROOT_ROWS:
            with self.subTest(sid), self.assertRaises(InvalidValue):
                put(self, sid, "maybe", dry_run=True)

    def test_root_apply_dry_run_runs_nothing(self):  # negative
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        for sid in ROOT_ROWS:
            with self.subTest(sid):
                self.assertEqual(rootapply.apply(sid, "on", True, env), 0)
        self.assertEqual(snapshot(self.etc), {})
        self.assertFalse((self.tmp / "rstate").exists())
        self.assertEqual(self.mutations(), [])

    def test_root_apply_ssh_round_trip(self):
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        self.set_state(sshd="masked")  # as the installer leaves it
        rootapply.apply("security.ssh_enable", "on", False, env)
        self.assertIs(row("security.ssh_enable", self.ctx()).value, True)
        self.assertEqual(self.stub_state()["sshd_active"], True)
        rootapply.apply("security.ssh_enable", "off", False, env)
        self.assertIs(row("security.ssh_enable", self.ctx()).value, False)
        self.assertEqual(self.stub_state()["sshd"], "masked")  # masked again
        units = " ".join(writers.SSHD_UNITS)
        self.assertEqual(self.mutations(), [
            f"systemctl unmask {units}", "systemctl enable --now sshd.service",
            "systemctl disable --now sshd.service", f"systemctl mask {units}",
        ])
        self.assertEqual(snapshot(self.etc), {})

    def test_root_apply_firewall_runs_ufw(self):
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        rootapply.apply("security.firewall", "on", False, env)
        rootapply.apply("security.firewall", "off", False, env)
        self.assertEqual(self.mutations(), ["ufw --force enable", "ufw disable"])
        self.assertEqual(snapshot(self.etc), {})


class UsersTests(StubCase):
    def calls(self) -> list:
        p = self.state / "calls.log"
        return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []

    def test_name_from_passwd(self):
        self.environ["USER"] = "ammar"
        (self.etc / "passwd").write_text(
            "root:x:0:0::/root:/bin/bash\nammar:x:1000:1000:Ammar Elkholy,,,:/home/ammar:/bin/zsh\n"
        )
        self.assertEqual(row("users.name", self.ctx()).value, "Ammar Elkholy (ammar)")

    def test_name_falls_back_to_the_login(self):
        self.environ["USER"] = "ammar"
        self.assertEqual(row("users.name", self.ctx()).value, "ammar")
        (self.etc / "passwd").write_text("ammar:x:1000:1000::/home/ammar:/bin/zsh\n")
        self.assertEqual(row("users.name", self.ctx()).value, "ammar")

    def test_face(self):
        self.assertEqual(row("users.face", self.ctx()).value, "not set")
        (self.home / ".face").write_bytes(b"x" * 2048)
        self.assertEqual(row("users.face", self.ctx()).value, "set (2.0 KB)")

    def test_autologin_is_read_only_from_greetd(self):
        self.assertEqual(row("users.autologin", self.ctx()).value, "off")
        (self.etc / "greetd").mkdir()
        (self.etc / "greetd/config.toml").write_text(
            '[initial_session]\ncommand = "Hyprland"\nuser = "live"\n'
        )
        self.assertEqual(row("users.autologin", self.ctx()).value, "on for live")
        with self.assertRaises(Refused):
            put(self, "users.autologin", "off")
        self.assertEqual(snapshot(self.home), {})

    def test_autologin_survives_a_broken_config(self):
        (self.etc / "greetd").mkdir()
        (self.etc / "greetd/config.toml").write_text("[initial_session\n")
        self.assertEqual(row("users.autologin", self.ctx()).value, "off")

    def test_name_and_face_are_read_only(self):
        for sid in ("users.name", "users.face"):
            with self.subTest(sid), self.assertRaises(Refused):
                put(self, sid, "x")

    def test_password_opens_passwd_in_a_terminal_and_takes_no_secret(self):
        res = put(self, "users.password", "run")
        (cmd,) = res.commands
        self.assertEqual(cmd[:3], ["xdg-terminal-exec", "sh", "-c"])
        self.assertTrue(cmd[3].startswith("passwd;"))
        end = time.monotonic() + 5  # the terminal is launched detached
        while time.monotonic() < end and not self.mutations():
            time.sleep(0.02)
        self.assertEqual(self.mutations(), ["xdg-terminal-exec sh -c " + cmd[3]])
        self.assertIn("never sees the password", res.notes[0])

    def test_password_row_accepts_only_run(self):  # negative: no value can carry a password
        for bad in ("hunter2", "now", ""):
            with self.subTest(bad), self.assertRaises(InvalidValue):
                put(self, "users.password", bad)
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.calls(), [])

    def test_password_dry_run_opens_nothing(self):
        put(self, "users.password", "run", dry_run=True)
        time.sleep(0.2)
        self.assertEqual(self.mutations(), [])

    def test_password_hidden_without_a_terminal(self):
        (self.bin / "xdg-terminal-exec").unlink()
        self.assertFalse(row("users.password", self.ctx()).visible)
        with self.assertRaises(Unavailable):
            put(self, "users.password", "run")


if __name__ == "__main__":
    unittest.main()
