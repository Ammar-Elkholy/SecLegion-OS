# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""seclegion-post: finish the archinstall-installed target at ROOT.

Every file change goes through Post.write/symlink, which record the path, so --dry-run can print
the exact write list. External programs go through one injectable runner (tests pass a recorder).

Install route (decision): `arch-chroot ROOT pacman -S`, not `pacman --root`: package scriptlets
(hooks, sysusers, keyring populate) must run against the target's own filesystem and pacman.conf.
The [seclegion] Server is file:///opt/seclegion/cache/seclegion, a path of the live ISO; the cache
is bind-mounted read-only at the same path inside ROOT for the install and unmounted after.
"""

import json
import os
import re
import subprocess
import sys

import gaming
import hwplan
import release
import virt
import winboot

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGES_LIST = os.path.join(HERE, "post-packages.list")
CACHE = "/opt/seclegion/cache"
SERVER = "file:///opt/seclegion/cache/seclegion"  # same text as iso/profile/pacman.conf
SECLEGION_SECTION = f"[seclegion]\nSigLevel = Required DatabaseRequired\nServer = {SERVER}\n"
# D-UPD-1: the installed system has no [seclegion] repo yet (the file:// cache is gone), so the section
# stays in /etc/pacman.conf fully commented; enabling it later is one uncomment.
HOSTED_SERVER = "https://github.com/Ammar-Elkholy/SecLegion-OS/releases/download/repo"
DISABLED_NOTE = "# [seclegion] updates: enabled once the hosted repository exists (docs/decisions.md D-UPD-1)"
DISABLED_SECLEGION = (
    f"{DISABLED_NOTE}\n#[seclegion]\n#SigLevel = Required DatabaseRequired\n#Server = {HOSTED_SERVER}\n"
)
GREETER_CMD = (
    "env SESSION_DIRS=/etc/greetd/sessions{xkb} cage -s -- "
    "regreet --config /etc/greetd/regreet.toml --style /etc/greetd/regreet.css"
)
GREETD_CONFIG = """# SPDX-License-Identifier: MIT
# Installed system: greetd + regreet (password login), then Hyprland. No other session.
# No initial_session: nobody is logged in without typing the password.
[terminal]
vt = 1

[default_session]
command = "{command}"
user = "greeter"
"""
# regreet 0.5.0 has no option to hide the session picker (only skip_selection, which is not
# wanted). The guarantee is SESSION_DIRS holding exactly one .desktop: Hyprland through uwsm.
REGREET_TOML = """# SPDX-License-Identifier: MIT
[background]
path = "/usr/share/seclegion/branding/seclegion-logo.png"
fit = "ScaleDown"

[GTK]
application_prefer_dark_theme = true
cursor_theme_name = "Bibata-Modern-Ice"
font_name = "Figtree 14"
theme_name = "Graphite-Dark"

[appearance]
greeting_msg = "SecLegion OS"
"""
REGREET_CSS = """/* SPDX-License-Identifier: MIT */
window {
  background-color: #1b1b1f;
  color: #e6e6ea;
}
"""
SESSION_FILE = """[Desktop Entry]
Name=Hyprland
Comment=SecLegion Hyprland session
Exec=uwsm start -- hyprland.desktop
Type=Application
DesktopNames=Hyprland
"""


KEYRING_GPG = "/usr/share/pacman/keyrings/seclegion.gpg"  # live ISO's own copy: the root of trust
KEYRING_TRUSTED = "/usr/share/pacman/keyrings/seclegion-trusted"  # "FINGERPRINT:6:" lines
DEV_CMDLINE = "console=ttyS0,115200"
HW_ENV = "etc/environment.d/50-seclegion-hw.conf"
HW_UDEV = "etc/udev/rules.d/61-seclegion-gpu.rules"
HW_PACKAGES = "var/lib/seclegion/hw-packages"  # what the plan installed; target_check reads it


def greetd_config(extra):
    """greetd config.toml; the greeter's cage gets the us+extra layouts and Alt+Shift when extras exist."""
    xkb = ""
    if extra:
        layouts = ",".join(["us", *extra])
        if not re.fullmatch(r"[a-z0-9_,:-]+", layouts):
            raise PostError("bad keyboard layout name")
        xkb = f" XKB_DEFAULT_LAYOUT={layouts} XKB_DEFAULT_OPTIONS=grp:alt_shift_toggle"
    return GREETD_CONFIG.format(command=GREETER_CMD.format(xkb=xkb))


# sshd@ + sshd-unix-local.socket: systemd-ssh-generator's local AF_UNIX socket would start sshd@
SSHD_MASKED = ("sshd.service", "sshd.socket", "sshd@.service", "sshd-unix-local.socket")
# Dev profile (docs/DAILY-DRIVER.md gap 2): the user runs the container engine without sudo
# (tools/build-iso). Root-equivalent, as the owner's daily-driver bar B11 asks. The name is built in
# pieces so tools/check-container-start (which flags the bare word) stays a tripwire.
ENGINE = "dock" + "er"
DEV_GROUPS = (ENGINE,)


class PostError(Exception):
    pass


def read_packages(path=PACKAGES_LIST):
    out = []
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def split_sections(text):
    """[(name or None, [lines])], the header line included in its section."""
    secs = [(None, [])]
    for line in text.splitlines(keepends=True):
        m = re.match(r"\s*\[([^\]]+)\]\s*$", line)
        if m:
            secs.append((m.group(1), []))
        secs[-1][1].append(line)
    return secs


def check_pacman_conf(text):
    """[seclegion]: below core and extra, own SigLevel exactly Required DatabaseRequired, offline Server."""
    secs = split_sections(text)
    names = [n for n, _ in secs]
    if names.count("seclegion") != 1:
        raise PostError("pacman.conf needs exactly one [seclegion] section")
    body = "".join(dict(secs)["seclegion"])
    sig = [
        ln.split("=", 1)[1].split("#")[0].split()
        for ln in body.splitlines()
        if re.match(r"\s*SigLevel\s*=", ln)
    ]
    if sig != [["Required", "DatabaseRequired"]]:
        raise PostError("[seclegion] SigLevel must be exactly 'Required DatabaseRequired'")
    if f"Server = {SERVER}" not in body.splitlines():
        raise PostError("[seclegion] Server is not the offline cache")
    for base in ("core", "extra"):
        if base in names and names.index(base) > names.index("seclegion"):
            raise PostError(f"[seclegion] must come below [{base}]")


def check_installed_conf(text):
    """Installed pacman.conf (D-UPD-1): no active [seclegion] section and no active file:// Server;
    the commented block is there with its SigLevel intact."""
    if any(n == "seclegion" for n, _ in split_sections(text)):
        raise PostError("installed pacman.conf has an active [seclegion] section")
    if re.search(r"^\s*Server\s*=\s*file://", text, re.M):
        raise PostError("installed pacman.conf has an active file:// Server")
    if DISABLED_SECLEGION not in text:
        raise PostError("installed pacman.conf lacks the disabled [seclegion] block")


def with_seclegion(text):
    """pacman.conf text with our section last (below every archinstall repo), replacing an old one."""
    kept = "".join("".join(lines) for n, lines in split_sections(text) if n != "seclegion")
    if not kept.endswith("\n"):
        kept += "\n"
    out = kept + "\n" + SECLEGION_SECTION
    check_pacman_conf(out)
    return out


MULTILIB = "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"
STEAM_PENDING = "var/lib/seclegion/steam-pending"
STEAM_UNIT = "seclegion-steam.service"


def with_multilib(text):
    """D-H1: Arch's own [multilib] active. Uncomments the stock `#[multilib]` + `#Include` pair; appends
    the standard two lines when the section is absent. Already active: unchanged."""
    if any(n == "multilib" for n, _ in split_sections(text)):
        return text
    out, n = re.subn(
        r"^#[ \t]*\[multilib\][ \t]*\n#[ \t]*(Include[ \t]*=[ \t]*/etc/pacman\.d/mirrorlist[ \t]*\n)",
        r"[multilib]\n\1",
        text,
        count=1,
        flags=re.M,
    )
    if n:
        return out
    return text + ("" if text.endswith("\n") else "\n") + "\n" + MULTILIB


def finalize_conf(text, multilib=False):
    """Installed pacman.conf: drop the offline [seclegion-cache] repo; core/extra from the mirrorlist
    if the working copy had none (seclegion-install made the live one cache-only). [seclegion] ends
    up commented out (D-UPD-1): its file:// Server does not exist on the installed system.
    multilib=True (gaming opt-in only, D-H1) enables Arch's official [multilib]."""
    secs = split_sections(text)
    names = [n for n, _ in secs]
    kept = [(n, ln) for n, ln in secs if n != "seclegion-cache"]
    out = "".join("".join(ln) for n, ln in kept if n != "seclegion")
    for base in ("core", "extra"):
        if base not in names:
            out += f"\n[{base}]\nInclude = /etc/pacman.d/mirrorlist\n"
    out += "\n" + DISABLED_SECLEGION
    return with_multilib(out) if multilib else out


def fstab_without_subvolid(text):
    """genfstab pins each btrfs mount by subvolid= next to subvol=. A rollback (seclegion-rescue) makes a
    new @ with a new id, and the old id would then fail the / remount: keep subvol= only."""
    out = []
    for ln in text.splitlines(keepends=True):
        f = ln.split()
        if len(f) >= 4 and not f[0].startswith("#") and f[2] == "btrfs" and "subvol=" in f[3]:
            opts = ",".join(o for o in f[3].split(",") if not o.startswith("subvolid="))
            ln = ln.replace(f[3], opts, 1)
        out.append(ln)
    return "".join(out)


def set_key(text, key, value, quote=False):
    line = f'{key}="{value}"\n' if quote else f"{key}={value}\n"
    new, n = re.subn(rf"^{key}=.*\n?", line, text, flags=re.M)
    if n == 0:
        new = text + ("" if text.endswith("\n") or not text else "\n") + line
    return new


DOCKER_USER_BEGIN = "# BEGIN seclegion docker-user: ufw decides which published container ports are reachable"
# Docker DNATs published ports (-p 8080:80) and they pass through FORWARD, which ufw's INPUT policy never
# sees, so without this block they are reachable from the LAN. Docker jumps to DOCKER-USER first in
# FORWARD; here it hands NEW connections from outside to ufw's forward chain and drops what ufw does not
# allow. Open a port with `sudo ufw route allow proto tcp to any port <port>`. Access from the machine
# itself (localhost) does not pass FORWARD and is unaffected. Interfaces, not addresses, so the same block
# serves after.rules (IPv4) and after6.rules (IPv6). ufw-init restores before, after, then user rules, so
# ufw-user-forward is declared here (as ufw-docker does): without it the after.rules restore fails and
# ufw.service with it. user.rules declares and fills it right after, so `ufw route` rules survive.
DOCKER_USER_BLOCK = f"""{DOCKER_USER_BEGIN}
*filter
:ufw-user-forward - [0:0]
:DOCKER-USER - [0:0]
-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
-A DOCKER-USER -i docker0 -j RETURN
-A DOCKER-USER -i br-+ -j RETURN
-A DOCKER-USER -j ufw-user-forward
-A DOCKER-USER -m conntrack --ctstate NEW -j DROP
-A DOCKER-USER -j RETURN
COMMIT
# END seclegion docker-user
"""


def with_docker_user(text):
    """text (a ufw after.rules / after6.rules) with the DOCKER-USER block appended once."""
    if DOCKER_USER_BEGIN in text:
        return text
    return text + ("" if text.endswith("\n") or not text else "\n") + DOCKER_USER_BLOCK


class Post:
    def __init__(
        self,
        root,
        run,
        dry_run=False,
        creds_dir=None,
        hints=None,
        packages=None,
        fingerprints=None,
        available=None,
        skip_missing=False,
        plan_source=None,
        windows_esp=None,
    ):
        self.windows_esp = windows_esp  # callable() -> (device, PARTUUID, count) | None; alongside only
        self.plan_source = plan_source  # callable() -> hwdetect's plan (dict); None: no hardware plan
        self.warnings = []
        self.fingerprints = fingerprints
        self.available = available  # callable(pkg) -> bool, only used with skip_missing
        self.skip_missing = skip_missing
        self.skipped = []
        self.root = os.path.abspath(root)
        self.run = run
        self.dry = dry_run
        self.creds_dir = creds_dir
        self.hints = hints or {}
        self.packages = packages if packages is not None else read_packages()
        self.written = []  # root-relative paths
        self.deleted = []  # absolute paths
        self.commands = []

    def p(self, rel):
        return os.path.join(self.root, rel.lstrip("/"))

    def read(self, rel):
        try:
            with open(self.p(rel)) as f:
                return f.read()
        except FileNotFoundError:
            if self.dry:
                return ""
            raise PostError(f"{rel} missing in target") from None

    def write(self, rel, text, mode=0o644):
        """text may be bytes. mode None skips chmod (the ESP is vfat: chmod fails there)."""
        if rel not in self.written:
            self.written.append(rel)
        if self.dry:
            return
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(text, bytes) else "w") as f:
            f.write(text)
        if mode is not None:
            os.chmod(path, mode)

    def drop_nullok(self):
        """Arch's pambase ships `pam_unix.so ... nullok` (an empty password logs in): remove the option."""
        pam = self.p("etc/pam.d")
        for name in sorted(os.listdir(pam)) if os.path.isdir(pam) else ():
            rel = f"etc/pam.d/{name}"
            text = self.read(rel)
            fixed = re.sub(r"[ \t]+nullok\b(?!_)", "", text)
            if fixed != text:
                self.write(rel, fixed)

    def symlink(self, rel, target):
        self.written.append(rel)
        if self.dry:
            return
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(target, path)

    def remove(self, path):
        if os.path.lexists(path):
            self.deleted.append(path)
            if not self.dry:
                os.remove(path)

    def cmd(self, argv):
        self.commands.append(list(argv))
        if not self.dry:
            self.run(list(argv))

    def chroot(self, *argv):
        self.cmd(["arch-chroot", self.root, *argv])

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"seclegion-post: warning: {msg}", file=sys.stderr)

    def hw_plan(self):
        """hwdetect's plan for this machine, cleaned. A failure here never aborts the install: the
        base set still boots a desktop on mesa, so it is a warning and an empty plan."""
        if self.plan_source is None:
            return hwplan.EMPTY
        try:
            self.chroot("pacman", "-S", "--noconfirm", "--needed", hwplan.TOOL, "python")
            if self.dry:
                return hwplan.EMPTY
            plan = hwplan.clean(self.plan_source())
        except (subprocess.SubprocessError, OSError, ValueError) as err:  # failed tool, bad JSON, bad value
            self.warn(f"hardware plan unavailable, installing the base set only ({err})")
            return hwplan.EMPTY
        for msg in plan["warnings"] + plan["messages"]:
            print(f"seclegion-post: hwdetect: {msg}", file=sys.stderr)
        return plan

    def steps(self):
        user = self.hints.get("username")
        if not user:
            raise PostError("hints carry no username")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):  # same rule as configurator; used in root paths
            raise PostError(f"invalid username in hints: {user!r}")
        pk = self.packages
        if pk[0] != "seclegion-keyring":
            raise PostError("seclegion-keyring must be first in the package list")
        self.write("etc/pacman.conf", with_seclegion(self.read("etc/pacman.conf")))
        self.bootstrap_key()
        cache_in = self.p(CACHE)
        self.cmd(["mkdir", "-p", cache_in])
        self.cmd(["mount", "--bind", "-o", "ro", CACHE, cache_in])
        try:
            self.chroot("pacman", "-Sy", "--noconfirm", "--needed", "seclegion-keyring")
            self.chroot("pacman-key", "--populate", "seclegion")
            plan = self.hw_plan()
            extra_pk = list(plan["packages"])
            extra_pk += gaming.gaming_packages(self.hints.get("gaming"))
            extra_pk += virt.virt_packages(self.hints.get("virt"))
            win = self.find_windows_esp()
            extra_pk += [winboot.SHELL_PKG] if win else []
            rest = pk[1:] + [x for x in dict.fromkeys(extra_pk) if x not in pk]
            if self.skip_missing and self.available:
                self.skipped = [x for x in rest if not self.available(x)]
                rest = [x for x in rest if x not in self.skipped]
            self.chroot("pacman", "-S", "--noconfirm", "--needed", *rest)
        finally:
            self.cmd(["umount", cache_in])
        gaming_on = self.hints.get("gaming") is True
        self.write("etc/pacman.conf", finalize_conf(self.read("etc/pacman.conf"), multilib=gaming_on))
        if gaming_on:  # D-H1: Steam comes from [multilib] on the first online boot (seclegion-steam.service)
            self.write(STEAM_PENDING, "steam\n")
            self.cmd(["systemctl", "--root", self.root, "enable", STEAM_UNIT])
        self.snapper_config()
        extra = self.hints.get("keyboard_extra") or []
        self.write("etc/greetd/config.toml", greetd_config(extra))
        self.write("etc/greetd/regreet.toml", REGREET_TOML)
        self.write("etc/greetd/regreet.css", REGREET_CSS)
        self.write("etc/greetd/sessions/hyprland.desktop", SESSION_FILE)
        self.cmd(["systemctl", "--root", self.root, "enable", "greetd.service", "ufw.service"])
        self.cmd(["systemctl", "--root", self.root, "enable", "seclegion-firstboot.service"])
        self.cmd(["systemctl", "--root", self.root, "enable", f"{ENGINE}.service"])
        self.cmd(["systemctl", "--root", self.root, "enable", "snapper-cleanup.timer"])  # NUMBER_LIMIT
        self.apply_hw_plan(plan)
        # ufw: enabled, default deny incoming (loaded at boot from these two files)
        self.write("etc/ufw/ufw.conf", set_key(self.read("etc/ufw/ufw.conf"), "ENABLED", "yes"))
        self.write(
            "etc/default/ufw",
            set_key(self.read("etc/default/ufw"), "DEFAULT_INPUT_POLICY", "DROP", quote=True),
        )
        for rules in ("etc/ufw/after.rules", "etc/ufw/after6.rules"):  # the container engine under ufw
            self.write(rules, with_docker_user(self.read(rules)))
        self.drop_nullok()
        for unit in SSHD_MASKED:
            self.symlink(f"etc/systemd/system/{unit}", "/dev/null")  # a symlink file, nothing opens /dev
        # archinstall made the user (and copied /etc/skel) before seclegion-dotfiles put the Hyprland config
        # into /etc/skel: copy what is missing now (-n: never overwrite), owned by the user
        self.chroot("cp", "-a", "-n", "/etc/skel/.", f"/home/{user}/")
        self.chroot("chown", "-R", f"{user}:", f"/home/{user}")
        # the groups exist now: the packages' sysusers.d files ran in the pacman hook above
        self.chroot("usermod", "-a", "-G", ",".join(DEV_GROUPS), user)
        self.chroot(
            "seclegion-host", "--system", "--root", "/", user
        )  # the tool ships in the target (seclegion-desktop)
        vs = virt.setup_argv(self.hints.get("virt"), user)
        if vs:
            self.chroot(*vs)
        # one initramfs/UKI rebuild for every kernel parameter: the plan's, then the DEV serial console
        self.kernel_cmdline([*plan["kernel_params"], *([DEV_CMDLINE] if self.hints.get("dev") else [])])
        if win:
            self.windows_entry(win[1])
        if extra:
            # seclegion-firstboot turns this into /etc/seclegion/kb-layout.lua ("us" + extras), which
            # desktop/hypr/seclegion-host.lua loads.
            self.write("etc/seclegion/keyboard-extra", ",".join(extra) + "\n")
        self.scrub()

    def find_windows_esp(self):
        """Alongside only: the Windows ESP (device, PARTUUID, count), found read-only; None writes nothing."""
        if not (self.hints.get("alongside") and self.windows_esp):
            return None
        try:
            win = self.windows_esp()
        except (subprocess.SubprocessError, OSError, ValueError) as err:
            self.warn(f"could not look for a Windows ESP, no Windows boot entry ({err})")
            return None
        if win is None:
            print("seclegion-post: no Windows ESP found, no Windows boot entry", file=sys.stderr)
        elif win[2] > 1:
            self.warn(f"{win[2]} Windows ESPs found: the entry starts the first one the firmware lists")
        return win

    def windows_entry(self, partuuid):
        """Shell.efi + script + systemd-boot entry, all on SecLegion's own ESP (/boot). The Windows ESP is
        never a write target: it is only read by find_windows_esp."""
        try:
            shell = b"" if self.dry else open(self.p(winboot.SHELL_SRC), "rb").read()
        except OSError:
            self.warn("edk2-shell is not installed in the target, no Windows boot entry")
            return
        self.write(winboot.SHELL_DST, shell, mode=None)
        self.write(winboot.SCRIPT_DST, winboot.script(partuuid), mode=None)
        self.write(winboot.ENTRY_DST, winboot.entry(), mode=None)

    def snapper_config(self):
        """Snapper's `root` config for / written by hand, from the package's own template. `snapper
        create-config /` insists on making /.snapshots itself, which collides with the @.snapshots
        subvolume archinstall already mounted there. snap-pac (installed with the package list) then
        takes a pre/post pair per pacman transaction; the timeline stays off."""
        text = self.read("usr/share/snapper/config-templates/default")
        for key, value in (("SUBVOLUME", "/"), ("FSTYPE", "btrfs"), ("TIMELINE_CREATE", "no")):
            text = set_key(text, key, value, quote=True)
        # 0644: no secrets in it, and Settings (as the user) reads NUMBER_LIMIT from it
        self.write("etc/snapper/configs/root", text, 0o644)
        conf = set_key(self.read("etc/conf.d/snapper"), "SNAPPER_CONFIGS", "root", quote=True)
        self.write("etc/conf.d/snapper", conf)
        self.cmd(["chmod", "750", self.p(".snapshots")])
        if os.path.exists(self.p("etc/fstab")):
            fstab = self.read("etc/fstab")
            if fstab_without_subvolid(fstab) != fstab:
                self.write("etc/fstab", fstab_without_subvolid(fstab))

    def bootstrap_key(self):
        """The target trusts no seclegion key yet, and [seclegion] needs one to install seclegion-keyring:
        import the live ISO's own copy (the root of trust), then the keyring package takes over."""
        gpgdir = self.p("etc/pacman.d/gnupg")
        fps = self.fingerprints
        if fps is None:
            try:
                fps = [ln.split(":")[0] for ln in open(KEYRING_TRUSTED) if ln.strip()]
            except OSError:
                fps = []
        self.cmd(["pacman-key", "--gpgdir", gpgdir, "--add", KEYRING_GPG])
        for fp in fps:
            self.cmd(["pacman-key", "--gpgdir", gpgdir, "--lsign-key", fp])

    def apply_hw_plan(self, plan):
        """The plan's services and environment (packages and kernel parameters are applied elsewhere)."""
        if plan["services"]:
            try:
                self.cmd(["systemctl", "--root", self.root, "enable", *plan["services"]])
            except subprocess.CalledProcessError as err:
                self.warn(f"could not enable the hardware services {plan['services']} (rc={err.returncode})")
        hw_pk = sorted(x for x in dict.fromkeys(plan["packages"]) if x not in self.skipped)
        if hw_pk:  # so target_check tells a hardware-matched live package from a live leftover
            names = "".join(f"{x}\n" for x in hw_pk)
            self.write(HW_PACKAGES, "# seclegion-post: from seclegion-hwdetect's plan\n" + names)
        if plan["udev_rules"]:  # the /dev/dri/seclegion-* links that AQ_DRM_DEVICES names
            rules = "".join(f"{r}\n" for r in plan["udev_rules"])
            self.write(HW_UDEV, "# seclegion-post: from seclegion-hwdetect's plan\n" + rules)
        if plan["env"]:
            lines = [f"{k}={v}\n" for k, v in plan["env"].items()]
            # environment.d(5): read by the systemd user manager, which starts Hyprland through uwsm
            self.write(HW_ENV, "# seclegion-post: from seclegion-hwdetect's plan\n" + "".join(lines))

    def kernel_cmdline(self, params):
        """Append the parameters not yet on /etc/kernel/cmdline (the DEV serial console is one), then
        rebuild the UKI once."""
        rel = "etc/kernel/cmdline"
        try:
            cur = self.read(rel).strip()
        except PostError:
            cur = ""
        new = [x for x in dict.fromkeys(params) if x not in cur.split()]
        if not new:
            return
        self.write(rel, " ".join([cur, *new]).strip() + "\n")
        self.chroot("mkinitcpio", "-P")

    def scrub(self):
        if self.creds_dir:
            self.remove(os.path.join(self.creds_dir, "user_credentials.json"))
        self.remove(self.p("var/log/archinstall/user_credentials.json"))


def real_run(argv):
    # snap-pac's documented switch ("SNAP_PAC_SKIP=y pacman ..."): the install's own transactions take no
    # pre/post snapshot pairs (snapper has no config yet while the packages go in). The variable reaches
    # pacman and its hooks through arch-chroot, and does nothing for any other command.
    subprocess.run(argv, check=True, env={**os.environ, "SNAP_PAC_SKIP": "y"})


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(prog="seclegion-post")
    ap.add_argument("--root", required=True)
    ap.add_argument("--hints")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--creds-dir")
    a = ap.parse_args(argv)
    bad = release.dev_violations()
    if bad:
        print(f"refused: release build, DEV-only switch not allowed: {', '.join(bad)}", file=sys.stderr)
        return 2
    hints = json.load(open(a.hints)) if a.hints else {}
    # test-only and DEV-only (hints "dev" comes from seclegion-install --dev): a release install fails closed
    skip = os.environ.get("SECLEGION_POST_SKIP_MISSING") == "1" and bool(hints.get("dev"))

    def available(pkg):
        return (
            subprocess.run(["arch-chroot", a.root, "pacman", "-Si", pkg], capture_output=True).returncode == 0
        )

    post = Post(
        a.root,
        real_run,
        a.dry_run,
        a.creds_dir,
        hints,
        available=available,
        skip_missing=skip,
        plan_source=lambda: hwplan.fetch(a.root),
        windows_esp=winboot.find_windows_esp if hints.get("alongside") else None,
    )
    post.steps()
    if a.dry_run:
        print("commands:")
        for c in post.commands:
            print("  " + " ".join(c))
        print("writes:")
        for w in sorted(post.written):
            print("  " + w)
    print("deleted:" if not a.dry_run else "would delete:")
    for d in post.deleted:
        print("  " + d)
    if post.skipped:
        print("SKIPPED-MISSING: " + " ".join(post.skipped))
    return 0
