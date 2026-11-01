# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""W4 utilities: G59 reachability, battery alerts, toggles (all external commands mocked)."""

import os
import pathlib
import re
import subprocess
import sys
import time
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
UTILS = ROOT / "desktop/utils"
BIN = UTILS / "bin"
KEYS = ROOT / "desktop/hypr/seclegion-keys.lua"
LINT = ROOT / "tools/seclegion-keys-lint"
PKGBUILD = ROOT / "pkgs/seclegion-desktop/PKGBUILD"


def registry():
    return tomllib.loads((UTILS / "utils.toml").read_text())["util"]


def norm(keys):
    return re.sub(r"\s+", "", keys.upper().replace("CTRL", "CONTROL"))


def lua_binds(text):
    return {
        norm(m.group(1)): m.group(2)
        for m in re.finditer(r'hl\.bind\("([^"]+)",\s*hl\.dsp\.exec_cmd\("([^"]*)"\)', text)
    }


def reachable_problems(entries, keys_text, units_dir, bar_text):
    binds = lua_binds(keys_text)
    out = []
    for e in entries:
        pkgbuild = (ROOT / f"pkgs/{e['pkg']}/PKGBUILD" if "pkg" in e else PKGBUILD).read_text()
        s = e["script"]
        # An entry may live in another component's tree: dir = "desktop/<name>" (bin/ + applications/).
        base = ROOT / e["dir"] if "dir" in e else UTILS
        installed = f"{e['dir']}/bin/{s}" if "dir" in e else "desktop/utils/bin/seclegion-*"
        if not (base / "bin" / s).is_file():
            out.append(f"{e['name']}: script {s} missing")
        if installed not in pkgbuild:
            out.append(f"{e['name']}: not installed by the PKGBUILD")
        r = e["reach"]
        if r == "bind":
            if binds.get(norm(e["bind"]), "").split()[:1] != [s]:
                out.append(f"{e['name']}: bind {e['bind']} does not run {s}")
        elif r == "launcher":
            d = base / "applications" / e["desktop"]
            if not d.is_file() or s not in d.read_text() or e["desktop"] not in pkgbuild:
                out.append(f"{e['name']}: launcher {e['desktop']} missing, not shipped, or does not run {s}")
        elif r == "bar":
            if s not in bar_text:
                out.append(f"{e['name']}: no waybar module runs {s}")
        elif r == "unit":
            u = units_dir / e["unit"]
            if not u.is_file() or s not in u.read_text():
                out.append(f"{e['name']}: unit {e['unit']} missing or does not run {s}")
        else:
            out.append(f"{e['name']}: unknown reach {r}")
    return out


def test_utils_reachable_every_registry_entry():
    entries = registry()
    assert len(entries) >= 7
    bar = (ROOT / "desktop/waybar/config.jsonc.in").read_text()
    assert reachable_problems(entries, KEYS.read_text(), ROOT / "desktop/units", bar) == []
    for e in entries:
        base = ROOT / e["dir"] if "dir" in e else UTILS
        assert os.access(base / "bin" / e["script"], os.X_OK), e["script"]


def test_utils_reachable_fails_when_a_bind_is_removed():
    text = "\n".join(ln for ln in KEYS.read_text().splitlines() if "seclegion-night-light" not in ln)
    p = reachable_problems(registry(), text, ROOT / "desktop/units", "")
    assert any("night-light" in x for x in p)


def test_utils_reachable_binds_do_not_collide_with_owner_keys():
    owner = ROOT / "tests/keys/fixtures/owner-keybinds.lua"
    r = subprocess.run([sys.executable, str(LINT), str(owner), str(KEYS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_utils_reachable_pkgbuild_ships_sources():
    assert "desktop/utils" in (ROOT / "pkgs/seclegion-desktop/source.list").read_text().split()


# --- battery -----------------------------------------------------------------


def fake_notify(tmp_path):
    log = tmp_path / "notify.log"
    n = tmp_path / "fake-notify"
    n.write_text(f'#!/bin/sh\necho "$*" >> {log}\n')
    n.chmod(0o755)
    return n, log


def run_batt(tmp_path, cap, status="Discharging"):
    ps = tmp_path / "ps"
    (ps / "BAT0").mkdir(parents=True, exist_ok=True)
    (ps / "BAT0/capacity").write_text(str(cap))
    (ps / "BAT0/status").write_text(status)
    n, log = fake_notify(tmp_path)
    env = {
        **os.environ,
        "SL_POWER_SUPPLY": str(ps),
        "SL_STATE_DIR": str(tmp_path / "st"),
        "SL_NOTIFY": str(n),
    }
    r = subprocess.run(
        [sys.executable, str(BIN / "seclegion-battery-watch"), "--once"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_battery_notifies_15_once_then_7_critical_once(tmp_path):
    assert run_batt(tmp_path, 50) == []
    ln = run_batt(tmp_path, 15)
    assert len(ln) == 1 and "-u normal" in ln[0] and "Battery low" in ln[0]
    assert len(run_batt(tmp_path, 14)) == 1  # no repeat
    ln = run_batt(tmp_path, 7)
    assert len(ln) == 2 and "-u critical" in ln[1] and "-t 0" in ln[1]
    assert len(run_batt(tmp_path, 5)) == 2  # no repeat
    assert len(run_batt(tmp_path, 40, "Charging")) == 2  # state resets on charge
    assert len(run_batt(tmp_path, 15)) == 3  # fires again on the next discharge


def test_battery_straight_to_critical(tmp_path):
    ln = run_batt(tmp_path, 6)
    assert len(ln) == 1 and "-u critical" in ln[0]
    assert len(run_batt(tmp_path, 14)) == 1  # low is implied by critical


def test_battery_no_battery_exits_zero(tmp_path):
    ps = tmp_path / "empty"
    ps.mkdir()
    n, log = fake_notify(tmp_path)
    env = {**os.environ, "SL_POWER_SUPPLY": str(ps), "SL_NOTIFY": str(n)}
    r = subprocess.run([sys.executable, str(BIN / "seclegion-battery-watch")], env=env, timeout=10)
    assert r.returncode == 0 and not log.exists()


# --- toggles ----------------------------------------------------------------


def sh(script, tmp_path, *args, **extra):
    n, _ = fake_notify(tmp_path)
    env = {
        **os.environ,
        "SL_STATE_DIR": str(tmp_path / "st"),
        "SL_NOTIFY": str(n),
        "HOME": str(tmp_path / "home"),
        "XDG_STATE_HOME": str(tmp_path / "home/.local/state"),
        **extra,
    }
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    return subprocess.run([str(BIN / script), *args], env=env, capture_output=True, text=True, timeout=20)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return (
        os.path.exists(f"/proc/{pid}")
        and "Z" not in pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1][:3]
    )


@pytest.mark.parametrize(
    "script,var", [("seclegion-stay-awake", "SL_INHIBIT"), ("seclegion-night-light", "SL_SUNSET")]
)
def test_toggle_pidfile_holder(tmp_path, script, var):
    holder = tmp_path / "holder"
    holder.write_text("#!/bin/sh\nexec sleep 300\n")
    holder.chmod(0o755)
    kw = {var: str(holder)}
    assert sh(script, tmp_path, "status", **kw).stdout.strip() == "off"
    assert sh(script, tmp_path, "toggle", **kw).returncode == 0
    assert sh(script, tmp_path, "status", **kw).stdout.strip() == "on"
    pidf = next((tmp_path / "st").glob("*.pid"))
    pid = int(pidf.read_text())
    assert sh(script, tmp_path, "on", **kw).returncode == 0  # idempotent
    assert int(pidf.read_text()) == pid
    sh(script, tmp_path, "toggle", **kw)
    assert sh(script, tmp_path, "status", **kw).stdout.strip() == "off"
    for _ in range(50):
        if not alive(pid):
            break
        time.sleep(0.05)
    assert not alive(pid)
    assert sh(script, tmp_path, "off", **kw).returncode == 0  # idempotent off


def test_reduced_motion_writes_state_and_reloads_mock(tmp_path):
    log = tmp_path / "hl.log"
    hl = tmp_path / "fake-hyprctl"
    hl.write_text(f'#!/bin/sh\necho "$*" >> {log}\n')
    hl.chmod(0o755)
    f = tmp_path / "st/reduced-motion.lua"
    assert sh("seclegion-reduced-motion", tmp_path, "on", SL_HYPRCTL=str(hl)).returncode == 0
    assert "enabled = false" in f.read_text()
    assert sh("seclegion-reduced-motion", tmp_path, "status", SL_HYPRCTL=str(hl)).stdout.strip() == "on"
    sh("seclegion-reduced-motion", tmp_path, "toggle", SL_HYPRCTL=str(hl))
    assert not f.exists()
    assert log.read_text().split() == ["reload", "reload"]
    assert "reduced-motion.lua" in (ROOT / "desktop/hypr/seclegion-host.lua").read_text()


def test_power_profile_cycles_available_profiles(tmp_path):
    state = tmp_path / "prof"
    state.write_text("balanced")
    pp = tmp_path / "fake-ppctl"
    pp.write_text(f"""#!/bin/sh
case "$1" in
get) cat {state} ;;
set) printf %s "$2" > {state} ;;
list) printf '  performance:\\n    Driver: x\\n\\n* balanced:\\n    Driver: x\\n'
     printf '\\n  power-saver:\\n    Driver: x\\n' ;;
esac
""")
    pp.chmod(0o755)
    seen = []
    for _ in range(4):
        assert sh("seclegion-power-profile", tmp_path, "cycle", SL_PPCTL=str(pp)).returncode == 0
        seen.append(state.read_text())
    assert seen == ["performance", "power-saver", "balanced", "performance"]
    assert sh("seclegion-power-profile", tmp_path, "set", "bogus", SL_PPCTL=str(pp)).returncode == 2


def test_emoji_list_has_emoji_and_copies_pick(tmp_path):
    out = subprocess.run(
        [sys.executable, str(BIN / "seclegion-emoji"), "--list"], capture_output=True, text=True
    ).stdout
    assert "\U0001f600 grinning face" in out
    rofi = tmp_path / "rofi"
    rofi.write_text('#!/bin/sh\ngrep "grinning face$" | head -1\n')
    rofi.chmod(0o755)
    cp = tmp_path / "wlcopy"
    cp.write_text(f"#!/bin/sh\ncat > {tmp_path}/clip\n")
    cp.chmod(0o755)
    subprocess.run(
        [sys.executable, str(BIN / "seclegion-emoji")],
        env={**os.environ, "SL_ROFI": str(rofi), "SL_WLCOPY": str(cp)},
        check=True,
    )
    assert (tmp_path / "clip").read_text() == "\U0001f600"
