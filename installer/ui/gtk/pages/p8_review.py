# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 8: review. Shows the exact command list from the configurator's dry run plus a summary.
Install is enabled only when the user has typed the disk's name (model, or name if no model) and
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
        """The name the user must type. None when the disk cannot be resolved."""
        try:
            disk = c.find_disk(self.answers_obj(), self.ctx.facts)
        except c.Refusal:
            return None
        return (disk.get("model") or disk.get("name") or "").strip() or None

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
            return f"Type the disk name exactly to confirm: {exp}"
        return None

    def fragment(self):
        return {"confirm": self.typed}


def widget(page):
    from view_util import entry_row, mono_view, page_box, switch_row, text_label

    box = page_box(page.title)
    r = page.refusal()
    if r:
        box.append(text_label(f"Cannot install: {r.message}", "error"))
    else:
        box.append(mono_view(page.commands()))
    box.append(text_label(f"This ERASES data on the selected disk (see above). Type its name to "
                          f"confirm: {page.expected() or '?'}"))
    box.append(entry_row("Disk name", page.typed, page.set_typed))
    if page.dev_options():
        box.append(switch_row("DEV build: pass --dev (not available in release images)", page.dev,
                              page.set_dev))
    return box
