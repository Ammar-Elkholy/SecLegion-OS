# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r12 S1: the Bluetooth, Storage and Updates pages (backend rows, against the stub tools).

Every user row writes only under the fake HOME; the one root row (snapshot count) previews here and
seclegion-root-apply edits a fake /etc (SL_ETC). Nothing here touches the real home, /etc or a real tool.
"""

import json
import stat
import time
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from seclegion_settings.backend import registry, rootapply
from seclegion_settings.backend.env import Ctx, InvalidValue, Refused, Unavailable
from stubs import StubCase, snapshot


def row(sid: str, ctx: Ctx):
    return registry.row(registry.get(sid), ctx)


class Gates(unittest.TestCase):
    def test_user_rows_never_write_outside_home(self):  # G3
        bad = [s.id for s in registry.SETTINGS if not s.privileged and s.file.startswith("/")]
        self.assertEqual(bad, [])

    def test_every_root_row_says_so(self):  # G4
        bad = [s.id for s in registry.SETTINGS if s.privileged and "Needs root" not in s.description]
        self.assertEqual(bad, [])

    def test_the_three_pages_have_rows(self):
        pages = {s.page for s in registry.SETTINGS}
        self.assertLessEqual({"bluetooth", "storage", "updates"}, pages)


class BluetoothTests(StubCase):
    def wait_mutation(self, text: str) -> bool:
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if any(text in m for m in self.mutations()):
                return True
            time.sleep(0.02)
        return False

    def test_paired_devices_listed(self):
        r = row("bluetooth.paired", self.ctx())
        self.assertTrue(r.visible)
        self.assertEqual(r.value, "Pixel Buds, Keyboard K2")

    def test_hidden_with_a_reason_without_an_adapter(self):
        empty = self.tmp / "sysfs-empty"
        empty.mkdir()
        self.environ["SL_SYSFS"] = str(empty)
        for sid in ("bluetooth.power", "bluetooth.paired", "bluetooth.advanced"):
            with self.subTest(sid):
                r = row(sid, self.ctx())
                self.assertFalse(r.visible)
                self.assertIn("no Bluetooth adapter", r.reason)
                with self.assertRaises(Unavailable):
                    registry.write(registry.get(sid), self.ctx(), "off" if sid.endswith("power") else "run")

    def test_advanced_launches_blueman_detached(self):
        res = registry.write(registry.get("bluetooth.advanced"), self.ctx(), "run")
        self.assertEqual(res.commands, [["blueman-manager"]])
        self.assertTrue(self.wait_mutation("blueman-manager"))

    def test_advanced_dry_run_launches_nothing(self):
        res = registry.write(registry.get("bluetooth.advanced"), self.ctx(dry_run=True), "run")
        self.assertEqual(res.commands, [["blueman-manager"]])
        time.sleep(0.2)
        self.assertEqual(self.mutations(), [])

    def test_blueman_missing_is_hidden(self):
        (self.bin / "blueman-manager").unlink()
        r = row("bluetooth.advanced", self.ctx())
        self.assertFalse(r.visible)
        self.assertIn("blueman-manager", r.reason)


class StorageTests(StubCase):
    def trash(self) -> Path:
        d = self.home / ".local/share/Trash"
        (d / "files").mkdir(parents=True, exist_ok=True)
        (d / "info").mkdir(parents=True, exist_ok=True)
        return d

    def test_mounts_per_mount_usage(self):
        r = row("storage.mounts", self.ctx())
        self.assertEqual(r.error, "")
        self.assertEqual(r.value, "/ 45% of 95.4 GB; /boot 13% of 1.0 GB")

    def test_trash_size(self):
        self.assertEqual(row("storage.trash_size", self.ctx()).value, "empty")
        (self.trash() / "files" / "a.bin").write_bytes(b"x" * 2048)
        self.assertEqual(row("storage.trash_size", self.ctx()).value, "2.0 KB")

    def test_empty_trash_empties_only_the_home_trash(self):
        t = self.trash()
        (t / "files" / "a.bin").write_bytes(b"x" * 10)
        (t / "info" / "a.bin.trashinfo").write_text("[Trash Info]\n")
        outside = self.tmp / "keep.txt"
        outside.write_text("keep")
        res = registry.write(registry.get("storage.empty_trash"), self.ctx(), "run")
        self.assertEqual(res.commands, [["gio", "trash", "--empty"]])
        self.assertEqual(list((t / "files").iterdir()), [])
        self.assertEqual(row("storage.trash_size", self.ctx()).value, "empty")
        self.assertEqual(outside.read_text(), "keep")

    def test_empty_trash_dry_run_deletes_nothing(self):
        t = self.trash()
        (t / "files" / "a.bin").write_bytes(b"x")
        before = snapshot(self.home)
        registry.write(registry.get("storage.empty_trash"), self.ctx(dry_run=True), "run")
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.mutations(), [])

    def test_empty_trash_needs_the_word_run(self):
        with self.assertRaises(InvalidValue):
            registry.write(registry.get("storage.empty_trash"), self.ctx(), "yes")
        self.assertEqual(self.mutations(), [])

    def test_empty_trash_row_asks_for_confirmation(self):
        self.assertIn("cannot be undone", registry.get("storage.empty_trash").confirm)

    def test_low_disk_default_and_write(self):
        self.assertEqual(row("storage.low_disk", self.ctx()).value, 90)
        res = registry.write(registry.get("storage.low_disk"), self.ctx(), "80")
        self.assertEqual(res.files, ["~/.config/seclegion/storage.toml"])
        text = (self.home / ".config/seclegion/storage.toml").read_text()
        self.assertEqual(
            text,
            # REUSE-IgnoreStart
            "# SPDX-License-Identifier: MIT\n# Written by SecLegion Settings.\n"
            # REUSE-IgnoreEnd
            "[storage]\nlow_disk_percent = 80\n",
        )
        self.assertEqual(row("storage.low_disk", self.ctx()).value, 80)

    def test_low_disk_range_refused_before_any_write(self):  # negative
        for bad in ("69", "96", "abc", "-1"):
            with self.subTest(bad), self.assertRaises(InvalidValue):
                registry.write(registry.get("storage.low_disk"), self.ctx(), bad)
        self.assertEqual(snapshot(self.home), {})

    def test_crafted_storage_toml_falls_back(self):
        d = self.home / ".config/seclegion"
        d.mkdir(parents=True)
        for body in (
            "[storage]\nlow_disk_percent = 500\n",
            "[storage]\nlow_disk_percent = true\n",
            "not toml [",
        ):
            (d / "storage.toml").write_text(body)
            self.assertEqual(row("storage.low_disk", self.ctx()).value, 90)


class UpdatesTests(StubCase):
    def test_pending_count(self):
        self.assertEqual(row("updates.pending", self.ctx()).value, "3 pending")

    def test_up_to_date_is_exit_2_not_an_error(self):
        (self.state / "state.json").write_text(json.dumps({"updates": 0}))
        r = row("updates.pending", self.ctx())
        self.assertEqual((r.value, r.error), ("up to date", ""))

    def test_checkupdates_missing_is_hidden(self):
        (self.bin / "checkupdates").unlink()
        r = row("updates.pending", self.ctx())
        self.assertFalse(r.visible)
        self.assertIn("checkupdates", r.reason)

    def test_last_update_from_pacman_log(self):
        log = self.tmp / "pacman.log"
        log.write_text(
            "[2026-10-01T09:00:00+0200] [PACMAN] starting full system upgrade\n"
            "[2026-10-01T09:05:00+0200] [ALPM] upgraded foo (1 -> 2)\n"
            "[2026-10-10T08:01:02+0200] [PACMAN] starting full system upgrade\n"
            "[2026-10-12T18:30:11+0200] [PACMAN] Running 'pacman -S bar'\n"
            "[2026-10-12T18:31:00+0200] [ALPM] installed bar (1-1)\n"
        )
        self.environ["SL_PACMAN_LOG"] = str(log)
        self.assertEqual(row("updates.last", self.ctx()).value, "2026-10-10 08:01")
        log.write_text("[2026-10-12T18:30:11+0200] [PACMAN] Running 'pacman -S bar'\n")
        self.assertEqual(row("updates.last", self.ctx()).value, "no full upgrade in the log")

    def test_last_update_unreadable_log_is_data_not_a_crash(self):
        self.environ["SL_PACMAN_LOG"] = str(self.tmp / "missing.log")
        r = row("updates.last", self.ctx())
        self.assertIsNone(r.value)
        self.assertIn("not readable", r.error)

    def test_update_now_opens_a_terminal_and_never_runs_sudo_itself(self):
        res = registry.write(registry.get("updates.update_now"), self.ctx(), "run")
        (cmd,) = res.commands
        self.assertEqual(cmd[0], "xdg-terminal-exec")
        self.assertIn("sudo pacman -Syu", cmd[-1])
        end = time.monotonic() + 5
        while time.monotonic() < end and not self.mutations():
            time.sleep(0.02)
        self.assertEqual(len(self.mutations()), 1)
        self.assertTrue(self.mutations()[0].startswith("xdg-terminal-exec sh -c"))
        calls = [json.loads(ln)[0] for ln in (self.state / "calls.log").read_text().splitlines()]
        self.assertNotIn("sudo", calls)
        self.assertNotIn("pacman", calls)

    def test_update_now_dry_run_launches_nothing(self):
        registry.write(registry.get("updates.update_now"), self.ctx(dry_run=True), "run")
        time.sleep(0.2)
        self.assertEqual(self.mutations(), [])


class SnapshotKeepTests(StubCase):
    CONFIG = 'SUBVOLUME="/"\nFSTYPE="btrfs"\nNUMBER_LIMIT="2-7"\nTIMELINE_CREATE="no"\n'

    def config(self):
        d = self.etc / "snapper/configs"
        d.mkdir(parents=True)
        (d / "root").write_text(self.CONFIG)
        return d / "root"

    def test_root_row_previews_an_edit_of_the_config(self):
        s = registry.get("updates.snapshot_keep")
        self.assertTrue(s.privileged)
        self.assertTrue(registry.root_ready(s))
        with self.assertRaises(Refused):  # sandboxed ctx: never the real pkexec
            registry.write(s, self.ctx(), "5")
        self.config()
        before = snapshot(self.etc)
        res = registry.write(s, self.ctx(dry_run=True), "5")
        self.assertEqual(res.files, ["/etc/snapper/configs/root"])
        self.assertEqual(res.texts["/etc/snapper/configs/root"], self.CONFIG.replace('"2-7"', '"5"'))
        self.assertEqual(snapshot(self.etc), before)
        self.assertEqual(snapshot(self.home), {})

    def test_preview_without_a_config_is_unavailable(self):
        with self.assertRaises(Unavailable):
            registry.write(registry.get("updates.snapshot_keep"), self.ctx(dry_run=True), "5")
        self.assertEqual(snapshot(self.etc), {})

    def test_reads_current_value_from_the_snapper_config(self):
        self.assertEqual(row("updates.snapshot_keep", self.ctx()).value, 10)
        d = self.etc / "snapper/configs"
        d.mkdir(parents=True)
        (d / "root").write_text('SUBVOLUME="/"\nNUMBER_LIMIT="2-7"\n')
        self.assertEqual(row("updates.snapshot_keep", self.ctx()).value, 7)

    def test_range_enforced(self):
        for bad in ("0", "51"):
            with self.subTest(bad), self.assertRaises(InvalidValue):
                registry.write(registry.get("updates.snapshot_keep"), self.ctx(dry_run=True), bad)

    def test_root_apply_edits_only_number_limit(self):
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        f = self.config()
        f.chmod(0o640)
        self.assertEqual(rootapply.apply("updates.snapshot_keep", "5", False, env), 0)
        self.assertEqual(f.read_text(), self.CONFIG.replace('"2-7"', '"5"'))
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o640)  # snapper's own mode is kept
        (bak,) = (self.tmp / "rstate").iterdir()
        self.assertEqual(bak.read_text(), self.CONFIG)
        self.assertEqual(row("updates.snapshot_keep", self.ctx()).value, 5)

    def test_root_apply_appends_a_missing_number_limit(self):
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        f = self.config()
        f.write_text('SUBVOLUME="/"')
        rootapply.apply("updates.snapshot_keep", "9", False, env)
        self.assertEqual(f.read_text(), 'SUBVOLUME="/"\nNUMBER_LIMIT="9"\n')

    def test_root_apply_refuses_without_a_config(self):  # negative: never creates one
        env = {**self.environ, "SL_ROOT_STATE": str(self.tmp / "rstate")}
        for dry in (False, True):
            with self.subTest(dry), self.assertRaises(Unavailable):
                rootapply.apply("updates.snapshot_keep", "5", dry, env)
        self.assertEqual(snapshot(self.etc), {})
        self.assertFalse((self.tmp / "rstate").exists())

    def test_hidden_without_snapper(self):
        (self.bin / "snapper").unlink()
        r = row("updates.snapshot_keep", self.ctx())
        self.assertFalse(r.visible)
        self.assertIn("snapper", r.reason)


if __name__ == "__main__":
    unittest.main()
