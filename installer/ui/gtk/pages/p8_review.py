# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 8: review. Shows the exact command list from the configurator's dry run plus a summary.
Install is enabled only when the user has typed the disk's name (model, or name if no model; the
partition's kernel name in partition mode) and
configurator.validate passes; any Refusal is shown verbatim."""

import configurator as c
import release

from .base import Page

DRY_DIR = "/run/seclegion-install"  # display only: the real tmp dir is created by seclegion-install


class ReviewPage(Page):
    key = "review"
    title = "Review and confirm"
    next_label = "Install"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.typed = ""
        self.dev = False

    def set_typed(self, v):
        self.typed = v
        self.notify()

    def dev_options(self):
        return [] if release.is_release() else ["dev"]

    def set_dev(self, on):
        self.dev = bool(on) and not release.is_release()

    def dev_flags(self):
        return ["--dev"] if self.dev and not release.is_release() else []

    def answers_obj(self):
        return c.Answers.from_dict(self.ctx.answers())

    def expected(self):
        """The name the user must type: the disk model (erase, alongside) or the partition's kernel name
        (partition mode), exactly what configurator.validate compares. None when it cannot be resolved."""
        try:
            a = self.answers_obj()
            disk = c.find_disk(a, self.ctx.facts)
        except c.Refusal:
            return None
        if a.effective_mode == "partition":
            for p in disk.get("children") or []:
                if p.get("type") == "part" and p.get("path") == a.partition:
                    return (p.get("name") or "").strip() or None
            return None
        return (disk.get("model") or disk.get("name") or "").strip() or None

    def confirm_noun(self):
        """What the confirmation names: "partition" in partition mode, else "disk"."""
        return "partition" if self.ctx.pages["disk"].mode == "partition" else "disk"

    def _with_name(self):
        """Answers as if the right name were typed, so real refusals show before the user types."""
        d = self.ctx.answers()
        d["confirm"] = self.expected() or ""
        return c.Answers.from_dict(d)

    def refusal(self):
        """configurator.Refusal for the current answers (typed-name check aside), or None."""
        try:
            a = self._with_name()
            c.validate(a, self.ctx.facts)
            c.build_config(a, self.ctx.facts)
        except c.Refusal as r:
            return r
        return None

    def commands(self):
        """Summary + exact dry-run command lines, as the configurator prints them."""
        a = self._with_name()
        config, _creds = c.build_config(a, self.ctx.facts)
        lines = []
        c.dry_run(config, a, DRY_DIR, out=lines.append)
        return "\n".join(lines)

    def error(self):
        exp = self.expected()
        if exp is None:
            r = self.refusal()
            return r.message if r else "Disk not found."
        r = self.refusal()
        if r:
            return r.message
        if self.typed != exp:
            return f"Type the {self.confirm_noun()} name exactly to confirm: {exp}"
        return None

    def fragment(self):
        return {"confirm": self.typed}


MODE_LABELS = {"erase": "Erase the whole disk", "alongside": "Alongside an existing system",
               "partition": "Replace one partition"}
EXTRAS = {"gaming": "Gaming", "virt": "Virtualisation"}


def summary_rows(page):
    """[(title, value, detail, page key to edit it on)] for the review cards: one row per answer."""
    a = page.ctx.answers()
    luks = bool(a.get("luks"))
    extras = [EXTRAS.get(k, k) for k in page.ctx.hints()]
    keyboard = a.get("keyboard", "") + "".join(f" + {k}" for k in a.get("keyboard_extra", []))
    return [
        ("Disk", page.expected() or "Not found", a.get("disk", ""), "disk"),
        ("Mode", MODE_LABELS.get(a.get("mode"), a.get("mode") or "erase"), "", "disk"),
        ("Encryption", "On (LUKS2)" if luks else "Off", "", "encryption" if luks else "disk"),
        ("User", f"{a.get('username', '')} on {a.get('hostname', '')}", "", "user"),
        ("Locale", f"{a.get('locale', '')}, keyboard {keyboard}", "", "language"),
        ("Extras", ", ".join(extras) or "None", "", "tiers"),
    ]


def widget(page):
    import gi

    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk
    from view_util import entry_row, mono_view, page_box, switch_row, text_label

    box = page_box(page.title, "Check your choices. Nothing is written to the disk until you press Install.")
    group = Adw.PreferencesGroup(title="Your choices")
    for title, value, detail, goto in summary_rows(page):
        row = Adw.ActionRow(title=title, subtitle=value + (f"\n{detail}" if detail else ""),
                            use_markup=False)
        edit = Gtk.Button(label="Edit", valign=Gtk.Align.CENTER)
        edit.add_css_class("flat")
        edit.connect("clicked", lambda _b, k=goto: page.ctx.goto(k))
        row.add_suffix(edit)
        group.add(row)
    box.append(group)
    r = page.refusal()
    if r:
        box.append(text_label(f"Cannot install: {r.message}", "error"))
    else:
        details = Gtk.Expander(label="Exact commands")
        details.set_child(mono_view(page.commands()))
        box.append(details)
    box.append(text_label(f"This ERASES data on the selected disk (see above). Type its name to "
                          f"confirm: {page.expected() or '?'}"))
    box.append(entry_row("Disk name", page.typed, page.set_typed))
    if page.dev_options():
        box.append(switch_row("DEV build: pass --dev (not available in release images)", page.dev,
                              page.set_dev))
    return box
