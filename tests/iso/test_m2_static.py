# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Plan r13 J2a (G11): package lists, archive-pinned pacman.conf, offline cache, checked statically.

No ISO, container or network needed. G10 (every package resolves, `packages-lock-ok`) and G12
(size) are read from a real build. J2b adds its `-k privilege` tests to this file's module later.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILE = REPO / "iso" / "profile"
LISTS = REPO / "iso" / "packages"
PACMAN_CONF = PROFILE / "pacman.conf"
CONTAINER_BUILD = REPO / "tools" / "container-build.sh"
BUILD_ISO = REPO / "tools" / "build-iso"

PIN_DATE = "2026/10/15"
SERVER_RE = re.compile(r"^https://archive\.archlinux\.org/repos/(\d{4}/\d{2}/\d{2})/\$repo/os/\$arch$")
ALLOWED_REPOS = ["core", "extra", "seclegion"]
# Our own signed file repository: below core and extra, never shadowing them, and the one section
# that may carry its own SigLevel (exactly this) and a file:// Server (no variables, no network).
SECLEGION_SIGLEVEL = "Required DatabaseRequired"
SECLEGION_SERVER_RE = re.compile(r"^file:///[A-Za-z0-9._/-]+$")
# The only SigLevel words allowed for packages. DatabaseOptional is the one weak-sounding
# word that is fine: it concerns the sync database, never a package.
GOOD_SIGLEVEL_WORDS = {"Required", "DatabaseOptional"}
MUST_HAVE = [
    "grub",
    "memtest86+-efi",
    "cage",
    "wlr-randr",
    "greetd",
    "greetd-regreet",
    "hyprland",
    "firefox",
    "archlinux-keyring",
]
FORBIDDEN_PACKAGES = ["openssh", "syslinux"]


def read_list(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def check_pacman_conf(text: str) -> list[str]:
    """Every rule violation in a pacman.conf, as messages (empty = clean)."""
    problems = []
    section = None
    repos = []
    seclegion_siglevel = []
    seclegion_servers = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            section = m.group(1)
            if section != "options":
                repos.append(section)
            continue
        key, _, value = (p.strip() for p in line.partition("="))
        if key in ("SigLevel", "LocalFileSigLevel", "RemoteFileSigLevel"):
            if section == "seclegion":
                if key != "SigLevel" or " ".join(value.split()) != SECLEGION_SIGLEVEL:
                    want = f"SigLevel = {SECLEGION_SIGLEVEL}"
                    problems.append(f"[seclegion] {key} = {value!r}: must be exactly {want!r}")
                seclegion_siglevel.append(value)
                continue
            bad = [w for w in value.split() if w not in GOOD_SIGLEVEL_WORDS]
            if bad:
                problems.append(f"{key} has {bad} (only {sorted(GOOD_SIGLEVEL_WORDS)} allowed)")
            if section != "options":
                problems.append(f"{key} set inside [{section}]: only the global value may be used")
        elif key == "Include":
            problems.append(f"Include {value}: mirrorlists are not pinned")
        elif key == "Server":
            m = SERVER_RE.match(value)
            if section == "seclegion":
                seclegion_servers.append(value)
                if not SECLEGION_SERVER_RE.match(value):
                    problems.append(f"[seclegion] Server {value!r} must be a plain file:// path")
            elif section not in ALLOWED_REPOS:
                problems.append(f"Server in [{section}]")
            elif not m or m.group(1) != PIN_DATE:
                problems.append(f"[{section}] Server {value!r} is not the {PIN_DATE} archive")
        elif key in ("XferCommand", "DownloadUser", "CacheServer"):
            problems.append(f"{key} is not allowed")
    if repos != ALLOWED_REPOS:
        problems.append(f"repositories are {repos}, must be exactly {ALLOWED_REPOS}")
    if "seclegion" in repos and (len(seclegion_siglevel) != 1 or len(seclegion_servers) != 1):
        problems.append("[seclegion] needs exactly one SigLevel and one Server line")
    if not re.search(r"^SigLevel\s*=\s*Required DatabaseOptional\s*$", text, re.MULTILINE):
        problems.append("global SigLevel must be 'Required DatabaseOptional'")
    return problems


def unsafe_pacman_lines(script: str) -> list[str]:
    """pacman commands that refresh the databases without upgrading (-Sy not followed by u).

    -Syuw (download only) and -Syu are fine. A bare -Sy, alone or with a package, is the
    partial upgrade Arch forbids.
    """
    bad = []
    for line in script.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"\bpacman\b[^|;&\n]*?\s-(?:-sync\s+-)?(S\w*)", line):
            flags = m.group(1)
            if "y" in flags and "u" not in flags:
                bad.append(line.strip())
        if re.search(r"\bpacman\b.*--refresh", line) and not re.search(r"--sysupgrade|-S\w*u", line):
            bad.append(line.strip())
    return bad


# ---- G11: repos ---------------------------------------------------------------------------


def test_repos_pacman_conf_is_clean():
    assert check_pacman_conf(PACMAN_CONF.read_text()) == []


def test_repos_seclegion_is_last_signed_and_local():
    text = PACMAN_CONF.read_text()
    assert re.findall(r"(?m)^\[([^\]]+)\]", text) == ["options", "core", "extra", "seclegion"]
    section = re.split(r"(?m)^\[seclegion\]$", text, maxsplit=1)[1]
    assert re.search(r"(?m)^SigLevel = Required DatabaseRequired$", section)
    assert re.search(r"(?m)^Server = file:///opt/seclegion/cache/seclegion$", section)


def test_repos_pin_date_is_the_default():
    dates = set(re.findall(r"/repos/(\d{4}/\d{2}/\d{2})/", PACMAN_CONF.read_text()))
    assert dates == {PIN_DATE}


@pytest.mark.parametrize(
    "planted",
    [
        "[foo]\nServer = https://example.org/$repo/os/$arch\n",
        "[core-testing]\nServer = https://archive.archlinux.org/repos/2026/10/15/$repo/os/$arch\n",
        "[multilib]\nServer = https://archive.archlinux.org/repos/2026/10/15/$repo/os/$arch\n",
        "[extra]\nInclude = /etc/pacman.d/mirrorlist\n",
        "[extra]\nSigLevel = Optional TrustAll\n",
        "[extra]\nSigLevel = Never\n",
        "[extra]\nServer = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n",
        "[extra]\nServer = https://archive.archlinux.org/repos/2026/10/14/$repo/os/$arch\n",
        "[custom]\nSigLevel = Required DatabaseRequired\nServer = file:///opt/custom\n",
        "[custom]\nServer = file:///opt/seclegion/cache/seclegion\n",
    ],
)
def test_repos_planted_foreign_or_weak_entry_is_rejected(planted):
    assert check_pacman_conf(PACMAN_CONF.read_text() + "\n" + planted) != []


def seclegion_conf(siglevel="Required DatabaseRequired", server="file:///opt/seclegion/cache/seclegion"):
    section = f"[seclegion]\nSigLevel = {siglevel}\nServer = {server}\n"
    return re.sub(r"(?ms)^\[seclegion\]$.*", section, PACMAN_CONF.read_text())


def test_repos_seclegion_section_as_committed_is_clean():
    assert check_pacman_conf(seclegion_conf()) == []


@pytest.mark.parametrize(
    "siglevel",
    [
        "Optional",
        "Required",
        "Required DatabaseOptional",
        "Required DatabaseRequired TrustAll",
        "Optional TrustAll",
        "Never",
        "PackageRequired DatabaseRequired",
        "DatabaseRequired",
    ],
)
def test_repos_seclegion_siglevel_must_be_exactly_required_databaserequired(siglevel):
    assert check_pacman_conf(seclegion_conf(siglevel=siglevel)) != []


@pytest.mark.parametrize(
    "server",
    [
        "https://example.org/seclegion",
        "http://localhost/seclegion",
        "file://relative/path",
        "file:///opt/$repo",
        "ftp://example.org/x",
    ],
)
def test_repos_seclegion_server_must_be_a_plain_file_url(server):
    assert check_pacman_conf(seclegion_conf(server=server)) != []


def test_repos_seclegion_without_siglevel_or_localfile_override_is_rejected():
    no_siglevel = re.sub(r"(?m)^SigLevel = Required DatabaseRequired\n", "", PACMAN_CONF.read_text())
    assert check_pacman_conf(no_siglevel) != []
    extra = PACMAN_CONF.read_text().replace("[seclegion]\n", "[seclegion]\nLocalFileSigLevel = Optional\n")
    assert check_pacman_conf(extra) != []
    above = PACMAN_CONF.read_text().replace(
        "[core]", "[seclegion]\nSigLevel = Required DatabaseRequired\nServer = file:///x\n[core]", 1
    )
    assert check_pacman_conf(above) != []  # not below core and extra, and listed twice


@pytest.mark.parametrize(
    "level", ["Optional", "Never", "PackageOptional", "PackageTrustAll", "Required TrustAll"]
)
def test_repos_weak_global_siglevel_is_rejected(level):
    text = re.sub(r"(?m)^SigLevel\s*=.*$", f"SigLevel = {level}", PACMAN_CONF.read_text())
    assert check_pacman_conf(text) != []


def test_repos_local_file_siglevel_is_not_weakened():
    text = PACMAN_CONF.read_text().replace("[core]", "LocalFileSigLevel = Optional\n[core]", 1)
    assert check_pacman_conf(text) != []


def test_repos_no_openssh_or_syslinux_anywhere_in_the_package_files():
    files = sorted(LISTS.glob("*.list")) + sorted(PROFILE.glob("packages.*"))
    assert len(files) >= 6
    for f in files:
        names = read_list(f)
        for forbidden in FORBIDDEN_PACKAGES:
            assert forbidden not in names, f"{forbidden} in {f.relative_to(REPO)}"


def test_repos_build_script_adds_no_key_and_no_foreign_repo():
    text = CONTAINER_BUILD.read_text()
    for needle in ("TrustAll", "--recv", "--lsign", "keyserver", "SigLevel"):
        assert needle not in text, needle
    # the one key it adds is the [seclegion] keyring's, from the package of the signed repository;
    # --init only makes the throwaway container's local master key, and only when it has none
    assert re.findall(
        r"pacman-key\S*(?:[ \t]+\S+)*",
        "\n".join(ln for ln in text.splitlines() if "pacman-key" in ln and not ln.lstrip().startswith("#")),
    ) == ["pacman-key --init", "pacman-key --populate seclegion"]
    init_line = next(ln for ln in text.splitlines() if "pacman-key --init" in ln)
    assert init_line.startswith("gpg --homedir /etc/pacman.d/gnupg --list-secret-keys") and "||" in init_line
    assert "archive.archlinux.org" in text
    # no partial upgrade anywhere in the build script, and the checker does see one
    assert unsafe_pacman_lines(text) == []
    assert unsafe_pacman_lines("pacman -Sy --noconfirm foo") != []
    assert unsafe_pacman_lines("pacman --config c -Syw foo") != []
    assert unsafe_pacman_lines("pacman -Syuw foo") == []


# ---- lists --------------------------------------------------------------------------------


def test_lists_exist_with_spdx_headers_and_no_duplicates():
    seen: dict[str, str] = {}
    for name in ("base", "live", "desktop", "cache"):
        path = LISTS / f"{name}.list"
        text = path.read_text()
        # REUSE-IgnoreStart
        assert "SPDX-License-Identifier: MIT" in text.splitlines()[1], path
        # REUSE-IgnoreEnd
        pkgs = read_list(path)
        assert pkgs, path
        assert len(pkgs) == len(set(pkgs)), f"duplicate inside {path.name}"
        for p in pkgs:
            assert re.fullmatch(r"[a-z0-9@._+-]+", p), p
            if name in ("base", "live", "desktop"):
                assert p not in seen, f"{p} is in {seen[p]}.list and {name}.list"
                seen[p] = name


def test_lists_have_the_required_packages():
    iso = (
        set(read_list(LISTS / "base.list"))
        | set(read_list(LISTS / "live.list"))
        | set(read_list(LISTS / "desktop.list"))
    )
    assert [p for p in MUST_HAVE if p not in iso] == []


def test_lists_cache_holds_the_nvidia_open_set():
    cache = set(read_list(LISTS / "cache.list"))
    assert {"nvidia-open", "nvidia-open-lts", "nvidia-utils"} <= cache
    live_only = set(read_list(LISTS / "live.list")) - set(read_list(LISTS / "base.list"))
    # the VM guest packages hwdetect's rules install into a VM target (hw/rules.d/10-virt.toml) are in both
    guests = {"qemu-guest-agent", "spice-vdagent", "open-vm-tools", "hyperv"}
    assert not (cache & live_only - guests)


def test_lists_packages_x86_64_is_the_union_of_the_iso_lists():
    union = set()
    for name in ("base", "live", "desktop", "seclegion"):
        union |= set(read_list(LISTS / f"{name}.list"))
    committed = (PROFILE / "packages.x86_64").read_text().splitlines()
    assert committed == sorted(union), "regenerate iso/profile/packages.x86_64 from iso/packages/*.list"
    assert "syslinux" not in committed
    assert "seclegion-keyring" in committed
    assert "seclegion-installer" in committed  # the install kiosk cannot start the installer without it


def test_lists_seclegion_list_is_our_repo_only_and_not_resolved_against_arch():
    path = LISTS / "seclegion.list"
    # REUSE-IgnoreStart
    assert "SPDX-License-Identifier: MIT" in path.read_text().splitlines()[1]
    # REUSE-IgnoreEnd
    # spec A3: the installer ships on the ISO from our repo (the install kiosk runs it);
    # seclegion-hwdetect is its runtime data (hwreport for page 11, hw/gaming.toml for the gaming tier)
    # and the live desktop (tests/iso/test_live_desktop_packages.py)
    assert sorted(read_list(path)) == [
        "seclegion-branding",
        "seclegion-desktop",
        "seclegion-dotfiles",
        "seclegion-hwdetect",
        "seclegion-installer",
        "seclegion-keyring",
        "seclegion-theme",
    ]
    official = set()
    for name in ("base", "live", "desktop", "cache"):
        official |= set(read_list(LISTS / f"{name}.list"))
    assert not official & set(read_list(path))
    script = CONTAINER_BUILD.read_text()
    # the resolve calls use the official lists only; the generated packages.x86_64 adds seclegion.list
    assert "read_list base.list live.list desktop.list)" in script
    assert "read_list base.list live.list desktop.list seclegion.list" in script
    assert 'resolve "${iso_pkgs[@]}"' in script and 'resolve "${all_iso_pkgs' not in script


# ---- the build script -----------------------------------------------------------------------


def test_build_writes_the_lock_and_the_signed_offline_cache():
    text = CONTAINER_BUILD.read_text()
    assert "packages.lock" in text
    assert "packages-lock-ok" in text
    assert "/opt/seclegion/cache" in text
    assert "repo-add" in text and "--include-sigs" in text
    assert ".sig" in text
    assert "-Syuw" in text
    assert "/usr/share/seclegion" in text
    assert '"$src"/desktop' in text and "$share/bin" in text
    for tool in ("seclegion-settings", "seclegion-theme", "seclegion-set"):
        assert tool in text
    # the container's own pacman is pinned to the same dated archive, from pacman.conf
    assert "/etc/pacman.d/mirrorlist" in text and "iso/profile/pacman.conf" in text


def test_build_iso_hands_the_lock_back():
    assert "packages.lock" in BUILD_ISO.read_text()


def test_build_iso_builds_the_signed_repo_first():
    lines = [ln.strip() for ln in BUILD_ISO.read_text().splitlines() if not ln.lstrip().startswith("#")]
    pkgs = next(i for i, ln in enumerate(lines) if ln.endswith('/tools/build-pkgs"'))
    iso = next(i for i, ln in enumerate(lines) if ln.endswith('docker-build.sh" iso'))
    assert pkgs < iso


def test_build_seclegion_repo_is_copied_in_trusted_and_the_conf_is_split():
    text = CONTAINER_BUILD.read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert 'sl_lock_conf /work/profile/pacman.conf "$pconf"' in code
    assert "pconf=/work/lock-pacman.conf" in code
    assert '"$cache/seclegion"' in code and "/work/out/repo" in code
    assert "sl_extract_keyring" in code and "pacman-key --populate seclegion" in code
    # order: -Syuw with the stripped conf, the repo copy, the key, the build conf, then mkarchiso
    order = [
        code.index(s)
        for s in (
            "-Syuw",
            'cp --no-preserve=ownership -- "$seclegion_repo"/*',
            "pacman-key --populate seclegion",
            "sl_build_conf",
            "mkarchiso -v",
        )
    ]
    assert order == sorted(order)
    assert "--config /work/profile/pacman.conf" not in code
    # the runtime copy (with the live path) is installed into the airootfs BEFORE the build rewrite
    assert code.index("airootfs/etc/pacman.conf") < code.index("sl_build_conf /work")


# ---- every command the airootfs runs is provided by a listed package -----------------------

AIROOTFS = PROFILE / "airootfs"
# command -> package that ships it. Extend this table when a unit or script starts a new command.
COMMAND_PACKAGE = {
    "cage": "cage",
    "foot": "foot",
    "regreet": "greetd-regreet",
    "greetd": "greetd",
    "Hyprland": "hyprland",
    "hypridle": "hypridle",
    "hyprlock": "hyprlock",
    "chvt": "util-linux",
    "agetty": "util-linux",
    "mount": "util-linux",
    "sudo": "sudo",
    "pacman-key": "pacman",
    "journalctl": "systemd",
    "systemctl": "systemd",
    "systemd-networkd-wait-online": "systemd",
    "sleep": "coreutils",
    "mkdir": "coreutils",
    "chmod": "coreutils",
    "echo": "coreutils",
    "install": "coreutils",
    "printf": "coreutils",
}
# Local files shipped by the airootfs itself.
LOCAL_COMMANDS = {
    "choose-mirror",
    "livecd-sound",
    "Installation_guide",
    "run",
    "error",
    "seclegion-selftest",
    "seclegion-live-session",
}
# Reached through the dependency closure of `base`, which base.list lists.
BASE_CLOSURE = {"pacman", "systemd", "coreutils", "sh", "bash"}
SHELL_WORDS = {
    "exec",
    "sh",
    "-c",
    "if",
    "then",
    "fi",
    "do",
    "done",
    "for",
    "while",
    "case",
    "esac",
    "set",
    "exit",
    "cd",
    "export",
    "[",
    "test",
    "true",
    "false",
    "read",
    "local",
    "return",
}


def referenced_commands() -> set[str]:
    """Commands named in airootfs unit Exec lines, the greetd config and the scripts it ships."""
    found: set[str] = set()
    for unit in (AIROOTFS / "etc" / "systemd" / "system").rglob("*"):
        if unit.is_symlink() or unit.suffix not in (".service", ".conf"):
            continue  # stock units are symlinks into packages
        for line in unit.read_text().splitlines():
            m = re.match(r"Exec\w*=[-+@!:]*(\S+)(?:\s+(.*))?", line)
            if m and m.group(1):
                found.add(Path(m.group(1)).name)
                # `sh -c '<cmd> ...'`: the first word of the quoted command
                q = re.match(r"-c\s+'\s*(\S+)", m.group(2) or "")
                if q:
                    found.add(Path(q.group(1)).name)
    greetd = AIROOTFS / "etc" / "greetd" / "config.toml"
    if greetd.exists():
        for m in re.finditer(r'^command\s*=\s*"([^"]+)"', greetd.read_text(), re.MULTILINE):
            found.add(Path(m.group(1).split()[0]).name)
    for script in (AIROOTFS / "usr" / "share" / "seclegion" / "kiosk").glob("*"):
        for line in script.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or re.match(r"\w+=", line):
                continue
            m = re.match(r"(?:exec\s+)?([A-Za-z][\w+.-]*)", line)
            if m:
                found.add(m.group(1))
            for m in re.finditer(r"(?:\s--\s+|\|\s*)([A-Za-z][\w+.-]*)", line):
                found.add(m.group(1))
    sudoers = AIROOTFS / "etc" / "sudoers.d"
    if sudoers.is_dir() and any(sudoers.iterdir()):
        found.add("sudo")
    return {c for c in found if c and not c.startswith("$")} - SHELL_WORDS


def all_listed() -> set[str]:
    return {p for n in ("base", "live", "desktop") for p in read_list(LISTS / f"{n}.list")}


def test_lists_cover_every_command_the_airootfs_runs():
    listed = all_listed()
    refs = referenced_commands()
    # the scan sees something (foot was only the kiosk placeholder's client; install is the polkit unit's)
    assert {"cage", "install", "chvt", "agetty", "pacman-key"} <= refs, refs
    unknown = sorted(c for c in refs - LOCAL_COMMANDS if c not in COMMAND_PACKAGE)
    assert unknown == [], f"classify in COMMAND_PACKAGE or LOCAL_COMMANDS: {unknown}"
    missing = sorted(
        f"{c} (package {COMMAND_PACKAGE[c]})"
        for c in refs - LOCAL_COMMANDS
        if COMMAND_PACKAGE[c] not in listed and COMMAND_PACKAGE[c] not in BASE_CLOSURE
    )
    assert missing == []


def test_lists_cover_the_greeter_and_the_live_user_packages():
    listed = all_listed()
    assert {"sudo", "foot", "util-linux", "cage", "greetd", "greetd-regreet", "hyprland"} <= listed
    assert "base" in listed  # BASE_CLOSURE relies on it


def test_build_drops_stale_seclegion_packages_from_the_reused_pkgcache():
    """A [seclegion] package left in the host pkgcache by an earlier build has the old throwaway key's
    signature; the ISO build must remove exactly this repo's file names before mkarchiso installs."""
    text = (REPO / "tools" / "container-build.sh").read_text()
    populate = text.index("pacman-key --populate seclegion")
    loop = text.index('for f in "$seclegion_repo"/*.pkg.tar.zst; do')
    assert populate < loop < text.index("mkarchiso -v")
    assert 'rm -f -- "/var/cache/pacman/pkg/${f##*/}" "/var/cache/pacman/pkg/${f##*/}.sig"' in text
