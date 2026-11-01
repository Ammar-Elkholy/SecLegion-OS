# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
import os
import re

import pytest

from tests.unit.conftest import REPO, load_tool

ccs = load_tool("check-container-start")
ENGINE = "doc" + "ker"  # names built in pieces so this file does not trip the checker
PODMAN = "pod" + "man"
RUN = ENGINE + " ru" + "n"
SUB = "sub" + "process"
COMPOSE = ENGINE + "-compose"
RUNC = "ru" + "nc"
AIO = "aio" + ENGINE
DV = "$" + ENGINE.upper()  # an engine variable
PV = "$" + PODMAN.upper()

FORBIDDEN = {
    "plain-run": RUN + " --rm alpine",
    "sudo": "  sudo " + RUN + " -it x",
    "sudo-flags": "sudo -E " + RUN + " x",
    "env": "env FOO=1 " + RUN + " x",
    "exec-prefix": "exec " + RUN + " x",
    "abs-path": "/usr/bin/" + RUN + " x",
    "relative-path": "./" + RUN + " x",
    "other-engine": PODMAN + " run x",
    "engine-n": "nerd" + "ctl run x",
    "engine-b": "build" + "ah run c sh",
    "engine-c": "c" + "tr run x y",
    "engine-c-ns": "c" + "tr -n k8s.io run x y",
    "compose-plugin": ENGINE + " compose up",
    "compose-hyphen": ENGINE + "-compose up -d",
    "alt-compose": PODMAN + "-compose up",
    "global-context": ENGINE + " --context x run y",
    "global-host-short": ENGINE + " -H tcp://h:2375 run y",
    "global-host-eq": ENGINE + " --host=tcp://h run y",
    "global-then-flag": ENGINE + " --tlsverify --context x run y",
    "start": ENGINE + " start box",
    "container-start": ENGINE + " container start box",
    "container-create": ENGINE + " container create x",
    "container-run": ENGINE + " container " + "ru" + "n x",
    "create": ENGINE + " create x",
    "exec": ENGINE + " exec box sh",
    "unknown-verb": ENGINE + " frobnicate x",
    "bare-engine": "ENGINE=" + ENGINE,
    "var": "$" + ENGINE.upper() + " ru" + "n x",
    "var-braces": "${" + "ENG" + "INE} ru" + "n x",
    "var-quoted": '"$' + ENGINE.upper() + '" ru' + "n x",
    "var-underscored": "$CONT" + "AINER_RUNTIME ru" + "n x",
    "var-global-flag": "$" + ENGINE.upper() + " --context x ru" + "n x",
    "readonly-then-run": ENGINE + " ps && " + RUN + " x",
    "continuation": ENGINE + " \\\n    ru" + "n x",
    "continuation-flags": ENGINE + " \\\n  --context x \\\n  ru" + "n x",
    "py-list": SUB + '.run(["' + ENGINE + '", "ru' + 'n", "x"])',
    "py-list-multiline": SUB + '.run([\n    "' + ENGINE + '",\n    "ru' + 'n",\n    "x",\n])',
    "py-list-single-quote": SUB + ".call(['" + ENGINE + "', 'ex" + "ec', 'x'])",
    "py-import": "import " + ENGINE,
    "py-from-import": "from " + ENGINE + " import from_env",
    "py-from-env": "client = " + ENGINE + ".from_env()",
    "py-containers-run": "client.containers." + "ru" + "n('alpine')",
    "py-client-class": "c = " + ENGINE.title() + "Client()",
    # Opus review bypasses: flags that take an argument hide the verb.
    "compose-p-flag": COMPOSE + " -p ps up -d",
    "compose-f-flag": COMPOSE + " -f ps up",
    "compose-profile": COMPOSE + " --profile ps up",
    "compose-env-file": COMPOSE + " --env-file ps up",
    "compose-project-dir": COMPOSE + " --project-directory ps up",
    "plugin-compose-f": ENGINE + " compose -f ps up",
    "unknown-flag-hides-verb": PODMAN + " --tmpdir ps run --rm alpine",
    "tls-flag-before-ps": ENGINE + " --tls ps",
    "unknown-flag-before-pull": ENGINE + " --frob pull x",
    "url-encoded-socket": "curl http+" + "unix://%2Fvar%2Frun%2F" + ENGINE + ".s" + "ock/containers/create",
    "url-encoded-socket-path": "http://x/%2Frun%2F" + ENGINE + ".s" + "ock/containers/create",
    "aio-import": "import " + AIO,
    "aio-create-or-replace": "c = await d.contain" + "ers.create_or_replace(config=cfg, name='x')",
    "aio-container-start": "await contain" + "er.sta" + "rt()",
    "runc-run": RUNC + " run box",
    "runc-abs": "/usr/bin/" + RUNC + " run box",
    "var-sudo-prefix": "sudo -E $" + ENGINE.upper() + " ru" + "n x",
    "var-after-semicolon": "true; $CONT" + "AINER_ENGINE create x",
    "var-sudo-quoted-user": 'sudo -u "$SUDO_USER" $DOC' + "KER run x",
    "var-timeout-quoted": 'timeout "$T" $DOC' + "KER run x",
    "var-run0": "run0 $DOC" + "KER run x",
    "var-retry-function": "retry 3 $DOC" + "KER run x",
    "var-make-assign": "CMD = $(DOC" + "KER) run x",
    "var-container-sub": "$" + ENGINE.upper() + " container st" + "art x",
    "socket": "curl --unix-socket /var/run/" + ENGINE + ".sock http://x/containers/create",
    # Opus review: an engine variable in command position is denied unless a read-only verb follows.
    "var-restart": DV + " restart x",
    "var-unpause": DV + " unpause x",
    "var-kube-play": PV + " kube play pod.yaml",
    "var-play-kube": PV + " play kube pod.yaml",
    "var-pod-start": PV + " pod start p",
    "var-service-create": DV + " service create x",
    "var-plugin-install": DV + " plugin install x",
    "var-build-host-net": DV + " build --network=host .",
    "var-buildx-insecure": DV + " buildx build --allow security.insecure .",
    "var-compose-name": DV + "_COMPOSE up -d",
    "var-unknown-flag": DV + " --foo val run x",
    "var-default-literal": "${" + ENGINE.upper() + ":-" + ENGINE + "} run x",
    "default-literal-any-name": "${X:-" + ENGINE + "} run x",
    "default-assign": "${X:=" + PODMAN + "} run x",
    "var-default-quoted": '"${ENG' + "INE:-" + PODMAN + '}" run x',
    "var-backtick": "x=`" + DV + " run x`",
    "var-cmd-subst": "x=$(" + DV + " run x)",
    "var-sudo-user": "sudo -u root " + DV + " run x",
    "var-sudo-long-user": "sudo --user root -E " + DV + " run x",
    "var-timeout": "timeout 60 " + DV + " run x",
    "var-timeout-signal": "timeout -s KILL 60 " + DV + " run x",
    "var-xargs": "xargs " + DV + " run",
    "var-nice": "nice -n 5 " + DV + " run x",
    "var-setsid": "setsid " + DV + " run x",
    "var-env-unset": "env -u HOME A=1 " + DV + " run x",
    "var-eval": 'eval "' + DV + ' run x"',
    "var-bash-c": 'bash -c "' + DV + ' run x"',
    "var-sh-c": "sh -c '" + DV + " run x'",
    "make-paren": "\t$(" + ENGINE.upper() + ") run x",
    "make-dollar-dollar": "\t$$" + ENGINE.upper() + " run x",
    "make-recipe-prefix": "\t@$(" + ENGINE.upper() + ") run x",
    "http-unix-alone": 'requests.post("http+' + 'unix://%2Ftmp%2Fx/containers/create")',
    "engine-host-tcp": ENGINE.upper() + "_HOST=tcp://h:2375 make x",
    "engine-host-export": "export " + ENGINE.upper() + "_HOST=ssh://u@h",
    "engine-host-py": 'os.environ["' + ENGINE.upper() + '_HOST"] = "tcp://h"',
    "engine-host-yaml": "  " + ENGINE.upper() + "_HOST: tcp://h",
    "container-host": "CONT" + "AINER_HOST=ssh://u@h",
    "api-port": "curl -X POST localhost:23" + "75/containers/create",
    "api-port-tls": "https://h:23" + "76/v1.43/containers/x/start",
    "engine-crun": "cr" + "un run x",
    "engine-youki": "/usr/bin/you" + "ki run x",
    "engine-nspawn": "systemd-" + "nspawn -D /srv/root",
    "engine-lxc": "lxc-" + "start -n c1",
}

# Read-only verbs and look-alike prose: must NOT be flagged.
HARMLESS = {
    "pull": ENGINE + " pull archlinux@sha256:abc",
    "image-inspect": ENGINE + " image inspect x",
    "images": ENGINE + " images",
    "ps": ENGINE + " ps -a",
    "version": ENGINE + " version",
    "info": ENGINE + " info",
    "sudo-pull": "sudo " + ENGINE + " pull x",
    "abs-path-pull": "/usr/bin/" + ENGINE + " pull x",
    "global-flag-pull": ENGINE + " --context x pull y",
    "var-info": "$" + ENGINE.upper() + " info",
    "py-list-ps": SUB + '.run(["' + ENGINE + '", "ps"])',
    "wrapper-name": "tools/" + ENGINE + "-build.sh iso",
    "wrapper-prose": "# started only by tools/" + ENGINE + "-build.sh",
    "unrelated": "echo hello; ls -l /work/out",
    "compose-ps": COMPOSE + " ps",
    "compose-file-flag-pull": COMPOSE + " -f x.yml pull",
    "compose-p-flag-pull": COMPOSE + " -p proj pull",
    "debug-flag-ps": ENGINE + " --debug ps",
    "var-not-command": 'echo "engine: $CONTAINER_ENGINE ru' + 'n"',
    "var-path-in-subshell": 'before="$(ls "$XDG_RUNTIME_DIR/hypr" 2>/dev/null)"',
    "var-path-in-parens": "JSON it renders ($XDG_RUNTIME_DIR/seclegion/ws/N.json,",
    # The seven lines the scanner used to flag by mistake (variable names, not engines).
    "fp-host-lib-20": '    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"',
    "fp-host-lib-21": (
        '    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"'
    ),
    "fp-host-lib-23": '        for s in "$XDG_RUNTIME_DIR"/wayland-[0-9]*; do',
    "fp-host-lib-28": '        for d in "$XDG_RUNTIME_DIR"/hypr/*/; do',
    "fp-host-lib-35": (
        'has_wayland() { [ -n "${WAYLAND_DISPLAY:-}" ] && [ -e "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; }'
    ),
    "fp-render-181": 'format = \\"\\"\\"\n[╭─](fg:accent2)${custom.vpn}$git_status$'
    + ENGINE
    + '_context$python\n[╰─❯](bold) \\"\\"\\"',
    "fp-starship-7": "[╭─](fg:accent2)${custom.vpn}${env_var.TARGET}$username$hostname$directory$git_branch"
    "$git_status$" + ENGINE + "_context$python$rust$golang$cmd_duration$status",
    "compose-filename": "see " + ENGINE + "-compose.yml for the layout",
    "var-default-info": "${" + ENGINE.upper() + ":-" + ENGINE + "} info",
    "var-sudo-ps": "sudo -u root " + DV + " ps",
    "make-paren-ps": "\t$(" + ENGINE.upper() + ") ps",
    "var-in-argument": 'cp x "$XDG_RUNTIME_DIR"/y',
    "engine-host-read": 'echo "${' + ENGINE.upper() + '_HOST:-unset}"',
    "engine-host-test": '[ -z "$' + ENGINE.upper() + '_HOST" ] && echo local',
    "engine-host-unset": "unset " + ENGINE.upper() + "_HOST",
}


def write_lines(path, text):
    path.write_text(text.replace("\\n", "\n") + "\n")


def test_repository_has_no_container_start_outside_wrapper():
    assert ccs.scan(REPO) == []


@pytest.mark.parametrize("line", list(FORBIDDEN.values()), ids=list(FORBIDDEN))
def test_scanner_catches_forms(tmp_path, line):
    write_lines(tmp_path / "evil.sh", line)
    assert [h[0] for h in ccs.scan(str(tmp_path))] == ["evil.sh"]


@pytest.mark.parametrize("line", list(HARMLESS.values()), ids=list(HARMLESS))
def test_scanner_allows_readonly_and_lookalikes(tmp_path, line):
    write_lines(tmp_path / "ok.sh", line)
    assert ccs.scan(str(tmp_path)) == []


def test_scanner_scans_a_top_level_file_named_like_a_skipped_directory(tmp_path):
    names = ["build", "out", ".pytest_cache", ".ruff_cache", ".claude"]  # .git file: worktree pointer
    for name in names:
        (tmp_path / name).write_text(RUN + " x\n")
    assert sorted(h[0] for h in ccs.scan(str(tmp_path))) == sorted(names)
    (tmp_path / "build").unlink()
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "x.sh").write_text(RUN + " x\n")  # the directory is still skipped
    assert sorted(h[0] for h in ccs.scan(str(tmp_path))) == sorted(names[1:])


def test_scanner_reports_the_line_of_a_multiline_list(tmp_path):
    write_lines(tmp_path / "evil.py", "x = 1\n" + FORBIDDEN["py-list-multiline"])
    assert [h[1] for h in ccs.scan(str(tmp_path))] == [3]  # the line holding the engine name


def test_scanner_allows_only_the_wrapper(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "docker-build.sh").write_text(RUN + " x\n")
    (tmp_path / "pull.txt").write_text(ENGINE + " pull x\n")
    assert ccs.scan(str(tmp_path)) == []
    (tmp_path / "docker-build.sh").write_text(RUN + " x\n")  # same name elsewhere is not the wrapper
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "tools").mkdir()
    (tmp_path / "sub" / "tools" / "docker-build.sh").write_text(RUN + " x\n")
    assert sorted(h[0] for h in ccs.scan(str(tmp_path))) == [
        "docker-build.sh",
        os.path.join("sub", "tools", "docker-build.sh"),
    ]


@pytest.mark.parametrize(
    "where",
    [
        "build/evil.sh",
        "out/evil.sh",
        "evidence/x/evil.sh",
        "src/build/evil.sh",
        "a/.git/evil.sh",
        "a/.venv/evil.sh",
        "tests/out/evil.sh",
        ".hidden/evil.sh",
    ],
)
def test_scanner_skips_only_top_level_scratch(tmp_path, where):
    path = tmp_path / where
    path.parent.mkdir(parents=True)
    path.write_text(RUN + " x\n")
    skipped_top = where.split("/")[0] in {"build", "out"}
    assert ccs.scan(str(tmp_path)) == ([] if skipped_top else [(where, 1, RUN + " x")])


def test_scanner_skips_only_log_transcripts_under_top_level_evidence(tmp_path):
    for where in ("evidence/M4-erase/h/run/serial.log", "evidence/x/run.sh", "src/evidence/serial.log"):
        path = tmp_path / where
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(RUN + " x\n")
    hits = sorted(rel for rel, _, _ in ccs.scan(str(tmp_path)))
    assert hits == ["evidence/x/run.sh", "src/evidence/serial.log"]


@pytest.mark.parametrize("top", [".git", ".venv"])
def test_scanner_skips_top_level_git_and_venv(tmp_path, top):
    (tmp_path / top).mkdir()
    (tmp_path / top / "x.sh").write_text(RUN + " x\n")
    assert ccs.scan(str(tmp_path)) == []


def test_scanner_skips_a_worktree_git_file(tmp_path):
    (tmp_path / ".git").write_text("gitdir: /elsewhere/" + ENGINE + " " + "ru" + "n\n")
    assert ccs.scan(str(tmp_path)) == []


def test_scanner_reads_markdown_code_blocks_only(tmp_path):
    (tmp_path / "prose.md").write_text("The " + ENGINE + " group is root-equivalent; use `" + RUN + "`.\n")
    assert ccs.scan(str(tmp_path)) == []
    (tmp_path / "code.md").write_text("text\n```sh\n" + RUN + " x\n```\n")
    assert ccs.scan(str(tmp_path)) == [("code.md", 3, RUN + " x")]


def test_scanner_allows_a_package_name_line_in_a_package_list_only(tmp_path):
    (tmp_path / "pkgs.list").write_text("# dev\ngit\n" + ENGINE + "\n  " + ENGINE + "\t\nsocat\n")
    assert ccs.scan(str(tmp_path)) == []
    (tmp_path / "pkgs.list").write_text("git\n" + ENGINE + "  # comment\n" + RUN + " x\n")
    assert [h[1] for h in ccs.scan(str(tmp_path))] == [2, 3]
    (tmp_path / "pkgs.list").unlink()
    (tmp_path / "pkgs.txt").write_text("git\n" + ENGINE + "\nsocat\n")  # not a package list
    assert [h[1] for h in ccs.scan(str(tmp_path))] == [2]


def test_scanner_flags_engine_symlinks(tmp_path):
    (tmp_path / "d").symlink_to("/usr/bin/" + ENGINE)
    (tmp_path / "ok").symlink_to("/dev/null")
    assert [h[0] for h in ccs.scan(str(tmp_path))] == ["d"]


def test_cli_exit_status(tmp_path):
    (tmp_path / "evil.sh").write_text(RUN + " x\n")
    assert ccs.main([str(tmp_path)]) == 1
    (tmp_path / "evil.sh").write_text(ENGINE + " pull x\n")
    assert ccs.main([str(tmp_path)]) == 0


def wrapper():
    with open(os.path.join(REPO, "tools", "docker-build.sh"), encoding="utf-8") as handle:
        return handle.read()


def test_wrapper_image_pinned_by_digest_not_tag():
    match = re.search(r"readonly IMAGE='([^']+)'", wrapper())
    assert match and re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", match.group(1))
    assert ":latest" not in match.group(1)


def test_wrapper_mounts_repo_readonly_and_nothing_sensitive():
    text = wrapper()
    assert "target=/src,readonly" in text
    start = text.split(RUN, 1)[-1]
    for forbidden in ("$HOME", "~", "source=/ ", "source=/etc", ".sock", " -v "):
        assert forbidden not in start, forbidden
    assert start.count("--mount") == 3  # repo (ro), workdir, pacman cache - nothing else
    assert "check-space" in text  # NTFS / low-space guard on the workdir
    assert "/var/tmp/" in text
