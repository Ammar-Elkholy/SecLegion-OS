# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Waybar bar-module helpers (seclegion-vpn, seclegion-sec) against fake
nmcli / nft / /proc/net, and the network module's config. Missing hardware or
tools must be quiet: valid JSON, exit 0, nothing on stderr.
Run: python3 -I -m unittest discover -s tests/desktop -v"""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WB = os.path.join(ROOT, "desktop", "waybar")
VPN = os.path.join(WB, "seclegion-vpn")
SEC = os.path.join(WB, "seclegion-sec")
GPU = os.path.join(WB, "seclegion-gpu")
UPTIME = os.path.join(WB, "seclegion-uptime")
DND = os.path.join(WB, "seclegion-dnd")

TCP_HEAD = (
    "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
)


def tcp_line(port, state):
    return (
        f"   0: 00000000:{port:04X} 00000000:0000 {state} "
        "00000000:00000000 00:00000000 00000000     0        0 1\n"
    )


class Fake(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = self._td.name

    def script(self, name, body):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        return p

    def run_helper(self, helper, **env):
        e = {"PATH": "/usr/bin:/bin", "HOME": self.tmp}
        e.update(env)
        r = subprocess.run([helper], env=e, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", "helper must be quiet on stderr")
        return json.loads(r.stdout)


class VpnTest(Fake):
    def nmcli(self, out, rc=0):
        return self.script("nmcli", f"cat <<'EOF'\n{out}EOF\nexit {rc}\n")

    def test_none_active_is_hidden(self):
        j = self.run_helper(VPN, SL_NMCLI=self.nmcli("802-11-wireless:home\nbridge:virbr0\nloopback:lo\n"))
        self.assertEqual(j, {"text": "", "class": "hidden"})

    def test_vpn_and_wireguard_shown(self):
        j = self.run_helper(
            VPN, SL_NMCLI=self.nmcli("802-11-wireless:home\nvpn:Work\\: VPN\nwireguard:wg0\n")
        )
        self.assertEqual(j["class"], "active")
        self.assertIn("Work: VPN", j["text"])
        self.assertIn("+1", j["text"])
        self.assertEqual(j["tooltip"], "VPN: Work: VPN\nVPN: wg0")

    def test_nmcli_missing_is_quiet(self):
        j = self.run_helper(VPN, SL_NMCLI=os.path.join(self.tmp, "no-such-nmcli"))
        self.assertEqual(j["text"], "")
        self.assertEqual(j["class"], "hidden")

    def test_nmcli_failing_is_quiet(self):
        j = self.run_helper(VPN, SL_NMCLI=self.nmcli("", rc=8))
        self.assertEqual(j["class"], "hidden")


class SecTest(Fake):
    def proc(self, tcp, tcp6):
        d = os.path.join(self.tmp, "net")
        os.makedirs(d, exist_ok=True)
        for name, rows in (("tcp", tcp), ("tcp6", tcp6)):
            if rows is not None:
                with open(os.path.join(d, name), "w") as f:
                    f.write(TCP_HEAD + "".join(rows))
        return d

    def nft(self, out, rc=0):
        return self.script("nft", f"cat <<'EOF'\n{out}EOF\nexit {rc}\n")

    def test_counts_distinct_listening_ports_only(self):
        d = self.proc(
            [tcp_line(22, "0A"), tcp_line(80, "0A"), tcp_line(5000, "01")],
            [tcp_line(22, "0A"), tcp_line(443, "0A"), tcp_line(6000, "06")],
        )
        j = self.run_helper(SEC, SL_PROC_NET=d, SL_NFT=os.path.join(self.tmp, "none"))
        self.assertEqual(j["text"], "\U000f0483 3")
        self.assertEqual(j["tooltip"], "Listening TCP ports: 3")
        self.assertEqual(j["class"], "ok")

    def test_firewall_part_left_out_without_nft(self):
        d = self.proc([tcp_line(22, "0A")], [])
        j = self.run_helper(SEC, SL_PROC_NET=d, SL_NFT=os.path.join(self.tmp, "none"))
        self.assertNotIn("fw", j["text"])
        self.assertNotIn("Firewall", j["tooltip"])

    def test_firewall_part_left_out_when_not_permitted(self):
        d = self.proc([tcp_line(22, "0A")], [])
        nft = self.script("nft", "echo 'Operation not permitted' >&2; exit 1\n")
        j = self.run_helper(SEC, SL_PROC_NET=d, SL_NFT=nft)
        self.assertNotIn("fw", j["text"])
        self.assertNotIn("Firewall", j["tooltip"])

    def test_firewall_active(self):
        d = self.proc([tcp_line(22, "0A")], [])
        j = self.run_helper(
            SEC,
            SL_PROC_NET=d,
            SL_NFT=self.nft("table inet f {\n chain input {\n  type filter hook input priority 0;\n }\n}\n"),
        )
        self.assertTrue(j["text"].endswith(" fw"))
        self.assertIn("Firewall: active", j["tooltip"])
        self.assertEqual(j["class"], "ok")

    def test_firewall_without_hook_chains_warns(self):
        d = self.proc([tcp_line(22, "0A")], [])
        j = self.run_helper(SEC, SL_PROC_NET=d, SL_NFT=self.nft("table inet f {\n chain x {\n }\n}\n"))
        self.assertTrue(j["text"].endswith(" no-fw"))
        self.assertEqual(j["class"], "warn")

    def test_empty_output_ok_when_proc_missing(self):
        # "empty-output-ok": no /proc/net files and no nft at all: still valid JSON, 0 ports, quiet
        j = self.run_helper(
            SEC, SL_PROC_NET=os.path.join(self.tmp, "nonet"), SL_NFT=os.path.join(self.tmp, "none")
        )
        self.assertEqual(j["text"], "\U000f0483 0")


class GpuTest(Fake):
    """seclegion-gpu against a fake DRM root (SL_DRM_ROOT). PATH holds only bash and,
    when a test adds it, a stub nvidia-smi that records its arguments in a marker file:
    the helper may start no other program."""

    AMD, NV = "0x1002", "0x10de"

    def setUp(self):
        super().setUp()
        self.drm = os.path.join(self.tmp, "drm")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.drm)
        os.makedirs(self.bin)
        os.symlink(shutil.which("bash"), os.path.join(self.bin, "bash"))
        self.marker = os.path.join(self.tmp, "smi-called")

    def card(self, name, vendor, busy=None, status=None, slot="0000:01:00.0", root=None):
        dev = os.path.join(root or self.drm, name, "device")
        os.makedirs(os.path.join(dev, "power"))
        files = {"vendor": vendor, "uevent": f"DRIVER=x\nPCI_SLOT_NAME={slot}\n"}
        if busy is not None:
            files["gpu_busy_percent"] = busy
        if status is not None:
            files["power/runtime_status"] = status
        for rel, text in files.items():
            with open(os.path.join(dev, rel), "w") as fh:
                fh.write(f"{text}\n")

    def smi(self, out="37, 52"):
        p = os.path.join(self.bin, "nvidia-smi")
        with open(p, "w") as f:
            f.write(f"#!/bin/sh\necho \"$@\" > '{self.marker}'\necho '{out}'\n")
        os.chmod(p, 0o755)

    def gpu(self, root=None):
        psu = os.path.join(self.tmp, "psu")  # never the host's own battery
        return self.run_helper(GPU, SL_DRM_ROOT=root or self.drm, SL_PSU_ROOT=psu, PATH=self.bin)

    def battery(self, status):
        bat = os.path.join(self.tmp, "psu", "BAT0")
        os.makedirs(bat, exist_ok=True)
        with open(os.path.join(bat, "status"), "w") as fh:
            fh.write(f"{status}\n")

    def lines(self, j):
        return j["tooltip"].split("\n")

    def test_busy_percent(self):
        self.card("card1", self.AMD, busy="7")
        j = self.gpu()
        self.assertEqual(j["text"], "\U000f08ae 7%")
        self.assertEqual(j["class"], "ok")
        with open(os.path.join(self.drm, "card1", "device", "gpu_busy_percent"), "w") as fh:
            fh.write("95\n")
        self.assertEqual(self.gpu()["class"], "warn")

    def test_missing_file_is_hidden_and_quiet(self):
        # G4: a fake sysfs with no gpu: empty-output-ok
        self.assertEqual(self.gpu(os.path.join(self.tmp, "no-drm")), {"text": "", "class": "hidden"})
        self.card("card1", self.AMD)  # an amdgpu without the busy counter
        self.assertEqual(self.gpu(), {"text": "", "class": "hidden"})

    def test_garbage_is_hidden(self):
        self.card("card1", self.AMD, busy="n/a")
        self.assertEqual(self.gpu()["class"], "hidden")

    def test_gpu_amd_only(self):
        self.card("card1", self.AMD, busy="12")
        # connector entries are skipped, even if one exposes a busy counter
        self.card("card1-eDP-1", self.AMD, busy="99")
        self.smi()
        j = self.gpu()
        self.assertEqual(j["text"], "\U000f08ae 12%")
        self.assertEqual(self.lines(j), ["AMD card1: busy 12%"])
        self.assertFalse(os.path.exists(self.marker), "no NVIDIA card: nvidia-smi must not run")

    def test_gpu_nvidia_suspended_no_smi_call(self):
        self.card("card0", self.NV, status="suspended")
        self.card("card1", self.AMD, busy="5", slot="0000:05:00.0")
        self.smi()
        j = self.gpu()
        self.assertFalse(os.path.exists(self.marker), "a suspended dGPU must not be woken by nvidia-smi")
        self.assertEqual(j["text"], "\U000f08ae 5%")
        self.assertEqual(self.lines(j), ["NVIDIA card0: dGPU off", "AMD card1: busy 5%"])
        self.assertEqual(j["class"], "ok")

    def test_gpu_nvidia_active(self):
        self.card("card0", self.NV, status="active")
        self.card("card1", self.AMD, busy="5", slot="0000:05:00.0")
        self.smi("37, 52")
        j = self.gpu()
        self.assertEqual(j["text"], "\U000f08ae 37%")
        self.assertEqual(self.lines(j), ["NVIDIA card0: busy 37% 52°C", "AMD card1: busy 5%"])
        with open(self.marker) as fh:
            args = fh.read().split()
        self.assertIn("--query-gpu=utilization.gpu,temperature.gpu", args)
        self.assertEqual(args[args.index("-i") + 1], "0000:01:00.0", "query only this card's PCI slot")

    def test_gpu_nvidia_active_on_battery_no_smi_call(self):
        self.card("card0", self.NV, status="active")
        self.card("card1", self.AMD, busy="5", slot="0000:05:00.0")
        self.smi()
        self.battery("Discharging")
        j = self.gpu()
        self.assertFalse(os.path.exists(self.marker), "on battery the poll must not keep the dGPU awake")
        self.assertEqual(self.lines(j), ["NVIDIA card0: dGPU on", "AMD card1: busy 5%"])
        self.battery("Charging")
        self.assertEqual(self.lines(self.gpu())[0], "NVIDIA card0: busy 37% 52°C")

    def test_gpu_nvidia_no_smi(self):
        self.card("card0", self.NV, status="active")
        self.card("card1", self.AMD, busy="5", slot="0000:05:00.0")
        self.assertEqual(self.lines(self.gpu()), ["AMD card1: busy 5%"])
        nv_only = os.path.join(self.tmp, "nv-only")
        self.card("card0", self.NV, status="active", root=nv_only)
        self.assertEqual(self.gpu(nv_only), {"text": "", "class": "hidden"})

    def test_gpu_card_order_independent(self):
        self.smi("37, 52")
        a, b = os.path.join(self.tmp, "a"), os.path.join(self.tmp, "b")
        self.card("card0", self.NV, status="active", root=a)
        self.card("card1", self.AMD, busy="95", slot="0000:05:00.0", root=a)
        self.card("card0", self.AMD, busy="95", slot="0000:05:00.0", root=b)
        self.card("card1", self.NV, status="active", root=b)
        for root, amd, nv in ((a, "card1", "card0"), (b, "card0", "card1")):
            j = self.gpu(root)
            self.assertEqual(j["text"], "\U000f08ae 95%", root)
            self.assertEqual(j["class"], "warn", root)
            self.assertEqual(
                sorted(self.lines(j)), [f"AMD {amd}: busy 95%", f"NVIDIA {nv}: busy 37% 52°C"]
            )


class UptimeTest(Fake):
    def up(self, seconds):
        f = os.path.join(self.tmp, "uptime")
        with open(f, "w") as fh:
            fh.write(f"{seconds}.55 1234.00\n")
        return self.run_helper(UPTIME, SL_UPTIME_FILE=f)["text"]

    def test_formats(self):
        self.assertEqual(self.up(5 * 60 + 3), "\U000f051f 5m")
        self.assertEqual(self.up(3 * 3600 + 120), "\U000f051f 3h 2m")
        self.assertEqual(self.up(2 * 86400 + 5 * 3600), "\U000f051f 2d 5h")

    def test_missing_is_hidden_and_quiet(self):
        j = self.run_helper(UPTIME, SL_UPTIME_FILE=os.path.join(self.tmp, "none"))
        self.assertEqual(j["class"], "hidden")


class DndTest(Fake):
    def swaync(self, dnd, count="0", rc=0):
        return self.script(
            "swaync-client", f'case "$1" in -D) printf %s {dnd};; -c) printf %s {count};; esac\nexit {rc}\n'
        )

    def test_dnd_on(self):
        j = self.run_helper(DND, SL_SWAYNC=self.swaync("true", "3"))
        self.assertEqual(j["class"], "dnd")
        self.assertIn("Do Not Disturb: on", j["tooltip"])

    def test_dnd_off_plain_and_unread(self):
        j = self.run_helper(DND, SL_SWAYNC=self.swaync("false", "0"))
        self.assertEqual(j["class"], "none")
        j = self.run_helper(DND, SL_SWAYNC=self.swaync("false", "4"))
        self.assertEqual(j["class"], "unread")
        self.assertIn("4", j["text"])

    def test_swaync_not_running_is_hidden_and_quiet(self):
        for sw in (os.path.join(self.tmp, "no-such-swaync"), self.swaync("", rc=1), self.swaync("maybe")):
            self.assertEqual(self.run_helper(DND, SL_SWAYNC=sw), {"text": "", "class": "hidden"})


class ConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(WB, "config.jsonc")) as f:
            cls.cfg = json.loads(re.sub(r"(?m)^\s*//.*$", "", f.read()))

    def test_helpers_are_executable_scripts_with_spdx(self):
        for h in (VPN, SEC, GPU, UPTIME, DND):
            self.assertTrue(os.access(h, os.X_OK), h)
            with open(h) as f:
                self.assertIn("SPDX-License-Identifier", f.read(300))
            subprocess.run(["bash", "-n", h], check=True)

    def test_network_module(self):
        n = self.cfg["network"]
        self.assertGreaterEqual(n["interval"], 5)
        for tok in ("{essid}", "{signalStrength}%", "{bandwidthUpBits}", "{bandwidthDownBits}"):
            self.assertIn(tok, n["format-wifi"])
        for tok in ("{ifname}", "{ipaddr}/{cidr}", "gw {gwaddr}", "{frequency}GHz"):
            self.assertIn(tok, n["tooltip-format-wifi"])
        # left click opens the Wi-Fi panel (test_wifi_click); right click Settings (P1);
        # the Wi-Fi radio toggle moved to middle click
        self.assertEqual(n["on-click-right"], "seclegion-settings --page network")
        self.assertIn("nmcli radio wifi", n["on-click-middle"])

    def test_network_bits(self):
        # owner issue 17: speeds compare against Mbit/s (link rate, speed tests), so bits, not bytes
        n = self.cfg["network"]
        for key in ("format-wifi", "format-ethernet"):
            self.assertIn("{bandwidthUpBits}", n[key], key)
            self.assertIn("{bandwidthDownBits}", n[key], key)
            self.assertNotIn("Bytes", n[key], key)
        self.assertEqual(n["interval"], 5)

    def test_network_interface(self):
        # no hardcoded interface: waybar follows the default route (Wi-Fi, wired, USB tether)
        self.assertNotIn("interface", self.cfg["network"])

    def test_sysmon_clicks(self):
        launcher = '"$HOME/.local/share/seclegion/host/bin/seclegion-sysmon"'
        self.assertEqual(self.cfg["cpu"]["on-click"], launcher)
        self.assertEqual(self.cfg["custom/sl-gpu"]["on-click"], launcher + " --page gpu")
        self.assertTrue(os.access(os.path.join(WB, "seclegion-sysmon"), os.X_OK))

    def test_wifi_click(self):
        # owner issue 17: one Wi-Fi place: the network module's left click opens the panel
        self.assertEqual(self.cfg["network"]["on-click"],
                         '"$HOME/.local/share/seclegion/host/bin/seclegion-wifi"')
        launcher = os.path.join(WB, "seclegion-wifi")
        self.assertTrue(os.access(launcher, os.X_OK))
        subprocess.run(["sh", "-n", launcher], check=True)

    def test_vpn_and_sec_modules(self):
        right = self.cfg["modules-right"]
        stats = self.cfg["group/sl-stats"]["modules"]
        self.assertIn("custom/sl-vpn", right)
        self.assertLess(right.index("custom/sl-vpn"), right.index("network"))
        for name, helper, interval in (
            ("custom/sl-vpn", "seclegion-vpn", None),
            ("custom/sl-sec", "seclegion-sec", 30),
            ("custom/sl-gpu", "seclegion-gpu", 5),
            ("custom/sl-uptime", "seclegion-uptime", 60),
        ):
            m = self.cfg[name]
            self.assertEqual(m["return-type"], "json")
            self.assertGreaterEqual(m["interval"], 5)
            self.assertIn("host/bin/" + helper, m["exec"])
            if interval:
                self.assertEqual(m["interval"], interval)
            if name != "custom/sl-vpn":
                self.assertIn(name, stats)
        with open(os.path.join(WB, "style.css")) as f:
            css = f.read()
        for sel in (
            "#custom-sl-vpn.hidden",
            "#custom-sl-gpu.hidden",
            "#custom-sl-uptime.hidden",
            "#custom-sl-sec.warn",
            "#cpu.critical",
            "#temperature.critical",
        ):
            self.assertIn(sel, css)

    def test_p1_chips_wired(self):
        right = self.cfg["modules-right"]
        for name in ("bluetooth", "power-profiles-daemon", "custom/notification"):
            self.assertIn(name, right)
        self.assertLess(right.index("network"), right.index("bluetooth"))
        self.assertLess(right.index("bluetooth"), right.index("pulseaudio"))
        self.assertLess(right.index("power-profiles-daemon"), right.index("battery"))
        # bluetooth: native, event-driven; hidden (empty format) when off, disabled or without an adapter
        bt = self.cfg["bluetooth"]
        self.assertNotIn("interval", bt)
        for k in ("format-off", "format-disabled", "format-no-controller"):
            self.assertEqual(bt[k], "")
        self.assertNotEqual(bt["format"], "")
        self.assertEqual(bt["on-click"], "seclegion-settings --page bluetooth")
        for name, helper, interval in (
            ("custom/notification", "seclegion-dnd", 5),
        ):
            m = self.cfg[name]
            self.assertEqual(m["return-type"], "json")
            self.assertEqual(m["interval"], interval)
            self.assertIn("host/bin/" + helper, m["exec"])
        self.assertEqual(self.cfg["custom/notification"]["on-click-right"], "swaync-client -d -sw")

    def test_power_profile_is_native_and_event_driven(self):
        # Fn+Q cycles the firmware platform_profile; ppd mirrors it and emits PropertiesChanged, which
        # waybar's native module follows. No helper, no polling interval, no on-click override.
        self.assertNotIn("custom/sl-ppd", self.cfg["modules-right"])
        self.assertNotIn("custom/sl-ppd", self.cfg)
        ppd = self.cfg["power-profiles-daemon"]
        self.assertNotIn("interval", ppd)
        self.assertNotIn("exec", ppd)
        self.assertNotIn("on-click", ppd)  # left click is the module's own cycle-profile
        self.assertEqual(ppd["on-click-right"], "seclegion-settings --page power")
        self.assertIn("{icon}", ppd["format"])
        self.assertIn("{profile}", ppd["tooltip-format"])
        icons = ppd["format-icons"]
        for k in ("default", "performance", "balanced", "power-saver"):
            self.assertTrue(icons.get(k), k)
        self.assertEqual(len({icons[k] for k in ("performance", "balanced", "power-saver")}), 3)
        self.assertFalse(os.path.exists(os.path.join(WB, "seclegion-ppd")))  # the old poller is gone

    def test_p1_right_click_deep_links(self):
        for mod, page in (("battery", "power"), ("network", "network"), ("pulseaudio", "sound")):
            self.assertEqual(self.cfg[mod]["on-click-right"], "seclegion-settings --page " + page, mod)

    def test_p1_no_live_hyprland_dispatch_in_chips(self):
        # negative: the chips and deep links never call hyprctl keyword/reload
        with open(os.path.join(WB, "config.jsonc")) as f:
            text = f.read()
        self.assertNotRegex(text, r"keyword|reload")
        for name in ("bluetooth", "power-profiles-daemon", "custom/notification", "battery", "pulseaudio"):
            self.assertNotIn("hyprctl", json.dumps(self.cfg[name]), name)

    def test_css_tokens_chips(self):
        # chip colours come from theme tokens: every @sl_ token is defined, no literal colours
        with open(os.path.join(WB, "style.css")) as f:
            css = f.read()
        with open(os.path.join(ROOT, "desktop", "theme", "default", "colors.css")) as f:
            defined = set(re.findall(r"@define-color\s+(sl_\w+)\s", f.read()))
        self.assertFalse(set(re.findall(r"@(sl_\w+)", css)) - defined)
        for sel in (
            "#bluetooth.connected",
            "#bluetooth.off",
            "#power-profiles-daemon.performance",
            "#power-profiles-daemon.balanced",
            "#power-profiles-daemon.power-saver",
            "#custom-notification.dnd",
            "#custom-notification.hidden",
        ):
            self.assertIn(sel, css)
            block = re.search(re.escape(sel) + r"[^{]*\{([^}]*)\}", css).group(1)
            self.assertNotRegex(block, r"#[0-9a-fA-F]{3,8}\b", sel)

    def test_stats_group(self):
        g = self.cfg["group/sl-stats"]
        self.assertIn("group/sl-stats", self.cfg["modules-right"])
        self.assertIn("drawer", g)
        self.assertEqual(g["modules"][0], "cpu")
        for name in (
            "cpu",
            "temperature",
            "memory",
            "disk",
            "custom/sl-gpu",
            "custom/sl-sec",
            "custom/sl-uptime",
        ):
            self.assertIn(name, g["modules"])
        self.assertEqual(self.cfg["disk"]["interval"], 30)
        for name in ("cpu", "temperature", "memory"):
            self.assertEqual(self.cfg[name]["interval"], 5)
        t = self.cfg["temperature"]
        self.assertTrue(t["hwmon-path-abs"].startswith("/sys/devices/"))
        self.assertEqual(t["input-filename"], "temp1_input")
        self.assertIn("{load}", self.cfg["cpu"]["tooltip-format"])
        self.assertIn("{power", self.cfg["battery"]["format"])


if __name__ == "__main__":
    unittest.main()
