"""Small color toolbox: parsing, HSL math, formatting."""
import colorsys
import re

HEX_RE = r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-zA-Z_-])"
RGB_RE = (r"rgba?\(\s*(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)"
          r"(?:\s*[,/]\s*([0-9.]+%?))?\s*\)")
COLOR_RE = re.compile(f"({HEX_RE})|({RGB_RE})", re.IGNORECASE)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def parse(s):
    """Return (r, g, b, a) floats 0..1 for '#rgb', '#rrggbb', '#rrggbbaa', rgb(), rgba()."""
    s = s.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    m = re.fullmatch(RGB_RE, s, re.IGNORECASE)
    if not m:
        raise ValueError(f"not a color: {s!r}")
    r, g, b = (float(m.group(i)) / 255 for i in (1, 2, 3))
    a = m.group(4)
    if a is None:
        a = 1.0
    elif a.endswith("%"):
        a = float(a[:-1]) / 100
    else:
        a = float(a)
    return r, g, b, a


def to_hex(r, g, b, a=1.0):
    h = "#%02x%02x%02x" % tuple(int(round(clamp(v) * 255)) for v in (r, g, b))
    if a < 1.0:
        h += "%02x" % int(round(clamp(a) * 255))
    return h


def to_rgba(r, g, b, a=1.0):
    return "rgba(%d, %d, %d, %s)" % (round(r * 255), round(g * 255), round(b * 255),
                                     ("%.3f" % a).rstrip("0").rstrip(".") or "0")


def hsl(hexcol):
    r, g, b, _ = parse(hexcol)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def from_hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, clamp(l), clamp(s))
    return to_hex(r, g, b)


def luminance(hexcol):
    r, g, b, _ = parse(hexcol)
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def is_dark(hexcol):
    return luminance(hexcol) < 0.4


def mix(c1, c2, t):
    """Linear mix of two colors, t=0 -> c1, t=1 -> c2."""
    a = parse(c1)
    b = parse(c2)
    return to_hex(*(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(c, amount):
    h, s, l = hsl(c)
    return from_hsl(h, s, l + amount)


def darken(c, amount):
    return lighten(c, -amount)


def shade(c, factor):
    h, s, l = hsl(c)
    return from_hsl(h, s, l * factor)


def saturate(c, amount):
    h, s, l = hsl(c)
    return from_hsl(h, s + amount, l)


def alpha(c, a):
    r, g, b, _ = parse(c)
    return to_rgba(r, g, b, a)


def contrast_fg(c, light="#ffffff", dark="#1b1b1f"):
    """Pick a readable foreground for a background color."""
    return light if luminance(c) < 0.45 else dark


def hue_distance(h1, h2):
    d = abs((h1 - h2) % 360)
    return min(d, 360 - d)
