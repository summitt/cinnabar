import argparse
import sys
from pathlib import Path

from . import __version__
from . import tokens as T


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cinnabar", description="Cinnabar — macOS/Hyprland-style theme engine for Cinnamon")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="list presets")
    p = sub.add_parser("show", help="print the resolved tokens of a preset"); p.add_argument("preset")
    p = sub.add_parser("build", help="build ~/.themes/Cinnabar without applying"); p.add_argument("preset")
    p = sub.add_parser("apply", help="build and apply a preset to the running desktop"); p.add_argument("preset")
    p.add_argument("--no-wallpaper", action="store_true"); p.add_argument("--no-terminals", action="store_true")
    sub.add_parser("restore", help="restore the desktop settings from before the first apply")
    p = sub.add_parser("wallpaper", help="only generate the wallpaper"); p.add_argument("preset"); p.add_argument("-o", "--out")
    sub.add_parser("fonts", help="install the Inter font family into ~/.local/share/fonts")
    sub.add_parser("gui", help="open the Cinnabar app")
    sub.add_parser("tray", help="run the tray icon (preset switcher in the panel)")
    p = sub.add_parser("login", help="theme the LightDM login screen with a preset (asks for the admin password)")
    p.add_argument("preset", nargs="?", help="preset or yaml; default: the current preset")
    p.add_argument("--restore", action="store_true", help="put the original slick-greeter.conf back")
    p.add_argument("--stage-only", action="store_true", help="only build the payload under ~/.config/cinnabar/login-stage")
    sub.add_parser("current", help="print the currently applied preset")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        cur = (T.CONFIG_DIR / "current.yaml")
        cur_name = T.load(cur)["name"] if cur.exists() else None
        for slug, path in T.list_presets().items():
            t = T.load(path)
            mark = "*" if t["name"] == cur_name else " "
            print(f"{mark} {slug:20} {t['name']:22} {t['variant']:5} accent {t['colors']['accent']}  ({path})")
    elif args.cmd == "show":
        import yaml
        print(yaml.safe_dump(T.load(args.preset).data, sort_keys=False))
    elif args.cmd == "build":
        from .builders import theme
        theme.build(T.load(args.preset))
    elif args.cmd == "apply":
        from . import apply
        apply.apply(T.load(args.preset), do_wallpaper=not args.no_wallpaper, do_terminals=not args.no_terminals)
    elif args.cmd == "restore":
        from . import apply
        apply.restore()
    elif args.cmd == "wallpaper":
        from .builders import wallpaper
        print(wallpaper.generate(T.load(args.preset), path=args.out))
    elif args.cmd == "fonts":
        from . import apply
        apply.ensure_inter()
    elif args.cmd == "current":
        cur = T.CONFIG_DIR / "current.yaml"
        print(cur.read_text() if cur.exists() else "nothing applied yet")
    elif args.cmd == "gui":
        from . import gui
        sys.exit(gui.main())
    elif args.cmd == "tray":
        from . import tray
        sys.exit(tray.main())
    elif args.cmd == "login":
        from . import login
        if args.restore:
            sys.exit(0 if login.restore() else 1)
        cur = T.CONFIG_DIR / "current.yaml"
        t = T.load(args.preset or (cur if cur.exists() else "sequoia-dark"))
        if args.stage_only:
            print(login.stage(t))
        else:
            sys.exit(0 if login.apply(t) else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
