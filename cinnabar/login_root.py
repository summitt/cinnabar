#!/usr/bin/python3
"""Root helper for the login screen.  Copies the staged theme/background into /usr/share and
rewrites /etc/lightdm/slick-greeter.conf.  It runs as root on user-supplied input, so it is
deliberately small, dependency-free and strict:

  * the theme directory name is fixed, the background must be background.<png|jpg|jpeg|webp>
  * the stage must contain regular files and directories only (no symlinks, devices, ...)
  * greeter keys are allow-listed and their values validated before being written

usage: login_root.py install <manifest.json> [--prefix /]
       login_root.py restore [--prefix /]
"""
import configparser
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

THEME_NAME = "Cinnabar-Login"
BG_RE = re.compile(r"^background\.(png|jpe?g|webp)$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.+-]{0,80}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
BOOL = {"true", "false"}
MAX_STAGE_BYTES = 200 * 1024 * 1024


def _printable(v, n):
    return isinstance(v, str) and 0 < len(v) <= n and v.isprintable()


CONF_KEYS = {
    "theme-name": lambda v: v == THEME_NAME,
    "icon-theme-name": lambda v: bool(NAME_RE.match(v or "")),
    "cursor-theme-name": lambda v: bool(NAME_RE.match(v or "")),
    "font-name": lambda v: _printable(v, 80),
    "background": lambda v: isinstance(v, str) and v.startswith("/usr/share/backgrounds/cinnabar/") and bool(BG_RE.match(v.rsplit("/", 1)[1])),
    "background-color": lambda v: bool(COLOR_RE.match(v or "")),
    "draw-user-backgrounds": lambda v: v in BOOL,
    "draw-grid": lambda v: v in BOOL,
    "show-hostname": lambda v: v in BOOL,
    "show-clock": lambda v: v in BOOL,
    "clock-format": lambda v: _printable(v, 40),
    "stretch-background-across-monitors": lambda v: v in BOOL,
    "logo": lambda v: isinstance(v, str) and v.startswith("/usr/share/") and os.path.isfile(v) and not os.path.islink(v),
}


def fail(msg):
    print("refused: " + msg, file=sys.stderr)
    sys.exit(3)


def check_stage_tree(root):
    """Only regular files and directories, no symlinks anywhere, bounded total size."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                fail(f"symlink in stage: {p}")
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                fail(f"special file in stage: {p}")
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
                if total > MAX_STAGE_BYTES:
                    fail("stage too large")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    prefix = Path("/")
    if "--prefix" in argv:
        i = argv.index("--prefix")
        prefix = Path(argv[i + 1]).resolve()
        argv = argv[:i] + argv[i + 2:]
    cmd = argv[0]
    conf_path = prefix / "etc/lightdm/slick-greeter.conf"
    backup = prefix / "etc/lightdm/slick-greeter.conf.cinnabar-backup"
    themes = prefix / "usr/share/themes"
    bgdir = prefix / "usr/share/backgrounds/cinnabar"

    if cmd == "restore":
        if backup.exists():
            shutil.copy(backup, conf_path)
            print("restored slick-greeter.conf from backup")
        elif conf_path.exists():
            conf_path.unlink()
            print("removed slick-greeter.conf (there was none before Cinnabar)")
        return 0

    if cmd != "install" or len(argv) < 2:
        print(__doc__)
        return 2

    manifest_path = Path(argv[1]).resolve()
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.name != "manifest.json":
        fail("manifest must be a regular file named manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as e:
        fail(f"bad manifest: {e}")
    stage = manifest_path.parent
    if manifest.get("theme") != THEME_NAME:
        fail("theme name must be " + THEME_NAME)
    bg = manifest.get("background")
    if bg is not None and not BG_RE.match(str(bg)):
        fail("background must be background.<png|jpg|jpeg|webp>")
    conf = manifest.get("conf")
    if not isinstance(conf, dict):
        fail("conf must be an object")
    for k, v in conf.items():
        if k not in CONF_KEYS or not isinstance(v, str) or "\n" in v or "\r" in v or not CONF_KEYS[k](v):
            fail(f"invalid greeter setting {k!r}")
    if bg is not None and conf.get("background") not in (None, f"/usr/share/backgrounds/cinnabar/{bg}"):
        fail("background path mismatch")

    src_theme = stage / THEME_NAME
    if src_theme.is_symlink() or not src_theme.is_dir():
        fail("staged theme directory missing")
    if not (src_theme / "gtk-3.0" / "gtk.css").is_file():
        fail("staged theme has no gtk-3.0/gtk.css")
    check_stage_tree(src_theme)
    if bg is not None:
        src_bg = stage / bg
        if src_bg.is_symlink() or not src_bg.is_file():
            fail("staged background missing")
        if src_bg.stat().st_size > 64 * 1024 * 1024:
            fail("background too large")

    # theme
    dst = themes / THEME_NAME
    themes.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        fail(f"{dst} is a symlink")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_theme, dst, symlinks=False)
    for p in [dst] + list(dst.rglob("*")):
        os.chmod(p, 0o755 if p.is_dir() else 0o644)
        os.chown(p, 0, 0) if os.geteuid() == 0 else None
    print(f"installed GTK theme {dst}")

    # background
    if bg is not None:
        bgdir.mkdir(parents=True, exist_ok=True)
        for old in bgdir.glob("background.*"):
            if not old.is_symlink():
                old.unlink()
        shutil.copyfile(src_bg, bgdir / bg)
        os.chmod(bgdir / bg, 0o644)
        print(f"installed background {bgdir / bg}")

    # greeter config (merge; keep any other keys the admin set)
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    if conf_path.exists() and not backup.exists():
        shutil.copy(conf_path, backup)
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    if conf_path.exists():
        cp.read(conf_path)
    if not cp.has_section("Greeter"):
        cp.add_section("Greeter")
    for k, v in conf.items():
        cp.set("Greeter", k, v)
    preset = re.sub(r"[^\w .+-]", "", str(manifest.get("preset", "")))[:60]
    with open(conf_path, "w") as f:
        f.write(f"# Written by Cinnabar (preset: {preset}); original saved as {backup.name}\n")
        cp.write(f, space_around_delimiters=False)
    os.chmod(conf_path, 0o644)
    print(f"wrote {conf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
