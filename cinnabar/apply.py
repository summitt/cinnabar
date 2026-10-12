"""Apply a built theme to the running Cinnamon session (with backups)."""
import datetime as _dt
import json
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

from . import color as C
from . import tokens as T
from .builders import terminals, theme, wallpaper

CFG = T.CONFIG_DIR
BLUR_UUID = "BlurCinnamon@klangman"
BLUR_JSON = Path.home() / ".config/cinnamon/spices" / BLUR_UUID / f"{BLUR_UUID}.json"
INTER_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
FONT_DIR = Path.home() / ".local/share/fonts/Inter"


def sh(*args, check=True, capture=True):
    return subprocess.run(args, check=check, capture_output=capture, text=True)


def gget(schema, key):
    return sh("gsettings", "get", schema, key).stdout.strip()


def gset(schema, key, value):
    r = subprocess.run(["gsettings", "set", schema, key, str(value)], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[warn] gsettings {schema} {key}: {r.stderr.strip()}")
    return r.returncode == 0


def _quote(s):
    return "'" + str(s).replace("'", "\\'") + "'"


# ---------------------------------------------------------------- backups
def backup(log=print):
    CFG.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dumps = {"cinnamon": "/org/cinnamon/", "gnome-interface": "/org/gnome/desktop/interface/"}
    for name, path in dumps.items():
        data = sh("dconf", "dump", path).stdout
        orig = CFG / f"backup-original-{name}.dconf"
        if not orig.exists():
            orig.write_text(data)
        (CFG / "backups").mkdir(exist_ok=True)
        (CFG / "backups" / f"{stamp}-{name}.dconf").write_text(data)
    if BLUR_JSON.exists() and not (CFG / "backup-original-blur.json").exists():
        shutil.copy(BLUR_JSON, CFG / "backup-original-blur.json")
    log(f"[backup] dconf snapshots in {CFG}")


def restore(log=print):
    for name, path in {"cinnamon": "/org/cinnamon/", "gnome-interface": "/org/gnome/desktop/interface/"}.items():
        orig = CFG / f"backup-original-{name}.dconf"
        if orig.exists():
            subprocess.run(["dconf", "load", path], input=orig.read_text(), text=True, check=True)
            log(f"[restore] loaded {orig.name}")
    blur = CFG / "backup-original-blur.json"
    if blur.exists():
        shutil.copy(blur, BLUR_JSON)
        log("[restore] restored Blur Cinnamon settings")
    if shutil.which("flatpak"):
        subprocess.run(["flatpak", "override", "--user", "--unset-env=GTK_THEME",
                        "--nofilesystem=~/.themes", "--nofilesystem=~/.icons"], check=False)
        log("[restore] removed flatpak overrides")
    log("[restore] done — the original desktop settings are back")


# ---------------------------------------------------------------- fonts
def font_installed(family):
    out = sh("fc-list", ":family", check=False).stdout.lower()
    return family.lower() in out


def ensure_inter(log=print):
    if font_installed("Inter"):
        return True
    log("[fonts] Inter not installed — downloading from GitHub (rsms/inter v4.1)")
    try:
        tmp = CFG / "Inter-4.1.zip"
        urllib.request.urlretrieve(INTER_URL, tmp)
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp) as z:
            for m in z.namelist():
                if m.startswith("extras/otf/") and m.endswith(".otf"):
                    (FONT_DIR / Path(m).name).write_bytes(z.read(m))
        tmp.unlink()
        sh("fc-cache", "-f", check=False)
        log(f"[fonts] installed Inter into {FONT_DIR}")
        return True
    except Exception as e:  # network failure etc.
        log(f"[fonts] could not install Inter ({e}); falling back to Noto Sans")
        return False


def _font_fallback(tokens):
    for key in ("fonts.ui", "fonts.title", "fonts.document"):
        v = tokens.get(key, "")
        if v.startswith("Inter"):
            tokens.set(key, v.replace("Inter", "Noto Sans", 1))


# ---------------------------------------------------------------- panels
def _panel_positions():
    """{panel_id: position} from org.cinnamon panels-enabled."""
    raw = gget("org.cinnamon", "panels-enabled")
    out = {}
    for item in json.loads(raw.replace("'", '"')):
        pid, _mon, pos = item.split(":")
        out[int(pid)] = pos
    return out


def _set_panels(tokens, log):
    pos = _panel_positions()
    heights = dict(h.split(":") for h in json.loads(gget("org.cinnamon", "panels-height").replace("'", '"')))
    for pid, p in pos.items():
        if p == "top":
            heights[str(pid)] = str(tokens.get("panel.top_height"))
        elif p == "bottom" and tokens.get("panel.dock"):
            heights[str(pid)] = str(tokens.get("panel.dock_height"))
    gset("org.cinnamon", "panels-height", json.dumps([f"{k}:{v}" for k, v in heights.items()]).replace('"', "'"))
    try:
        sizes = json.loads(gget("org.cinnamon", "panel-zone-icon-sizes").strip("'"))
    except Exception:
        sizes = []
    by_id = {s.get("panelId"): s for s in sizes}
    for pid, p in pos.items():
        if p == "bottom" and tokens.get("panel.dock"):
            entry = by_id.setdefault(pid, {"panelId": pid, "left": 0, "center": 0, "right": 0})
            entry["center"] = int(tokens.get("panel.dock_icon_size"))
            entry["left"] = entry["right"] = int(tokens.get("panel.dock_icon_size"))
        elif p == "top":
            entry = by_id.setdefault(pid, {"panelId": pid, "left": 0, "center": 0, "right": 0})
            for z in ("left", "center", "right"):
                entry[z] = 16
    gset("org.cinnamon", "panel-zone-icon-sizes", _quote(json.dumps(list(by_id.values()))))
    log(f"[panels] heights {heights}, dock icons {tokens.get('panel.dock_icon_size')}px")


# ---------------------------------------------------------------- blur
def _rgb_str(hexcol):
    r, g, b, _ = C.parse(hexcol)
    return "rgb(%d,%d,%d)" % (round(r * 255), round(g * 255), round(b * 255))


def _set_blur(tokens, log):
    c = tokens.palette
    enabled = json.loads(gget("org.cinnamon", "enabled-extensions").replace("'", '"'))
    if not tokens.get("panel.blur"):
        if BLUR_UUID in enabled:
            enabled.remove(BLUR_UUID)
            gset("org.cinnamon", "enabled-extensions", json.dumps(enabled).replace('"', "'"))
        log("[blur] disabled")
        return
    ext_dir = Path.home() / ".local/share/cinnamon/extensions" / BLUR_UUID
    if not ext_dir.exists():
        log("[blur] Blur Cinnamon extension not installed (install it from Extensions > Download); skipping")
        return
    if BLUR_UUID not in enabled:
        enabled.append(BLUR_UUID)
        gset("org.cinnamon", "enabled-extensions", json.dumps(enabled).replace('"', "'"))
        time.sleep(1.5)  # let Cinnamon create the settings file
    if not BLUR_JSON.exists():
        log("[blur] settings file not created yet; re-run apply once Cinnamon has loaded the extension")
        return
    data = json.loads(BLUR_JSON.read_text())
    pos = _panel_positions()
    pct = lambda x: int(round(float(x) * 100))
    values = {
        "enable-panels-effects": True, "enable-panels-override": True, "allow-transparent-color-panels": True,
        "panels-blendColor": _rgb_str(c["bg_dark"]), "panels-opacity": pct(tokens.get("panel.top_opacity")),
        "panels-blurType": 8, "panels-radius": 9, "no-panel-effects-maximized": False,
        "enable-panel-unique-settings": True,
        "panel-unique-settings": [
            {"enabled": pos.get(i) == "top" or (pos.get(i) == "bottom" and not tokens.get("panel.dock")),
             "panels": i, "monitors": 100, "opacity": pct(tokens.get("panel.top_opacity")),
             "color": _rgb_str(c["bg_dark"]), "blurtype": 8, "radius": 9, "saturation": 100}
            for i in range(1, 5)],
        "enable-popup-effects": True, "enable-popup-override": True, "allow-transparent-color-popup": True,
        "popup-blendColor": _rgb_str(c["surface"]), "popup-opacity": pct(tokens.get("panel.popup_opacity")),
        "popup-accent-opacity": 60, "popup-blurType": 8, "popup-radius": 20,
        "enable-notification-effects": True, "enable-notification-override": True, "allow-transparent-color-notifications": True,
        "notification-blendColor": _rgb_str(c["surface"]), "notification-opacity": 92, "notification-blurType": 8,
        "enable-tooltips-effects": True, "enable-tooltips-override": True, "allow-transparent-color-tooltips": True,
        "tooltips-blendColor": _rgb_str(c["surface"]), "tooltips-opacity": 95, "tooltips-blurType": 8,
        "enable-osd-effects": True, "enable-osd-override": True, "allow-transparent-color-osd": True,
        "osd-blendColor": _rgb_str(c["surface"]), "osd-opacity": 85, "osd-blurType": 8,
        "enable-appswitcher-effects": True, "enable-appswitcher-override": True, "allow-transparent-color-switcher": True,
        "appswitcher-blendColor": _rgb_str(c["surface"]), "appswitcher-opacity": 90, "appswitcher-blurType": 8,
    }
    n = 0
    for k, v in values.items():
        if k in data and isinstance(data[k], dict):
            data[k]["value"] = v
            n += 1
    BLUR_JSON.write_text(json.dumps(data, indent=4))
    log(f"[blur] configured Blur Cinnamon ({n} keys): translucent top panel, menus, notifications")


# ---------------------------------------------------------------- flatpak
def _flatpak(tokens, log):
    if not tokens.get("flatpak") or not shutil.which("flatpak"):
        return
    r = subprocess.run(["flatpak", "override", "--user", "--filesystem=~/.themes:ro", "--filesystem=~/.icons:ro",
                        "--filesystem=xdg-data/icons:ro", f"--env=GTK_THEME={T.THEME_NAME}"],
                       capture_output=True, text=True)
    log("[flatpak] GTK apps in flatpaks will use the theme" if r.returncode == 0 else f"[flatpak] override failed: {r.stderr.strip()}")


def restart_cinnamon(log=print):
    """Soft-restart the Cinnamon shell (windows stay open) so Muffin reloads the frame CSS."""
    r = subprocess.run(["dbus-send", "--session", "--print-reply", "--dest=org.Cinnamon", "/org/Cinnamon",
                        "org.Cinnamon.RestartCinnamon", "boolean:true"], capture_output=True, text=True)
    log("[apply] restarting Cinnamon so window frames pick up the new decorations" if r.returncode == 0
        else f"[apply] could not restart Cinnamon automatically ({r.stderr.strip()}); press Ctrl+Alt+Esc")


# ---------------------------------------------------------------- main
def apply(tokens, log=print, do_wallpaper=True, do_terminals=True, restart=True):
    backup(log)
    if any(str(tokens.get(k, "")).startswith("Inter") for k in ("fonts.ui", "fonts.title", "fonts.document")):
        if not ensure_inter(log):
            _font_fallback(tokens)

    dst = theme.build(tokens, log=log)
    name = T.THEME_NAME
    base = "Mint-Y-Dark" if tokens.dark else "Mint-Y"

    # GTK + Cinnamon + WM theme (toggle through the base so a re-apply reloads)
    iface = "org.cinnamon.desktop.interface"
    wm = "org.cinnamon.desktop.wm.preferences"
    was_active = gget(iface, "gtk-theme").strip("'") == name
    gset(iface, "gtk-theme", base)
    gset("org.cinnamon.theme", "name", base)
    gset(wm, "theme", "Mint-Y")
    time.sleep(0.4)
    gset(iface, "gtk-theme", name)
    gset("org.cinnamon.theme", "name", name)
    gset(wm, "theme", name)
    gset(iface, "icon-theme", tokens.get("icons"))
    gset(iface, "cursor-theme", tokens.get("cursor.theme"))
    gset(iface, "cursor-size", str(tokens.get("cursor.size", 24)))
    gset(iface, "font-name", tokens.get("fonts.ui"))
    gset("org.gnome.desktop.interface", "document-font-name", tokens.get("fonts.document"))
    gset("org.gnome.desktop.interface", "monospace-font-name", tokens.get("fonts.mono"))
    gset("org.gnome.desktop.interface", "font-name", tokens.get("fonts.ui"))
    gset(wm, "titlebar-font", tokens.get("fonts.title"))
    gset(wm, "button-layout", "close,minimize,maximize:" if tokens.get("window.buttons") == "left" else ":minimize,maximize,close")
    gset("org.cinnamon.desktop.interface", "gtk-overlay-scrollbars", "true")
    log(f"[apply] GTK/Cinnamon/WM theme -> {name}; icons {tokens.get('icons')}; fonts {tokens.get('fonts.ui')}")

    _set_panels(tokens, log)
    _set_blur(tokens, log)
    _flatpak(tokens, log)

    if do_wallpaper and tokens.get("wallpaper.mode") != "keep":
        if tokens.get("wallpaper.mode") == "file" and tokens.get("wallpaper.file"):
            wp = Path(tokens.get("wallpaper.file")).expanduser()
        else:
            wp = wallpaper.generate(tokens)
        gset("org.cinnamon.desktop.background", "picture-uri", f"file://{wp}")
        gset("org.cinnamon.desktop.background", "picture-options", "zoom")
        log(f"[wallpaper] {wp}")
    if do_terminals:
        terminals.build(tokens, log=log)

    if was_active and restart:
        # GTK caches a theme's CSS per process by name, so Muffin (inside the cinnamon
        # process) keeps the previous build of 'Cinnabar' until Cinnamon restarts.
        restart_cinnamon(log)
    T.save(tokens, CFG / "current.yaml")
    log(f"[apply] done — preset '{tokens['name']}' is live. Undo anytime with: cinnabar restore")
    return dst
