# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""One registry row as a widget (plan-r8 B5): an Adw.ExpanderRow whose header carries the label,
the control and the status chips, and whose chevron reveals "Details": the setting id, the current
value, the file or command the app writes or runs for you, the exact text, privilege, live-apply,
and the buttons. Settings acts: nothing here asks the user to run a command.

Writes go through `registry.write` only, off the UI thread (`writeflow.WriteFlow`); a privileged row
shows a busy state while the administrator password is asked for. A reader failure is shown as
"Unavailable" with the error in Details, never raised.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from ..backend import readers, registry  # noqa: E402
from ..backend.env import Ctx, SettingError, WriteResult  # noqa: E402
from . import writeflow  # noqa: E402
from .writeflow import WriteFlow  # noqa: E402

RANGE_DEBOUNCE_MS = 400
PROFILE_LABELS = {"power-saver": "Saver", "balanced": "Balanced", "performance": "Performance"}
# Rows drawn with a bespoke control. The registry row (reader, writer, details) is unchanged.
PROFILE_BUTTONS = {"power.profile"}
BATTERY_BAR = {"power.battery_status"}
THEME_PICK = {"appearance.theme"}  # a drop-down of `seclegion-theme list` with a colour swatch
ACTION_SHOWN = {"appearance.reset": "Back to SecLegion Dark"}
_PCT = re.compile(r"(\d{1,3})\s*%")
# Reset to default: read the row against a home with nothing in it.
_EMPTY_HOME = "/nonexistent/seclegion-settings-default-home"


def fmt(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def as_raw(value) -> str | None:
    """A value as the text `registry.write` accepts."""
    return None if value is None else fmt(value)


def _choice_label(s: registry.Setting, choice: str) -> str:
    if choice in registry.CHOICE_LABELS.get(s.id, {}):
        return registry.CHOICE_LABELS[s.id][choice]
    return f"{choice} {s.unit}" if s.unit and choice.isdigit() else choice


def _label(text: str, *classes: str, **kw) -> Gtk.Label:
    lab = Gtk.Label(label=text, **kw)
    for c in classes:
        lab.add_css_class(c)
    return lab


def _chip(text: str, kind: str) -> Gtk.Label:
    lab = _label(text, "sl-chip", f"sl-chip-{kind}", valign=Gtk.Align.CENTER)
    lab.set_tooltip_text(writeflow.CHIP_TIPS[kind])
    return lab


class SettingRow(WriteFlow):
    """Controller for one setting. `host` is the window: ctx, toast(), saved(), details_everywhere."""

    def __init__(self, setting: registry.Setting, host):
        self.s = setting
        self.host = host
        self.state: registry.Row | None = None
        self.raw: str | None = None  # current value as raw text (from the last read)
        self.plan: WriteResult | None = None  # dry run of the shown value
        self.plan_error = ""
        self._sync = False
        self._pending = 0
        self.busy = False  # a privileged write is waiting for the password or the helper
        self.control: Gtk.Widget | None = None
        self.header_widget: Gtk.Widget | None = None  # drawn above the group (profile buttons)
        self.profile_buttons: dict[str, Gtk.ToggleButton] = {}
        self.battery_bar: Gtk.ProgressBar | None = None
        self.themes: list[dict] = []
        self.theme_dd: Gtk.DropDown | None = None
        self.swatch: Gtk.Label | None = None
        self.confirm_dialog: Adw.AlertDialog | None = None

        r = Adw.ExpanderRow()
        r.set_use_markup(False)
        r.set_title(setting.label)
        r.set_tooltip_text(setting.description)
        r.sl_setting_id = setting.id
        r.add_css_class("sl-setting")
        self.widget = r
        self._build_control()
        self.value_label = _label(
            "", "sl-value", "dim-label", valign=Gtk.Align.CENTER, ellipsize=3, max_width_chars=28
        )
        self.live_chip = _chip("LIVE", "live")
        self.live_chip.set_visible(False)
        r.add_suffix(self.live_chip)
        self.spinner = Adw.Spinner(visible=False, valign=Gtk.Align.CENTER)
        r.add_suffix(self.spinner)
        if setting.privileged:
            r.add_suffix(_chip("ROOT", "root"))
        r.add_suffix(self.value_label if self.control is None else self.control)
        self._build_details()
        r.connect("notify::expanded", self._on_expanded)

    # -- construction ---------------------------------------------------------------------------
    def _build_control(self) -> None:
        s = self.s
        if s.id in PROFILE_BUTTONS:
            box = Gtk.Box(spacing=8, homogeneous=True)
            box.add_css_class("sl-profiles")
            first = None
            for choice in s.choices:
                b = Gtk.ToggleButton(label=PROFILE_LABELS.get(choice, choice))
                b.add_css_class("sl-profile")
                b.sl_choice = choice
                if first is None:
                    first = b
                else:
                    b.set_group(first)
                b.connect("toggled", self._on_profile)
                box.append(b)
                self.profile_buttons[choice] = b
            self.header_widget = box
            return  # the expander row shows the value; the buttons are the control
        if s.id in THEME_PICK:
            c = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
            self.swatch = Gtk.Label(use_markup=True)
            self.swatch.add_css_class("sl-swatch")
            self.theme_dd = Gtk.DropDown(model=Gtk.StringList())
            self.theme_dd.connect("notify::selected", self._on_theme)
            c.append(self.swatch)
            c.append(self.theme_dd)
        elif s.kind == "action":
            c = Gtk.Button(label=s.action_label or "Reset", valign=Gtk.Align.CENTER)
            c.connect("clicked", lambda _b: self.run_action())
        elif s.kind == "toggle":
            c = Gtk.Switch(valign=Gtk.Align.CENTER)
            c.connect("notify::active", lambda w, _p: self._changed(fmt(w.get_active())))
        elif s.kind == "choice":
            c = Gtk.DropDown.new_from_strings([_choice_label(s, ch) for ch in s.choices])
            c.set_valign(Gtk.Align.CENTER)
            c.connect("notify::selected", self._on_selected)
        elif s.kind == "range":
            c = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            self.spin = Gtk.SpinButton.new_with_range(s.minimum, s.maximum, 1)
            self.spin.set_valign(Gtk.Align.CENTER)
            self.spin.connect("value-changed", self._on_spin)
            c.append(self.spin)
            if s.unit:
                c.append(_label(s.unit, "dim-label"))
        elif s.kind == "text":
            c = Gtk.Entry(valign=Gtk.Align.CENTER, width_chars=22)
            c.connect("activate", lambda w: self._changed(w.get_text()))
        else:  # info
            if s.id in BATTERY_BAR:
                self.battery_bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=120)
                self.battery_bar.add_css_class("sl-battery-bar")
                self.widget.add_prefix(self.battery_bar)
            return
        self.control = c

    def _build_details(self) -> None:
        s = self.s
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("sl-details")
        grid = Gtk.Grid(column_spacing=12, row_spacing=4)
        self._grid_row = 0
        self.details_value = self._kv(grid, "current value", "")
        if s.file:
            self._kv(grid, "file", s.file, path=True)
        if s.command:
            self._kv(grid, "command", s.command, path=True)
        self._kv(grid, "setting id", s.id, path=True)
        self._kv(grid, "needs privilege", writeflow.privilege(s))
        self.details_live = self._kv(grid, "applies live", "")
        box.append(grid)
        box.append(_label(s.description, "dim-label", xalign=0, wrap=True))
        self.details_text = _label("", "sl-details-text", xalign=0, selectable=True, wrap=True, wrap_mode=2)
        box.append(self.details_text)
        buttons = Gtk.Box(spacing=6)
        if s.file.startswith("~/") and s.kind != "action":
            self.open_button = Gtk.Button(label="Open file in editor")
            self.open_button.connect("clicked", lambda _b: self.open_file())
            buttons.append(self.open_button)
        else:
            self.open_button = None
        if not s.readonly and not s.privileged and s.kind != "action":
            self.reset_button = Gtk.Button(label="Reset to default")
            self.reset_button.connect("clicked", lambda _b: self.reset())
            buttons.append(self.reset_button)
        else:
            self.reset_button = None
        box.append(buttons)
        holder = Gtk.ListBoxRow(activatable=False, selectable=False, child=box)
        self.widget.add_row(holder)
        self.widget.sl_details = box

    def _kv(self, grid: Gtk.Grid, key: str, value: str, path: bool = False) -> Gtk.Label:
        grid.attach(_label(key, "sl-details-key", xalign=0, valign=Gtk.Align.START), 0, self._grid_row, 1, 1)
        v = _label(
            value,
            "sl-path" if path else "sl-mono",
            xalign=0,
            selectable=True,
            wrap=True,
            halign=Gtk.Align.START,
        )
        grid.attach(v, 1, self._grid_row, 1, 1)
        self._grid_row += 1
        return v

    # -- state ----------------------------------------------------------------------------------
    @property
    def ctx(self) -> Ctx:
        return self.host.ctx

    def refresh(self) -> None:
        """Re-read the value and redraw the header and details."""
        self.state = registry.row(self.s, self.ctx)
        st = self.state
        self.raw = as_raw(st.value) if st.visible and not st.error else None
        r = self.widget
        for c in ("sl-unavailable",):
            r.remove_css_class(c)
        r.set_subtitle(writeflow.subtitle(self.s, st))
        if not st.visible:
            r.add_css_class("sl-unavailable")
            shown = f"Unavailable on this machine: {st.reason}"
        elif st.error:
            r.add_css_class("sl-unavailable")
            shown = f"Unavailable: {st.error}"
        else:
            shown = self._shown(st.value)
        self.value_label.set_label(shown if st.visible and not st.error else "Unavailable")
        self.details_value.set_label(shown)
        usable = st.visible and not st.error and writeflow.changeable(self.s) and not self.busy
        if self.control is not None:
            self.control.set_visible(st.visible)
            self.control.set_sensitive(usable)
        for b in self.profile_buttons.values():
            b.set_sensitive(usable)
        self._sync_control()
        self._plan(self.raw)
        self._update_details()

    def _shown(self, value) -> str:
        numeric = isinstance(value, int) and not isinstance(value, bool)
        if self.s.id in PROFILE_BUTTONS:
            return PROFILE_LABELS.get(value, fmt(value))
        if self.s.kind == "action":
            return ACTION_SHOWN.get(self.s.id, "")
        if self.s.id in THEME_PICK:
            return next(
                (t.get("label", value) for t in self.themes if t["id"] == value), value or "custom accent"
            )
        if value in registry.CHOICE_LABELS.get(self.s.id, {}):
            return registry.CHOICE_LABELS[self.s.id][value]
        return fmt(value) + (f" {self.s.unit}" if numeric and self.s.unit else "")

    def _sync_control(self) -> None:
        st = self.state
        value = st.value if st and st.visible and not st.error else None
        self._sync = True
        try:
            if self.profile_buttons:
                for choice, b in self.profile_buttons.items():
                    b.set_active(choice == value)
            elif self.theme_dd is not None:
                self._sync_theme(value)
            elif self.s.kind == "action":
                pass
            elif self.s.kind == "toggle":
                self.control.set_active(bool(value))
            elif self.s.kind == "choice":
                if value in self.s.choices:
                    self.control.set_selected(self.s.choices.index(value))
            elif self.s.kind == "range":
                if isinstance(value, int):
                    self.spin.set_value(value)
            elif self.s.kind == "text":
                self.control.set_text("" if value is None else str(value))
            elif self.battery_bar is not None:
                m = _PCT.search(str(value or ""))
                self.battery_bar.set_fraction(min(int(m.group(1)), 100) / 100 if m else 0.0)
                self.battery_bar.set_visible(m is not None)
        finally:
            self._sync = False

    def _sync_theme(self, value) -> None:
        """Fill the drop-down from `seclegion-theme list` and show the current theme's swatch."""
        try:
            self.themes = readers.theme_list(self.ctx) if value is not None else []
        except readers.ReadError:
            self.themes = []
        model = self.theme_dd.get_model()
        model.splice(0, model.get_n_items(), [t.get("label") or t["id"] for t in self.themes])
        ids = [t["id"] for t in self.themes]
        cur = self.themes[ids.index(value)] if value in ids else None
        if cur is not None:
            self.theme_dd.set_selected(ids.index(value))
        self.swatch.set_visible(cur is not None)
        if cur is not None:
            self.swatch.set_markup(
                "".join(
                    f'<span background="{cur.get(k, "#000000")}">  </span>'
                    for k in ("bg", "surface", "accent", "text")
                )
            )

    def _plan(self, raw: str | None) -> None:
        """Dry-run `raw`: the exact text and commands shown in Details. Writes nothing."""
        self.plan, self.plan_error = None, ""
        st = self.state
        if self.s.readonly:
            self.plan_error = "read-only"
        elif st is None or not st.visible:
            self.plan_error = st.reason if st else ""
        elif raw is None:
            self.plan_error = "current value unreadable"
        else:
            pctx = Ctx(self.ctx.environ, dry_run=True)
            pctx.caps = self.ctx.caps
            try:
                self.plan = registry.write(self.s, pctx, raw)
                self.plan.dry_run = True
            except SettingError as e:
                self.plan_error = str(e)
            except OSError as e:
                self.plan_error = f"{e.strerror or e}"
        self.live_chip.set_visible(bool(self.plan and self.plan.applied_live))

    def _update_details(self) -> None:
        p = self.plan
        self.details_live.set_label(
            ("yes" if p.applied_live else "no") if p else ("-" if self.s.readonly else "unknown")
        )
        lines = []
        if p:
            for f in p.files:
                lines.append(f"file: {f}")
                if f in p.texts:
                    lines.extend("  " + ln for ln in p.texts[f].rstrip("\n").split("\n"))
            for c in p.commands:
                lines.append("runs: " + shlex.join(c))
            for n in p.notes:
                lines.append(f"note: {n}")
        elif self.plan_error:
            lines.append(self.plan_error)
        if self.state is not None and self.state.error:
            lines.insert(0, f"read error: {self.state.error}")
        if self.last_error:
            lines.insert(0, f"last change failed: {self.last_error}")
        self.details_text.set_label("\n".join(lines) or "-")
        if self.state is not None and (self.state.error or not self.state.visible):
            self.details_text.add_css_class("sl-error")
        else:
            self.details_text.remove_css_class("sl-error")
        if self.open_button is not None:
            self.open_button.set_sensitive(self._user_file().is_file())
        if self.reset_button is not None:
            self.reset_button.set_sensitive(self.default_raw() is not None and self.raw is not None)

    def _on_expanded(self, row, _pspec) -> None:
        if not row.get_expanded() and self.host.details_everywhere:
            row.set_expanded(True)  # "Show details everywhere" keeps every expander open

    # -- control events -------------------------------------------------------------------------
    def _on_profile(self, b: Gtk.ToggleButton) -> None:
        if b.get_active():
            self._changed(b.sl_choice)

    def _on_selected(self, dd: Gtk.DropDown, _pspec) -> None:
        i = dd.get_selected()
        if 0 <= i < len(self.s.choices):
            self._changed(self.s.choices[i])

    def _on_theme(self, dd: Gtk.DropDown, _pspec) -> None:
        i = dd.get_selected()
        if 0 <= i < len(self.themes):
            self._changed(self.themes[i]["id"])

    def _on_spin(self, spin: Gtk.SpinButton) -> None:
        if self._sync:
            return
        if self._pending:
            GLib.source_remove(self._pending)
        self._pending = GLib.timeout_add(RANGE_DEBOUNCE_MS, self.flush)

    def flush(self) -> bool:
        """Apply a pending range change now (the debounce timer calls this)."""
        if self._pending:
            GLib.source_remove(self._pending)
            self._pending = 0
            self._changed(str(self.spin.get_value_as_int()))
        return False

    def _changed(self, raw: str) -> None:
        if not self._sync:
            self.apply(raw)

    # -- actions --------------------------------------------------------------------------------
    def run_action(self) -> None:
        """An action row's button: ask first when the row has a `confirm` text."""
        if not self.s.confirm:
            self.apply("run")
            return
        dlg = Adw.AlertDialog(heading=self.s.label, body=self.s.confirm)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("run", self.s.action_label or "Run")
        dlg.set_response_appearance("run", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, rid: self.apply("run") if rid == "run" else None)
        self.confirm_dialog = dlg
        dlg.present(self.host)

    def set_busy(self, on: bool) -> None:
        """While a privileged write runs: a spinner, a plain subtitle and no second change."""
        self.busy = on
        self.spinner.set_visible(on)
        if on:
            self.widget.set_subtitle(writeflow.BUSY)
            if self.control is not None:
                self.control.set_sensitive(False)
            for b in self.profile_buttons.values():
                b.set_sensitive(False)

    def _user_file(self) -> Path:
        return self.ctx.home / self.s.file[2:] if self.s.file.startswith("~/") else Path("/nonexistent")

    def open_file(self) -> None:
        f = self._user_file()
        if f.is_file():
            Gtk.FileLauncher.new(Gio.File.new_for_path(str(f))).launch(
                self.widget.get_root(), None, None, None
            )

    def default_raw(self) -> str | None:
        """The value this row has with no user file: user-file rows only, else None."""
        if self.s.privileged or self.s.readonly or not self.s.file.startswith("~/"):
            return None
        env = {
            "PATH": "",
            "SL_HOME": _EMPTY_HOME,
            "SL_SYSFS": str(self.ctx.sysfs),
            "SL_ETC": str(self.ctx.etc),
        }
        value, err = registry.read_value(self.s, Ctx(env))
        raw = as_raw(value)
        if err or raw is None:
            return None
        try:
            self.s.coerce(raw)
        except SettingError:
            return None
        return raw

    def reset(self) -> None:
        raw = self.default_raw()
        if raw is not None:
            self.apply(raw)
