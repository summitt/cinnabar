"""Login screen (LightDM + slick-greeter) theming.

The greeter runs as the `lightdm` user, so nothing under ~/ is usable: the GTK theme,
the background and the greeter config all have to be installed system-wide.  The user
side stages everything under ~/.config/cinnabar/login-stage, then a small root helper
(run through pkexec, or sudo on a terminal) copies it into place and writes
/etc/lightdm/slick-greeter.conf, keeping a backup of the original.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import color as C
from . import tokens as T
from .builders import theme, wallpaper

STAGE = T.CONFIG_DIR / "login-stage"
ROOT_HELPER = Path(__file__).resolve().parent / "login_root.py"
SYSTEM_HELPER = Path("/usr/local/lib/cinnabar/login_root.py")
LOGIN_THEME = "Cinnabar-Login"


def _system_font(tokens):
    """Fonts in ~/.local/share/fonts are invisible to the greeter; fall back if needed."""
    font = tokens.get("login.font") or tokens.get("fonts.ui", "Noto Sans 10")
    family = font.rsplit(" ", 1)[0].replace(" Semi-Bold", "").replace(" Bold", "")
    try:
        out = subprocess.run(["fc-list", ":family", "file"], capture_output=True, text=True).stdout
        if not any(l.startswith("/usr/share/fonts") and family.lower() in l.lower() for l in out.splitlines()):
            return font.replace(family, "Noto Sans")
    except OSError:
        pass
    return font


def _background(tokens, log):
    mode = tokens.get("login.background", "desktop")
    if mode == "file" and tokens.get("login.background_file"):
        return Path(tokens.get("login.background_file")).expanduser(), None
    if mode == "color":
        return None, tokens.palette["bg"]
    if mode == "generate":
        return wallpaper.generate(tokens, path=STAGE / "background.png"), None
    # desktop: whatever is on the desktop right now
    uri = subprocess.run(["gsettings", "get", "org.cinnamon.desktop.background", "picture-uri"],
                         capture_output=True, text=True).stdout.strip().strip("'")
    p = Path(uri.replace("file://", "")) if uri.startswith("file://") else None
    if p and p.exists():
        return p, None
    log("[login] desktop wallpaper not found; generating one")
    return wallpaper.generate(tokens, path=STAGE / "background.png"), None


def stage(tokens, log=print):
    """Build the payload for the root helper; returns the path of the manifest."""
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    src = theme.theme_dir()
    if not src.exists():
        theme.build(tokens, log=log)
    shutil.copytree(src, STAGE / LOGIN_THEME, ignore=shutil.ignore_patterns("cinnamon", "metacity-1", "gtk-4.0", "libadwaita-*"))
    bg_path, bg_color = _background(tokens, log)
    if bg_path and bg_path.resolve() != (STAGE / "background.png").resolve():
        shutil.copy(bg_path, STAGE / ("background" + bg_path.suffix.lower()))
        bg_name = "background" + bg_path.suffix.lower()
    elif bg_path:
        bg_name = "background.png"
    else:
        bg_name = None
    icons = tokens.get("login.icons") or tokens.get("icons")
    if not any((Path(d) / icons).exists() for d in ("/usr/share/icons",)):
        log(f"[login] icon theme {icons} is not installed system-wide; the greeter will use Mint-Y")
        icons = "Mint-Y"
    conf = {
        "theme-name": LOGIN_THEME,
        "icon-theme-name": icons,
        "font-name": _system_font(tokens),
        "cursor-theme-name": tokens.get("cursor.theme") if (Path("/usr/share/icons") / tokens.get("cursor.theme", "")).exists() else None,
        "background": f"/usr/share/backgrounds/cinnabar/{bg_name}" if bg_name else None,
        "background-color": bg_color or tokens.palette["bg_deep"],
        "draw-user-backgrounds": str(bool(tokens.get("login.draw_user_backgrounds", False))).lower(),
        "draw-grid": str(bool(tokens.get("login.draw_grid", False))).lower(),
        "show-hostname": str(bool(tokens.get("login.show_hostname", False))).lower(),
        "show-clock": str(bool(tokens.get("login.show_clock", True))).lower(),
        "clock-format": tokens.get("login.clock_format") or "%H:%M",
        "logo": tokens.get("login.logo") or None,
        "stretch-background-across-monitors": str(bool(tokens.get("login.stretch", False))).lower(),
    }
    manifest = {"theme": LOGIN_THEME, "background": bg_name, "conf": {k: v for k, v in conf.items() if v is not None},
                "preset": tokens["name"]}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log(f"[login] staged theme, background and greeter config for '{tokens['name']}'")
    return STAGE / "manifest.json"


def _helper(log):
    """Use the root-owned copy installed by install.sh when it exists: a helper that lives in
    the user's home could be swapped by any process running as the user before it runs as root."""
    try:
        st = SYSTEM_HELPER.stat()
        if st.st_uid == 0 and not (st.st_mode & 0o022):
            return [str(SYSTEM_HELPER)]
    except OSError:
        pass
    log("[login] note: system helper not installed (run ./install.sh); using the copy in the repo")
    return ["/usr/bin/python3", str(ROOT_HELPER)]


def _run_as_root(args, log):
    cmd = _helper(log) + args
    if sys.stdin.isatty() and shutil.which("sudo"):
        full = ["sudo"] + cmd
    else:
        full = ["pkexec"] + cmd
    log("[login] installing system-wide (administrator password required)")
    r = subprocess.run(full, capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        log("[login] " + line)
    if r.returncode != 0:
        log(f"[login] failed ({r.returncode}): {(r.stderr or '').strip()[-300:]}")
        return False
    return True


def apply(tokens, log=print):
    manifest = stage(tokens, log)
    ok = _run_as_root(["install", str(manifest)], log)
    if ok:
        log("[login] done — preview with: slick-greeter --test-mode")
    return ok


def restore(log=print):
    return _run_as_root(["restore"], log)
