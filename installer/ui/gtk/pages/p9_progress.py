# SPDX-FileCopyrightText: 2026 Ammar Elkholy and SecLegion contributors
# SPDX-License-Identifier: MIT
"""Page 9: progress. Runs `seclegion-install --answers FILE` as a child and streams its output.

The answers file (passwords inside) is a 0600 file in a 0700 dir on tmpfs (/run), deleted when the child
exits. Secrets are never passed on argv and any streamed line is scrubbed of the secret values before it
reaches the screen or the log file."""

import json
import os
import shutil
import subprocess
import tempfile

from .base import Page

INSTALLER = "seclegion-install"
# The install kiosk runs as the no-sudo seclegion-installer user. The polkit rule that the install target
# writes into /run (iso/profile/airootfs/usr/share/seclegion/install) lets it run exactly this program.
KIOSK_INSTALLER = ["pkexec", "/usr/bin/seclegion-install"]
OK_MARK = "SECLEGION-INSTALL-OK"
DEFAULT_LOG = "/var/log/seclegion-installer.log"


def tmpfs_dir():
    for d in ("/run", os.environ.get("XDG_RUNTIME_DIR")):
        if d and os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    return tempfile.gettempdir()


def scrub(line, secrets):
    for s in secrets:
        if s:
            line = line.replace(s, "***")
    return line


class ProgressPage(Page):
    key = "progress"
    title = "Installing"
    show_back = False
    show_next = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self.installer = [INSTALLER]  # argv prefix (tests substitute a fake)
        self.run_dir = None  # None = tmpfs_dir()
        self.log_path = os.environ.get("SECLEGION_GUI_LOG", DEFAULT_LOG)
        self.lines = []
        self.done = False
        self.ok = False
        self.answers_path = None  # kept after the run only to prove deletion

    def use_pkexec(self):
        """Kiosk mode: seclegion-install needs root, which the kiosk user gets only through pkexec."""
        self.installer = list(KIOSK_INSTALLER)

    def error(self):
        return None if self.ok else "Installing..."

    def fragment(self):
        return {}

    def argv(self, answers_path):
        argv = [*self.installer, "--answers", answers_path]
        argv += self.ctx.pages["review"].dev_flags()
        hints = self.ctx.hints()
        if hints:
            # non-secret extras for the post step
            argv += ["--hints", os.path.join(os.path.dirname(answers_path), "hints.json")]
        return argv

    def run(self, on_line=lambda s: None):
        """Blocking: run the install, call on_line(scrubbed line) per line. Returns True on success."""
        answers = self.ctx.answers()
        secrets = [answers.get("password"), answers.get("luks_passphrase")]
        tmp = tempfile.mkdtemp(prefix="seclegion-gui-", dir=self.run_dir or tmpfs_dir())
        os.chmod(tmp, 0o700)
        self.lines, self.done, self.ok = [], False, False
        self.answers_path = os.path.join(tmp, "answers.json")
        try:
            self._write(self.answers_path, answers)
            hints = self.ctx.hints()
            if hints:
                self._write(os.path.join(tmp, "hints.json"), hints)
            argv = self.argv(self.answers_path)
            logfd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(logfd, "a") as log:
                try:
                    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, text=True, errors="replace")
                except OSError as e:
                    self._emit(scrub(f"cannot start installer: {e}", secrets), log, on_line)
                    self.done = True
                    return False
                for raw in proc.stdout:
                    line = scrub(raw.rstrip("\n"), secrets)
                    self._emit(line, log, on_line)
                    if line == OK_MARK:
                        self.ok = True
                rc = proc.wait()
                self.ok = self.ok and rc == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.done = True
        return self.ok

    def _emit(self, line, log, on_line):
        self.lines.append(line)
        log.write(line + "\n")
        log.flush()
        on_line(line)

    @staticmethod
    def _write(path, data):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)


def widget(page):
    from gi.repository import Adw, GLib, Gtk, Pango
    from view_util import status_page

    sp = status_page("system-software-install-symbolic", "Installing SecLegion OS",
                     "Do not power off. This can take several minutes.")
    bar = Gtk.ProgressBar()
    step = Gtk.Label(name="progress-step", xalign=0, ellipsize=Pango.EllipsizeMode.END)
    step.add_css_class("dim-label")
    log = Gtk.Label(name="progress-log", xalign=0, yalign=0, wrap=True, selectable=True)
    log.add_css_class("monospace")
    scroller = Gtk.ScrolledWindow(min_content_height=240)
    scroller.set_child(log)
    details = Gtk.Expander(label="Details")
    details.set_child(scroller)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for w in (bar, step, details):
        col.append(w)
    sp.set_child(Adw.Clamp(maximum_size=560, child=col))

    def update():
        """Called by the app for every new output line: current step, log text, bar pulse."""
        shown = [ln for ln in page.lines if ln.strip()]
        step.set_label(shown[-1] if shown else "Starting...")
        log.set_label("\n".join(page.lines[-200:]) or "Starting...")
        bar.pulse()
        GLib.idle_add(to_end)

    def to_end():
        adj = scroller.get_vadjustment()
        adj.set_value(adj.get_upper())
        return GLib.SOURCE_REMOVE

    shown_once = []

    def tick():  # the install has no percentage, so the bar keeps moving until the page goes away
        if bar.get_mapped():
            shown_once.append(1)
        if page.done or (shown_once and not bar.get_mapped()):
            return GLib.SOURCE_REMOVE
        bar.pulse()
        return GLib.SOURCE_CONTINUE

    sp.update = update
    update()
    GLib.timeout_add(250, tick)
    return sp
