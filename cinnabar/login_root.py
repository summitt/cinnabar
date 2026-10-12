#!/usr/bin/python3
"""Root helper for the login screen: copies the staged theme/background into /usr/share
and rewrites /etc/lightdm/slick-greeter.conf.  Deliberately dependency-free and small.

usage: login_root.py install <manifest.json> [--prefix /]
       login_root.py restore [--prefix /]
"""
import configparser
import json
import shutil
import sys
from pathlib import Path


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    prefix = Path("/")
    if "--prefix" in argv:
        i = argv.index("--prefix")
        prefix = Path(argv[i + 1])
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
    manifest = json.loads(Path(argv[1]).read_text())
    stage = Path(argv[1]).parent

    # theme
    dst = themes / manifest["theme"]
    themes.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(stage / manifest["theme"], dst)
    for p in dst.rglob("*"):
        p.chmod(0o755 if p.is_dir() else 0o644)
    print(f"installed GTK theme {dst}")

    # background
    if manifest.get("background"):
        bgdir.mkdir(parents=True, exist_ok=True)
        for old in bgdir.glob("background.*"):
            old.unlink()
        shutil.copy(stage / manifest["background"], bgdir / manifest["background"])
        (bgdir / manifest["background"]).chmod(0o644)
        print(f"installed background {bgdir / manifest['background']}")

    # greeter config (merge; keep any other keys the user set)
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    if conf_path.exists() and not backup.exists():
        shutil.copy(conf_path, backup)
    elif not conf_path.exists() and not backup.exists():
        pass  # nothing to back up; restore will delete the file
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    if conf_path.exists():
        cp.read(conf_path)
    if not cp.has_section("Greeter"):
        cp.add_section("Greeter")
    for k, v in manifest["conf"].items():
        cp.set("Greeter", k, str(v))
    with open(conf_path, "w") as f:
        f.write(f"# Written by Cinnabar (preset: {manifest.get('preset')}); original saved as {backup.name}\n")
        cp.write(f, space_around_delimiters=False)
    conf_path.chmod(0o644)
    print(f"wrote {conf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
