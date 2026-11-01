# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""W2b capture tools: G55 behaviour (external tools mocked or real fixtures) and G59 reachability."""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CAP = ROOT / "desktop/capture"
BIN = CAP / "bin"
KEYS = ROOT / "desktop/hypr/seclegion-keys.lua"
LINT = ROOT / "tools/seclegion-keys-lint"
PKGBUILD = ROOT / "pkgs/seclegion-desktop/PKGBUILD"


def norm(keys):
    return re.sub(r"\s+", "", keys.upper().replace("CTRL", "CONTROL"))


def registry():
    return tomllib.loads((CAP / "capture.toml").read_text())["util"]


def lua_binds(text):
    return {
        norm(m.group(1)): m.group(2)
        for m in re.finditer(r'hl\.bind\("([^"]+)",\s*hl\.dsp\.exec_cmd\("([^"]*)"\)', text)
    }


def reachable_problems(entries, keys_text):
    binds = lua_binds(keys_text)
    out = []
    for e in entries:
        if not (BIN / e["script"]).is_file():
            out.append(f"{e['name']}: script {e['script']} missing")
        got = binds.get(norm(e["bind"]), "").split()[:1]
        if got != [e["script"]]:
            out.append(f"{e['name']}: bind {e['bind']} does not run {e['script']}")
    return out


# --- G59 reachability --------------------------------------------------------


def test_capture_reachable_every_registry_entry():
    entries = registry()
    assert len(entries) >= 6
    assert reachable_problems(entries, KEYS.read_text()) == []
    for e in entries:
        assert os.access(BIN / e["script"], os.X_OK), e["script"]


def test_capture_reachable_fails_when_a_bind_is_removed():
    text = "\n".join(ln for ln in KEYS.read_text().splitlines() if "seclegion-qr" not in ln)
    assert any("qr" in x for x in reachable_problems(registry(), text))


def test_capture_reachable_no_collision_with_owner_keys_and_packaged():
    owner = ROOT / "tests/keys/fixtures/owner-keybinds.lua"
    r = subprocess.run([sys.executable, str(LINT), str(owner), str(KEYS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "desktop/capture/bin/seclegion-*" in PKGBUILD.read_text()
    assert "desktop/capture" in (ROOT / "pkgs/seclegion-desktop/source.list").read_text().split()


# --- helpers -----------------------------------------------------------------


def script(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def env(tmp_path):
    log = tmp_path / "log"
    script(tmp_path / "notify", f'echo "notify $*" >> {log}\n')
    script(tmp_path / "wlcopy", f'echo "wlcopy $*" >> {log}\ncat > {tmp_path}/clip\n')
    e = {
        **os.environ,
        "SL_NOTIFY": str(tmp_path / "notify"),
        "SL_WLCOPY": str(tmp_path / "wlcopy"),
        "XDG_RUNTIME_DIR": str(tmp_path),
        "SL_SCREENSHOT_DIR": str(tmp_path / "shots"),
        "SL_RECORD_DIR": str(tmp_path / "rec"),
    }
    return e, tmp_path, log


def run(name, args, e):
    return subprocess.run([sys.executable, str(BIN / name), *args], env=e, capture_output=True, text=True)


# --- screenshot --------------------------------------------------------------


def mock_shot_tools(tmp, e):
    script(tmp / "slurp", 'echo "10,20 300x200"\n')
    script(tmp / "grim", f'echo "grim $*" >> {tmp}/log\nfor last; do :; done\nprintf PNG > "$last"\n')
    script(tmp / "hyprctl", 'echo \'{"at":[5,6],"size":[700,400]}\'\n')
    e.update(SL_SLURP=str(tmp / "slurp"), SL_GRIM=str(tmp / "grim"), SL_HYPRCTL=str(tmp / "hyprctl"))


@pytest.mark.parametrize(
    "mode,geom", [("region", "10,20 300x200"), ("window", "5,6 700x400"), ("screen", None)]
)
def test_capture_screenshot_modes(env, mode, geom):
    e, tmp, log = env
    mock_shot_tools(tmp, e)
    r = run("seclegion-screenshot", [mode], e)
    assert r.returncode == 0, r.stderr
    files = list((tmp / "shots").glob("screenshot-*.png"))
    assert len(files) == 1
    text = log.read_text()
    if geom:
        assert f"grim -g {geom} {files[0]}" in text
    else:
        assert f"grim {files[0]}" in text and "-g" not in text.split("grim", 1)[1].split("\n")[0]
    assert "wlcopy --type image/png" in text and str(files[0]) in text
    assert (tmp / "clip").read_bytes() == b"PNG"


def test_capture_screenshot_region_cancel_does_nothing(env):
    e, tmp, log = env
    mock_shot_tools(tmp, e)
    script(tmp / "slurp", "exit 1\n")
    assert run("seclegion-screenshot", ["region"], e).returncode == 0
    assert not (tmp / "shots").exists() and not log.exists()


# --- OCR ---------------------------------------------------------------------


def render(path, text, font_markup=None):
    if not shutil.which("magick"):
        pytest.skip("ImageMagick (magick) not installed: cannot render the fixture")
    if font_markup:
        src = ["pango:" + font_markup.format(text)]
    else:
        src = ["-font", "Arimo-Regular", f"label:{text}"]
    subprocess.run(
        [
            "magick",
            "-background",
            "white",
            "-fill",
            "black",
            "-pointsize",
            "48",
            *src,
            "-bordercolor",
            "white",
            "-border",
            "30",
            str(path),
        ],
        check=True,
    )


def tess_langs():
    r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return set(r.stdout.split()[1:])


def test_capture_ocr_english_real_tesseract(env):
    if not shutil.which("tesseract") or "eng" not in tess_langs():
        pytest.skip("tesseract with eng data not installed on this host")
    e, tmp, log = env
    render(tmp / "eng.png", "Hello SecLegion")
    r = run("seclegion-ocr", [str(tmp / "eng.png")], e)
    assert r.returncode == 0, r.stderr
    assert "Hello SecLegion" in (tmp / "clip").read_text()
    assert "notify -a seclegion-capture Text copied Hello SecLegion" in log.read_text()


def test_capture_ocr_arabic_real_tesseract(env):
    if not shutil.which("tesseract") or "ara" not in tess_langs():
        pytest.skip("tesseract-data-ara not installed on this host (listed in the ISO/PKGBUILD)")
    e, tmp, _ = env
    render(tmp / "ara.png", "مرحبا بالعالم", '<span font="Noto Sans Arabic">{}</span>')
    r = run("seclegion-ocr", [str(tmp / "ara.png")], e)
    assert r.returncode == 0, r.stderr
    assert "مرحبا" in (tmp / "clip").read_text()


def test_capture_ocr_region_mocked_uses_eng_ara_and_first_line(env):
    e, tmp, log = env
    mock_shot_tools(tmp, e)
    script(
        tmp / "tess",
        'if [ "$1" = --list-langs ]; then printf "List of available languages (2):\\neng\\nara\\n"; '
        'exit 0; fi\n'
        f'echo "tess $*" >> {log}\nprintf "first line\\nsecond\\n"\n',
    )
    e["SL_TESSERACT"] = str(tmp / "tess")
    assert run("seclegion-ocr", [], e).returncode == 0
    text = log.read_text()
    assert "-l eng+ara" in text
    assert (tmp / "clip").read_text() == "first line\nsecond"
    assert "Text copied first line" in text


# --- QR ----------------------------------------------------------------------


def test_capture_qr_decodes_real_fixture_and_never_opens(env):
    if not shutil.which("zbarimg") or not shutil.which("qrencode"):
        pytest.skip("zbarimg or qrencode not installed on this host")
    e, tmp, log = env
    url = "https://example.org/a?b=1"
    subprocess.run(["qrencode", "-o", str(tmp / "q.png"), "-s", "8", url], check=True)
    script(tmp / "xdg-open", f"echo OPENED >> {log}\n")
    e["PATH"] = f"{tmp}:{e['PATH']}"
    r = run("seclegion-qr", [str(tmp / "q.png")], e)
    assert r.returncode == 0, r.stderr
    assert (tmp / "clip").read_text() == url
    assert "OPENED" not in log.read_text() and "not opened" in log.read_text()


def test_capture_qr_region_mocked(env):
    e, tmp, log = env
    mock_shot_tools(tmp, e)
    script(tmp / "zbar", f'echo "zbar $*" >> {log}\necho "payload"\n')
    e["SL_ZBARIMG"] = str(tmp / "zbar")
    assert run("seclegion-qr", [], e).returncode == 0
    assert (tmp / "clip").read_text() == "payload" and "zbar --quiet --raw" in log.read_text()


# --- record ------------------------------------------------------------------


def alive(pid):
    try:
        return pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def test_capture_record_toggle_starts_then_stops_own_pid(env):
    import time

    e, tmp, log = env
    rec = tmp / "wf-recorder"
    script(
        rec,
        f'echo "$@" > {tmp}/argv\nfor last; do :; done\n: > "$last"\n'
        "trap 'exit 0' INT\nwhile :; do sleep 0.05; done\n",
    )
    e["SL_RECORDER"] = str(rec)
    pf = tmp / "seclegion-record.pid"
    pid = None
    try:
        assert run("seclegion-record", ["screen", "toggle"], e).returncode == 0
        pid_s, out = pf.read_text().split("\n")[:2]
        pid = int(pid_s)
        assert re.fullmatch(r"recording-\d{8}-\d{6}\.mp4", pathlib.Path(out).name)
        assert pathlib.Path(out).parent == tmp / "rec"
        for _ in range(50):
            if (tmp / "argv").exists() and pathlib.Path(out).exists():
                break
            time.sleep(0.05)
        assert (tmp / "argv").read_text().split() == ["-f", out]
        assert alive(pid)
        assert run("seclegion-record", ["screen", "toggle"], e).returncode == 0
        assert not alive(pid) and not pf.exists()
        assert f"Recording saved {out}" in log.read_text()
    finally:
        if pid and alive(pid):
            os.kill(pid, 9)


def test_capture_record_region_passes_geometry_and_stale_pidfile_ignored(env):
    import time

    e, tmp, _ = env
    mock_shot_tools(tmp, e)
    rec = tmp / "wf-recorder"
    script(rec, f"echo \"$@\" > {tmp}/argv\ntrap 'exit 0' INT\nwhile :; do sleep 0.05; done\n")
    e["SL_RECORDER"] = str(rec)
    pf = tmp / "seclegion-record.pid"
    pf.write_text("999999\n/nonexistent.mp4\n")  # stale: must start, not "stop"
    pid = None
    try:
        assert run("seclegion-record", ["region", "toggle"], e).returncode == 0
        pid = int(pf.read_text().split("\n")[0])
        assert pid != 999999
        for _ in range(50):
            if (tmp / "argv").exists():
                break
            time.sleep(0.05)
        assert (tmp / "argv").read_text().split()[:3] == ["-g", "10,20", "300x200"]
    finally:
        if pid and alive(pid):
            os.kill(pid, 2)


@pytest.mark.skipif(
    not (shutil.which("wf-recorder") and shutil.which("ffprobe")),
    reason=(
        "wf-recorder or ffprobe missing; a real recording needs a Wayland session and must not "
        "capture the owner's screen, so only the mocked tests run"
    ),
)
def test_capture_record_real_tools_present_are_runnable():
    assert subprocess.run(["wf-recorder", "--version"], capture_output=True).returncode == 0
