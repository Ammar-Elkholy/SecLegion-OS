# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""The System Monitor window: Overview, GPUs and Processes pages in an Adw.ViewStack.

Refresh is a 1 s GLib timer that runs only while the window is mapped and its toplevel is neither
minimized nor suspended (the compositor says it cannot be seen). The GPU page is read only while it is
the visible page, off the main loop; the process list only while Processes is visible.
"""
from __future__ import annotations

import signal
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from .. import procs as P  # noqa: E402
from ..data import History, Sampler, fmt_bits, fmt_byte_rate, fmt_bytes  # noqa: E402
from ..gpu import GpuReader  # noqa: E402

PAGES = (("overview", "Overview", "utilities-system-monitor-symbolic"),
         ("gpu", "GPUs", "video-display-symbolic"),
         ("processes", "Processes", "view-list-symbolic"))
HIDDEN_STATES = Gdk.ToplevelState.MINIMIZED | getattr(Gdk.ToplevelState, "SUSPENDED", 0)


class Graph(Gtk.DrawingArea):
    """One series, the last 60 samples, scaled to `top` (or to its peak when top is None)."""

    def __init__(self, history: History, css: str, top: float | None = 100.0):
        super().__init__(content_width=160, content_height=36, valign=Gtk.Align.CENTER)
        self.history, self.top = history, top
        self.add_css_class("sl-graph")
        self.add_css_class(css)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h) -> None:
        vals = list(self.history.values)
        c = self.get_color()
        cr.set_source_rgba(c.red, c.green, c.blue, 0.15)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        if len(vals) < 2:
            return
        top = self.top or max(self.history.peak(), 1.0)
        step = w / (self.history.values.maxlen - 1)
        x0 = w - step * (len(vals) - 1)
        cr.move_to(x0, h)
        for i, v in enumerate(vals):
            cr.line_to(x0 + i * step, h - min(v / top, 1.0) * (h - 2))
        cr.line_to(w, h)
        cr.close_path()
        cr.set_source_rgba(c.red, c.green, c.blue, 0.35)
        cr.fill_preserve()
        cr.set_source_rgba(c.red, c.green, c.blue, 1.0)
        cr.set_line_width(1.5)
        cr.stroke()


class Rows:
    """Rows of one PreferencesGroup keyed by id: created on first sight, updated, removed when gone."""

    def __init__(self, group: Adw.PreferencesGroup):
        self.group, self.rows = group, {}

    def set(self, items: list[tuple[str, str, str, str]]) -> None:  # (key, title, subtitle, value)
        keep = set()
        for key, title, subtitle, value in items:
            keep.add(key)
            row = self.rows.get(key)
            if row is None:
                row = Adw.ActionRow(title=title, use_markup=False)
                row.sl_value = Gtk.Label(css_classes=["sl-value"], valign=Gtk.Align.CENTER)
                row.add_suffix(row.sl_value)
                self.group.add(row)
                self.rows[key] = row
            row.set_subtitle(subtitle)
            row.sl_value.set_label(value)
        for key in [k for k in self.rows if k not in keep]:
            self.group.remove(self.rows.pop(key))


class ProcItem(GObject.Object):
    pid = GObject.Property(type=int)
    name = GObject.Property(type=str)
    user = GObject.Property(type=str)
    cpu = GObject.Property(type=float)
    rss = GObject.Property(type=GObject.TYPE_INT64)
    cpu_text = GObject.Property(type=str)
    mem_text = GObject.Property(type=str)
    own = GObject.Property(type=bool, default=False)

    def update(self, p: P.Proc) -> None:
        for k, v in (("name", p.name), ("user", p.user), ("cpu", p.cpu), ("rss", p.rss),
                     ("cpu_text", f"{p.cpu:.1f}"), ("mem_text", fmt_bytes(p.rss)), ("own", p.own)):
            if self.get_property(k) != v:
                self.set_property(k, v)


def _group(title: str) -> Adw.PreferencesGroup:
    return Adw.PreferencesGroup(title=title)


def _fmt_temp(t) -> str:
    return "" if t is None else f"{t:.0f} °C"


class SysmonWindow(Adw.ApplicationWindow):
    def __init__(self, application=None, sampler=None, gpus=None, list_procs=P.list_procs, send=P.send):
        super().__init__(application=application, title="SecLegion System Monitor")
        self.sampler = sampler or Sampler()
        self.gpus = gpus or GpuReader()
        self.list_procs, self.send = list_procs, send
        self.hist = {k: History() for k in ("cpu", "mem", "down", "up")}
        self.timer = 0
        self.ticks = 0
        self._gpu_busy = False
        self.last_toast: Adw.Toast | None = None
        self.confirm_dialog: Adw.AlertDialog | None = None
        self.set_default_size(900, 680)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(self._overview(), *PAGES[0])
        self.stack.add_titled_with_icon(self._gpu_page(), *PAGES[1])
        self.stack.add_titled_with_icon(self._proc_page(), *PAGES[2])
        self.stack.connect("notify::visible-child-name", lambda *_: self.tick() if self.timer else None)
        header = Adw.HeaderBar(title_widget=Adw.ViewSwitcher(stack=self.stack,
                                                             policy=Adw.ViewSwitcherPolicy.WIDE))
        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(header)
        self.toasts = Adw.ToastOverlay(child=view)
        self.set_content(self.toasts)

        self.connect("map", lambda *_: self._update_polling())
        self.connect("unmap", lambda *_: self._update_polling())
        self.connect("realize", self._on_realize)
        self.connect("destroy", lambda *_: self._stop())

    # -- polling --------------------------------------------------------------------------------
    @property
    def polling(self) -> bool:
        return self.timer != 0

    def should_poll(self) -> bool:
        if not self.get_mapped():
            return False
        surface = self.get_surface()
        state = surface.get_state() if isinstance(surface, Gdk.Toplevel) else 0
        return not (state & HIDDEN_STATES)

    def _on_realize(self, *_):
        surface = self.get_surface()
        if surface is not None:
            surface.connect("notify::state", lambda *_: self._update_polling())

    def _update_polling(self) -> None:
        if self.should_poll() and not self.timer:
            self.tick()
            self.timer = GLib.timeout_add_seconds(1, self._on_timer)
        elif not self.should_poll():
            self._stop()

    def _stop(self) -> None:
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _on_timer(self) -> bool:
        self.tick()
        return GLib.SOURCE_CONTINUE

    def show_page(self, name: str) -> bool:
        if name not in {p[0] for p in PAGES}:
            return False
        self.stack.set_visible_child_name(name)
        return True

    def tick(self) -> None:
        self.ticks += 1
        self.update_overview(self.sampler.sample())
        page = self.stack.get_visible_child_name()
        if page == "gpu":
            self.refresh_gpus()
        elif page == "processes":
            self.refresh_procs()

    # -- overview -------------------------------------------------------------------------------
    def _overview(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        cpu = _group("CPU")
        self.cpu_row = Adw.ActionRow(title="Total")
        self.graphs = [Graph(self.hist["cpu"], "sl-graph-cpu"), Graph(self.hist["mem"], "sl-graph-mem"),
                       Graph(self.hist["down"], "sl-graph-down", top=None),
                       Graph(self.hist["up"], "sl-graph-up", top=None)]
        self.cpu_row.add_suffix(self.graphs[0])
        self.cpu_row.sl_value = Gtk.Label(css_classes=["sl-value"], width_chars=7, xalign=1)
        self.cpu_row.add_suffix(self.cpu_row.sl_value)
        cpu.add(self.cpu_row)
        self.cores = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8,
                                 homogeneous=True, margin_top=6, margin_bottom=6)
        self.core_labels: list[Gtk.Label] = []
        cpu.add(self.cores)
        self.cpu_info = Rows(cpu)
        mem = _group("Memory")
        self.mem_row = Adw.ActionRow(title="Memory")
        self.mem_row.add_suffix(self.graphs[1])
        mem.add(self.mem_row)
        self.mem_info = Rows(mem)
        net = _group("Network")
        self.net_row = Adw.ActionRow(title="All interfaces", subtitle="down, up")
        self.net_row.add_suffix(self.graphs[2])
        self.net_row.add_suffix(self.graphs[3])
        net.add(self.net_row)
        self.nets = Rows(net)
        disks, temps, power = _group("Disks"), _group("Temperatures"), _group("Power")
        self.disks, self.temps, self.power = Rows(disks), Rows(temps), Rows(power)
        for g in (cpu, mem, net, disks, temps, power):
            page.add(g)
        return page

    def update_overview(self, s) -> None:
        c, m = s.cpu, s.mem
        self.hist["cpu"].push(c.total)
        self.hist["mem"].push(m.percent)
        self.hist["down"].push(sum(n.down_bps for n in s.nets))
        self.hist["up"].push(sum(n.up_bps for n in s.nets))
        self.cpu_row.sl_value.set_label(f"{c.total:.0f} %")
        while len(self.core_labels) < len(c.per_core):
            lab = Gtk.Label(css_classes=["sl-core", "sl-mono"], xalign=0)
            self.core_labels.append(lab)
            self.cores.append(lab)
        for i, v in enumerate(c.per_core):
            self.core_labels[i].set_label(f"cpu{i} {v:3.0f}%")
        freq = "" if c.freq_mhz is None else f"{c.freq_mhz / 1000:.2f} GHz"
        if freq and c.freq_max_mhz:
            freq += f" of {c.freq_max_mhz / 1000:.2f}"
        self.cpu_info.set([("load", "Load average", "1, 5, 15 min", "  ".join(f"{x:.2f}" for x in c.load)),
                           ("freq", "Frequency", "", freq or "unknown")])
        self.mem_row.set_subtitle(f"{fmt_bytes(m.used)} of {fmt_bytes(m.total)} ({m.percent:.0f} %)")
        swap = f"{fmt_bytes(m.swap_used)} of {fmt_bytes(m.swap_total)}" if m.swap_total else "none"
        self.mem_info.set([("swap", "Swap", "", swap)])
        self.net_row.set_subtitle(f"↓ {fmt_bits(self.hist['down'].values[-1])}  "
                                  f"↑ {fmt_bits(self.hist['up'].values[-1])}")
        self.nets.set([(n.name, n.name, "", f"↓ {fmt_bits(n.down_bps)}  ↑ {fmt_bits(n.up_bps)}")
                       for n in s.nets])
        self.disks.set([(d.device, ", ".join(d.mounts),
                         f"{d.device} {d.fstype}  read {fmt_byte_rate(d.read_bps)}  "
                         f"write {fmt_byte_rate(d.write_bps)}",
                         "" if d.total is None else f"{fmt_bytes(d.used)} of {fmt_bytes(d.total)}"
                                                    f" ({d.percent:.0f} %)") for d in s.disks])
        self.temps.set([(f"{i}:{t.label}", t.label, "", _fmt_temp(t.celsius)) for i, t in enumerate(s.temps)])
        p = s.power
        rows = [(b.name, f"Battery {b.name}", b.status, "" if b.capacity is None else f"{b.capacity} %")
                for b in p.batteries]
        if p.ac_online is not None:
            rows.append(("ac", "AC power", "", "connected" if p.ac_online else "unplugged"))
        self.power.set(rows)
        for g in self.graphs:
            g.queue_draw()

    # -- GPUs -----------------------------------------------------------------------------------
    def _gpu_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        g = _group("Graphics cards")
        g.set_description("A sleeping NVIDIA dGPU is not queried; on battery it is not polled either.")
        self.gpu_rows = Rows(g)
        page.add(g)
        return page

    def refresh_gpus(self) -> None:
        """Read the cards on a worker thread (nvidia-smi can take a while); one read at a time."""
        if self._gpu_busy:
            return
        self._gpu_busy = True

        def work():
            try:
                cards = self.gpus.read(query=True)
            except Exception as e:  # noqa: BLE001 (shown on the page, never lost in the worker)
                cards = e
            GLib.idle_add(lambda: self.show_gpus(cards) and False)

        threading.Thread(target=work, name="sysmon-gpu", daemon=True).start()

    def show_gpus(self, cards) -> None:
        self._gpu_busy = False
        if isinstance(cards, Exception):
            self.gpu_rows.set([("err", "GPUs unavailable", str(cards), "")])
            return
        rows = []
        for c in cards:
            stats = []
            if c.busy is not None:
                stats.append(f"busy {c.busy} %")
            if c.vram_total:
                stats.append(f"VRAM {fmt_bytes(c.vram_used or 0)} of {fmt_bytes(c.vram_total)}")
            if c.temp is not None:
                stats.append(_fmt_temp(c.temp))
            if c.power_w is not None:
                stats.append(f"{c.power_w:.1f} W")
            sub = " ".join(x for x in (c.slot, c.note) if x)
            rows.append((c.card, f"{c.vendor} {c.card}", sub, "  ".join(stats)))
        self.gpu_rows.set(rows or [("none", "No graphics card found", "", "")])

    # -- processes ------------------------------------------------------------------------------
    def _proc_page(self) -> Gtk.Widget:
        self.store = Gio.ListStore(item_type=ProcItem)
        self.items: dict[int, ProcItem] = {}
        self.search = Gtk.SearchEntry(placeholder_text="Filter by name, user or PID", hexpand=True)
        self.filter = Gtk.CustomFilter.new(self._match)
        self.search.connect("search-changed", lambda *_: self.filter.changed(Gtk.FilterChange.DIFFERENT))
        self.view = Gtk.ColumnView(show_row_separators=False, vexpand=True)
        self.sort_model = Gtk.SortListModel(model=Gtk.FilterListModel(model=self.store, filter=self.filter),
                                            sorter=self.view.get_sorter())
        self.selection = Gtk.SingleSelection(model=self.sort_model, autoselect=False, can_unselect=True)
        self.selection.connect("notify::selected-item", lambda *_: self._sync_buttons())
        self.view.set_model(self.selection)
        self.columns = {}
        for key, title, prop, expand in (("name", "Name", "name", True), ("pid", "PID", "pid", False),
                                         ("user", "User", "user", False), ("cpu", "CPU %", "cpu_text", False),
                                         ("memory", "Memory", "mem_text", False)):
            col = Gtk.ColumnViewColumn(title=title, factory=self._factory(prop), expand=expand,
                                       sorter=Gtk.CustomSorter.new(self._cmp, key))
            self.view.append_column(col)
            self.columns[key] = col
        self.view.sort_by_column(self.columns["cpu"], Gtk.SortType.DESCENDING)
        self.end_btn = Gtk.Button(label="End process", sensitive=False)
        self.end_btn.connect("clicked", lambda *_: self.ask_signal(signal.SIGTERM))
        self.kill_btn = Gtk.Button(label="Kill", sensitive=False, css_classes=["destructive-action"])
        self.kill_btn.connect("clicked", lambda *_: self.ask_signal(signal.SIGKILL))
        bar = Gtk.ActionBar()
        bar.pack_start(self.search)
        bar.pack_end(self.kill_btn)
        bar.pack_end(self.end_btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Gtk.ScrolledWindow(child=self.view, vexpand=True))
        box.append(bar)
        return box

    @staticmethod
    def _factory(prop: str) -> Gtk.SignalListItemFactory:
        f = Gtk.SignalListItemFactory()
        numeric = prop in ("pid", "cpu_text", "mem_text")

        def setup(_f, li):
            li.set_child(Gtk.Label(xalign=1 if numeric else 0, ellipsize=3, css_classes=["sl-mono"]))

        def bind(_f, li):
            item, label = li.get_item(), li.get_child()
            label.sl_binding = item.bind_property(prop, label, "label", GObject.BindingFlags.SYNC_CREATE,
                                                  (lambda _b, v: str(v)) if prop == "pid" else None)

        def unbind(_f, li):
            label = li.get_child()
            if getattr(label, "sl_binding", None) is not None:
                label.sl_binding.unbind()
                label.sl_binding = None

        f.connect("setup", setup)
        f.connect("bind", bind)
        f.connect("unbind", unbind)
        return f

    def _match(self, item: ProcItem) -> bool:
        q = self.search.get_text().strip().lower()
        return not q or q in item.name.lower() or q in item.user.lower() or q == str(item.pid)

    @staticmethod
    def _cmp(a: ProcItem, b: ProcItem, key: str) -> int:
        ka = {"name": a.name.lower(), "pid": a.pid, "user": a.user, "cpu": a.cpu, "memory": a.rss}[key]
        kb = {"name": b.name.lower(), "pid": b.pid, "user": b.user, "cpu": b.cpu, "memory": b.rss}[key]
        return (ka > kb) - (ka < kb)

    def refresh_procs(self) -> None:
        try:
            fresh = {p.pid: p for p in self.list_procs()}
        except Exception as e:  # noqa: BLE001 (shown to the user)
            self.toast(f"Process list unavailable: {e}")
            return
        for i in range(self.store.get_n_items() - 1, -1, -1):
            if self.store.get_item(i).pid not in fresh:
                self.items.pop(self.store.get_item(i).pid, None)
                self.store.remove(i)
        new = []
        for pid, p in fresh.items():
            item = self.items.get(pid)
            if item is None:
                item = self.items[pid] = ProcItem(pid=pid)
                new.append(item)
            item.update(p)
        if new:
            self.store.splice(self.store.get_n_items(), 0, new)
        for col in self.columns.values():
            col.get_sorter().changed(Gtk.SorterChange.DIFFERENT)
        self._sync_buttons()

    def selected(self) -> ProcItem | None:
        return self.selection.get_selected_item()

    def _sync_buttons(self) -> None:
        item = self.selected()
        own = item is not None and item.own
        self.end_btn.set_sensitive(own)
        self.kill_btn.set_sensitive(own)
        tip = None if item is None or own else "Only your own processes can be ended"
        self.end_btn.set_tooltip_text(tip)
        self.kill_btn.set_tooltip_text(tip)

    def ask_signal(self, sig: int) -> None:
        item = self.selected()
        if item is None or not item.own:
            return
        verb = "End" if sig == signal.SIGTERM else "Kill"
        body = (f"{item.name} (PID {item.pid}) is asked to quit (SIGTERM); unsaved work may be lost."
                if sig == signal.SIGTERM else
                f"{item.name} (PID {item.pid}) is stopped at once (SIGKILL); unsaved work is lost.")
        dlg = Adw.AlertDialog(heading=f"{verb} {item.name}?", body=body)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("signal", "End process" if sig == signal.SIGTERM else "Kill")
        dlg.set_response_appearance("signal", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        pid = item.pid
        dlg.connect("response", lambda _d, rid: self._signal(pid, sig) if rid == "signal" else None)
        self.confirm_dialog = dlg
        dlg.present(self)

    def _signal(self, pid: int, sig: int) -> None:
        try:
            self.send(pid, sig)
        except P.Refused as e:
            self.toast(f"Not sent: {e}")
            return
        self.toast(f"{'SIGTERM' if sig == signal.SIGTERM else 'SIGKILL'} sent to PID {pid}.")

    def toast(self, text: str) -> None:
        self.last_toast = Adw.Toast(title=text, use_markup=False)
        self.toasts.add_toast(self.last_toast)

