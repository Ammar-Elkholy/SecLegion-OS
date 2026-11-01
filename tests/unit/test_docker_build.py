# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Behaviour of the build wrapper's path checks and the in-container chown-back.

Nothing here starts a container: SECLEGION_TEST_ROOT only works with the wrapper's
'check' mode, and every run gets a fake engine on PATH that records any call.
"""

import os
import subprocess

import pytest

from tests.unit.conftest import REPO

ENGINE = "doc" + "ker"
WRAPPER = os.path.join(REPO, "tools", ENGINE + "-build.sh")
CONTAINER_SCRIPT = os.path.join(REPO, "tools", "container-build.sh")


def shim(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    """A resolved temp root, a bin dir with a recording fake engine, and a runner."""
    root = tmp_path.resolve() / "root"
    root.mkdir()
    bindir = tmp_path.resolve() / "bin"
    bindir.mkdir()
    called = tmp_path.resolve() / "engine-called"
    shim(bindir, ENGINE, f'echo "$@" >> {called}; exit 99')

    def run(*args, extra_env=None, path_first=None):
        path = os.pathsep.join(filter(None, [path_first, str(bindir), "/usr/bin", "/bin"]))
        env = {"PATH": path, "SECLEGION_TEST_ROOT": str(root), **(extra_env or {})}
        proc = subprocess.run(["bash", WRAPPER, *args], env=env, capture_output=True,
                              text=True, check=False)
        assert not called.exists(), f"the wrapper called the engine: {called.read_text()}"
        return proc

    run.root = root
    run.bindir = bindir
    return run


def test_check_accepts_a_plain_layout_and_creates_the_dirs(sandbox):
    proc = sandbox("check")
    assert proc.returncode == 0, proc.stderr
    assert "check OK" in proc.stdout
    for name in ("work", "out", "pkgcache"):
        assert (sandbox.root / "seclegion-build" / name).is_dir()


def test_symlinked_pkgcache_is_refused(sandbox):
    work = sandbox.root / "seclegion-build"
    work.mkdir()
    elsewhere = sandbox.root / "elsewhere"
    elsewhere.mkdir()
    (work / "pkgcache").symlink_to(elsewhere)
    proc = sandbox("check")
    assert proc.returncode == 1
    assert "no path component may be a symlink" in proc.stderr and "pkgcache" in proc.stderr
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize("name", ["work", "out"])
def test_other_symlinked_subdirs_are_refused(sandbox, name):
    work = sandbox.root / "seclegion-build"
    work.mkdir()
    (sandbox.root / "elsewhere").mkdir()
    (work / name).symlink_to(sandbox.root / "elsewhere")
    proc = sandbox("check")
    assert proc.returncode == 1 and "no path component may be a symlink" in proc.stderr


def test_dangling_symlinked_subdir_is_refused(sandbox):
    work = sandbox.root / "seclegion-build"
    work.mkdir()
    (work / "pkgcache").symlink_to(sandbox.root / "does-not-exist")
    proc = sandbox("check")
    assert proc.returncode == 1 and "no path component may be a symlink" in proc.stderr
    assert not (sandbox.root / "does-not-exist").exists()


def test_symlinked_workdir_is_refused(sandbox):
    (sandbox.root / "real").mkdir()
    (sandbox.root / "seclegion-build").symlink_to(sandbox.root / "real")
    proc = sandbox("check")
    assert proc.returncode == 1 and "no path component may be a symlink" in proc.stderr
    assert list((sandbox.root / "real").iterdir()) == []


def test_symlinked_parent_of_a_nested_workdir_is_refused(sandbox):
    (sandbox.root / "real").mkdir()
    (sandbox.root / "link").symlink_to(sandbox.root / "real")
    proc = sandbox("check", extra_env={"SECLEGION_WORKDIR": str(sandbox.root / "link" / "w")})
    assert proc.returncode == 1 and "no path component may be a symlink" in proc.stderr
    assert list((sandbox.root / "real").iterdir()) == []


def test_workdir_not_owned_by_the_invoking_user_is_refused(sandbox):
    shim(sandbox.bindir, "id", "echo 4242")  # we are suddenly someone else
    proc = sandbox("check")
    assert proc.returncode == 1 and "not owned by uid 4242" in proc.stderr


def test_workdir_must_stay_under_the_root(sandbox):
    proc = sandbox("check", extra_env={"SECLEGION_WORKDIR": "/tmp/elsewhere"})
    assert proc.returncode == 1 and "must be a plain path under" in proc.stderr


def test_test_root_cannot_be_used_to_start_a_build(sandbox):
    proc = sandbox("iso")
    assert proc.returncode == 1 and "check' only" in proc.stderr


def test_unknown_mode_is_refused(sandbox):
    assert sandbox("shell").returncode == 1


def test_production_default_is_var_tmp():
    with open(WRAPPER, encoding="utf-8") as handle:
        text = handle.read()
    assert "base=/var/tmp\n" in text and "default_workdir=/var/tmp/seclegion-build\n" in text
    assert "min_gib=25\n" in text


def container_test_env(tmp_path):
    """The script runs outside a container here: point it at this checkout and a scratch mirrorlist."""
    return {"SECLEGION_TEST_SRC": REPO, "SECLEGION_TEST_MIRRORLIST": str(tmp_path / "mirrorlist")}


def test_container_script_gives_output_back_even_when_the_build_fails(tmp_path):
    log = tmp_path / "chown.log"
    shim(tmp_path, "pacman", "exit 1")  # the build fails at its first step
    shim(tmp_path, "chown", f'echo "$@" >> {log}')
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "HOST_UID": "1234", "HOST_GID": "5678",
           **container_test_env(tmp_path)}
    proc = subprocess.run(["bash", CONTAINER_SCRIPT], env=env, capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 1
    args = log.read_text().split()
    assert "1234:5678" in args and "-R" in args
    assert "/work" in args and "/var/cache/pacman/pkg" in args  # work/, out/, pkgcache/ live there


# --- the 'theme' mode (plan r13 J1b) --------------------------------------------------

def test_theme_mode_is_a_known_mode_but_never_runs_under_the_test_root(sandbox):
    proc = sandbox("theme")
    assert proc.returncode == 1 and "check' only" in proc.stderr
    assert "iso|theme|pkgs <dir>|check" in sandbox("shell").stderr


def test_wrapper_hands_its_hard_coded_mode_to_the_container_script():
    with open(WRAPPER, encoding="utf-8") as handle:
        text = handle.read()
    assert text.count("bash /src/tools/container-build.sh") == 1
    assert 'container-build.sh "$mode"' in text
    assert "$@" not in text.split(ENGINE + " run")[-1]  # no caller-supplied arguments reach the engine


def _pacman_args(tmp_path, *args):
    log = tmp_path / ("pacman-" + "-".join(args or ("default",)))
    shim(tmp_path, "pacman", f'echo "$@" > {log}; exit 1')
    shim(tmp_path, "chown", "exit 0")
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "HOST_UID": "1", "HOST_GID": "1",
           **container_test_env(tmp_path)}
    proc = subprocess.run(["bash", CONTAINER_SCRIPT, *args], env=env, capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 1
    return log.read_text().split()


def test_container_script_installs_archiso_for_iso_only(tmp_path):
    assert "archiso" in _pacman_args(tmp_path) and "archiso" in _pacman_args(tmp_path, "iso")
    theme = _pacman_args(tmp_path, "theme")
    assert "archiso" not in theme and {"grub", "freetype2", "ttf-jetbrains-mono"} <= set(theme)


def test_container_script_refuses_an_unknown_mode():
    env = {"PATH": "/usr/bin:/bin", "HOST_UID": "1", "HOST_GID": "1"}
    proc = subprocess.run(["bash", CONTAINER_SCRIPT, "shell"], env=env, capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 2 and "unknown mode" in proc.stderr


# --- the 'pkgs' mode and the build lock (R0) ----------------------------------------------

@pytest.mark.parametrize("arg", ["/etc", "pkgs/../tools", "../etc", "pkgs", "pkgs/", "pkgs/nope",
                                 "pkgs/hello/../../tools", "pkgs/./hello", "pkgs/he llo", "tools"])
def test_pkgs_refuses_anything_but_a_plain_dir_under_pkgs(sandbox, arg):
    proc = sandbox("pkgs", arg)
    assert proc.returncode == 1 and "REFUSED: pkgs:" in proc.stderr, proc.stderr


def test_pkgs_refuses_a_symlinked_dir_and_missing_pkgbuild():
    link = os.path.join(REPO, "pkgs", "zz-link")
    empty = os.path.join(REPO, "pkgs", "zz-empty")
    try:
        os.symlink(os.path.join(REPO, "tools"), link)
        os.mkdir(empty)
        for arg in (link, "pkgs/zz-link", "pkgs/zz-empty"):
            proc = subprocess.run(["bash", WRAPPER, "pkgs", arg], env={"PATH": "/usr/bin:/bin"},
                                  capture_output=True, text=True, check=False)
            assert proc.returncode == 1 and "REFUSED: pkgs:" in proc.stderr, proc.stderr
    finally:
        if os.path.islink(link):
            os.unlink(link)
        if os.path.isdir(empty):
            os.rmdir(empty)


def test_pkgs_needs_exactly_one_argument_and_other_modes_none(sandbox):
    assert "usage" in sandbox("pkgs").stderr
    assert "no further arguments" in sandbox("iso", "pkgs/hello").stderr


def test_pkgs_accepts_hello_up_to_the_test_root_refusal(sandbox):
    # Valid directory passes validation; the test root then stops it before any container.
    proc = sandbox("pkgs", "pkgs/hello")
    assert proc.returncode == 1 and "check' only" in proc.stderr


def test_wrapper_locks_before_starting_and_never_in_check():
    with open(WRAPPER, encoding="utf-8") as handle:
        text = handle.read()
    assert text.index("sl_build_lock") < text.index(ENGINE + " run")
    assert text.index("sl_build_lock") > text.index('if [[ $mode == check ]]')


def test_second_build_waits_while_the_lock_is_held(tmp_path):
    lock = tmp_path / "build.lock"
    locks = os.path.join(REPO, "tools", "lib", "locks.sh")
    script = f'source {locks}; sl_build_lock "$1"; echo got'
    holder = subprocess.Popen(["bash", "-c", script + "; read _", "_", str(lock)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "got"
        with pytest.raises(subprocess.TimeoutExpired) as waiting:
            subprocess.run(["bash", "-c", script, "_", str(lock)], capture_output=True,
                           text=True, timeout=2, check=False)
        assert "waiting for build lock" in (waiting.value.stderr or b"").decode()
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=10)
        proc = subprocess.run(["bash", "-c", script, "_", str(lock)], capture_output=True,
                              text=True, timeout=10, check=False)
        assert proc.returncode == 0 and proc.stdout.strip() == "got"
    finally:
        holder.kill()
        holder.wait()


def test_container_script_pkgs_mode_installs_only_base_devel(tmp_path):
    args = _pacman_args(tmp_path, "pkgs")
    assert "base-devel" in args and "archiso" not in args and "grub" not in args
