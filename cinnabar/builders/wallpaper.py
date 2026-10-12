"""Generate a wallpaper that matches the palette (soft blurred color fields)."""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .. import color as C

OUT_DIR = Path.home() / ".local/share/backgrounds/cinnabar"


def _rgb(hexcol):
    r, g, b, _ = C.parse(hexcol)
    return int(r * 255), int(g * 255), int(b * 255)


def _gradient(size, c1, c2):
    w, h = size
    base = Image.new("RGB", (2, 2))
    px = base.load()
    px[0, 0] = _rgb(c1)
    px[1, 1] = _rgb(c2)
    px[1, 0] = _rgb(C.mix(c1, c2, 0.5))
    px[0, 1] = _rgb(C.mix(c1, c2, 0.5))
    return base.resize((w, h), Image.BICUBIC)


def generate(tokens, size=(2560, 1440), path=None):
    c = tokens.palette
    style = tokens.get("wallpaper.style", "blobs")
    slug = tokens.get("slug", "cinnabar")
    path = Path(path) if path else OUT_DIR / f"{slug}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(slug)
    dark = tokens.dark
    w, h = size
    sw, sh = w // 4, h // 4  # work at quarter size, blur, upscale

    if style == "gradient":
        img = _gradient((sw, sh), C.mix(c["bg"], c["accent"], 0.35 if dark else 0.25), C.darken(c["bg"], 0.06 if dark else -0.03))
    else:
        bottom = C.darken(c["bg"], 0.08) if dark else C.lighten(c["bg"], 0.03)
        img = _gradient((sw, sh), C.darken(c["bg"], 0.03), bottom)
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        pool = [c["accent"], c.get("purple", c["accent"]), c.get("blue", c["accent"]), c.get("teal", c["accent"]), c["accent"]]
        for i, col in enumerate(pool):
            rx, ry = rnd.randint(sw // 6, sw * 5 // 6), rnd.randint(sh // 6, sh * 5 // 6)
            rad = rnd.randint(sw // 5, sw // 3)
            a = 150 if dark else 110
            d.ellipse((rx - rad, ry - rad * 0.8, rx + rad, ry + rad * 0.8), fill=_rgb(col) + (a,))
        layer = layer.filter(ImageFilter.GaussianBlur(sw // 7))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
        # a second, tighter pass for depth
        glow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(glow)
        rx, ry = rnd.randint(sw // 4, sw * 3 // 4), rnd.randint(sh // 4, sh * 3 // 4)
        d.ellipse((rx - sw // 5, ry - sh // 5, rx + sw // 5, ry + sh // 5), fill=_rgb(C.lighten(c["accent"], 0.15)) + (90,))
        glow = glow.filter(ImageFilter.GaussianBlur(sw // 10))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    img = img.resize((w, h), Image.BICUBIC)
    # subtle grain so gradients do not band
    noise = Image.effect_noise((w, h), 12).convert("L")
    grain = Image.merge("RGB", (noise, noise, noise))
    img = Image.blend(img, grain, 0.035)
    img.save(path, optimize=True)
    return path
