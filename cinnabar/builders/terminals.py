"""Terminal color schemes (kitty, alacritty, ghostty) derived from the palette."""
from pathlib import Path

from .. import color as C

CFG = Path.home() / ".config"


def ansi(tokens):
    c = tokens.palette
    d = tokens.dark
    sem = {k: c[k] for k in ("red", "green", "yellow", "blue", "purple", "teal")}
    bright = {k: C.lighten(v, 0.08 if d else -0.08) for k, v in sem.items()}
    return {
        "bg": c["bg"], "fg": c["fg"], "cursor": c["accent"], "cursor_text": c["accent_fg"],
        "selection_bg": C.mix(c["bg"], c["accent"], 0.45), "selection_fg": c["fg"],
        "black": C.mix(c["bg"], c["fg"], 0.12), "bright_black": C.mix(c["bg"], c["fg"], 0.40),
        "red": sem["red"], "green": sem["green"], "yellow": sem["yellow"], "blue": sem["blue"],
        "magenta": sem["purple"], "cyan": sem["teal"], "white": C.mix(c["fg"], c["bg"], 0.15),
        "bright_red": bright["red"], "bright_green": bright["green"], "bright_yellow": bright["yellow"],
        "bright_blue": bright["blue"], "bright_magenta": bright["purple"], "bright_cyan": bright["teal"],
        "bright_white": c["fg"], "url": c["accent"], "border_active": c["accent"], "border_inactive": c["border"],
        "tab_bg": c["bg_dark"], "tab_active": c["surface2"],
    }


def _mono_font(tokens):
    spec = tokens.get("fonts.mono", "monospace 11").rsplit(" ", 1)
    family, size = (spec[0], spec[1]) if len(spec) == 2 and spec[1].replace(".", "").isdigit() else (spec[0], "11")
    return family, size


def _ensure_line(path, line, create_header=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = path.read_text() if path.exists() else create_header
    if line.strip() in [l.strip() for l in txt.splitlines()]:
        return False
    sep = "" if txt.endswith("\n") or not txt else "\n"
    path.write_text(txt + sep + line + "\n")
    return True


def build(tokens, log=print):
    a = ansi(tokens)
    family, size = _mono_font(tokens)
    ctx = {"a": a, "font_family": family, "font_size": size}
    done = []
    if tokens.get("terminals.kitty"):
        p = CFG / "kitty" / "cinnabar-theme.conf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_render("kitty.conf.j2", tokens, ctx))
        _ensure_line(CFG / "kitty" / "kitty.conf", "include cinnabar-theme.conf", "# kitty.conf (created by cinnabar)\n")
        done.append("kitty")
    if tokens.get("terminals.alacritty"):
        p = CFG / "alacritty" / "cinnabar-theme.toml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_render("alacritty.toml.j2", tokens, ctx))
        main = CFG / "alacritty" / "alacritty.toml"
        if not main.exists():
            main.write_text('# alacritty.toml (created by cinnabar)\nimport = ["~/.config/alacritty/cinnabar-theme.toml"]\n')
        elif "cinnabar-theme.toml" not in main.read_text():
            main.write_text('import = ["~/.config/alacritty/cinnabar-theme.toml"]\n' + main.read_text())
        done.append("alacritty")
    if tokens.get("terminals.ghostty"):
        p = CFG / "ghostty" / "themes" / "cinnabar"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_render("ghostty.j2", tokens, ctx))
        _ensure_line(CFG / "ghostty" / "config", "theme = cinnabar", "# ghostty config (created by cinnabar)\n")
        done.append("ghostty")
    if tokens.get("terminals.terminator"):
        if _terminator(a, log):
            done.append("terminator")
    log(f"[terminals] wrote color schemes for: {', '.join(done) or 'none'}")
    return done


def _terminator(a, log):
    """Recolor the [[default]] profile of ~/.config/terminator/config in place (font, background
    image etc. are left alone).  The original file is backed up once under ~/.config/cinnabar."""
    import re
    from ..tokens import CONFIG_DIR
    cfg = CFG / "terminator" / "config"
    palette = ":".join([a["black"], a["red"], a["green"], a["yellow"], a["blue"], a["magenta"], a["cyan"], a["white"],
                        a["bright_black"], a["bright_red"], a["bright_green"], a["bright_yellow"], a["bright_blue"],
                        a["bright_magenta"], a["bright_cyan"], a["bright_white"]])
    values = {"background_color": f'"{a["bg"]}"', "foreground_color": f'"{a["fg"]}"', "palette": f'"{palette}"',
              "cursor_bg_color": f'"{a["cursor"]}"', "cursor_fg_color": f'"{a["cursor_text"]}"',
              "cursor_color": f'"{a["cursor"]}"', "use_theme_colors": "False"}
    if not cfg.exists():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        body = "[profiles]\n  [[default]]\n" + "".join(f"    {k} = {v}\n" for k, v in values.items() if k != "cursor_color")
        cfg.write_text("[global_config]\n[keybindings]\n" + body + "[layouts]\n  [[default]]\n    [[[window0]]]\n      type = Window\n      parent = \"\"\n    [[[child1]]]\n      type = Terminal\n      parent = window0\n      profile = default\n[plugins]\n")
        return True
    backup = CONFIG_DIR / "backup-original-terminator.config"
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(cfg.read_text())
    lines = cfg.read_text().splitlines()
    out, in_profiles, in_default, indent, done_keys, inserted = [], False, False, "    ", set(), False

    def flush_missing():
        nonlocal inserted
        if inserted:
            return
        for k, v in values.items():
            if k not in done_keys and k != "cursor_color":
                out.append(f"{indent}{k} = {v}")
        inserted = True

    for line in lines:
        stripped = line.strip()
        if re.match(r"^\[[^\[]", stripped):            # top-level section
            if in_default:
                flush_missing()
            in_profiles = stripped == "[profiles]"
            in_default = False
        elif in_profiles and re.match(r"^\[\[[^\[]", stripped):   # a profile
            if in_default:
                flush_missing()
            in_default = stripped == "[[default]]"
            done_keys, inserted = set(), False
        elif in_default and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            indent = line[:len(line) - len(line.lstrip())] or "    "
            if key in values:
                out.append(f"{indent}{key} = {values[key]}")
                done_keys.add(key)
                continue
        out.append(line)
    if in_default:
        flush_missing()
    if not in_profiles and "[profiles]" not in "\n".join(lines):
        out += ["[profiles]", "  [[default]]"] + [f"    {k} = {v}" for k, v in values.items() if k != "cursor_color"]
    cfg.write_text("\n".join(out) + "\n")
    return True


def _render(name, tokens, ctx):
    from .theme import _env
    return _env().get_template(name).render(t=tokens.data, c=tokens.palette, **ctx)
