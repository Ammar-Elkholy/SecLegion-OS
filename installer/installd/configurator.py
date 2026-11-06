# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""SecLegion install configurator (I1): answers + disk facts -> archinstall JSON.

Pure functions; no disk access. Format source (read only, nothing executed):
  https://archinstall.archlinux.page/installing/guided.html
  https://raw.githubusercontent.com/archlinux/archinstall/4.5/examples/config-sample.json
  https://raw.githubusercontent.com/archlinux/archinstall/4.5/examples/creds-sample.json
  https://raw.githubusercontent.com/archlinux/archinstall/4.5/archinstall/lib/models/device.py
Tag 4.5 (note: the sample files at that tag are stale, version 2.8.6; keys for
uki, disk_encryption, subvolumes come from guided.html and device.py).
The creds file holds plaintext passwords because archinstall needs them; I2
deletes it (tmpfs, 0600) right after archinstall exits.
"""
import json
import os
import re
import uuid
from dataclasses import dataclass, field

import winguide

GIB = 1 << 30
MIB = 1 << 20
MIN_GAP = 40 * GIB
MIN_DISK = 20 * GIB  # erase: the system needs ~6 GiB; the rest is room for snapshots and updates
ESP_SIZE = GIB
_NS = uuid.UUID("5ec1e610-0000-4000-8000-000000000001")
SUBVOLS = [("@", "/"), ("@home", "/home"), ("@log", "/var/log"),
           ("@pkg", "/var/cache/pacman/pkg"), ("@.snapshots", "/.snapshots")]
ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
_WINDOWS_PARTTYPES = ("e3c9e316-0b5c-4db8-817d-f92df00215ae",  # Microsoft reserved (MSR)
                      "de94bba4-06d1-4d40-a16a-bfd50179d6ac")  # Windows recovery
_FS = {"vfat": "fat32", "ntfs": "ntfs", "ext4": "ext4", "btrfs": "btrfs",
       "xfs": "xfs", "crypto_LUKS": "crypto_LUKS", "swap": "linux-swap"}


class Refusal(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class Answers:
    disk: str
    username: str
    password: str = field(repr=False)
    confirm: str = ""
    mode: str = "erase"
    luks: bool | None = None
    partition: str | None = None
    luks_passphrase: str | None = field(default=None, repr=False)
    hostname: str = "seclegion"
    timezone: str | None = None
    keyboard: str = "us"
    keyboard_extra: tuple = ()
    locale: str = "en_US.UTF-8"

    def __post_init__(self):
        if self.mode not in ("erase", "erase-luks", "alongside", "partition"):
            raise Refusal("bad_mode", "mode must be erase, erase-luks, alongside or partition")
        if self.mode == "partition" and not self.partition:
            raise Refusal("bad_partition", "partition mode needs the partition to replace")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", self.username or ""):
            raise Refusal("bad_username", "invalid username")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", self.hostname or ""):
            raise Refusal("bad_hostname", "invalid hostname")
        if not self.password:
            raise Refusal("bad_password", "password must not be empty")
        if self.timezone is None:
            self.timezone = default_timezone()
        self.keyboard_extra = tuple(self.keyboard_extra)

    @property
    def use_luks(self):
        if self.mode == "erase-luks":
            return True
        return self.luks if self.luks is not None else self.mode == "erase"

    @property
    def effective_mode(self):
        return self.mode if self.mode in ("alongside", "partition") else "erase"

    @property
    def passphrase(self):
        return self.luks_passphrase or self.password

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def default_timezone(link="/etc/localtime"):
    try:
        t = os.readlink(link)
        if "zoneinfo/" in t:
            return t.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return "UTC"


def valid_timezone(name, root="/usr/share/zoneinfo"):
    """True for a real zoneinfo name (a file under root, no path tricks)."""
    if not name or name.startswith("/") or ".." in name.split("/"):
        return False
    return os.path.isfile(os.path.join(root, name))


# ---- facts -----------------------------------------------------------------
# facts = {"install_mode": bool, "dev_build": bool, "boot_medium": "/dev/sdX",
#          "root_disk": "/dev/sdY" (optional), "by_id": {"/dev/disk/by-id/x": "/dev/sdX"},
#          "probes": {"/dev/sdX2": winguide.probe() result} (optional; NTFS/BitLocker partitions),
#          "lsblk": <output of lsblk -J -b -O>}

def _walk(node, skip=None):
    if skip and node.get("path") == skip:
        return  # the whole subtree is left out
    yield node
    for c in node.get("children") or []:
        yield from _walk(c, skip)


def find_disk(answers, facts):
    path = facts.get("by_id", {}).get(answers.disk, answers.disk)
    for d in facts["lsblk"]["blockdevices"]:
        if d.get("type") == "disk" and path in (d.get("path"), d.get("name")):
            return d
    raise Refusal("no_such_disk", "chosen disk not found")


def _mountpoints(disk, skip=None):
    """Mount points under disk; skip is the path of a partition whose subtree is left out."""
    out = []
    for n in _walk(disk, skip):
        out += [m for m in (n.get("mountpoints") or [n.get("mountpoint")]) if m]
    return out


def _sec(disk):
    return int(disk.get("log-sec") or 512)


def free_gaps(disk):
    """Aligned (start_bytes, size_bytes) gaps, in disk order."""
    sec = _sec(disk)
    total = int(disk["size"])
    parts = sorted((int(p["start"]) * sec, int(p["start"]) * sec + int(p["size"]))
                   for p in disk.get("children") or [] if p.get("type") == "part")
    hi, gaps, cur = total - MIB, [], MIB
    for s, e in parts:
        if s - cur >= MIB:
            gaps.append((cur, s))
        cur = max(cur, e)
    if hi - cur >= MIB:
        gaps.append((cur, hi))
    out = []
    for s, e in gaps:
        s = -(-s // MIB) * MIB
        e = e // MIB * MIB
        if e > s:
            out.append((s, e - s))
    return out


def _aligned_extent(part, sec):
    """(start, end) bytes of a partition, start aligned UP and end aligned DOWN to MiB."""
    start = int(part["start"]) * sec
    end = start + int(part["size"])
    return -(-start // MIB) * MIB, end // MIB * MIB


def _partition_refusal(part, sec):
    """Refusal code for replacing this partition, or None. Order matters; fail closed."""
    if _mountpoints(part):
        return "part_mounted"
    parttype = (part.get("parttype") or "").lower()
    fstype = (part.get("fstype") or "").lower()
    if parttype == ESP_GUID:
        return "part_is_esp"
    # exfat/refs: Windows or shared data volumes, never a partition prepared for Linux (fail closed)
    if fstype in ("ntfs", "bitlocker", "refs", "exfat") or parttype in _WINDOWS_PARTTYPES:
        return "part_is_windows"
    if not parttype and not fstype:
        return "part_unknown"
    start, end = _aligned_extent(part, sec)
    if end - start < MIN_DISK:
        return "part_too_small"
    return None


def partition_choices(disk, facts):
    """[(path, size bytes, refusal code or None)] for every partition of the disk, in disk order."""
    sec = _sec(disk)
    return [(p["path"], int(p["size"]), _partition_refusal(p, sec))
            for p in sorted((c for c in disk.get("children") or [] if c.get("type") == "part"),
                            key=lambda p: int(p["start"]))]


def _chosen_partition(answers, disk):
    """The lsblk node of the partition to replace; a direct part child of the disk only."""
    for p in disk.get("children") or []:
        if p.get("type") == "part" and p.get("path") == answers.partition:
            return p
    raise Refusal("no_such_partition", "the chosen partition is not on the chosen disk")


def validate(answers, facts, defer_unreadable=False):
    """Refuse an unsafe plan. defer_unreadable is for the unprivileged installer GUI only: a Windows partition
    it could not read stays open there (seclegion-install re-checks it as root, never deferring)."""
    if not facts.get("install_mode"):
        raise Refusal("not_install_mode", "not booted in install mode")
    if not valid_timezone(answers.timezone):
        raise Refusal("bad_timezone", "time zone is not a zoneinfo name")
    disk = find_disk(answers, facts)
    path = disk["path"]
    partition = answers.effective_mode == "partition"
    if facts.get("root_disk") == path or "/" in _mountpoints(disk):
        raise Refusal("root_disk", "disk holds the running root filesystem")
    if facts.get("boot_medium") == path:
        raise Refusal("boot_medium", "disk is the boot medium")
    # partition mode: the chosen partition's own mounts are reported as part_mounted below
    if _mountpoints(disk, answers.partition if partition else None):
        raise Refusal("mounted", "disk has mounted filesystems")
    if disk.get("pttype") == "dos":
        raise Refusal("mbr_disk", "MBR (dos) disks are not supported; GPT/UEFI only")
    if facts.get("dev_build"):
        who = f"{disk.get('vendor') or ''} {disk.get('model') or ''}".upper()
        if "QEMU" not in who:
            raise Refusal("dev_build_real_disk", "DEV build installs only to QEMU disks")
    if not partition:
        expected = (disk.get("model") or disk.get("name") or "").strip()
        if not expected or answers.confirm != expected:
            raise Refusal("confirm_mismatch", "typed disk name does not match")
    if answers.effective_mode not in ("alongside", "partition") and int(disk.get("size") or 0) < MIN_DISK:
        # refuse before anything is written: a too-small disk otherwise fails late, half installed (U5 G49)
        raise Refusal("disk_too_small", "the disk is under 20 GiB")
    if answers.effective_mode in ("alongside", "partition"):
        for part in disk.get("children") or []:
            probe = (facts.get("probes") or {}).get(part.get("path"))
            if probe is None and (part.get("fstype") or "").lower() in ("ntfs", "bitlocker"):
                probe = "unreadable"  # fail closed: a Windows partition nobody probed is not assumed clean
            if probe == "unreadable" and defer_unreadable:
                continue
            blocked = winguide.refusal_for(probe)
            if blocked:
                raise Refusal(*blocked)
    if partition:
        chosen = _chosen_partition(answers, disk)
        code = _partition_refusal(chosen, _sec(disk))
        if code:
            raise Refusal(code, f"{chosen['path']} cannot be replaced ({code})")
        if not chosen.get("name") or answers.confirm != chosen["name"]:
            raise Refusal("confirm_mismatch", "typed partition name does not match")
    if answers.effective_mode == "alongside":
        gaps = free_gaps(disk)
        if not gaps or max(g[1] for g in gaps) < MIN_GAP:
            if sum(g[1] for g in gaps) >= MIN_GAP:
                raise Refusal("gap_not_contiguous",
                              "enough free space but split across gaps; need one 40 GiB gap")
            raise Refusal("gap_too_small", "largest free gap is under 40 GiB")


# ---- config ----------------------------------------------------------------

def _u(value, unit, sec):
    return {"sector_size": {"unit": "B", "value": sec}, "unit": unit, "value": value}


def _oid(name):
    return str(uuid.uuid5(_NS, name))


def _existing(p, sec):
    flags = []
    if (p.get("parttype") or "").lower() == ESP_GUID:
        flags = ["boot", "esp"]
    return {"btrfs": [], "dev_path": p["path"], "flags": flags,
            "fs_type": _FS.get(p.get("fstype")), "mount_options": [],
            "mountpoint": None, "obj_id": _oid("existing:" + p["path"]),
            "size": _u(int(p["size"]), "B", sec),
            "start": _u(int(p["start"]) * sec, "B", sec),
            "status": "existing", "type": "primary"}


def build_config(answers, facts):
    validate(answers, facts)
    disk = find_disk(answers, facts)
    sec = _sec(disk)
    total = int(disk["size"])
    if answers.effective_mode == "alongside":
        start, size = max(free_gaps(disk), key=lambda g: g[1])
        parts = [_existing(p, sec) for p in sorted(
            disk.get("children") or [], key=lambda p: int(p["start"]))
            if p.get("type") == "part"]
        wipe = False
    elif answers.effective_mode == "partition":
        chosen = _chosen_partition(answers, disk)
        lo, hi = _aligned_extent(chosen, sec)
        start, size = lo, hi - lo
        parts = []
        for p in sorted(disk.get("children") or [], key=lambda p: int(p["start"])):
            if p.get("type") != "part":
                continue
            m = _existing(p, sec)
            if p is chosen:
                m["status"] = "delete"
            parts.append(m)
        wipe = False
    else:
        start, size = MIB, (total - 2 * MIB) // MIB * MIB
        parts, wipe = [], True
    esp = {"btrfs": [], "dev_path": None, "flags": ["boot", "esp"], "fs_type": "fat32",
           "mount_options": [], "mountpoint": "/boot", "obj_id": _oid("esp"),
           "size": _u(ESP_SIZE // MIB, "MiB", sec), "start": _u(start // MIB, "MiB", sec),
           "status": "create", "type": "primary"}
    root = {"btrfs": [{"name": n, "mountpoint": m} for n, m in SUBVOLS], "dev_path": None,
            "flags": [], "fs_type": "btrfs", "mount_options": ["compress=zstd"],
            "mountpoint": None, "obj_id": _oid("root"),
            "size": _u((size - ESP_SIZE) // MIB, "MiB", sec),
            "start": _u((start + ESP_SIZE) // MIB, "MiB", sec),
            "status": "create", "type": "primary"}
    dm = {"device": disk["path"], "wipe": wipe, "partitions": parts + [esp, root]}
    cfg = {
        "archinstall-language": "English",
        "bootloader_config": {"bootloader": "Systemd-boot", "uki": True, "removable": False},
        "custom_commands": [],
        "disk_config": {"config_type": "default_layout", "device_modifications": [dm]},
        "hostname": answers.hostname,
        "kernels": ["linux"],
        "locale_config": {"kb_layout": answers.keyboard, "sys_enc": "UTF-8",
                          "sys_lang": answers.locale},
        "network_config": {"type": "nm"},
        "ntp": True,
        "offline": True,
        "packages": [],
        "profile_config": {"gfx_driver": None, "greeter": None,
                           "profile": {"details": [], "main": "Minimal"}},
        "script": "guided",
        "swap": {"enabled": True, "algorithm": "zstd"},
        "timezone": answers.timezone,
    }
    creds = {"users": [{"username": answers.username, "!password": answers.password,
                        "sudo": True}]}
    if answers.use_luks:
        # archinstall 4.5 (read in the VM): disk_encryption nests in disk_config, the password
        # is the top-level creds key "encryption_password" (an empty one raises ValueError).
        cfg["disk_config"]["disk_encryption"] = {"encryption_type": "luks", "lvm_volumes": [],
                                                 "partitions": [root["obj_id"]]}
        creds["encryption_password"] = answers.passphrase
    return cfg, creds


def post_hints(answers):
    """Non-secret extras for the post step (archinstall has one kb_layout only)."""
    hints = {"keyboard_extra": list(answers.keyboard_extra), "username": answers.username}
    if answers.effective_mode in ("alongside", "partition"):
        hints["alongside"] = True  # seclegion-post then looks for a Windows ESP (winboot.py)
    return hints


def write(config, creds, outdir, hints=None):
    os.makedirs(outdir, exist_ok=True)
    files = {"user_configuration.json": config, "user_credentials.json": creds}
    if hints is not None:
        files["seclegion-post.json"] = hints
    paths = []
    for name, data in files.items():
        p = os.path.join(outdir, name)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.chmod(p, 0o600)
        paths.append(p)
    return paths


def summary(config, answers):
    dm = config["disk_config"]["device_modifications"][0]
    wipe = "wipe whole disk" if dm["wipe"] else "free space only"
    if answers.effective_mode == "partition":
        wipe = f"replace {answers.partition}"
    kb = config["locale_config"]["kb_layout"]
    if answers.keyboard_extra:
        kb += " (+" + ",".join(answers.keyboard_extra) + ")"
    return "\n".join([
        f"Disk:       {dm['device']} ({wipe})",
        f"Mode:       {answers.effective_mode}, LUKS2: {'yes' if answers.use_luks else 'no'}",
        f"Hostname:   {config['hostname']}",
        f"User:       {answers.username}",
        f"Timezone:   {config['timezone']}",
        f"Keyboard:   {kb}",
        f"Locale:     {config['locale_config']['sys_lang']}",
        "Filesystem: btrfs (@, @home, @log, @pkg, @.snapshots), systemd-boot + UKI"])


def dry_run(config, answers, outdir, out=print):
    out(summary(config, answers))
    out(f"Would run: archinstall --config {os.path.join(outdir, 'user_configuration.json')} "
        f"--creds {os.path.join(outdir, 'user_credentials.json')} --silent")
