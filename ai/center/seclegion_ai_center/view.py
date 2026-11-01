# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Thin GTK4/libadwaita view over model.py. Keys are only ever shown masked; the entry used to type
a new key is cleared as soon as the key is handed to the Secret Service."""

from __future__ import annotations

import sys

from . import model
from .secrets import SecretError, SecretToolStore


def _offthread():
    # Same helper the Settings app uses; fall back to a plain thread-free call if it is absent.
    from seclegion_settings.ui import offthread

    return offthread.run_async


def _gui() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    center = model.Center(SecretToolStore())
    run_async = _offthread()

    def activate(app):
        win = Adw.ApplicationWindow(
            application=app, title="SecLegion AI Center", default_width=560, default_height=640
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        runtime = Adw.PreferencesGroup(title="Local runtime", description="Off by default; loopback only.")
        models = Adw.PreferencesGroup(title="Installed models")
        cloud = Adw.PreferencesGroup(
            title="Cloud providers", description="Keys are kept in the Secret Service only."
        )
        for g in (runtime, models, cloud):
            page.add(g)
        rows: dict[str, list] = {"runtime": [], "models": [], "cloud": []}

        def fill(group, key, new_rows):
            for r in rows[key]:
                group.remove(r)
            rows[key] = new_rows
            for r in new_rows:
                group.add(r)

        def refresh_runtime():
            def done(res, err):
                lines, names = res if res else (["could not read runtime status"], [])
                fill(runtime, "runtime", [Adw.ActionRow(title=ln) for ln in lines])
                fill(
                    models, "models", [Adw.ActionRow(title=n) for n in names] or [Adw.ActionRow(title="none")]
                )

            run_async(center.runtime, done)

        def refresh_cloud():
            out = []
            for p in center.providers():
                row = Adw.ActionRow(
                    title=p.name, subtitle=f"{p.base_url}  {p.model}  key: {center.masked(p.name)}"
                )
                test = Gtk.Button(label="Test connection", valign=Gtk.Align.CENTER)

                def clicked(_b, p=p, row=row):
                    def done(res, err):
                        row.set_subtitle(str(err) if err else res[1])

                    run_async(lambda: center.test_connection(p.name), done)

                test.connect("clicked", clicked)
                row.add_suffix(test)
                out.append(row)
            fill(cloud, "cloud", out)

        add_row = Adw.ExpanderRow(title="Add provider")
        fields = {}
        for label, kind in (
            ("Name", Adw.EntryRow),
            ("Base URL", Adw.EntryRow),
            ("Model id", Adw.EntryRow),
            ("API key", Adw.PasswordEntryRow),
        ):
            e = kind(title=label)
            fields[label] = e
            add_row.add_row(e)
        fields["Base URL"].set_text(model.PRESETS["OpenAI"]["base_url"])
        status = Adw.ActionRow(title="")
        save = Gtk.Button(label="Save", valign=Gtk.Align.CENTER)

        def on_save(_b):
            try:
                name = fields["Name"].get_text()
                preset = model.PRESETS.get(name, {})
                center.add(
                    name,
                    fields["Base URL"].get_text(),
                    fields["Model id"].get_text(),
                    key=fields["API key"].get_text() or None,
                    auth=preset.get("auth", "bearer"),
                )
                fields["API key"].set_text("")
                status.set_title("Saved.")
                refresh_cloud()
            except (model.CenterError, SecretError) as e:
                status.set_title(str(e))

        save.connect("clicked", on_save)
        status.add_suffix(save)
        add_row.add_row(status)
        cloud.add(add_row)
        refresh_runtime()
        refresh_cloud()
        box.append(page)
        win.set_content(box)
        win.present()

    app = Adw.Application(application_id="org.seclegion.AICenter")
    app.connect("activate", activate)
    return app.run([sys.argv[0]])


def main(argv=None) -> int:
    return _gui()
