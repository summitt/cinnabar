"""Palette remapping: turn a Mint-Y base theme into any palette.

Every color literal in the base theme is classified as neutral, accent, or one of
a few semantic hues and re-targeted onto the token palette while preserving the
relative lightness structure of the original theme.  The same mapping is applied
to CSS/SVG text and to PNG assets pixel by pixel, so the result is a complete
theme rather than a pile of overrides.
"""
import re
from functools import lru_cache

from . import color as C

SEMANTIC_BANDS = [  # (name, hue_low, hue_high)
    ("red", 340, 360), ("red", 0, 18), ("orange", 18, 45), ("yellow", 45, 72),
    ("green", 72, 160), ("teal", 160, 200), ("blue", 200, 262), ("purple", 262, 340),
]

RADIUS_RE = re.compile(r"(border-radius\s*:\s*)([^;}]+)")


class Recolorer:
    def __init__(self, base, palette, radii=None):
        """base: dict(bg, fg, accent) hex of the base theme.
        palette: dict with bg, fg, accent and optional red/orange/yellow/green/teal/blue/purple.
        radii: optional dict(control=px, large=px) used to remap border radii."""
        self.base = base
        self.pal = palette
        self.radii = radii or {}
        self.accent_hue, self.accent_sat, self.accent_l = C.hsl(base["accent"])
        self.n_accent_hue, self.n_accent_sat, self.n_accent_l = C.hsl(palette["accent"])
        _, _, lbg_b = C.hsl(base["bg"])
        _, _, lfg_b = C.hsl(base["fg"])
        self.tint_h, self.tint_s, lbg_n = C.hsl(palette["bg"])
        _, _, lfg_n = C.hsl(palette["fg"])
        self.l_bg_new = lbg_n
        pts = sorted([(0.0, 0.0), (lbg_b, lbg_n), (lfg_b, lfg_n), (1.0, 1.0)])
        self.anchors = pts

    # ---- lightness curve -------------------------------------------------
    def _remap_l(self, l):
        pts = self.anchors
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if l <= x1:
                if x1 == x0:
                    return y1
                return y0 + (y1 - y0) * (l - x0) / (x1 - x0)
        return l

    # ---- single color ----------------------------------------------------
    @lru_cache(maxsize=None)
    def map_hex(self, hexcol):
        h, s, l = C.hsl(hexcol)
        if s < 0.14 or l > 0.985 or l < 0.015:
            nl = self._remap_l(l)
            span = max(self.l_bg_new, 1 - self.l_bg_new)
            w = C.clamp(1 - abs(nl - self.l_bg_new) / span)
            return C.from_hsl(self.tint_h, self.tint_s * w, nl)
        if C.hue_distance(h, self.accent_hue) <= 24:
            nl = C.clamp(l + (self.n_accent_l - self.accent_l), 0.03, 0.97)
            return C.from_hsl(self.n_accent_hue, self.n_accent_sat, nl)
        for name, lo, hi in SEMANTIC_BANDS:
            if lo <= h < hi and self.pal.get(name):
                th, ts, _ = C.hsl(self.pal[name])
                return C.from_hsl(th, ts, l)
        return hexcol

    def map_rgb8(self, r, g, b):
        out = self.map_hex(C.to_hex(r / 255, g / 255, b / 255))
        return tuple(int(out[i:i + 2], 16) for i in (1, 3, 5))

    # ---- text --------------------------------------------------------------
    def _sub(self, m):
        tok = m.group(0)
        try:
            r, g, b, a = C.parse(tok)
        except ValueError:
            return tok
        nh = self.map_hex(C.to_hex(r, g, b))
        nr, ng, nb, _ = C.parse(nh)
        if tok.startswith("#"):
            return C.to_hex(nr, ng, nb, a)
        return C.to_rgba(nr, ng, nb, a)

    def _radius(self, m):
        def one(v):
            mm = re.fullmatch(r"(\d+(?:\.\d+)?)px", v)
            if not mm:
                return v
            px = float(mm.group(1))
            if px <= 3 and self.radii.get("control") is not None:
                return f"{self.radii['control']}px"
            if 3 < px <= 8 and self.radii.get("large") is not None:
                return f"{self.radii['large']}px"
            return v
        return m.group(1) + " ".join(one(v) for v in m.group(2).split())

    def map_text(self, text):
        text = C.COLOR_RE.sub(self._sub, text)
        if self.radii:
            text = RADIUS_RE.sub(self._radius, text)
        return text

    # ---- images --------------------------------------------------------------
    def map_image(self, path):
        from PIL import Image
        img = Image.open(path).convert("RGBA")
        px = img.load()
        cache = {}
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                key = (r, g, b)
                if key not in cache:
                    cache[key] = self.map_rgb8(r, g, b)
                px[x, y] = cache[key] + (a,)
        img.save(path)
