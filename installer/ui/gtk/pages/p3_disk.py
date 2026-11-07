# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 3: disk + how to install. One card per disk (model, size, a map of its partitions); under the chosen
disk: erase it, use free space, or replace one partition. Owns disk, mode, luks and (partition mode only)
partition. Eligibility reuses configurator.validate, so the page never offers what the review step would
refuse; a partition that could not be identified is not selectable."""

import configurator as cfg
from diskmap import human

from .base import Page

GIB = 1 << 30
MIB = 1 << 20
RECOVERY_GUID = "de94bba4-06d1-4d40-a16a-bfd50179d6ac"
MIN_FREE_ROW = GIB  # free gaps under this are not listed

MODES = {"erase": "Erase the whole disk",
         "alongside": "Install alongside an existing system (use free space)",
         "partition": "Replace one partition"}

# plain words for the reasons a disk, a partition or the free space cannot be used
DISK_REASON = {
    "boot_medium": "This is the USB stick or disc the installer started from.",
    "root_disk": "This disk holds the system that is running right now.",
    "mounted": "Something on this disk is in use (mounted). Unmount it or restart the installer.",
    "mbr_disk": "This disk uses the old MBR layout. SecLegion needs a GPT/UEFI disk.",
    "disk_too_small": "This disk is under 20 GiB, too small for SecLegion.",
    "not_install_mode": "The installer was not started in install mode.",
    "dev_build_real_disk": "This development build installs only to virtual (QEMU) disks.",
}
PART_REASON = {
    "part_mounted": "This partition is in use (mounted). Unmount it first.",
    "part_is_esp": "This is the EFI boot partition. Other systems on this disk need it.",
    "part_is_windows": "It holds Windows or shared data. Delete or shrink it in Windows Disk Management "
                       "first, leaving free space, then choose Use free space.",
    "part_unknown": "The installer could not tell what is on this partition, so it stays untouched.",
    "part_too_small": "It is smaller than 20 GiB, too small for SecLegion.",
}
GAP_REASON = {
    "gap_not_contiguous": "There is enough free space in total, but it is split into pieces. "
                          "One free block of 40 GiB or more is needed.",
    "gap_too_small": "No free space of 40 GiB or more. Shrink a partition in Windows Disk Management "
                     "to make room, or replace a partition instead.",
}
SHRINK_REASON = {
    "shrink_mounted": "This partition is in use (mounted). Unmount it first.",
    "shrink_boot_medium": "This is the USB stick or disc the installer started from.",
    "shrink_too_small": "There is not enough unused space in this partition to shrink it.",
    "bitlocker": "This partition is encrypted with BitLocker. Boot Windows, suspend BitLocker "
                 "protection (or decrypt the drive), shut down fully and restart the installer.",
    "windows_hibernated": "Windows is hibernated or Fast Startup is on. Boot Windows, turn off Fast "
                          "Startup (or run shutdown /s /t 0), then restart the installer.",
    "shrink_bad_partition": "The chosen partition is not on this disk or cannot be shrunk.",
    "shrink_bad_size": "The chosen size is not allowed for this partition. Choose another amount of space.",
    "shrink_fs_refused": "The partition could not be shrunk safely. In Windows, turn off Fast Startup, "
                         "run chkdsk, and free some space, then try again.",
}
# every plain-words reason by refusal code
REASONS = {**DISK_REASON, **PART_REASON, **GAP_REASON, **SHRINK_REASON}


def describe_partition(part):
    """What a partition (an lsblk node) is: Windows, EFI system, Linux, Recovery, Swap or Unknown."""
    parttype = (part.get("parttype") or "").lower()
    fstype = (part.get("fstype") or "").lower()
    if parttype == cfg.ESP_GUID:
        return "EFI system"
    if parttype == RECOVERY_GUID:
        return "Recovery"
    if fstype in ("ntfs", "bitlocker"):
        return "Windows"
    if fstype in ("ext4", "btrfs", "xfs"):
        return "Linux"
    if fstype == "swap":
        return "Swap"
    return "Unknown"


def analysis_rows(disk):
    """Read-only rows for the whole disk in disk order, whatever its eligibility:
    [{kind: part|free, path, name, label, fstype, size, what, start}]. Free gaps under 1 GiB are left out."""
    rows = []
    sec = int(disk.get("log-sec") or 512)
    for p in disk.get("children") or []:
        if p.get("type") != "part":
            continue
        rows.append({"kind": "part", "path": p.get("path"), "name": p.get("name") or "",
                     "label": p.get("label") or "", "fstype": p.get("fstype") or "",
                     "size": int(p["size"]), "what": describe_partition(p),
                     "start": int(p["start"]) * sec})
    for start, size in cfg.free_gaps(disk):
        if size >= MIN_FREE_ROW:
            rows.append({"kind": "free", "path": None, "name": "", "label": "", "fstype": "", "size": size,
                         "what": "Free space", "start": start})
    return sorted(rows, key=lambda r: r["start"])


def shrink_label(opt):
    """The partition's name for the user: its label, else Windows for NTFS/BitLocker, else the fs type."""
    fs = (opt.get("fstype") or "").lower()
    return opt.get("label") or ("Windows" if fs in ("ntfs", "bitlocker") else fs or "partition")


def shrink_bounds(opt):
    """(lo, hi, default) in bytes for the space given to SecLegion, whole GiB. hi < lo: no room."""
    lo = cfg.MIN_GAP
    hi = (opt["size"] - -(-opt["min_size"] // MIB) * MIB) // GIB * GIB
    default = min(100 * GIB, opt["size"] // 2 // GIB * GIB)
    return lo, hi, (max(lo, min(default, hi)) if hi >= lo else lo)


def shrunk_size(opt, space):
    """The partition's new size in bytes (MiB multiple) after giving `space` bytes to SecLegion."""
    return max(0, opt["size"] - space) // MIB * MIB


def _model_name(disk):
    return (disk.get("model") or disk.get("name") or "").strip()


def partition_name(disk, path):
    """The kernel name of the partition at path (what the user types to confirm), or None."""
    for p in disk.get("children") or []:
        if p.get("type") == "part" and p.get("path") == path:
            return p.get("name") or None
    return None


def disk_problem(disk_id, mode, facts, partition=None):
    """Refusal for disk_id under mode via configurator.validate (confirm filled in), else None."""
    try:
        disk = cfg.find_disk(cfg.Answers(disk=disk_id, username="x", password="x"), facts)
        confirm = (partition_name(disk, partition) or "") if mode == "partition" else _model_name(disk)
        a = cfg.Answers(disk=disk_id, username="x", password="x", mode=mode, confirm=confirm,
                        partition=partition)
        cfg.validate(a, facts, defer_unreadable=True)  # the root-side run in seclegion-install checks
    except cfg.Refusal as r:
        return r
    return None


def list_disks(facts):
    """[{id, path, model, label, size, problem, code, reason}] for every disk; id is the by-id link."""
    by_path = {}
    for link, path in sorted(facts.get("by_id", {}).items()):
        by_path.setdefault(path, link)
    out = []
    for d in facts["lsblk"]["blockdevices"]:
        if d.get("type") != "disk":
            continue
        disk_id = by_path.get(d["path"], d["path"])
        prob = disk_problem(disk_id, "erase", facts)
        gib = int(d["size"]) / (1 << 30)
        out.append({"id": disk_id, "path": d["path"], "size": int(d["size"]), "model": _model_name(d),
                    "label": f"{_model_name(d)} ({gib:.0f} GiB) {d['path']}",
                    "problem": prob.message if prob else None, "code": prob.code if prob else None,
                    "reason": DISK_REASON.get(prob.code, prob.message) if prob else None})
    return out


class DiskPage(Page):
    key = "disk"
    title = "Where to install"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.disk = None
        self.mode = "erase"
        self.partition = None  # /dev path, meaningful in partition mode only
        self._luks = None  # None = default for the mode (D11/G7: on for erase and partition)
        self.shrink_on = False  # mode alongside via "shrink a partition" instead of free space
        self.shrink_path = None  # the partition to shrink
        self.shrink_space = None  # bytes for SecLegion; None = the default for the partition
        self.message = ""  # why the choice was cleared (the disk changed under a retry)

    @property
    def luks(self):
        return self._luks if self._luks is not None else self.mode in ("erase", "partition")

    def reset(self, message=""):
        """Forget the choice (disk, mode, partition, encryption) and show `message` on the page."""
        self.disk, self.mode, self.partition, self._luks = None, "erase", None, None
        self._clear_shrink()
        self.message = message

    def disk_path(self, facts):
        """The /dev path of the chosen disk in `facts` (its by-id link resolved)."""
        return facts.get("by_id", {}).get(self.disk, self.disk)

    def set_disk(self, disk_id):
        if disk_id != self.disk:
            self.mode, self.partition, self._luks = "erase", None, None
            self._clear_shrink()
        self.disk = disk_id
        self.message = ""

    def set_mode(self, mode):
        self.mode = mode
        self._luks = None
        self.shrink_on = False

    def set_partition(self, path):
        self.partition = path
        self.mode = "partition"
        self._luks = None
        self.shrink_on = False

    def _clear_shrink(self):
        self.shrink_on, self.shrink_path, self.shrink_space = False, None, None

    @staticmethod
    def shrink_supported():
        """False on a base without configurator.shrink_choices: the option is then hidden."""
        return getattr(cfg, "shrink_choices", None) is not None

    def shrink_options(self, disk_id=None):
        """[{path, name, fstype, label, size, min_size, max_size, code, reason, selectable, title}]."""
        if not self.shrink_supported():
            return []
        out = []
        for c in cfg.shrink_choices(self.disk_node(disk_id), self.ctx.facts):
            c = dict(c)
            c["title"] = shrink_label(c)
            c["selectable"] = c.get("code") is None
            c["reason"] = (REASONS.get(c["code"], f"This partition cannot be shrunk ({c['code']}).")
                           if c.get("code") else None)
            out.append(c)
        return out

    def shrink_option(self):
        """The option chosen for shrinking (or None)."""
        return next((o for o in self.shrink_options() if o["path"] == self.shrink_path), None)

    def set_shrink_mode(self):
        """Choose "shrink a partition": mode alongside; the first shrinkable partition is picked."""
        self.mode, self._luks, self.shrink_on = "alongside", None, True
        cur = self.shrink_option()
        if cur is None or not cur["selectable"]:
            first = next((o for o in self.shrink_options() if o["selectable"]), None)
            self.shrink_path = first["path"] if first else None
            self.shrink_space = None

    def set_shrink_partition(self, path):
        if path != self.shrink_path:
            self.shrink_path, self.shrink_space = path, None
        self.mode, self.shrink_on = "alongside", True

    def set_shrink_space(self, nbytes):
        self.shrink_space = int(nbytes)

    def shrink_amount(self):
        """Bytes for SecLegion, clamped to the chosen partition's bounds (None: nothing chosen)."""
        opt = self.shrink_option()
        if opt is None:
            return None
        lo, hi, default = shrink_bounds(opt)
        space = default if self.shrink_space is None else self.shrink_space
        return max(lo, min(hi, space // GIB * GIB)) if hi >= lo else None

    def shrink_new_size(self):
        opt, space = self.shrink_option(), self.shrink_amount()
        return None if opt is None or space is None else shrunk_size(opt, space)

    def shrink_summary(self):
        """"SecLegion: 100 GiB · Windows: 400 GiB left" for the slider, or ""."""
        opt, space, new = self.shrink_option(), self.shrink_amount(), self.shrink_new_size()
        if opt is None or space is None:
            return ""
        return f"SecLegion: {human(space)} · {opt['title']}: {human(new)} left"

    def analysis(self, disk_id=None):
        """Read-only rows of the disk (analysis_rows), even when the disk is refused."""
        return analysis_rows(self.disk_node(disk_id))

    def set_luks(self, on):
        self._luks = bool(on)

    def disks(self):
        return list_disks(self.ctx.facts)

    def disk_node(self, disk_id=None):
        return cfg.find_disk(cfg.Answers(disk=disk_id or self.disk, username="x", password="x"),
                             self.ctx.facts)

    def partition_rows(self, disk_id=None):
        """[{path, name, size, fstype, code, reason, selectable}] in disk order, from partition_choices."""
        disk = self.disk_node(disk_id)
        nodes = {p.get("path"): p for p in disk.get("children") or []}
        out = []
        for path, size, code in cfg.partition_choices(disk, self.ctx.facts):
            out.append({"path": path, "name": nodes[path].get("name"), "size": size,
                        "fstype": nodes[path].get("fstype"), "code": code,
                        "reason": PART_REASON.get(code, f"This partition cannot be used ({code}).")
                        if code else None, "selectable": code is None})
        return out

    def free_option(self, disk_id=None):
        """{selectable, gaps: [(start, size)] of 40 GiB or more, reason when not selectable}."""
        disk_id = disk_id or self.disk
        gaps = [g for g in cfg.free_gaps(self.disk_node(disk_id)) if g[1] >= cfg.MIN_GAP]
        reason = None
        if not gaps:
            prob = disk_problem(disk_id, "alongside", self.ctx.facts)
            reason = GAP_REASON.get(prob.code if prob else None, GAP_REASON["gap_too_small"])
        return {"selectable": bool(gaps), "gaps": gaps, "reason": reason}

    def _partition_block(self):
        """winguide refusal (code, message) over the disk's Windows partitions this process could probe."""
        from .p4_alongside import partition_refusal
        return partition_refusal(self.disk_node(), self.ctx.facts)

    def guide(self):
        """Steps for a Windows finding that blocks partition mode (BitLocker, hibernation)."""
        from .p4_alongside import GUIDE
        if self.mode != "partition" or not self.disk:
            return []
        blocked = self._partition_block()
        return GUIDE.get(blocked[0], []) if blocked else []

    def error(self):
        if self.mode not in MODES:
            return "Choose how to install."
        if not self.disk:
            return "Choose a disk."
        prob = disk_problem(self.disk, "erase", self.ctx.facts)
        if prob:
            return f"This disk cannot be used: {prob.message}."
        if self.mode == "alongside" and self.shrink_on:
            return self._shrink_error()
        if self.mode != "partition":
            return None
        if not self.partition:
            return "Choose the partition to replace."
        row = next((r for r in self.partition_rows() if r["path"] == self.partition), None)
        if row is None:
            return "The chosen partition is not on this disk."
        if not row["selectable"]:
            return row["reason"]
        blocked = self._partition_block()
        if blocked:
            return f"{blocked[1]}."
        prob = disk_problem(self.disk, "partition", self.ctx.facts, self.partition)
        return f"This partition cannot be used: {prob.message}." if prob else None

    def _shrink_error(self):
        opt = self.shrink_option()
        if self.shrink_path is None or opt is None:
            return "Choose the partition to shrink."
        if not opt["selectable"]:
            return opt["reason"]
        if self.shrink_amount() is None:
            return REASONS["shrink_too_small"]
        return None

    def fragment(self):
        out = {"disk": self.disk, "mode": self.mode, "luks": self.luks}
        if self.mode == "partition" and self.partition:
            out["partition"] = self.partition
        if self.mode == "alongside" and self.shrink_supported():
            shrink = self.shrink_on and self._shrink_error() is None
            out["shrink"] = self.shrink_path if shrink else None
            out["shrink_size"] = self.shrink_new_size() if shrink else None
        return out


def analysis_group(page, disk_id):
    """Read-only rows (name, label, filesystem, size, what it is) for one disk, refused or not."""
    from gi.repository import Adw

    group = Adw.PreferencesGroup(title="What is on this disk")
    rows = page.analysis(disk_id)
    if not rows:
        group.add(Adw.ActionRow(title="Nothing: the disk is empty.", use_markup=False))
    for r in rows:
        if r["kind"] == "free":
            row = Adw.ActionRow(title="Free space", subtitle=human(r["size"]), use_markup=False)
            row.set_name(f"info:free:{r['start']}")
        else:
            title = r["name"] + (f"  ·  {r['label']}" if r["label"] else "")
            sub = " · ".join(x for x in (r["what"], r["fstype"], human(r["size"])) if x)
            row = Adw.ActionRow(title=title, subtitle=sub, use_markup=False)
            row.set_name("info:" + (r["path"] or r["name"]))
        group.add(row)
    return group


def shrink_widgets(page, disk_id, erase, option, pick, guard):
    """The "shrink a partition" option row and its group (partition choice + size slider), or None
    when the configurator cannot shrink."""
    from gi.repository import Adw, Gtk

    if not page.shrink_supported():
        return None
    opts = page.shrink_options(disk_id)
    row, radio = option(erase, "Install alongside: shrink a partition",
                        None if any(o["selectable"] for o in opts)
                        else "No partition on this disk can be shrunk right now.",
                        "shrink:" + disk_id, any(o["selectable"] for o in opts))
    group = Adw.PreferencesGroup(title="Shrink a partition",
                                 description="Choose the partition and how much space SecLegion gets.")
    radios, first = {}, None
    for o in opts:
        prow, btn = option(first, f"{o['name']}  ·  {o['title']}  ·  {human(o['size'])}", o["reason"],
                           "shrinkpart:" + o["path"], o["selectable"])
        first = first or btn
        radios[o["path"]] = btn
        btn.connect("toggled", lambda b, p=o["path"]: b.get_active() and pick(page.set_shrink_partition, p))
        group.add(prow)
    adj = Gtk.Adjustment(value=40, lower=40, upper=41, step_increment=1, page_increment=10)
    scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj, hexpand=True, draw_value=False)
    scale.set_name("shrinkscale:" + disk_id)
    label = Gtk.Label(xalign=0, wrap=True)
    label.set_name("shrinklabel:" + disk_id)
    holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10, margin_bottom=10,
                     margin_start=10, margin_end=10)
    holder.append(Gtk.Label(label="Space for SecLegion", xalign=0))
    holder.append(scale)
    holder.append(label)
    srow = Adw.PreferencesRow(activatable=False, selectable=False, focusable=False)
    srow.set_child(holder)
    group.add(srow)

    def sync():
        opt = page.shrink_option()
        holder.set_visible(opt is not None and opt["selectable"])
        for path, btn in radios.items():
            btn.set_active(path == page.shrink_path)
        if opt is None or not opt["selectable"]:
            label.set_label(page.error() or "")
            return
        lo, hi, _d = shrink_bounds(opt)
        space = page.shrink_amount()
        scale.set_sensitive(hi > lo)
        adj.configure(space / GIB if space else lo / GIB, lo / GIB, max(hi, lo) / GIB, 1, 10, 0)
        label.set_label(page.shrink_summary())

    def moved(sc):
        if guard["busy"]:
            return
        page.set_shrink_space(round(sc.get_value()) * GIB)
        label.set_label(page.shrink_summary())
        page.notify()

    scale.connect("value-changed", moved)
    radio.connect("toggled", lambda b: b.get_active() and pick(page.set_shrink_mode))
    return {"row": row, "radio": radio, "group": group, "sync": sync}


def widget(page):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from diskmap import DiskMap
    from gi.repository import Adw, Gtk
    from view_util import page_box, switch_row, text_label

    box = page_box(page.title)
    if page.message:
        box.append(text_label(page.message, "error"))
    rescan = Gtk.Button(label="Rescan disks", halign=Gtk.Align.START)
    rescan.set_name("rescan")
    rescan.connect("clicked", lambda _b: page.ctx.rescan_disks())
    box.append(rescan)
    guard = {"busy": False}
    cards = []
    first_radio = None

    def pick(fn, *args):
        if guard["busy"]:
            return
        fn(*args)
        sync()
        page.notify()

    def option(group, title, reason, name, sensitive=True):
        """ActionRow with a radio prefix; a refused option is insensitive and says why as the subtitle."""
        btn = Gtk.CheckButton()
        btn.set_name(name)
        if group is not None:
            btn.set_group(group)
        btn.set_sensitive(sensitive)
        row = Adw.ActionRow(title=title, use_markup=False, sensitive=sensitive, activatable_widget=btn)
        if reason:
            row.set_subtitle(reason)
            row.set_subtitle_lines(0)
        row.add_prefix(btn)
        return row, btn

    for d in page.disks():
        node = page.disk_node(d["id"])
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        head = Adw.PreferencesGroup(title=d["model"] or d["path"],
                                    description=f"{human(d['size'])} · {d['path']}")
        head.set_name("card:" + d["id"])
        dmap = DiskMap(node)
        maprow = Adw.PreferencesRow(activatable=False, selectable=False, focusable=False)
        dmap.set_margin_top(10)
        dmap.set_margin_bottom(10)
        dmap.set_margin_start(10)
        dmap.set_margin_end(10)
        maprow.set_child(dmap)
        head.add(maprow)
        ok = not d["problem"]
        if not ok:
            why = text_label(d["reason"], "error")
            why.set_name("why:" + d["id"])
            card.append(why)
        head.add(analysis_group(page, d["id"]))
        radio_row, radio = option(first_radio, "Install to this disk", None if ok else d["reason"],
                                  "disk:" + d["id"], ok)
        if first_radio is None:
            first_radio = radio
        head.add(radio_row)
        card.append(head)
        entry = {"id": d["id"], "radio": radio, "map": dmap, "opts": []}
        if ok:
            how = Adw.PreferencesGroup(title="How to install")
            row, erase = option(None, "Erase this disk", "Everything on it is deleted.",
                                "erase:" + d["id"])
            how.add(row)
            fo = page.free_option(d["id"])
            title = "Use free space" + (f" ({human(max(g[1] for g in fo['gaps']))} free)"
                                         if fo["gaps"] else "")
            row, free = option(erase, title, fo["reason"], "free:" + d["id"], fo["selectable"])
            how.add(row)
            parts = Adw.PreferencesGroup(title="Or replace one partition",
                                         description="Everything else on the disk stays.")
            rows = {}
            for r in page.partition_rows(d["id"]):
                kind = human(r["size"]) + (f" · {r['fstype']}" if r["fstype"] else "")
                prow, btn = option(erase, f"{r['name']}  ·  {kind}", r["reason"], "row:" + r["path"],
                                   r["selectable"])
                rows[r["path"]] = btn
                btn.connect("toggled", lambda b, p=r["path"]: b.get_active() and pick(page.set_partition, p))
                parts.add(prow)
            shrink = shrink_widgets(page, d["id"], erase, option, pick, guard)
            if shrink:
                how.add(shrink["row"])
            erase.connect("toggled", lambda b: b.get_active() and pick(page.set_mode, "erase"))
            free.connect("toggled", lambda b: b.get_active() and pick(page.set_mode, "alongside"))
            parts.set_visible(bool(rows))  # nothing to replace: no empty heading
            for g in (how, shrink["group"] if shrink else None, parts):
                if g is not None:
                    card.append(g)
            entry.update(opts=[how, parts], parts=parts, erase=erase, free=free, rows=rows, shrink=shrink)
            if shrink:
                entry["opts"].append(shrink["group"])
            radio.connect("toggled", lambda b, i=d["id"]: b.get_active() and pick(page.set_disk, i))
        cards.append(entry)
        box.append(card)

    luks = switch_row("Encrypt the disk (LUKS2)", False,
                      lambda on: None if guard["busy"] else page.set_luks(on))
    box.append(luks)
    blocked = text_label("", "error")
    box.append(blocked)

    def sync():
        guard["busy"] = True
        try:
            for e in cards:
                chosen = e["id"] == page.disk
                e["radio"].set_active(chosen)
                shrink = e.get("shrink")
                for g in e["opts"]:
                    if shrink and g is shrink["group"]:
                        g.set_visible(chosen and page.mode == "alongside" and page.shrink_on)
                        continue
                    g.set_visible(chosen and (g is not e.get("parts") or bool(e["rows"])))
                if "erase" not in e or not chosen:
                    continue
                if page.mode == "partition" and page.partition in e["rows"]:
                    e["rows"][page.partition].set_active(True)
                elif page.mode == "alongside" and page.shrink_on and shrink:
                    shrink["radio"].set_active(True)
                    shrink["sync"]()
                elif page.mode == "alongside":
                    e["free"].set_active(True)
                else:
                    e["erase"].set_active(True)
                e["map"].set_selected(page.partition if page.mode == "partition" else None)
            luks.set_active(page.luks)
            steps = page.guide()
            err = page.error() if steps else None
            blocked.set_label((err + "\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
                              if err else "")
        finally:
            guard["busy"] = False

    sync()
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(box)
    return scroll
