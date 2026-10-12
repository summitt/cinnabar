"""Token schema: defaults, preset loading, derived palette."""
import copy
import os
from pathlib import Path

import yaml

from . import color as C

PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent
PRESET_DIRS = [PROJECT_DIR / "presets", Path.home() / ".config/cinnabar/presets"]
CONFIG_DIR = Path.home() / ".config/cinnabar"
THEME_NAME = "Cinnabar"

DEFAULTS = {
    "name": "Cinnabar",
    "slug": "cinnabar",
    "variant": "dark",                 # dark | light  (picks the Mint-Y base)
    "colors": {
        "bg": "#1e1e24", "fg": "#e8e8ee", "accent": "#0a84ff",
        "red": "#ff5f57", "yellow": "#febc2e", "green": "#28c840",
        "orange": "#ff9f0a", "blue": "#0a84ff", "purple": "#bf5af2", "teal": "#5ac8fa",
    },
    "window": {
        "radius": 12,                 # corner radius of windows (px)
        "round_bottom": True,         # also round the bottom corners (X11 clips the client)
        "border": 2,                  # Hyprland-style border width (px)
        "border_focused": "accent",   # hex, 'accent', or 'gradient'
        "border_gradient_to": "purple",  # second gradient stop: hex or a color token name
        "border_unfocused": None,     # hex or None -> derived from bg/fg
        "titlebar_height": 36,
        "buttons": "left",            # left (macOS) | right
        "button_size": 12,            # traffic light diameter
        "title_align": "center",
    },
    "controls": {"radius": 6, "radius_large": 10, "popup_radius": 12},
    "panel": {
        "top_height": 28, "top_opacity": 0.55,
        "dock": True, "dock_height": 52, "dock_icon_size": 36, "dock_opacity": 0.55, "dock_radius": 18,
        "popup_opacity": 0.90, "blur": True,
    },
    "fonts": {
        "ui": "Inter 10", "title": "Inter Semi-Bold 10", "document": "Inter 11",
        "mono": "0xProto Nerd Font Mono 11",
    },
    "icons": "Papirus-Dark",
    "cursor": {"theme": "Bibata-Modern-Classic", "size": 24},
    "wallpaper": {"mode": "generate", "file": None, "style": "blobs"},
    "terminals": {"kitty": True, "alacritty": True, "ghostty": True},
    "flatpak": True,
}


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def list_presets():
    """Return {slug: path} for every preset file (user presets override bundled ones)."""
    found = {}
    for d in PRESET_DIRS:
        if d.is_dir():
            for p in sorted(d.glob("*.yaml")):
                found[p.stem] = p
    return found


def load(preset):
    """Load a preset by slug or path and merge over DEFAULTS."""
    p = Path(preset)
    if not p.exists():
        presets = list_presets()
        if preset not in presets:
            raise FileNotFoundError(f"unknown preset {preset!r}; available: {', '.join(presets)}")
        p = presets[preset]
    with open(p) as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("slug", p.stem)
    data.setdefault("name", p.stem.replace("-", " ").title())
    return Tokens(deep_merge(DEFAULTS, data))


def save(tokens, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(tokens.data, f, sort_keys=False, allow_unicode=True)


class Tokens:
    """Dict wrapper with dotted access and a derived palette."""

    def __init__(self, data):
        self.data = data
        self._derive()

    def get(self, dotted, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, dotted, value):
        parts = dotted.split(".")
        cur = self.data
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value
        self._derive()

    def __getitem__(self, k):
        return self.data[k]

    @property
    def dark(self):
        return self.data.get("variant", "dark") == "dark"

    def resolve_color(self, value, fallback):
        """'accent' / 'purple' / hex / None -> hex."""
        if not value:
            return fallback
        if isinstance(value, str) and value.startswith("#"):
            return value
        return self.data["colors"].get(value, fallback)

    def _derive(self):
        c = dict(self.data["colors"])
        d = self.dark
        bg, fg, accent = c["bg"], c["fg"], c["accent"]
        sign = 1 if d else -1
        c["surface"] = C.lighten(bg, 0.045 * sign)       # cards / popups
        c["surface2"] = C.lighten(bg, 0.09 * sign)       # hover rows
        c["bg_dark"] = C.darken(bg, 0.035 * sign)        # headerbars, panel
        c["bg_deep"] = C.darken(bg, 0.07 * sign)         # sidebars
        c["border"] = C.mix(bg, fg, 0.14)
        c["border_strong"] = C.mix(bg, fg, 0.26)
        c["fg_dim"] = C.mix(fg, bg, 0.45)
        c["fg_muted"] = C.mix(fg, bg, 0.30)
        c["accent_fg"] = C.contrast_fg(accent)
        c["accent_hover"] = C.lighten(accent, 0.07)
        c["accent_active"] = C.darken(accent, 0.07)
        w = self.data["window"]
        c["wm_border_focused"] = self.resolve_color(w.get("border_focused"), accent)
        if w.get("border_focused") == "gradient":
            c["wm_border_focused"] = accent
        c["wm_border_gradient_to"] = self.resolve_color(w.get("border_gradient_to"), c.get("purple", accent))
        c["wm_border_unfocused"] = self.resolve_color(w.get("border_unfocused"), C.mix(bg, fg, 0.22))
        c["wm_bg"] = c["bg_dark"]
        c["wm_bg_unfocused"] = C.mix(c["bg_dark"], bg, 0.5)
        c["wm_title"] = fg
        c["wm_title_unfocused"] = c["fg_dim"]
        c["wm_button_unfocused"] = C.mix(bg, fg, 0.28)
        c["shadow"] = "#000000"
        self.palette = c
