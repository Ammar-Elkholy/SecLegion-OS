# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Static checks on every pkgs/*/PKGBUILD and on tools/pkg-source. No container, no makepkg."""

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PKGS = REPO / "pkgs"
PKG_SOURCE = REPO / "tools" / "pkg-source"
PKGBUILDS = sorted(PKGS.glob("*/PKGBUILD"))
NAMES = {p.parent.name for p in PKGBUILDS}


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def tracked(path):
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--", path],
        capture_output=True, check=True, env=clean_env(),
    ).stdout
    return [f for f in out.decode().split("\0") if f]


def source_list(pkg_dir):
    f = pkg_dir / "source.list"
    if not f.exists():
        return []
    lines = (line.split("#", 1)[0].strip() for line in f.read_text().splitlines())
    return [line for line in lines if line]


def array(text, name):
    """The words of a bash array `name=(...)` (single/double quoted or bare), [] when absent."""
    m = re.search(rf"""^{name}=\(((?:[^()'"]|'[^']*'|"[^"]*")*)\)""", text, re.S | re.M)
    if not m:
        return []
    return re.findall(r"""'([^']*)'|"([^"]*)"|([^\s'"()]+)""", re.sub(r"(?m)#.*$", "", m.group(1)))


def words(text, name):
    return [a or b or c for a, b, c in array(text, name)]


def test_there_are_packages():
    assert {"seclegion-desktop", "seclegion-dotfiles", "seclegion-theme", "seclegion-settings",
            "seclegion-sysmon", "seclegion-wifi", "seclegion-branding", "seclegion-hwdetect",
            "seclegion-keyring"} <= NAMES


@pytest.mark.parametrize("pkgbuild", PKGBUILDS, ids=lambda p: p.parent.name)
class TestPkgbuild:
    def test_name_licence_arch(self, pkgbuild):
        text = pkgbuild.read_text()
        assert re.search(rf"^pkgname={pkgbuild.parent.name}$", text, re.M), "pkgname must equal the directory"
        assert words(text, "license"), "no license=()"
        assert words(text, "arch"), "no arch=()"

    def test_reuse_header(self, pkgbuild):
        head = "\n".join(pkgbuild.read_text().splitlines()[:6])
        assert "SPDX-License-Identifier:" in head and "SPDX-FileCopyrightText:" in head

    def test_no_parent_directory_paths(self, pkgbuild):
        code = re.sub(r"(?m)^\s*#.*$", "", pkgbuild.read_text())
        assert "../" not in code, "a PKGBUILD cannot see outside its directory in the container build"

    def test_seclegion_depends_are_real_packages(self, pkgbuild):
        text = pkgbuild.read_text()
        for field in ("depends", "makedepends", "optdepends", "checkdepends"):
            for dep in words(text, field):
                name = re.split(r"[<>=:]", dep, maxsplit=1)[0]
                if name.startswith("seclegion"):
                    assert name in NAMES, f"{field} names {name!r}, which is not a pkgs/ directory (typo?)"

    def test_source_list_pattern(self, pkgbuild):
        pkg_dir = pkgbuild.parent
        text = pkgbuild.read_text()
        listed = source_list(pkg_dir)
        uses_tarball = "seclegion-src.tar.zst" in words(text, "source")
        has_list = (pkg_dir / "source.list").exists()
        assert uses_tarball == has_list, "source=() and source.list must go together"
        if not listed:
            return
        assert words(text, "sha256sums") == ["SKIP"]
        for path in listed:
            assert not path.startswith("/") and ".." not in path.split("/"), path
            assert tracked(path), f"source.list path {path!r} matches no file tracked by git"
        # every repository path the PKGBUILD reads from $srcdir (or hands to _tree) is listed
        code = re.sub(r"(?m)^\s*#.*$", "", text)
        used = re.findall(r"\$srcdir/((?:desktop|tools|hw|installer|LICENSES?)[\w./-]*|LICENSE)", code)
        used += re.findall(r"^\s*_tree\s+((?:desktop|tools|hw|installer)[\w./-]*)", code, re.M)
        for path in used:
            if path.endswith("/") or "/" not in path and path != "LICENSE":
                continue  # a directory prefix completed by a variable, such as "$srcdir/tools/$t"
            assert any(path == p or path.startswith(p.rstrip("/") + "/") for p in listed), (
                f"{path!r} is read by the PKGBUILD but not in source.list"
            )


def run_pkg_source(arg, root=None, **env):
    extra = dict(env)
    if root is not None:
        extra["PKG_SOURCE_ROOT"] = str(root)
    return subprocess.run([str(PKG_SOURCE), arg], capture_output=True, text=True, env=clean_env(**extra))


def make_repo(tmp_path, files, source_list_text):
    """A throwaway git repository holding `files` (path -> text) and pkgs/p/source.list."""
    root = tmp_path / "repo"
    assert root.resolve().parent == tmp_path.resolve()
    (root / "pkgs" / "p").mkdir(parents=True)
    (root / "pkgs" / "p" / "source.list").write_text(source_list_text)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    env = clean_env(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)
    return root


class TestPkgSource:
    def test_missing_path_fails(self, tmp_path):
        root = make_repo(tmp_path, {"a/one": "1\n"}, "a/one\ndoes/not/exist\n")
        r = run_pkg_source("pkgs/p", root)
        assert r.returncode != 0
        assert "does/not/exist" in r.stderr
        assert not (root / "pkgs" / "p" / "seclegion-src.tar.zst").exists()

    def test_untracked_path_fails(self, tmp_path):
        root = make_repo(tmp_path, {"a/one": "1\n"}, "a/one\nnew\n")
        (root / "new").write_text("untracked\n")
        assert run_pkg_source("pkgs/p", root).returncode != 0

    @pytest.mark.parametrize("bad", ["../escape", "/etc/passwd"])
    def test_unsafe_path_fails(self, tmp_path, bad):
        root = make_repo(tmp_path, {"a/one": "1\n"}, f"a/one\n{bad}\n")
        assert run_pkg_source("pkgs/p", root).returncode != 0

    def test_no_source_list_fails(self, tmp_path):
        root = make_repo(tmp_path, {"a/one": "1\n"}, "a/one\n")
        (root / "pkgs" / "p" / "source.list").unlink()
        assert run_pkg_source("pkgs/p", root).returncode != 0

    def test_packs_tracked_files_deterministically(self, tmp_path):
        root = make_repo(tmp_path, {"a/one": "1\n", "a/sub/two": "2\n", "b": "3\n", "other": "x\n"},
                         "# comment\n\na\nb\n")
        out = root / "pkgs" / "p" / "seclegion-src.tar.zst"
        assert run_pkg_source("pkgs/p", root, SOURCE_DATE_EPOCH="1700000000").returncode == 0
        first = hashlib.sha256(out.read_bytes()).hexdigest()
        out.unlink()
        assert run_pkg_source("pkgs/p", root, SOURCE_DATE_EPOCH="1700000000").returncode == 0
        assert hashlib.sha256(out.read_bytes()).hexdigest() == first
        with subprocess.Popen(["zstd", "-dc", str(out)], stdout=subprocess.PIPE) as z:
            with tarfile.open(fileobj=z.stdout, mode="r|") as t:
                members = [(m.name, m.uid, m.gid, m.mtime) for m in t]
        t0 = 1700000000
        assert members == [("a/one", 0, 0, t0), ("a/sub/two", 0, 0, t0), ("b", 0, 0, t0)]

    @pytest.mark.parametrize("pkg", ["seclegion-theme", "seclegion-desktop", "seclegion-settings",
                                     "seclegion-sysmon", "seclegion-wifi", "seclegion-branding",
                                     "seclegion-hwdetect"])
    def test_real_source_lists_pack(self, tmp_path, pkg):
        """The repository's own source.list files pack (the gitignored output is removed again)."""
        r = run_pkg_source(f"pkgs/{pkg}", SOURCE_DATE_EPOCH="1700000000")
        out = PKGS / pkg / "seclegion-src.tar.zst"
        try:
            assert r.returncode == 0, r.stderr
            names = subprocess.run(["tar", "--zstd", "-tf", str(out)], capture_output=True, text=True,
                                   check=True)
            listed = names.stdout.split()
            for path in source_list(PKGS / pkg):
                assert any(n == path or n.startswith(path.rstrip("/") + "/") for n in listed), path
        finally:
            out.unlink(missing_ok=True)


@pytest.mark.parametrize("launcher,pkg_dir,mod", [
    ("seclegion-theme", "desktop/theme", "seclegion_theme"),
    ("seclegion-set", "desktop/settings", "seclegion_settings"),
    ("seclegion-settings", "desktop/settings", "seclegion_settings"),
    ("seclegion-sysmon", "desktop/sysmon", "seclegion_sysmon"),
    ("seclegion-wifi", "desktop/wifi", "seclegion_wifi"),
    ("seclegion-root-apply", "desktop/settings", "seclegion_settings"),
])
def test_launcher_finds_python_in_an_extracted_root(tmp_path, launcher, pkg_dir, mod):
    """usr/bin/<launcher> finds usr/lib/seclegion/python next to it, as the packages lay it out."""
    root = tmp_path / "root"
    (root / "usr" / "bin").mkdir(parents=True)
    shutil.copytree(REPO / pkg_dir / mod, root / "usr" / "lib" / "seclegion" / "python" / mod,
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(REPO / "tools" / launcher, root / "usr" / "bin" / launcher)
    probe = (
        "import sys\n"
        "src = open(sys.argv[1]).read().split('\\nfrom seclegion')[0]\n"
        "exec(compile(src, sys.argv[1], 'exec'), {'__file__': sys.argv[1]})\n"
        f"import {mod}\nprint({mod}.__file__)\n"
    )
    r = subprocess.run(["python3", "-I", "-c", probe, str(root / "usr" / "bin" / launcher)],
                       capture_output=True, text=True, env=clean_env())
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().startswith(str(root / "usr" / "bin" / ".." / "lib" / "seclegion" / "python"))


RULE = "desktop/settings/62-seclegion-ideapad.rules"


def test_conservation_rule_opens_the_attribute_to_wheel():
    """The Settings toggle writes conservation_mode unprivileged: the rule gives it group wheel, 0664."""
    text = (REPO / RULE).read_text()
    rules = " ".join(ln.rstrip("\\") for ln in text.splitlines() if not ln.startswith("#"))
    assert 'DRIVER=="ideapad_acpi"' in rules
    assert re.search(r'ACTION=="add\|bind"', rules)  # the attribute appears while the driver probes
    assert 'TEST=="conservation_mode"' in rules
    assert 'RUN+="/usr/bin/chgrp wheel /sys%p/conservation_mode"' in rules
    assert 'RUN+="/usr/bin/chmod 0664 /sys%p/conservation_mode"' in rules
    assert "SPDX-License-Identifier" in text


def test_conservation_rule_is_packed_and_installed_by_seclegion_settings():
    assert RULE in source_list(PKGS / "seclegion-settings")
    pkgbuild = (PKGS / "seclegion-settings" / "PKGBUILD").read_text()
    assert f'"$srcdir/{RULE}"' in pkgbuild
    assert "usr/lib/udev/rules.d/62-seclegion-ideapad.rules" in pkgbuild


def test_conservation_package_is_in_the_install_list():
    lst = (REPO / "installer" / "installd" / "post-packages.list").read_text().split()
    assert "seclegion-settings" in lst
