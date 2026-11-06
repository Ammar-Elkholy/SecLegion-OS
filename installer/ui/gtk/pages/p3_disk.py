# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 3: disk + how to install. One card per disk (model, size, a map of its partitions); under the chosen
disk: erase it, use free space, or replace one partition. Owns disk, mode, luks and (partition mode only)
partition. Eligibility reuses configurator.validate, so the page never offers what the review step would
refuse; a partition that could not be identified is not selectable."""

import configurator as cfg

from .base import Page

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

    @property
    def luks(self):
        return self._luks if self._luks is not None else self.mode in ("erase", "partition")

    def set_disk(self, disk_id):
        if disk_id != self.disk:
            self.mode, self.partition, self._luks = "erase", None, None
        self.disk = disk_id

    def set_mode(self, mode):
        self.mode = mode
        self._luks = None

    def set_partition(self, path):
        self.partition = path
        self.mode = "partition"
        self._luks = None

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

    def fragment(self):
        out = {"disk": self.disk, "mode": self.mode, "luks": self.luks}
        if self.mode == "partition" and self.partition:
            out["partition"] = self.partition
        return out


def widget(page):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from diskmap import DiskMap, human
    from gi.repository import Adw, Gtk
    from view_util import page_box, switch_row, text_label

    box = page_box(page.title)
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
        radio_row, radio = option(first_radio, "Install to this disk", None if ok else d["reason"],
                                  "disk:" + d["id"], ok)
        if first_radio is None:
            first_radio = radio
        head.add(radio_row)
        card.append(head)
        entry = {"id": d["id"], "radio": radio, "map": dmap, "opts": []}
        if ok:
            dmap.set_sensitive(True)
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
            erase.connect("toggled", lambda b: b.get_active() and pick(page.set_mode, "erase"))
            free.connect("toggled", lambda b: b.get_active() and pick(page.set_mode, "alongside"))
            for g in (how, parts):
                card.append(g)
            entry.update(opts=[how, parts], erase=erase, free=free, rows=rows)
            radio.connect("toggled", lambda b, i=d["id"]: b.get_active() and pick(page.set_disk, i))
        else:
            dmap.set_sensitive(False)
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
                for g in e["opts"]:
                    g.set_visible(chosen)
                if "erase" not in e or not chosen:
                    continue
                if page.mode == "partition" and page.partition in e["rows"]:
                    e["rows"][page.partition].set_active(True)
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
