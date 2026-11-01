# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Desktop content tests: notify-test parsing (stubbed commands), config
invariants, licence-similarity. Run: python3 -I -m unittest discover -s tests/desktop -v"""

import json
import os
import pathlib
import re
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOTIFY = os.path.join(ROOT, "tools", "seclegion-notify-test")
SIM = os.path.join(ROOT, "tools", "licence-similarity")


def stub_dir(tmp, owners=1, count="3", reuse_id=True, sendfail=False):
    """Create stub notify-send / busctl / swaync-client in tmp."""

    def w(name, body):
        p = os.path.join(tmp, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)

    if sendfail:
        w("notify-send", "exit 1\n")
    else:
        # -r ID echoes ID back when reuse_id, else a fresh id
        w(
            "notify-send",
            'if [ "$2" = "-r" ]; then echo %s; else echo 41; fi\n' % ("$3" if reuse_id else "99"),
        )
    comm = "".join(f"PID={100 + i}\nComm=swaync\n" for i in range(owners))
    w("busctl", f"cat <<'EOF'\n{comm}EOF\n[ {owners} -gt 0 ]\n")
    w("swaync-client", f"echo {count}\n")


def run_notify(args, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        stub_dir(tmp, **kw)
        env = {"PATH": tmp + ":/usr/bin:/bin", "HOME": tmp}
        return subprocess.run([NOTIFY] + args, env=env, capture_output=True, text=True)


class NotifyTest(unittest.TestCase):
    def test_all_pass(self):
        r = run_notify([])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("PASS bus owner: exactly one (comm=swaync)", r.stdout)
        self.assertIn("PASS replace-id", r.stdout)
        self.assertNotIn("FAIL", r.stdout)

    def test_two_bus_owners_fails(self):
        r = run_notify([], owners=2)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL bus owner: expected exactly 1, found 2", r.stdout)

    def test_no_owner_fails(self):
        r = run_notify([], owners=0)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL bus owner", r.stdout)

    def test_replace_id_mismatch_fails(self):
        r = run_notify([], reuse_id=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL replace-id", r.stdout)

    def test_send_failure_fails(self):
        r = run_notify([], sendfail=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL send low", r.stdout)

    def test_swaync_non_numeric_fails(self):
        r = run_notify([], count="oops")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL swaync-client", r.stdout)

    def test_dry_run_sends_nothing(self):
        # sendfail stubs would fail any real send; dry-run must still exit 0
        r = run_notify(["--dry-run"], sendfail=True, owners=2)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("+ notify-send -p", r.stderr)

    def test_bad_usage(self):
        self.assertEqual(run_notify(["bogus"]).returncode, 2)


class ConfigTest(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel)) as f:
            return f.read()

    def test_waybar_no_playerctl_or_fast_interval(self):
        s = self.read("desktop/waybar/config.jsonc")
        self.assertNotIn("playerctl", s)
        cfg = json.loads(re.sub(r"(?m)^\s*//.*$", "", s))
        self.assertIn("mpris#sl-media", cfg)
        for name, mod in cfg.items():
            # "once" = run at start and on a signal (the workspace pills): not polling
            if isinstance(mod, dict) and "interval" in mod and mod["interval"] != "once":
                self.assertGreaterEqual(mod["interval"], 5, name)

    def test_waybar_disk_chip(self):
        cfg = json.loads(re.sub(r"(?m)^\s*//.*$", "", self.read("desktop/waybar/config.jsonc")))
        # the chip lives in the statistics drawer (T12), not on the bar itself
        self.assertIn("disk", cfg["group/sl-stats"]["modules"])
        self.assertEqual(
            cfg["disk"],
            {
                "format": "\U000f02ca {free}",
                "path": "/",
                "interval": 30,
                "tooltip-format": "{used} used of {total}",
                "on-click": "thunar",
                "states": {"warning": 85, "critical": 95},
            },
        )
        css = self.read("desktop/waybar/style.css")
        for sel in ("#disk.warning", "#disk.critical"):
            self.assertIn(sel, css)

    def test_swaync_style(self):
        s = self.read("desktop/swaync/style.css")
        self.assertNotIn("00e5ff", s)
        self.assertIn("border-color: @sl_osd_frame", s)  # colours come from theme tokens
        self.assertNotRegex(s, r"#[0-9a-fA-F]{6}")
        row = re.search(r"\.floating-notifications \.notification-row\s*\{([^}]*)\}", s).group(1)
        self.assertNotIn("50px", row)
        json.loads(self.read("desktop/swaync/config.json"))


class SimilarityTest(unittest.TestCase):
    def sim(self, a, b, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            pa, pb = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            pathlib.Path(pa).write_text(a)
            pathlib.Path(pb).write_text(b)
            return subprocess.run(["python3", "-I", SIM, pa, pb, *extra], capture_output=True, text=True)

    def test_identical_fails(self):
        t = "one two three four five six seven\neight nine ten eleven twelve thirteen\n"
        self.assertEqual(self.sim(t, t).returncode, 1)

    def test_different_passes(self):
        r = self.sim("alpha beta gamma delta epsilon zeta eta\n", "red green blue cyan pink gold teal\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_ignores_comments_blank_braces(self):
        r = self.sim(
            "// c\n\n{\n}\nreal line here is long enough ok\n",
            "// c\n\n{\n}\nother stuff entirely different words\n",
        )
        self.assertIn("line overlap:   0.0%", r.stdout)

    def test_ignore_keys(self):
        a = '{"positionX": "right",\n"foo": "uniqueaaa bbb ccc ddd eee fff"}\n'
        b = '{"positionX": "left",\n"foo": "different words go here now okay yes"}\n'
        base = self.sim(a, b)
        keys = self.sim(a, b, "--ignore-keys")
        self.assertNotEqual(base.stdout, keys.stdout)

    def test_max_flag(self):
        t = "one two three four five six seven\n"
        self.assertEqual(self.sim(t, t, "--max", "100").returncode, 0)


WS = os.path.join(ROOT, "desktop", "waybar", "seclegion-ws")
WSEVENTS = os.path.join(ROOT, "desktop", "waybar", "seclegion-wsevents")
GEN = os.path.join(ROOT, "tools", "gen-waybar-ws")
BAR = os.path.join(ROOT, "desktop", "waybar", "config.jsonc")


def hyprctl_stub(tmp, workspaces, active, clients=None):
    """A hyprctl that answers `workspaces|activeworkspace|clients -j` from fixed data
    and appends each call's first argument to tmp/hyprctl-calls."""
    data = os.path.join(tmp, "hyprctl-data.json")
    with open(data, "w") as f:
        json.dump({"workspaces": workspaces, "activeworkspace": {"id": active}, "clients": clients or []}, f)
    stub = os.path.join(tmp, "hyprctl")
    with open(stub, "w") as f:
        f.write(
            "#!/usr/bin/env python3\nimport json,sys\n"
            "open({!r},'a').write(sys.argv[1]+'\\n')\n"
            "print(json.dumps(json.load(open({!r}))[sys.argv[1]]))\n".format(
                os.path.join(tmp, "hyprctl-calls"), data
            )
        )
    os.chmod(stub, 0o755)
    return stub


def load_jsonc(path):
    with open(path) as f:
        return json.loads("\n".join(ln for ln in f if not ln.lstrip().startswith("//")))


class WsPillTest(unittest.TestCase):
    """seclegion-ws N against a stubbed hyprctl (SL_HYPRCTL)."""

    def ws(self, n, workspaces, active, clients=None, urgent=None):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"workspaces": workspaces, "activeworkspace": {"id": active}, "clients": clients or []}
            with open(os.path.join(tmp, "data.json"), "w") as f:
                json.dump(data, f)
            stub = os.path.join(tmp, "hyprctl")
            with open(stub, "w") as f:
                f.write(
                    "#!/usr/bin/env python3\nimport json,sys\n"
                    "print(json.dumps(json.load(open({!r}))[sys.argv[1]]))\n".format(
                        os.path.join(tmp, "data.json")
                    )
                )
            os.chmod(stub, 0o755)
            ufile = os.path.join(tmp, "urgent")
            with open(ufile, "w") as f:
                f.write("".join(a + "\n" for a in (urgent or [])))
            env = {"PATH": "/usr/bin:/bin", "SL_HYPRCTL": stub, "SL_WS_URGENT": ufile}
            r = subprocess.run([WS, str(n)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    W = [{"id": 1, "windows": 2}, {"id": 2, "windows": 0}, {"id": 3, "windows": 1}, {"id": 4, "windows": 1}]

    def test_missing_workspace_is_hidden(self):
        self.assertEqual(self.ws(15, self.W, 1), {"text": "", "class": "hidden"})

    def test_hidden_output_is_compact_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = os.path.join(tmp, "hyprctl")
            with open(stub, "w") as f:
                f.write("#!/bin/sh\n[ \"$1\" = workspaces ] && echo '[]' || echo '{\"id\":1}'\n")
            os.chmod(stub, 0o755)
            r = subprocess.run(
                [WS, "15"], env={"PATH": "/usr/bin:/bin", "SL_HYPRCTL": stub}, capture_output=True, text=True
            )
        self.assertIn('"class":"hidden"', r.stdout)

    def test_active_occupied_empty(self):
        self.assertEqual(self.ws(1, self.W, 1), {"text": "1", "class": "active"})
        self.assertEqual(self.ws(3, self.W, 1), {"text": "3", "class": "occupied"})
        self.assertEqual(self.ws(2, self.W, 1), {"text": "2", "class": "empty"})  # persistent and empty

    def test_urgent_window_marks_its_workspace(self):
        clients = [{"address": "0xabc", "workspace": {"id": 3}}, {"address": "0xdef", "workspace": {"id": 4}}]
        self.assertEqual(self.ws(3, self.W, 1, clients, ["abc"])["class"], "urgent")
        self.assertEqual(self.ws(4, self.W, 1, clients, ["abc"])["class"], "occupied")
        self.assertEqual(self.ws(3, self.W, 3, clients, ["abc"])["class"], "active")  # focus wins

    def test_hyprctl_failure_hides_the_pill(self):
        env = {"PATH": "/usr/bin:/bin", "SL_HYPRCTL": "/nonexistent/hyprctl"}
        r = subprocess.run([WS, "3"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["class"], "hidden")

    def test_bad_usage(self):
        self.assertEqual(subprocess.run([WS, "x"], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run([WS], capture_output=True).returncode, 2)


class WsConfigTest(unittest.TestCase):
    def test_generated_files_are_current(self):
        r = subprocess.run([GEN, "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_twenty_pills_with_lua_dispatch(self):
        cfg = load_jsonc(BAR)
        self.assertNotIn("hyprland/workspaces", cfg)
        left = [m for m in cfg["modules-left"] if m.startswith("custom/ws")]
        self.assertEqual(left, [f"custom/ws{i}" for i in range(1, 21)])
        for i in range(1, 21):
            m = cfg[f"custom/ws{i}"]
            self.assertEqual(
                m["exec"],
                f'cat "$XDG_RUNTIME_DIR/seclegion/ws/{i}.json" 2>/dev/null'
                ' || echo \'{"text":"","class":"hidden"}\'',
            )
            self.assertEqual((m["return-type"], m["interval"], m["signal"]), ("json", "once", 8))
            self.assertEqual(m["on-click"], f"hyprctl dispatch 'hl.dsp.focus({{ workspace = \"{i}\" }})'")
            self.assertIn('workspace = "e-1"', m["on-scroll-up"])
            self.assertIn('workspace = "e+1"', m["on-scroll-down"])
            self.assertTrue(all("dispatch workspace" not in v for v in m.values() if isinstance(v, str)))

    def test_exec_prints_the_rendered_file_or_a_hidden_pill(self):
        cmd = load_jsonc(BAR)["custom/ws3"]["exec"]
        with tempfile.TemporaryDirectory() as rt:
            env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": rt}
            r = subprocess.run(["sh", "-c", cmd], env=env, capture_output=True, text=True)
            self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {"text": "", "class": "hidden"}))
            os.makedirs(os.path.join(rt, "seclegion", "ws"))
            with open(os.path.join(rt, "seclegion", "ws", "3.json"), "w") as f:
                f.write('{"text":"3","class":"active"}\n')
            r = subprocess.run(["sh", "-c", cmd], env=env, capture_output=True, text=True)
            self.assertEqual(r.stdout, '{"text":"3","class":"active"}\n')

    def test_css_covers_every_pill_and_state(self):
        with open(os.path.join(ROOT, "desktop", "waybar", "style.css")) as f:
            css = f.read()
        for state in ("", ":hover", ".occupied", ".empty", ".active", ".urgent", ".hidden"):
            for i in (1, 20):
                self.assertIn(f"#custom-ws{i}{state}", css)
        self.assertNotIn("#workspaces", css)


class WsEventsTest(unittest.TestCase):
    """seclegion-wsevents against a fake event socket and a fake waybar."""

    def test_burst_is_one_signal_and_urgent_is_tracked(self):
        import socket
        import time

        with tempfile.TemporaryDirectory() as tmp:
            hits = os.path.join(tmp, "hits")
            waybar = subprocess.Popen(
                [
                    "python3",
                    "-c",
                    "import signal,time,sys\n"
                    f"def h(*a): open({hits!r},'a').write('x')\n"
                    "signal.signal(signal.SIGRTMIN+8,h)\n"
                    "print('ready',flush=True)\n"
                    "time.sleep(30)\n",
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            self.addCleanup(waybar.kill)
            waybar.stdout.readline()
            pg = os.path.join(tmp, "pgrep")
            with open(pg, "w") as f:
                f.write(
                    f'#!/bin/sh\n[ "$1 $2 $3" = "-x -u {os.getuid()}" ] '
                    f'&& [ "$4" = waybar ] && echo {waybar.pid}\n'
                )
            os.chmod(pg, 0o755)
            sock = os.path.join(tmp, "s2")
            srv = socket.socket(socket.AF_UNIX)
            srv.bind(sock)
            srv.listen(1)
            urgent = os.path.join(tmp, "urgent")
            env = {
                "PATH": "/usr/bin:/bin",
                "SL_WS_PGREP": pg,
                "SL_WS_SOCKET": sock,
                "SL_WS_URGENT": urgent,
                "SL_WS_ONCE": "1",
                "XDG_RUNTIME_DIR": tmp,
                "SL_HYPRCTL": hyprctl_stub(tmp, [{"id": 1, "windows": 0}], 1),
            }
            p = subprocess.Popen([WSEVENTS], env=env, stderr=subprocess.PIPE, text=True)
            self.addCleanup(p.kill)
            conn, _ = srv.accept()
            time.sleep(0.4)
            self.assertEqual(open(hits).read(), "x")  # connect: rendered, then one signal
            with open(os.path.join(tmp, "seclegion", "ws", "1.json")) as f:
                self.assertEqual(f.read(), '{"text":"1","class":"active"}\n')
            conn.sendall(
                b"".join(
                    b"workspace>>%d\nopenwindow>>a,1,x,y\nfocusedmon>>m,1\nirrelevant>>z\n" % i
                    for i in range(1, 6)
                )
            )
            conn.sendall(b"urgent>>dead01\n")
            time.sleep(0.6)
            with open(urgent) as f:
                self.assertEqual(f.read(), "dead01\n")
            self.assertEqual(open(hits).read(), "xx")  # 11 relevant events, one signal
            conn.sendall(b"activewindowv2>>dead01\n")  # focus clears urgent and redraws
            time.sleep(0.6)
            with open(urgent) as f:
                self.assertEqual(f.read(), "")
            self.assertEqual(open(hits).read(), "xxx")
            conn.sendall(b"someunrelated>>1\n")
            time.sleep(0.4)
            self.assertEqual(open(hits).read(), "xxx")  # ignored events send nothing
            conn.close()
            p.communicate(timeout=10)


def load_wsevents():
    """seclegion-wsevents as a module (it has no .py suffix), without bytecode."""
    import importlib.util
    import sys
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("seclegion_wsevents", WSEVENTS)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


class WsEventsSocketTest(unittest.TestCase):
    """Which Hyprland event socket seclegion-wsevents follows, in a fake runtime dir."""

    def instance(self, rt, sig, live, mtime=None):
        import socket

        d = os.path.join(rt, "hypr", sig)
        os.makedirs(d)
        path = os.path.join(d, ".socket2.sock")
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(path)
        if live:
            srv.listen(1)
            srv.settimeout(5)
            self.addCleanup(srv.close)
        else:
            srv.close()  # what a crashed Hyprland leaves: the file, nobody listening
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return srv

    def follows(self, rt, srv, extra_env):
        env = {
            "PATH": "/usr/bin:/bin",
            "XDG_RUNTIME_DIR": rt,
            "SL_WS_PGREP": "true",
            "SL_WS_URGENT": os.path.join(rt, "urgent"),
            "SL_HYPRCTL": "false",
            "SL_WS_ONCE": "1",
        }
        env.update(extra_env)
        p = subprocess.Popen([WSEVENTS], env=env, stderr=subprocess.PIPE, text=True)
        self.addCleanup(p.kill)
        try:
            conn, _ = srv.accept()
        except TimeoutError:
            p.kill()
            self.fail("wsevents never connected to the live socket: " + p.communicate()[1])
        conn.close()
        err = p.communicate(timeout=10)[1]
        self.assertEqual(p.returncode, 0, err)

    def test_refused_env_signature_falls_through_to_a_live_instance(self):
        with tempfile.TemporaryDirectory() as rt:
            self.instance(rt, "crashed", live=False)
            srv = self.instance(rt, "running", live=True)
            self.follows(rt, srv, {"HYPRLAND_INSTANCE_SIGNATURE": "crashed"})

    def test_stale_newer_dir_loses_to_an_older_live_one(self):
        with tempfile.TemporaryDirectory() as rt:
            srv = self.instance(rt, "older", live=True, mtime=1_000_000)
            self.instance(rt, "newer", live=False, mtime=2_000_000)
            self.follows(rt, srv, {})

    def test_backoff_doubles_to_a_cap_and_resets_after_a_connection(self):
        import socket
        from unittest import mock

        mod = load_wsevents()
        a, b = socket.socketpair()
        b.close()  # one session that ends at once
        delays = []

        def sleep(d):
            delays.append(d)
            if len(delays) == 12:
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as rt:
            env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": rt, "SL_WS_URGENT": os.path.join(rt, "urgent")}
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch.object(mod, "redraw"),
                mock.patch.object(mod, "connect", side_effect=[None] * 8 + [a] + [None] * 3),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    mod.main(sleep=sleep)
        self.assertEqual(delays, [2, 4, 8, 10, 10, 10, 10, 10, 2, 2, 4, 8])

    def render(self, rt, stub, urgent=()):
        from unittest import mock

        mod = load_wsevents()
        ufile = os.path.join(rt, "urgent")
        with open(ufile, "w") as f:
            f.write("".join(a + "\n" for a in urgent))
        env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": rt, "SL_HYPRCTL": stub, "SL_WS_URGENT": ufile}
        with mock.patch.dict(os.environ, env, clear=True):
            mod.render()
        d = os.path.join(rt, "seclegion", "ws")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertEqual(sorted(os.listdir(d)), sorted(f"{n}.json" for n in range(1, 21)))  # no .tmp left
        out = {}
        for n in range(1, 21):
            with open(os.path.join(d, f"{n}.json")) as f:
                text = f.read()
            self.assertTrue(text.endswith("}\n") and "\n" not in text[:-1], text)
            out[n] = json.loads(text)
        return out

    def test_render_writes_every_pill_from_one_snapshot(self):
        with tempfile.TemporaryDirectory() as rt:
            ws = [
                {"id": 1, "windows": 2},
                {"id": 2, "windows": 0},
                {"id": 3, "windows": 1},
                {"id": 4, "windows": 1},
            ]
            clients = [
                {"address": "0xabc", "workspace": {"id": 3}},
                {"address": "0xdef", "workspace": {"id": 4}},
            ]
            out = self.render(rt, hyprctl_stub(rt, ws, 1, clients), urgent=["abc"])
            with open(os.path.join(rt, "hyprctl-calls")) as f:  # one snapshot for all 20 pills
                self.assertEqual(f.read().split(), ["workspaces", "activeworkspace", "clients"])
        self.assertEqual(out[1], {"text": "1", "class": "active"})
        self.assertEqual(out[2], {"text": "2", "class": "empty"})
        self.assertEqual(out[3], {"text": "3", "class": "urgent"})
        self.assertEqual(out[4], {"text": "4", "class": "occupied"})
        for n in range(5, 21):
            self.assertEqual(out[n], {"text": "", "class": "hidden"})

    def test_render_hides_every_pill_when_hyprctl_fails(self):
        with tempfile.TemporaryDirectory() as rt:
            out = self.render(rt, "/nonexistent/hyprctl")
        self.assertEqual(set(map(json.dumps, out.values())), {json.dumps({"text": "", "class": "hidden"})})

    def test_nothing_listening_connects_to_nothing(self):
        with tempfile.TemporaryDirectory() as rt:
            self.instance(rt, "gone", live=False)
            from unittest import mock

            mod = load_wsevents()
            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": rt}, clear=True):
                self.assertIsNone(mod.connect())


if __name__ == "__main__":
    unittest.main()
