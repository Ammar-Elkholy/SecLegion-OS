# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The signed [seclegion] repository: tampering is refused, SigLevel stays strict, no secret key leaks.

The repository is built once per session by tools/lib/mkrepo.sh on the host (unprivileged, no
network), or taken from $SECLEGION_TEST_REPO. pacman is run as this user under fakeroot against a
throwaway gpgdir on tmpfs that trusts only the key from the repository's own keyring package.
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from tests.unit.conftest import REPO

REQUIRED = "Required DatabaseRequired"
BAD_TOKENS = ("Optional", "Never", "TrustAll", "PackageOptional")
KEYRING_FILES = ("seclegion.gpg", "seclegion-trusted", "seclegion-revoked")
TOOLS = ("makepkg", "repo-add", "gpg", "gpgconf", "gpgv", "fakeroot", "pacman", "pacman-key", "bsdtar")
PRIV = b"BEGIN PGP PRIVATE KEY BLOCK"


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run(cmd, **kw):
    return subprocess.run(cmd, env=clean_env(), capture_output=True, text=True, timeout=120, **kw)


def need_tools():
    missing = [t for t in TOOLS if shutil.which(t) is None]
    if missing:
        pytest.skip("missing tools: " + ", ".join(missing))


def kill_gpg(g, sockdir):
    run(["gpgconf", "--homedir", g, "--kill", "all"])
    shutil.rmtree(g, ignore_errors=True)
    if re.search(r"/gnupg/d\.[^/]+$", sockdir):
        try:
            os.rmdir(sockdir)
        except OSError:
            pass


# --- SigLevel scanner ---------------------------------------------------------------------------


def check_siglevel(path):
    """Return a list of problems in one pacman.conf (empty means fine)."""
    problems = []
    section = None
    seen = False
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            m = re.fullmatch(r"\[([^\]]+)\]", line)
            if m:
                if section == "seclegion" and not seen:
                    problems.append(f"{path}: [seclegion] has no SigLevel line")
                section, seen = m.group(1), False
                continue
            m = re.fullmatch(r"(Local|Remote)?SigLevel\s*=\s*(.*)", line)
            if not m:
                continue
            value = " ".join(m.group(2).split())
            if section == "seclegion":
                seen = True
                if m.group(1) or value != REQUIRED:
                    problems.append(
                        f"{path}:{n}: [seclegion] {line!r} is not exactly 'SigLevel = {REQUIRED}'"
                    )
                continue
            # Elsewhere Arch's stock "Required DatabaseOptional" is tolerated; anything weaker is not.
            bad = [t for t in value.split() if any(b in t for b in BAD_TOKENS) and t != "DatabaseOptional"]
            if bad:
                problems.append(f"{path}:{n}: [{section or 'top'}] weak SigLevel {bad}")
    if section == "seclegion" and not seen:
        problems.append(f"{path}: [seclegion] has no SigLevel line")
    return problems


def tracked_confs():
    out = run(["git", "ls-files", "*pacman.conf"], cwd=REPO).stdout.split()
    found = {os.path.join(REPO, p) for p in out}
    for top in ("iso", "pkgs", "tools"):
        found.update(glob.glob(os.path.join(REPO, top, "**", "pacman.conf"), recursive=True))
    return sorted(found)


def test_siglevel_required():
    confs = tracked_confs()
    assert confs, "no pacman.conf found in the tree"
    problems = [p for c in confs for p in check_siglevel(c)]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "text",
    [
        "[options]\nSigLevel = Required DatabaseOptional\n[seclegion]\nSigLevel = Optional TrustAll\nServer = file:///x\n",
        "[seclegion]\nServer = file:///x\n",
        "[seclegion]\nSigLevel = Required\n",
        "[options]\nSigLevel = Never\n",
        "[options]\nSigLevel = Required TrustAll\n",
        "[core]\nSigLevel = PackageOptional\n",
    ],
)
def test_siglevel_negative(tmp_path, text):
    conf = tmp_path / "pacman.conf"
    conf.write_text(text)
    assert check_siglevel(str(conf))


def test_siglevel_accepts_good_and_absent(tmp_path):
    conf = tmp_path / "pacman.conf"
    conf.write_text("[options]\nSigLevel = Required DatabaseOptional\n[core]\nInclude = x\n")
    assert check_siglevel(str(conf)) == []
    conf.write_text(
        f"[options]\nSigLevel = Required\n[seclegion]\nSigLevel = {REQUIRED}\nServer = file:///x\n"
    )
    assert check_siglevel(str(conf)) == []


# --- Built repository ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """(repo dir holding seclegion.db, outdir)"""
    existing = os.environ.get("SECLEGION_TEST_REPO")
    if existing:
        sub = os.path.join(existing, "seclegion")
        return (sub if os.path.isdir(sub) else existing), existing
    need_tools()
    base = tmp_path_factory.mktemp("mkrepo")
    out, work = base / "out", base / "work"
    out.mkdir()
    work.mkdir()
    r = run(
        ["bash", os.path.join(REPO, "tools/lib/mkrepo.sh"), REPO, str(out), str(work), "pkgs/hello"], cwd=REPO
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return str(out / "seclegion"), str(out)


def keyring_pkg(repo):
    return sorted(glob.glob(os.path.join(repo, "seclegion-keyring-*.pkg.tar.zst")))[0]


@pytest.fixture(scope="session")
def gpgdir(built, tmp_path_factory):
    need_tools()
    repo, _ = built
    kr = tmp_path_factory.mktemp("keyring")
    for f in KEYRING_FILES:
        data = subprocess.run(
            ["bsdtar", "-xOf", keyring_pkg(repo), f"usr/share/pacman/keyrings/{f}"],
            capture_output=True,
            check=True,
        )
        (kr / f).write_bytes(data.stdout)
    g = tempfile.mkdtemp(prefix="sl-t", dir="/dev/shm")  # short path: deep ones break the agent socket
    sockdir = run(["gpgconf", "--homedir", g, "--list-dirs", "socketdir"]).stdout.strip()
    try:
        r = run(["fakeroot", "pacman-key", "--gpgdir", g, "--init"])
        assert r.returncode == 0, r.stdout + r.stderr
        r = run(
            ["fakeroot", "pacman-key", "--gpgdir", g, "--populate-from", str(kr), "--populate", "seclegion"]
        )
        assert r.returncode == 0, r.stdout + r.stderr
        yield g
    finally:
        kill_gpg(g, sockdir)


def pacman(work, repo, g, *args, siglevel=REQUIRED):
    """Run pacman against repo with a fresh root, dbpath and cache; return the CompletedProcess."""
    work = str(work)
    for d in ("root", "db", "cache"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    conf = os.path.join(work, "pacman.conf")
    with open(conf, "w", encoding="utf-8") as fh:
        fh.write(
            f"[options]\nLogFile = {work}/pacman.log\nSigLevel = {siglevel}\n"
            f"[seclegion]\nSigLevel = {siglevel}\nServer = file://{repo}\n"
        )
    base = [
        "fakeroot",
        "pacman",
        "--config",
        conf,
        "--root",
        f"{work}/root",
        "--dbpath",
        f"{work}/db",
        "--gpgdir",
        g,
        "--cachedir",
        f"{work}/cache",
        "--noconfirm",
    ]
    return run(base + list(args))


def wipe(work):
    for d in ("root", "db", "cache"):
        shutil.rmtree(os.path.join(str(work), d), ignore_errors=True)


def copy_repo(repo, dest):
    shutil.copytree(repo, dest, symlinks=True)
    return str(dest)


def flip_byte(path):
    real = os.path.realpath(path)
    with open(real, "r+b") as fh:
        fh.seek(os.path.getsize(real) // 2)
        b = fh.read(1)
        fh.seek(-1, os.SEEK_CUR)
        fh.write(bytes([b[0] ^ 0xFF]))


def test_tampered_pkg(built, gpgdir, tmp_path):
    repo, _ = built
    good = copy_repo(repo, tmp_path / "good")
    w = tmp_path / "w"
    assert (r := pacman(w, good, gpgdir, "-Sy")).returncode == 0, r.stdout + r.stderr
    assert (r := pacman(w, good, gpgdir, "-Sw", "seclegion-keyring")).returncode == 0, (
        "control: " + r.stdout + r.stderr
    )

    bad = copy_repo(repo, tmp_path / "bad")
    flip_byte(keyring_pkg(bad))
    wipe(w)
    assert (r := pacman(w, bad, gpgdir, "-Sy")).returncode == 0, r.stdout + r.stderr  # database intact
    r = pacman(w, bad, gpgdir, "-Sw", "seclegion-keyring")
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert re.search(r"signature|integrity|corrupted", out, re.I), out


def retarget_unsigned_db(repo, tmp_path):
    """Copy repo; swap the keyring package for altered content under the same name, rebuild the
    database UNSIGNED so the checksum matches, and keep the old (now stale) package .sig. Only the
    package signature can reject this."""
    bad = copy_repo(repo, tmp_path / "forged")
    pkg = keyring_pkg(bad)
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(["bsdtar", "-xf", pkg, "-C", str(src)], check=True)
    with open(src / "usr/share/pacman/keyrings/seclegion-trusted", "a") as fh:
        fh.write("0000000000000000000000000000000000000000:4:\n")
    os.unlink(pkg)
    subprocess.run(["bsdtar", "--zstd", "-cf", pkg, "-C", str(src), *sorted(os.listdir(src))], check=True)
    for f in glob.glob(os.path.join(bad, "seclegion.*")):
        os.unlink(f)
    r = run(
        [
            "repo-add",
            "--quiet",
            "seclegion.db.tar.zst",
            *[os.path.basename(p) for p in glob.glob(os.path.join(bad, "*.pkg.tar.zst"))],
        ],
        cwd=bad,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return bad


def test_forged_pkg_signature(built, gpgdir, tmp_path):
    """Checksum-consistent but unsigned-change package: only the signature check stops it."""
    repo, _ = built
    bad = retarget_unsigned_db(repo, tmp_path)
    w = tmp_path / "w"
    db_only = "Required DatabaseNever"
    assert (r := pacman(w, bad, gpgdir, "-Sy", siglevel=db_only)).returncode == 0, r.stdout + r.stderr
    r = pacman(w, bad, gpgdir, "-Sw", "seclegion-keyring", siglevel=db_only)
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert re.search(r"signature", out, re.I), out
    # Set-aside proof: with SigLevel = Never the same forged package is accepted.
    wipe(w)
    assert (r := pacman(w, bad, gpgdir, "-Sy", siglevel="Never")).returncode == 0, r.stdout + r.stderr
    r = pacman(w, bad, gpgdir, "-Sw", "seclegion-keyring", siglevel="Never")
    assert r.returncode == 0, "SigLevel=Never control: " + r.stdout + r.stderr


def test_tampered_db(built, gpgdir, tmp_path):
    repo, _ = built
    bad = copy_repo(repo, tmp_path / "bad")
    flip_byte(os.path.join(bad, "seclegion.db"))
    r = pacman(tmp_path / "w", bad, gpgdir, "-Sy")
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert re.search(r"signature|integrity|corrupted|invalid|failed", out, re.I), out


# --- No secret key anywhere ---------------------------------------------------------------------


def secret_findings(root):
    """Files under root holding a private key block or a secret key packet."""
    found = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            with open(p, "rb") as fh:
                data = fh.read()
            if PRIV in data:
                found.append(p)
            elif name.endswith((".gpg", ".sig", ".asc", ".key")):
                out = run(["gpg", "--batch", "--list-packets", p]).stdout
                if re.search(r"^:secret (sub)?key packet:", out, re.M | re.I):
                    found.append(p)
    return found


def test_no_secret_key(built, tmp_path):
    need_tools()
    repo, out = built
    assert secret_findings(repo) == []
    assert secret_findings(out) == []
    assert secret_findings(os.path.join(REPO, "pkgs")) == []
    kr = tmp_path / "kr"
    kr.mkdir()
    subprocess.run(
        ["bsdtar", "-xf", keyring_pkg(repo), "-C", str(kr), "usr/share/pacman/keyrings"], check=True
    )
    assert glob.glob(str(kr / "**/seclegion.gpg"), recursive=True)
    assert secret_findings(str(kr)) == []
    tracked = run(["git", "ls-files", "-z"], cwd=REPO).stdout.split("\0")
    assert tracked
    hits = []
    for rel in filter(None, tracked):
        p = os.path.join(REPO, rel)
        if rel != "tests/unit/test_repo.py" and os.path.isfile(p) and not os.path.islink(p):
            with open(p, "rb") as fh:
                if PRIV in fh.read():
                    hits.append(rel)
    assert hits == []


def test_secret_key_detected(tmp_path):
    """Negative case: an exported secret key from a throwaway tmpfs key is found."""
    need_tools()
    g = tempfile.mkdtemp(prefix="sl-s", dir="/dev/shm")
    sockdir = run(["gpgconf", "--homedir", g, "--list-dirs", "socketdir"]).stdout.strip()
    try:
        env = dict(clean_env(), GNUPGHOME=g)
        r = subprocess.run(
            [
                "gpg",
                "--batch",
                "--quiet",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "neg <neg@seclegion.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, r.stderr
        for armor, name in ((["--armor"], "secret.asc"), ([], "secret.gpg")):
            d = tmp_path / name.replace(".", "_")
            d.mkdir()
            r = subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "",
                    "--export-secret-keys",
                    *armor,
                ],
                env=env,
                capture_output=True,
                timeout=60,
            )
            assert r.returncode == 0 and r.stdout
            (d / name).write_bytes(r.stdout)
            assert secret_findings(str(d)) == [str(d / name)]
    finally:
        kill_gpg(g, sockdir)
