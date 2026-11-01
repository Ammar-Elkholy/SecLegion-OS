# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""tools/lib/seclegion-iso.sh: the steps that put the signed [seclegion] repo into the ISO build.

Run on fake trees, outside a container: no ISO, no network, no root. The keyring checks use a
throwaway gpg key made here (public part only is packed) in a short tmpfs directory.
"""

import os
import shutil
import subprocess
import tempfile

import pytest

from tests.unit.conftest import REPO

LIB = os.path.join(REPO, "tools", "lib", "seclegion-iso.sh")
CONF = os.path.join(REPO, "iso", "profile", "pacman.conf")
KDIR = "usr/share/pacman/keyrings"
RUNTIME = "Server = file:///opt/seclegion/cache/seclegion"
BUILD = "Server = file:///work/profile/airootfs/opt/seclegion/cache/seclegion"


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def sl(*call, cwd=None):
    """Source the library and run one bash command line; return the CompletedProcess."""
    script = f'source "{LIB}"; ' + " ".join(call)
    return subprocess.run(
        ["bash", "-c", script], env=clean_env(), capture_output=True, text=True, cwd=cwd, timeout=60
    )


def test_lock_conf_drops_only_the_seclegion_section(tmp_path):
    out = tmp_path / "lock.conf"
    r = sl("sl_lock_conf", CONF, str(out))
    assert r.returncode == 0, r.stderr
    text, orig = out.read_text(), open(CONF, encoding="utf-8").read()
    live = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert "[seclegion]" not in live
    assert not [ln for ln in live if "file://" in ln or "DatabaseRequired" in ln]
    assert text.count("[core]") == 1 and text.count("[extra]") == 1
    for line in orig.splitlines():
        if line.startswith("Server = https://") or line.startswith("SigLevel = Required DatabaseOptional"):
            assert line in text.splitlines()


def test_lock_conf_keeps_a_section_that_follows_seclegion(tmp_path):
    src = tmp_path / "in.conf"
    src.write_text(
        "[options]\nX = 1\n[seclegion]\nSigLevel = S\nServer = file:///a\n[after]\nServer = https://z\n"
    )
    out = tmp_path / "out.conf"
    assert sl("sl_lock_conf", str(src), str(out)).returncode == 0
    assert out.read_text() == "[options]\nX = 1\n[after]\nServer = https://z\n"


def test_build_conf_rewrites_the_one_runtime_server_line(tmp_path):
    conf = tmp_path / "pacman.conf"
    shutil.copy(CONF, conf)
    before = conf.read_text()
    r = sl("sl_build_conf", str(conf))
    assert r.returncode == 0, r.stderr
    after = conf.read_text()
    assert RUNTIME not in after.splitlines() and after.splitlines().count(BUILD) == 1
    assert after == before.replace(RUNTIME, BUILD)  # nothing else changed


@pytest.mark.parametrize("body", ["[seclegion]\nServer = https://x\n", RUNTIME + "\n" + RUNTIME + "\n", ""])
def test_build_conf_refuses_a_conf_without_exactly_one_runtime_line(tmp_path, body):
    conf = tmp_path / "pacman.conf"
    conf.write_text(body)
    r = sl("sl_build_conf", str(conf))
    assert r.returncode == 1 and "exactly one" in r.stderr
    assert conf.read_text() == body


# --- keyring extraction -----------------------------------------------------------------------


def need(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        pytest.skip("missing tools: " + ", ".join(missing))


@pytest.fixture(scope="module")
def keys():
    """(fingerprint, armour-free public key file) for two throwaway keys, made in tmpfs."""
    need("gpg", "gpgconf", "bsdtar")
    home = tempfile.mkdtemp(prefix="sl-iso", dir="/dev/shm")
    env = {**clean_env(), "GNUPGHOME": home}
    try:
        made = []
        for n in (1, 2):
            subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--quiet",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "",
                    "--quick-generate-key",
                    f"SecLegion ISO test {n} <t{n}@seclegion.invalid>",
                    "ed25519",
                    "sign",
                    "1d",
                ],
                env=env,
                check=True,
                capture_output=True,
                timeout=60,
            )
            out = subprocess.run(
                ["gpg", "--batch", "--with-colons", "--list-keys", f"t{n}@seclegion.invalid"],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            fpr = next(ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr"))
            pub = subprocess.run(
                ["gpg", "--batch", "--export", fpr], env=env, check=True, capture_output=True
            ).stdout
            made.append((fpr, pub))
        yield made
    finally:
        subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], env=env, capture_output=True)
        shutil.rmtree(home, ignore_errors=True)


def make_pkg(tmp_path, gpg: bytes, trusted: str, revoked=True, name="seclegion-keyring-1-1-any.pkg.tar.zst"):
    root = tmp_path / "pkgroot"
    shutil.rmtree(root, ignore_errors=True)
    (root / KDIR).mkdir(parents=True)
    (root / KDIR / "seclegion.gpg").write_bytes(gpg)
    (root / KDIR / "seclegion-trusted").write_text(trusted)
    if revoked:
        (root / KDIR / "seclegion-revoked").write_text("")
    pkg = tmp_path / name
    subprocess.run(
        ["bsdtar", "--zstd", "-cf", str(pkg), "-C", str(root), "usr"], check=True, capture_output=True
    )
    return pkg


def fprfile(tmp_path, text):
    path = tmp_path / "dev-key.fingerprint"
    path.write_text(text)
    return path


def test_extract_keyring_accepts_the_matching_key(tmp_path, keys):
    (fpr, pub), _ = keys
    pkg = make_pkg(tmp_path, pub, f"{fpr}:4:\n")
    out = tmp_path / "out"
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr + "\n")), str(out))
    assert r.returncode == 0, r.stderr
    assert sorted(os.listdir(out / KDIR)) == ["seclegion-revoked", "seclegion-trusted", "seclegion.gpg"]
    assert (out / KDIR / "seclegion.gpg").read_bytes() == pub


def test_extract_keyring_refuses_another_key_in_the_package(tmp_path, keys):
    (fpr, _), (_, other_pub) = keys
    pkg = make_pkg(tmp_path, other_pub, f"{fpr}:4:\n")
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr)), str(tmp_path / "out"))
    assert r.returncode == 1 and "not exactly the key" in r.stderr


def test_extract_keyring_refuses_two_keys_in_the_package(tmp_path, keys):
    (fpr, pub), (_, other_pub) = keys
    pkg = make_pkg(tmp_path, pub + other_pub, f"{fpr}:4:\n")
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr)), str(tmp_path / "out"))
    assert r.returncode == 1 and "not exactly the key" in r.stderr


@pytest.mark.parametrize("suffix", [":5:\n", ":4:\n" + "A" * 40 + ":4:\n", ":3:\n", "\n"])
def test_extract_keyring_refuses_a_trust_line_that_is_not_exactly_the_fingerprint_at_4(
    tmp_path, keys, suffix
):
    (fpr, pub), _ = keys
    pkg = make_pkg(tmp_path, pub, fpr + suffix)
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr)), str(tmp_path / "out"))
    assert r.returncode == 1 and "seclegion-trusted" in r.stderr


def test_extract_keyring_refuses_a_trust_line_for_another_key(tmp_path, keys):
    (fpr, pub), (other, _) = keys
    pkg = make_pkg(tmp_path, pub, f"{other}:4:\n")
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr)), str(tmp_path / "out"))
    assert r.returncode == 1 and "seclegion-trusted" in r.stderr


def test_extract_keyring_refuses_a_missing_file_in_the_package(tmp_path, keys):
    (fpr, pub), _ = keys
    pkg = make_pkg(tmp_path, pub, f"{fpr}:4:\n", revoked=False)
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, fpr)), str(tmp_path / "out"))
    assert r.returncode == 1 and "lacks" in r.stderr


@pytest.mark.parametrize("text", ["", "abc\n", "a" * 40 + "\n", "0" * 39 + "\n", "0" * 40 + ":4:\n"])
def test_extract_keyring_refuses_a_malformed_fingerprint_file(tmp_path, keys, text):
    (fpr, pub), _ = keys
    pkg = make_pkg(tmp_path, pub, f"{fpr}:4:\n")
    r = sl("sl_extract_keyring", str(pkg), str(fprfile(tmp_path, text)), str(tmp_path / "out"))
    assert r.returncode == 1 and "fingerprint" in r.stderr


def test_extract_keyring_refuses_missing_inputs(tmp_path, keys):
    (fpr, pub), _ = keys
    pkg = make_pkg(tmp_path, pub, f"{fpr}:4:\n")
    r = sl("sl_extract_keyring", str(pkg), str(tmp_path / "nope"), str(tmp_path / "out"))
    assert r.returncode == 1 and "no " in r.stderr
    r = sl(
        "sl_extract_keyring",
        str(tmp_path / "nope.pkg.tar.zst"),
        str(fprfile(tmp_path, fpr)),
        str(tmp_path / "out"),
    )
    assert r.returncode == 1 and "keyring package" in r.stderr
