#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Behaviour tests for tools/seclegion-keys-lint (run as a subprocess on tiny fixtures).

python3 -m unittest discover -s tests/keys -p 'test_lint.py'
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINT = os.path.join(ROOT, "tools", "seclegion-keys-lint")
FIX = os.path.join(ROOT, "tests", "keys", "fixtures")
OURS = os.path.join(ROOT, "desktop", "hypr", "seclegion-keys.lua")


class LintTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def lint(self, owner, ours, live=None):
        """Lint two Lua sources given as text; returns (rc, stdout, stderr)."""
        args = [sys.executable, LINT, self.write("owner.lua", owner), self.write("ours.lua", ours)]
        if live is not None:
            args += ["--binds-json", self.write("binds.json", json.dumps(live))]
        return self.run_lint(args)

    def run_lint(self, args):
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertNotIn("Traceback", p.stderr)
        return p.returncode, p.stdout, p.stderr

    def collides(self, owner_key, our_key):
        rc, out, err = self.lint(
            f'hl.bind("{owner_key}", hl.dsp.exec_cmd("a"))\n', f'hl.bind("{our_key}", hl.dsp.exec_cmd("b"))\n'
        )
        self.assertEqual(rc, 1, (out, err))
        self.assertIn("collisions=1", out)

    def clean(self, owner, ours, live=None):
        rc, out, err = self.lint(owner, ours, live)
        self.assertEqual((rc, out), (0, "collisions=0\n"), err)

    def unknown(self, owner, ours='hl.bind("SUPER + F13", hl.dsp.exec_cmd("b"))\n', live=None):
        rc, out, err = self.lint(owner, ours, live)
        self.assertEqual(rc, 2, (out, err))
        self.assertNotIn("collisions=", out)
        self.assertIn("seclegion-keys-lint:", err)

    # --- the committed fixtures ---------------------------------------------------------
    def test_committed_keys_do_not_collide_with_owner_snapshot(self):
        rc, out, _ = self.run_lint([sys.executable, LINT, os.path.join(FIX, "owner-keybinds.lua"), OURS])
        self.assertEqual((rc, out), (0, "collisions=0\n"))

    def test_mutant_collides_once(self):
        rc, out, _ = self.run_lint(
            [sys.executable, LINT, os.path.join(FIX, "owner-keybinds.lua"), os.path.join(FIX, "mutant.lua")]
        )
        self.assertEqual(rc, 1)
        self.assertIn("collisions=1", out)

    # --- normalisation ------------------------------------------------------------------
    def test_super_aliases_collide(self):
        for a, b in (("SUPER", "META"), ("SUPER", "MOD4"), ("META", "WIN"), ("LOGO", "SUPER")):
            with self.subTest(a=a, b=b):
                self.collides(f"{a} + Q", f"{b} + Q")

    def test_ctrl_alias_collides(self):
        self.collides("CTRL + Q", "CONTROL + Q")

    def test_modifier_order_and_case(self):
        self.collides("super + alt + 1", "ALT + SUPER + 1")

    def test_super_alt_digit(self):
        self.collides("SUPER + ALT + 1", "SUPER + ALT + code:10")

    def test_super_ctrl_left(self):
        self.collides("SUPER + CTRL + left", "SUPER + CONTROL + Left")

    def test_digit_vs_keycode(self):
        self.collides("SUPER + 1", "SUPER + code:10")

    def test_arabic_alias_vs_keycode(self):
        self.collides("SUPER + Arabic_1", "SUPER + code:10")
        self.collides("SUPER + Arabic_zain", "SUPER + code:60")

    def test_paren_keysyms_vs_keycodes_either_layout(self):
        for key in ("parenleft", "parenright"):
            for code in ("code:18", "code:19"):
                with self.subTest(key=key, code=code):
                    self.collides(f"SUPER + {key}", f"SUPER + {code}")
        self.collides("SUPER + code:19", "SUPER + parenleft")

    def test_different_mods_do_not_collide(self):
        self.clean(
            'hl.bind("SUPER + 1", hl.dsp.exec_cmd("a"))\n',
            'hl.bind("SUPER + ALT + 1", hl.dsp.exec_cmd("b"))\n',
        )

    def test_bound_twice_in_our_file(self):
        rc, out, _ = self.lint(
            'hl.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            'hl.bind("SUPER + 1", hl.dsp.exec_cmd("a"))\nhl.bind("SUPER + code:10", hl.dsp.exec_cmd("b"))\n',
        )
        self.assertEqual(rc, 1)
        self.assertIn("bound twice", out)

    # --- the evaluator ------------------------------------------------------------------
    def test_numeric_for_loop_bind(self):
        rc, out, _ = self.lint(
            'hl.bind("SUPER + 3", hl.dsp.exec_cmd("a"))\n',
            'for i = 1, 5 do\n  hl.bind("SUPER + " .. i, hl.dsp.exec_cmd("b"))\nend\n',
        )
        self.assertEqual(rc, 1)
        self.assertIn("collisions=1", out)

    def test_variables_and_concatenation(self):
        rc, out, _ = self.lint(
            'local m = "SUPER"\nhl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n',
            'hl.bind("SUPER + Q", hl.dsp.exec_cmd("b"))\n',
        )
        self.assertEqual(rc, 1, out)

    def test_local_in_block_is_scoped(self):
        # inner `local m` must not leak out of the do-block, nor shadow the outer m
        self.clean(
            'local m = "SUPER"\ndo local m = "ALT" end\nhl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n',
            'hl.bind("ALT + Q", hl.dsp.exec_cmd("b"))\n',
        )
        self.unknown('do local m = "SUPER" end\nhl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n')

    def test_non_colliding_clean(self):
        self.clean(
            'hl.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n', 'hl.bind("SUPER + F13", hl.dsp.exec_cmd("b"))\n'
        )

    # --- exit 2: anything the evaluator cannot work out ---------------------------------
    def test_unknown_forms(self):
        forms = {
            "hl alias": 'local h = hl\nh.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            "hl index": 'hl["bind"]("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            "bind alias": 'local b = hl.bind\nb("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            "bind table call": 'hl.bind{ "SUPER + Q" }\n',
            "bind string call": 'hl.bind "SUPER + Q"\n',
            "method on a key part": (
                'local m = "super"\n'
                'hl.bind(m:upper() .. " + period", hl.dsp.exec_cmd("a"))\n'
            ),
            "call on a key part": 'hl.bind(mod() .. " + Q", hl.dsp.exec_cmd("a"))\n',
            "index on a key part": 'local t = "SUPER"\nhl.bind(t[1] .. " + Q", hl.dsp.exec_cmd("a"))\n',
            "unresolved atom": 'hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd("a"))\n',
            "text after the key": 'hl.bind("SUPER + Q" or "SUPER + W", hl.dsp.exec_cmd("a"))\n',
            "unscoped reassignment": (
                'local m = "SUPER"\n'
                'm = "ALT"\n'
                'hl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n'
            ),
            "local of an if used outside": (
                'if true then local m = "SUPER" end\n'
                'hl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n'
            ),
            "local of a function used outside": (
                'local function f() local m = "SUPER" end\n'
                'hl.bind(m .. " + Q", hl.dsp.exec_cmd("a"))\n'
            ),
            "generic for variable": (
                'for _, k in ipairs({"1"}) do hl.bind("SUPER + " .. k, hl.dsp.exec_cmd("a")) end\n'
            ),
            "generic for shadowing": (
                'local k = "1"\n'
                'for _, k in ipairs({"2"}) do hl.bind("SUPER + " .. k, hl.dsp.exec_cmd("a")) end\n'
            ),
            "function parameter": 'function f(k) hl.bind("SUPER + " .. k, hl.dsp.exec_cmd("a")) end\n',
            "unicode escape": 'hl.bind("SUPER + \\u{41}", hl.dsp.exec_cmd("a"))\n',
            "unicode escape elsewhere": 'local x = "\\u{41}"\n',
            "non-numeric for bounds": 'for i = 1, n do hl.bind("SUPER + " .. i, hl.dsp.exec_cmd("a")) end\n',
        }
        for name, src in forms.items():
            with self.subTest(name):
                self.unknown(src)

    def test_unknown_form_in_our_file(self):
        self.unknown(
            'hl.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            'hl["bind"]("SUPER + F13", hl.dsp.exec_cmd("b"))\n',
        )

    def test_missing_file_is_exit_2(self):
        rc, _, err = self.run_lint([sys.executable, LINT, os.path.join(self.dir, "nope.lua"), OURS])
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", err)

    # --- submaps: binds inside hl.define_submap have their own scope -------------------
    SUB = 'hl.define_submap("resize", function()\n{body}end)\n'

    def test_submap_dup(self):
        # the same key twice inside one submap is a collision (red case: the scope must not hide it)
        body = (
            '  hl.bind("left", hl.dsp.window.resize({ x = -40, y = 0, relative = true }))\n'
            '  hl.bind("left", hl.dsp.window.resize({ x = 40, y = 0, relative = true }))\n'
        )
        rc, out, _ = self.lint("", self.SUB.format(body=body))
        self.assertEqual(rc, 1, out)
        self.assertIn("collisions=1", out)
        self.assertIn("submap resize", out)

    def test_submap_dup_with_reset_argument(self):
        body = '  hl.bind("left", hl.dsp.exec_cmd("a"))\n  hl.bind("LEFT", hl.dsp.exec_cmd("b"))\n'
        rc, out, _ = self.lint("", self.SUB.format(body=body).replace('"resize", ', '"resize", "reset", '))
        self.assertEqual(rc, 1, out)

    def test_submap_key_is_not_the_global_key(self):
        # `left` in the submap vs a global `left`, and the same key in two submaps: no collision
        owner = 'hl.bind("left", hl.dsp.exec_cmd("a"))\n'
        ours = (
            self.SUB.format(body='  hl.bind("left", hl.dsp.exec_cmd("b"))\n')
            + 'hl.define_submap("other", function()\n  hl.bind("left", hl.dsp.exec_cmd("c"))\nend)\n'
            + 'hl.bind("SUPER + ALT + R", hl.dsp.submap("resize"))\n'
        )
        self.clean(owner, ours)

    def test_global_bind_after_submap_is_global_again(self):
        # the Q inside the submap is not the owner's Q; the Q after the submap is
        inside = self.SUB.format(body='  hl.bind("SUPER + Q", hl.dsp.exec_cmd("b"))\n')
        self.clean('hl.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n', inside)
        rc, out, _ = self.lint(
            'hl.bind("SUPER + Q", hl.dsp.exec_cmd("a"))\n',
            inside + 'hl.bind("SUPER + Q", hl.dsp.exec_cmd("c"))\n',
        )
        self.assertEqual(rc, 1, out)

    def test_submap_unknown_forms_are_exit_2(self):
        for name, src in {
            "name not a string": 'hl.define_submap(nm, function() hl.bind("a", hl.dsp.exec_cmd("b")) end)\n',
            "body not inline": 'local f = 1\nhl.define_submap("r", f)\n',
            "not called directly": 'hl.define_submap "r"\n',
        }.items():
            with self.subTest(name):
                self.unknown("", src)

    def test_function_bind_is_read(self):
        # Super+Ctrl+1 bound to a Lua function (the size presets) still takes part in the check
        rc, out, _ = self.lint(
            'hl.bind("SUPER + CONTROL + 1", hl.dsp.exec_cmd("a"))\n',
            'hl.bind("SUPER + CONTROL + code:10", function() M.winsize(50) end, { description = "x" })\n',
        )
        self.assertEqual(rc, 1, out)

    # --- --binds-json -------------------------------------------------------------------
    def test_live_bind_collides(self):
        live = [{"modmask": 64, "key": "Q", "keycode": 0, "description": "owner"}]
        rc, out, _ = self.lint("", 'hl.bind("MOD4 + Q", hl.dsp.exec_cmd("b"))\n', live)
        self.assertEqual(rc, 1)
        self.assertIn("collisions=1", out)

    def test_live_keycode_bind_collides_when_listed_with_keycode(self):
        live = [{"modmask": 64, "key": "", "keycode": 10, "description": "owner"}]
        rc, out, _ = self.lint("", 'hl.bind("SUPER + 1", hl.dsp.exec_cmd("b"))\n', live)
        self.assertEqual(rc, 1, out)

    def test_unreadable_live_binds_are_exit_2(self):
        live = [{"modmask": 64, "key": "", "keycode": 0, "description": "owner code:N bind"}]
        self.unknown("", 'hl.bind("SUPER + F13", hl.dsp.exec_cmd("b"))\n', live)

    def test_our_own_live_binds_are_ignored(self):
        live = [
            {"modmask": 64, "key": "", "keycode": 0, "description": "seclegion-keys: ours"},
            {"modmask": 64, "key": "", "keycode": 0, "description": "x", "submap": "resize"},
        ]
        self.clean("", 'hl.bind("SUPER + F13", hl.dsp.exec_cmd("b"))\n', live)


if __name__ == "__main__":
    unittest.main()
