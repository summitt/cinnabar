"""Cinnabar tray icon: switch presets from Cinnamon's status area (XApp.StatusIcon, GTK3)."""
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("XApp", "1.0")
from gi.repository import Gio, GLib, Gtk, XApp  # noqa: E402

from . import tokens as T  # noqa: E402

PROJECT = T.PROJECT_DIR
AUTOSTART = Path.home() / ".config/autostart/cinnabar-tray.desktop"
ICON_DIR = Path.home() / ".local/share/icons/hicolor/scalable/apps"


def _icon_name():
    # Prefer the installed symbolic icon (panel recolors it); fall back to the repo file path.
    if (ICON_DIR / "cinnabar-symbolic.svg").exists():
        return "cinnabar-symbolic"
    return str(PROJECT / "data" / "cinnabar-symbolic.svg")


def _notify(title, body=""):
    subprocess.Popen(["notify-send", "-a", "Cinnabar", "-i", "cinnabar", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Tray:
    def __init__(self):
        self.icon = XApp.StatusIcon()
        self.icon.set_name("cinnabar")
        self.icon.set_icon_name(_icon_name())
        self.icon.set_tooltip_text("Cinnabar — switch theme")
        self.busy = False
        self._monitors = []
        for d in T.PRESET_DIRS + [T.CONFIG_DIR]:
            d.mkdir(parents=True, exist_ok=True)
            m = Gio.File.new_for_path(str(d)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            m.connect("changed", lambda *a: self._schedule_rebuild())
            self._monitors.append(m)
        self._rebuild_id = 0
        self.rebuild_menu()

    # ---- menu
    def _schedule_rebuild(self):
        if self._rebuild_id:
            GLib.source_remove(self._rebuild_id)
        self._rebuild_id = GLib.timeout_add(400, self._do_rebuild)

    def _do_rebuild(self):
        self._rebuild_id = 0
        self.rebuild_menu()
        return False

    def _current_name(self):
        cur = T.CONFIG_DIR / "current.yaml"
        try:
            return T.load(cur)["name"] if cur.exists() else None
        except Exception:
            return None

    def rebuild_menu(self):
        menu = Gtk.Menu()
        head = Gtk.MenuItem(label="Cinnabar")
        head.set_sensitive(False)
        menu.append(head)
        menu.append(Gtk.SeparatorMenuItem())
        current = self._current_name()
        presets = []
        for slug, path in T.list_presets().items():
            try:
                presets.append((T.load(path), slug))
            except Exception:
                continue
        presets.sort(key=lambda p: (p[0]["variant"] != "dark", p[0]["name"].lower()))
        group = None
        last_variant = None
        for t, slug in presets:
            if t["variant"] != last_variant:
                sub = Gtk.MenuItem(label="Dark" if t["variant"] == "dark" else "Light")
                sub.set_sensitive(False)
                menu.append(sub)
                last_variant = t["variant"]
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, t["name"])
            group = group or item
            item.set_active(t["name"] == current)
            item.connect("toggled", self._on_preset, slug, t["name"])
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        self.apply_item = Gtk.MenuItem(label="Re-apply current preset")
        self.apply_item.connect("activate", lambda *_: self._apply_current())
        menu.append(self.apply_item)
        open_item = Gtk.MenuItem(label="Open Cinnabar…")
        open_item.connect("activate", lambda *_: subprocess.Popen([str(PROJECT / "bin" / "cinnabar"), "gui"]))
        menu.append(open_item)
        auto = Gtk.CheckMenuItem(label="Start tray icon at login")
        auto.set_active(AUTOSTART.exists())
        auto.connect("toggled", self._on_autostart)
        menu.append(auto)
        restore = Gtk.MenuItem(label="Restore original desktop")
        restore.connect("activate", self._on_restore)
        menu.append(restore)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        self.menu = menu
        self.icon.set_primary_menu(menu)
        self.icon.set_secondary_menu(menu)
        self.icon.set_tooltip_text(f"Cinnabar — {current}" if current else "Cinnabar — switch theme")

    # ---- actions
    def _on_preset(self, item, slug, name):
        if not item.get_active() or self.busy:
            return
        if name == self._current_name():
            return
        self._run(["apply", slug], f"Applying {name}…", f"Applied {name}")

    def _apply_current(self):
        cur = T.CONFIG_DIR / "current.yaml"
        if cur.exists():
            self._run(["apply", str(cur)], "Re-applying…", "Theme re-applied")

    def _on_restore(self, *_):
        dlg = Gtk.MessageDialog(message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.OK_CANCEL,
                                text="Restore the original desktop?",
                                secondary_text="Reloads the settings snapshot taken before Cinnabar was first applied.")
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK:
            self._run(["restore"], "Restoring…", "Original desktop restored")

    def _on_autostart(self, item):
        if item.get_active():
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text((PROJECT / "data" / "cinnabar-tray.desktop").read_text().replace("@HERE@", str(PROJECT)))
        elif AUTOSTART.exists():
            AUTOSTART.unlink()

    def _run(self, args, busy_text, done_text):
        self.busy = True
        self.icon.set_tooltip_text(f"Cinnabar — {busy_text}")
        _notify("Cinnabar", busy_text)
        proc = Gio.Subprocess.new([str(PROJECT / "bin" / "cinnabar")] + args,
                                  Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)

        def done(p, res):
            ok, out, _ = p.communicate_utf8_finish(res)
            self.busy = False
            if p.get_successful():
                _notify("Cinnabar", done_text)
            else:
                tail = "\n".join((out or "").strip().splitlines()[-3:])
                _notify("Cinnabar failed", tail or "see the terminal output")
            self.rebuild_menu()
        proc.communicate_utf8_async(None, None, done)


def main(argv=None):
    Tray()
    Gtk.main()
    return 0
