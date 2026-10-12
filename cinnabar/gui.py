"""Cinnabar app — GTK4 / libadwaita front end for the theme engine."""
import math
import os
import re
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import __version__  # noqa: E402
from . import color as C  # noqa: E402
from . import tokens as T  # noqa: E402

APP_ID = "io.github.nullop.Cinnabar"
USER_PRESETS = T.CONFIG_DIR / "presets"

COLOR_ROWS = [
    ("bg", "Background", "Window and panel base"), ("fg", "Text", "Foreground text"),
    ("accent", "Accent", "Selection, focus, active indicators"),
    ("red", "Red", "Close light, errors"), ("yellow", "Yellow", "Minimize light, warnings"),
    ("green", "Green", "Zoom light, success"), ("orange", "Orange", ""), ("blue", "Blue", ""),
    ("purple", "Purple", "Gradient border end"), ("teal", "Teal", ""),
]


def rgba_from_hex(h):
    c = Gdk.RGBA()
    c.parse(h)
    return c


def hex_from_rgba(c):
    return C.to_hex(c.red, c.green, c.blue)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "custom"


def installed_themes(kind):
    """kind: 'icons' or 'cursors'."""
    found = set()
    for base in (Path.home() / ".icons", Path.home() / ".local/share/icons", Path("/usr/share/icons")):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if not (d / "index.theme").exists():
                continue
            if kind == "cursors" and (d / "cursors").is_dir():
                found.add(d.name)
            elif kind == "icons" and not (d / "cursors").is_dir() and d.name not in ("default", "hicolor", "locolor"):
                found.add(d.name)
    return sorted(found)


# ---------------------------------------------------------------- preview
class Preview(Gtk.DrawingArea):
    """A cairo mock-up of the desktop: panel, dock, a window with lights and border, a menu."""

    def __init__(self, get_tokens):
        super().__init__()
        self.get_tokens = get_tokens
        self.set_content_height(260)
        self.set_draw_func(self._draw)
        self.add_css_class("card")

    @staticmethod
    def _set(cr, hexcol, a=1.0):
        r, g, b, _ = C.parse(hexcol)
        cr.set_source_rgba(r, g, b, a)

    @staticmethod
    def _rrect(cr, x, y, w, h, r):
        r = max(0, min(r, w / 2, h / 2))
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw(self, area, cr, W, H):
        t = self.get_tokens()
        c = t.palette
        import cairo
        # wallpaper
        g = cairo.LinearGradient(0, 0, W, H)
        for stop, col in ((0, C.darken(c["bg"], 0.04)), (0.55, C.mix(c["bg"], c["accent"], 0.45)), (1, C.mix(c["bg"], c.get("purple", c["accent"]), 0.35))):
            r, gg, b, _ = C.parse(col)
            g.add_color_stop_rgb(stop, r, gg, b)
        self._rrect(cr, 0, 0, W, H, 12)
        cr.set_source(g)
        cr.fill()
        s = 0.55  # pixel scale of the mock-up
        # top panel
        ph = t.get("panel.top_height") * s
        self._set(cr, c["bg_dark"], t.get("panel.top_opacity"))
        cr.rectangle(0, 0, W, ph)
        cr.fill()
        self._set(cr, c["fg"], 0.9)
        cr.arc(14, ph / 2, 4, 0, 2 * math.pi)
        cr.fill()
        cr.set_font_size(8)
        cr.move_to(W - 70, ph / 2 + 3)
        cr.show_text("Mon 13:50")
        # window
        R = t.get("window.radius") * s
        B = max(1, t.get("window.border") * s)
        th = t.get("window.titlebar_height") * s
        x, y, w, h = 40, ph + 22, W * 0.52, H - ph - 80
        # shadow
        self._set(cr, "#000000", 0.35)
        self._rrect(cr, x + 2, y + 6, w, h, R)
        cr.fill()
        # border
        if t.get("window.border_focused") == "gradient":
            bg = cairo.LinearGradient(x, y, x + w, y + h)
            for stop, col in ((0, c["wm_border_focused"]), (1, c["wm_border_gradient_to"])):
                r, gg, b, _ = C.parse(col)
                bg.add_color_stop_rgb(stop, r, gg, b)
            cr.set_source(bg)
        else:
            self._set(cr, c["wm_border_focused"])
        self._rrect(cr, x, y, w, h, R)
        cr.fill()
        # titlebar + body
        self._set(cr, c["wm_bg"])
        self._rrect(cr, x + B, y + B, w - 2 * B, h - 2 * B, max(0, R - B))
        cr.fill()
        self._set(cr, c["bg"])
        cr.rectangle(x + B, y + B + th, w - 2 * B, h - 2 * B - th)
        cr.fill()
        self._set(cr, c["surface"])
        self._rrect(cr, x + B, y + B + th, w - 2 * B, h - 2 * B - th, max(0, R - B))
        cr.fill()
        cr.rectangle(x + B, y + B + th, w - 2 * B, 10)
        cr.fill()
        # traffic lights
        bs = t.get("window.button_size") * s
        lights = [c["red"], c["yellow"], c["green"]]
        if t.get("window.buttons") != "left":
            lights = list(reversed(lights))
        for i, col in enumerate(lights):
            lx = (x + B + 10 + i * (bs + 6)) if t.get("window.buttons") == "left" else (x + w - B - 10 - i * (bs + 6) - bs)
            self._set(cr, col)
            cr.arc(lx + bs / 2, y + B + th / 2, bs / 2, 0, 2 * math.pi)
            cr.fill()
        self._set(cr, c["wm_title"])
        cr.set_font_size(8)
        cr.move_to(x + w / 2 - 18, y + B + th / 2 + 3)
        cr.show_text("Finder")
        # accent selection row + text lines
        self._set(cr, c["accent"])
        self._rrect(cr, x + B + 12, y + B + th + 18, w * 0.45, 12, t.get("controls.radius") * s)
        cr.fill()
        self._set(cr, c["fg"], 0.6)
        for i in range(4):
            cr.rectangle(x + B + 12, y + B + th + 40 + i * 12, w * (0.35 + 0.08 * (i % 3)), 4)
            cr.fill()
        # popup menu
        mx, my, mw, mh = x + w + 24, ph + 30, W - x - w - 50, 110
        self._set(cr, "#000000", 0.3)
        self._rrect(cr, mx + 2, my + 5, mw, mh, t.get("controls.popup_radius") * s)
        cr.fill()
        self._set(cr, c["surface"], t.get("panel.popup_opacity"))
        self._rrect(cr, mx, my, mw, mh, t.get("controls.popup_radius") * s)
        cr.fill()
        self._set(cr, c["fg"], 0.12)
        cr.set_line_width(1)
        self._rrect(cr, mx + 0.5, my + 0.5, mw - 1, mh - 1, t.get("controls.popup_radius") * s)
        cr.stroke()
        for i in range(4):
            if i == 1:
                self._set(cr, c["accent"])
                self._rrect(cr, mx + 6, my + 8 + i * 24, mw - 12, 20, t.get("controls.radius") * s)
                cr.fill()
                self._set(cr, c["accent_fg"], 0.9)
            else:
                self._set(cr, c["fg"], 0.7)
            cr.rectangle(mx + 14, my + 16 + i * 24, mw * 0.5, 4)
            cr.fill()
        # dock
        if t.get("panel.dock"):
            dh = t.get("panel.dock_height") * s
            dw = W * 0.5
            dx, dy = (W - dw) / 2, H - dh - 6
            self._set(cr, c["bg_dark"], t.get("panel.dock_opacity"))
            self._rrect(cr, dx, dy, dw, dh, t.get("panel.dock_radius") * s)
            cr.fill()
            self._set(cr, c["fg"], 0.12)
            self._rrect(cr, dx + 0.5, dy + 0.5, dw - 1, dh - 1, t.get("panel.dock_radius") * s)
            cr.stroke()
            isz = t.get("panel.dock_icon_size") * s
            cols = [c["accent"], c["red"], c["green"], c["purple"], c["orange"], c["teal"], c["blue"]]
            for i, col in enumerate(cols):
                ix = dx + 10 + i * (isz + 8)
                if ix + isz > dx + dw - 8:
                    break
                self._set(cr, col, 0.9)
                self._rrect(cr, ix, dy + (dh - isz) / 2, isz, isz, isz * 0.25)
                cr.fill()
                if i == 0:
                    self._set(cr, c["accent"])
                    self._rrect(cr, ix, dy + dh - 3, isz, 2, 1)
                    cr.fill()


# ---------------------------------------------------------------- window
class CinnabarWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Cinnabar", default_width=1060, default_height=760)
        self.tokens = self._initial_tokens()
        self._building = False
        self._widgets = {}

        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        self.split = Adw.NavigationSplitView(min_sidebar_width=220, max_sidebar_width=280)
        self.toast.set_child(self.split)

        # ---- sidebar: presets
        side = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title="Presets"))
        side.add_top_bar(hb)
        self.preset_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.preset_list.add_css_class("navigation-sidebar")
        self.preset_list.connect("row-selected", self._on_preset_selected)
        sc = Gtk.ScrolledWindow(child=self.preset_list, vexpand=True)
        side.set_content(sc)
        self.split.set_sidebar(Adw.NavigationPage(child=side, title="Presets"))

        # ---- content
        content = Adw.ToolbarView()
        hb2 = Adw.HeaderBar()
        self.title_w = Adw.WindowTitle(title="Cinnabar", subtitle=self.tokens["name"])
        hb2.set_title_widget(self.title_w)
        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", self._on_apply)
        hb2.pack_end(self.apply_btn)
        menu = Gio.Menu()
        menu.append("Save as preset…", "win.save")
        menu.append("Preview wallpaper", "win.wallpaper")
        menu.append("Open theme folder", "win.open_theme")
        menu.append("Restore original desktop", "win.restore")
        menu.append("About Cinnabar", "win.about")
        hb2.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))
        content.add_top_bar(hb2)
        for name, cb in (("save", self._on_save), ("wallpaper", self._on_wallpaper), ("open_theme", self._on_open_theme),
                         ("restore", self._on_restore), ("about", self._on_about)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

        page = Adw.PreferencesPage()
        content.set_content(page)
        self.split.set_content(Adw.NavigationPage(child=content, title="Theme"))

        self.preview = Preview(lambda: self.tokens)
        pg = Adw.PreferencesGroup(title="Preview")
        pg.add(self.preview)
        page.add(pg)
        self._build_colors(page)
        self._build_window(page)
        self._build_panel(page)
        self._build_fonts(page)
        self._build_misc(page)

        self._refresh_presets()
        self._load_widgets()

    # ---- helpers
    def _initial_tokens(self):
        cur = T.CONFIG_DIR / "current.yaml"
        try:
            return T.load(cur if cur.exists() else "sequoia-dark")
        except Exception:
            return T.Tokens(T.deep_merge(T.DEFAULTS, {}))

    def _set(self, key, value):
        if self._building:
            return
        self.tokens.set(key, value)
        self.preview.queue_draw()
        self.title_w.set_subtitle(self.tokens["name"] + " (edited)")

    def _reg(self, key, widget, getter, setter):
        self._widgets[key] = (widget, getter, setter)

    # ---- groups
    def _build_colors(self, page):
        g = Adw.PreferencesGroup(title="Colors", description="Everything else is derived from these")
        row = Adw.ComboRow(title="Variant", subtitle="Base theme family", model=Gtk.StringList.new(["Dark", "Light"]))
        row.connect("notify::selected", lambda r, _: self._set("variant", "dark" if r.get_selected() == 0 else "light"))
        self._reg("variant", row, None, lambda w, v: w.set_selected(0 if v == "dark" else 1))
        g.add(row)
        for key, title, sub in COLOR_ROWS:
            r = Adw.ActionRow(title=title, subtitle=sub)
            btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
            btn.connect("notify::rgba", lambda b, _, k=key: self._set(f"colors.{k}", hex_from_rgba(b.get_rgba())))
            r.add_suffix(btn)
            self._reg(f"colors.{key}", btn, None, lambda w, v: w.set_rgba(rgba_from_hex(v)))
            g.add(r)
        page.add(g)

    def _spin(self, g, key, title, sub, lo, hi, step=1):
        r = Adw.SpinRow.new_with_range(lo, hi, step)
        r.set_title(title)
        r.set_subtitle(sub)
        r.connect("notify::value", lambda w, _: self._set(key, int(w.get_value())))
        self._reg(key, r, None, lambda w, v: w.set_value(float(v)))
        g.add(r)
        return r

    def _switch(self, g, key, title, sub=""):
        r = Adw.SwitchRow(title=title, subtitle=sub)
        r.connect("notify::active", lambda w, _: self._set(key, bool(w.get_active())))
        self._reg(key, r, None, lambda w, v: w.set_active(bool(v)))
        g.add(r)
        return r

    def _scale(self, g, key, title, sub, lo=0.0, hi=1.0):
        r = Adw.ActionRow(title=title, subtitle=sub)
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 0.05)
        sc.set_size_request(180, -1)
        sc.set_draw_value(True)
        sc.set_digits(2)
        sc.set_valign(Gtk.Align.CENTER)
        sc.connect("value-changed", lambda w: self._set(key, round(w.get_value(), 2)))
        r.add_suffix(sc)
        self._reg(key, sc, None, lambda w, v: w.set_value(float(v)))
        g.add(r)

    def _combo(self, g, key, title, sub, options, values=None):
        values = values or options
        r = Adw.ComboRow(title=title, subtitle=sub, model=Gtk.StringList.new(options))
        r.connect("notify::selected", lambda w, _: self._set(key, values[w.get_selected()]))
        self._reg(key, r, None, lambda w, v: w.set_selected(values.index(v) if v in values else 0))
        g.add(r)
        return r

    def _build_window(self, page):
        g = Adw.PreferencesGroup(title="Windows", description="Muffin frames and GTK client-side decorations")
        self._spin(g, "window.radius", "Corner radius", "px", 0, 24)
        self._switch(g, "window.round_bottom", "Round bottom corners", "X11 clips the client area at the bottom corners")
        self._spin(g, "window.border", "Border width", "Hyprland-style frame border, px", 0, 6)
        self._combo(g, "window.border_focused", "Focused border", "", ["Accent color", "Gradient (accent → purple)"], ["accent", "gradient"])
        self._spin(g, "window.titlebar_height", "Titlebar height", "px", 24, 56)
        self._spin(g, "window.button_size", "Traffic light size", "px", 8, 18)
        self._combo(g, "window.buttons", "Window buttons", "", ["Left (macOS)", "Right"], ["left", "right"])
        self._spin(g, "controls.radius", "Control radius", "buttons, entries, menu items", 0, 14)
        self._spin(g, "controls.popup_radius", "Popup radius", "menus, notifications, dialogs", 0, 24)
        page.add(g)

    def _build_panel(self, page):
        g = Adw.PreferencesGroup(title="Panel and dock")
        self._spin(g, "panel.top_height", "Top panel height", "px", 20, 48)
        self._scale(g, "panel.top_opacity", "Top panel opacity", "blurred behind when Blur Cinnamon is enabled")
        self._switch(g, "panel.blur", "Blur", "Uses the Blur Cinnamon extension (panels, menus, notifications)")
        self._switch(g, "panel.dock", "Bottom panel as floating dock", "transparent panel with a rounded pill for the window list")
        self._spin(g, "panel.dock_height", "Dock height", "px", 32, 80)
        self._spin(g, "panel.dock_icon_size", "Dock icon size", "px", 16, 64)
        self._scale(g, "panel.dock_opacity", "Dock opacity", "")
        self._spin(g, "panel.dock_radius", "Dock radius", "px", 0, 40)
        self._scale(g, "panel.popup_opacity", "Menu opacity", "popup menus, app menu")
        page.add(g)

    def _font_row(self, g, key, title):
        r = Adw.ActionRow(title=title)
        btn = Gtk.FontDialogButton(dialog=Gtk.FontDialog(), valign=Gtk.Align.CENTER)
        btn.connect("notify::font-desc", lambda b, _: self._set(key, b.get_font_desc().to_string()))
        r.add_suffix(btn)
        self._reg(key, btn, None, lambda w, v: w.set_font_desc(Pango.FontDescription.from_string(v)))
        g.add(r)

    def _build_fonts(self, page):
        g = Adw.PreferencesGroup(title="Fonts", description="Inter is downloaded automatically if missing")
        for key, title in (("fonts.ui", "Interface"), ("fonts.title", "Window titles"), ("fonts.document", "Documents"), ("fonts.mono", "Monospace / terminals")):
            self._font_row(g, key, title)
        page.add(g)

    def _build_misc(self, page):
        g = Adw.PreferencesGroup(title="Icons, cursor, wallpaper")
        icons = installed_themes("icons")
        cursors = installed_themes("cursors")
        self._combo(g, "icons", "Icon theme", "", icons or ["Papirus-Dark"])
        self._combo(g, "cursor.theme", "Cursor theme", "", cursors or ["Bibata-Modern-Classic"])
        self._spin(g, "cursor.size", "Cursor size", "px", 16, 48)
        self._combo(g, "wallpaper.mode", "Wallpaper", "", ["Generate from palette", "Keep current", "Use a file"], ["generate", "keep", "file"])
        self._combo(g, "wallpaper.style", "Generated style", "", ["Soft color fields", "Plain gradient"], ["blobs", "gradient"])
        fr = Adw.ActionRow(title="Wallpaper file", subtitle="used when Wallpaper = Use a file")
        fb = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        fb.connect("clicked", self._on_choose_wallpaper)
        fr.add_suffix(fb)
        self.wp_row = fr
        self._reg("wallpaper.file", fr, None, lambda w, v: w.set_subtitle(str(v) if v else "used when Wallpaper = Use a file"))
        g.add(fr)
        page.add(g)
        g2 = Adw.PreferencesGroup(title="Apps and terminals")
        self._switch(g2, "terminals.kitty", "kitty", "write ~/.config/kitty/cinnabar-theme.conf and include it")
        self._switch(g2, "terminals.alacritty", "Alacritty", "write and import ~/.config/alacritty/cinnabar-theme.toml")
        self._switch(g2, "terminals.ghostty", "Ghostty", "write ~/.config/ghostty/themes/cinnabar")
        self._switch(g2, "flatpak", "Flatpak apps", "give sandboxed GTK apps access to the theme")
        page.add(g2)

    # ---- state <-> widgets
    def _load_widgets(self):
        self._building = True
        try:
            for key, (w, _g, setter) in self._widgets.items():
                v = self.tokens.get(key)
                if v is None and key == "wallpaper.file":
                    v = ""
                if v is not None:
                    try:
                        setter(w, v)
                    except Exception as e:  # unknown icon theme etc.
                        print("widget", key, e)
        finally:
            self._building = False
        self.title_w.set_subtitle(self.tokens["name"])
        self.preview.queue_draw()

    def _refresh_presets(self):
        self._building = True
        while (row := self.preset_list.get_row_at_index(0)) is not None:
            self.preset_list.remove(row)
        self._preset_paths = []
        select = None
        for slug, path in T.list_presets().items():
            try:
                t = T.load(path)
            except Exception:
                continue
            row = Adw.ActionRow(title=t["name"], subtitle=("light" if t["variant"] == "light" else "dark") + (" · user" if path.parent == USER_PRESETS else ""))
            sw = Gtk.DrawingArea(content_width=22, content_height=22, valign=Gtk.Align.CENTER)
            sw.set_draw_func(self._draw_swatch, (t.palette["bg"], t.palette["accent"]))
            row.add_prefix(sw)
            row.set_activatable(True)
            self.preset_list.append(row)
            self._preset_paths.append(path)
            if t["name"] == self.tokens["name"]:
                select = row
        if select is not None:
            self.preset_list.select_row(select)
        self._building = False

    @staticmethod
    def _draw_swatch(area, cr, w, h, cols):
        bg, ac = cols
        r, g, b, _ = C.parse(bg)
        cr.set_source_rgb(r, g, b)
        cr.arc(w / 2, h / 2, w / 2, 0, 2 * math.pi)
        cr.fill()
        r, g, b, _ = C.parse(ac)
        cr.set_source_rgb(r, g, b)
        cr.arc(w / 2, h / 2, w / 4, 0, 2 * math.pi)
        cr.fill()

    def _on_preset_selected(self, box, row):
        if row is None or self._building:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._preset_paths):
            self.tokens = T.load(self._preset_paths[idx])
            self._load_widgets()

    # ---- actions
    def _on_choose_wallpaper(self, *_):
        dlg = Gtk.FileDialog(title="Choose wallpaper")
        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            self._set("wallpaper.file", f.get_path())
            self._set("wallpaper.mode", "file")
            self._load_widgets()
        dlg.open(self, None, done)

    def _on_apply(self, *_):
        from . import apply as A
        self.apply_btn.set_sensitive(False)
        self.apply_btn.set_label("Applying…")
        tokens = T.Tokens(T.deep_merge(T.DEFAULTS, self.tokens.data))
        lines = []

        def log(msg):
            lines.append(msg)
            GLib.idle_add(self.title_w.set_subtitle, msg[:70])

        def work():
            err = None
            try:
                A.apply(tokens, log=log)
            except Exception as e:  # report in UI
                err = e
            GLib.idle_add(finish, err)

        def finish(err):
            self.apply_btn.set_sensitive(True)
            self.apply_btn.set_label("Apply")
            self.title_w.set_subtitle(self.tokens["name"])
            self.toast.add_toast(Adw.Toast(title=f"Applied {tokens['name']}" if err is None else f"Apply failed: {err}", timeout=4))
            return False

        threading.Thread(target=work, daemon=True).start()

    def _on_save(self, *_):
        dlg = Adw.AlertDialog(heading="Save preset", body="Saved presets live in ~/.config/cinnabar/presets")
        entry = Gtk.Entry(text=self.tokens["name"], activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("save")

        def resp(d, r):
            if r != "save":
                return
            name = entry.get_text().strip() or "Custom"
            self.tokens.data["name"] = name
            self.tokens.data["slug"] = slugify(name)
            T.save(self.tokens, USER_PRESETS / f"{slugify(name)}.yaml")
            self._refresh_presets()
            self.title_w.set_subtitle(name)
            self.toast.add_toast(Adw.Toast(title=f"Saved preset {name}"))
        dlg.connect("response", resp)
        dlg.present(self)

    def _on_wallpaper(self, *_):
        from .builders import wallpaper
        tokens = T.Tokens(T.deep_merge(T.DEFAULTS, self.tokens.data))
        out = Path(GLib.get_user_cache_dir()) / "cinnabar-preview.png"

        def work():
            p = wallpaper.generate(tokens, path=out)
            GLib.idle_add(lambda: Gtk.FileLauncher(file=Gio.File.new_for_path(str(p))).launch(self, None, None))
        threading.Thread(target=work, daemon=True).start()
        self.toast.add_toast(Adw.Toast(title="Rendering wallpaper preview…"))

    def _on_open_theme(self, *_):
        d = Path.home() / ".themes" / T.THEME_NAME
        Gtk.FileLauncher(file=Gio.File.new_for_path(str(d if d.exists() else T.PROJECT_DIR))).launch(self, None, None)

    def _on_restore(self, *_):
        dlg = Adw.AlertDialog(heading="Restore original desktop?",
                              body="Reloads the dconf snapshot taken before the first apply and removes the flatpak overrides.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("restore", "Restore")
        dlg.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(d, r):
            if r == "restore":
                from . import apply as A
                A.restore(log=print)
                self.toast.add_toast(Adw.Toast(title="Original settings restored"))
        dlg.connect("response", resp)
        dlg.present(self)

    def _on_about(self, *_):
        Adw.AboutDialog(application_name="Cinnabar", application_icon="preferences-desktop-theme",
                        developer_name="nullop", version=__version__,
                        comments="A token-driven theme engine that makes Cinnamon look like macOS with Hyprland-style window borders.",
                        license_type=Gtk.License.MIT_X11).present(self)


class CinnabarApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window or CinnabarWindow(self)
        win.present()


def main(argv=None):
    return CinnabarApp().run(argv or [])
