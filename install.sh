#!/usr/bin/env bash
# Cinnabar installer: dependencies (apt), fonts, Blur Cinnamon, CLI, app entries, tray autostart.
# Usage: ./install.sh [--no-apt] [--no-tray] [--no-blur]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NO_APT=0; NO_TRAY=0; NO_BLUR=0
for a in "$@"; do case "$a" in --no-apt) NO_APT=1;; --no-tray) NO_TRAY=1;; --no-blur) NO_BLUR=1;; esac; done
say() { printf '\033[1;35m[cinnabar]\033[0m %s\n' "$*"; }

# ---- 1. system packages ------------------------------------------------------
PKGS=(python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-xapp-1.0
      python3-yaml python3-jinja2 python3-pil wmctrl dconf-cli libglib2.0-bin libnotify-bin unzip curl)
# Inter is the UI font; use the distro package unless it is already installed (e.g. by cinnabar's downloader)
fc-list : family 2>/dev/null | grep -qi '^Inter' || PKGS+=(fonts-inter)
if [ "$NO_APT" = 0 ] && command -v apt-get >/dev/null; then
  MISSING=()
  for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
  if [ ${#MISSING[@]} -gt 0 ]; then
    say "installing packages: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}"
  else
    say "all system packages already installed"
  fi
fi
check_py() { /usr/bin/python3 -c "$1" 2>/dev/null || { echo "Python bindings missing ($2); re-run without --no-apt"; exit 1; }; }
check_py "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw; import yaml, jinja2, PIL" "GTK4/libadwaita"
check_py "import gi; gi.require_version('Gtk','3.0'); gi.require_version('XApp','1.0'); from gi.repository import Gtk, XApp" "GTK3/XApp"

# ---- 2. Blur Cinnamon extension (optional, from Cinnamon Spices) -------------
BLUR=~/.local/share/cinnamon/extensions/BlurCinnamon@klangman
if [ "$NO_BLUR" = 0 ] && [ ! -d "$BLUR" ]; then
  say "installing the Blur Cinnamon extension (used for translucent panels/menus)"
  TMP=$(mktemp -d)
  if curl -fsSL "https://cinnamon-spices.linuxmint.com/files/extensions/BlurCinnamon@klangman.zip" -o "$TMP/blur.zip"; then
    mkdir -p ~/.local/share/cinnamon/extensions && unzip -qo "$TMP/blur.zip" -d ~/.local/share/cinnamon/extensions/
  else
    say "could not download Blur Cinnamon; install it later from Extensions > Download (optional)"
  fi
  rm -rf "$TMP"
fi

# ---- 3. CLI, icons, application entries --------------------------------------
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps ~/.config/autostart
ln -sf "$HERE/bin/cinnabar" ~/.local/bin/cinnabar
cp "$HERE/data/cinnabar.svg" ~/.local/share/icons/hicolor/scalable/apps/cinnabar.svg
cp "$HERE/data/cinnabar-symbolic.svg" ~/.local/share/icons/hicolor/scalable/apps/cinnabar-symbolic.svg
sed "s|@HERE@|$HERE|g" "$HERE/data/cinnabar.desktop" > ~/.local/share/applications/cinnabar.desktop
sed "s|@HERE@|$HERE|g" "$HERE/data/cinnabar-tray.desktop" > ~/.local/share/applications/cinnabar-tray.desktop
gtk-update-icon-cache -q -f ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
say "app menu: 'Cinnabar' (theme app) and 'Cinnabar Tray'"

# ---- 4. tray icon: autostart + start now -------------------------------------
if [ "$NO_TRAY" = 0 ]; then
  sed "s|@HERE@|$HERE|g" "$HERE/data/cinnabar-tray.desktop" > ~/.config/autostart/cinnabar-tray.desktop
  if ! pgrep -f "cinnabar tray" >/dev/null; then
    nohup setsid "$HERE/bin/cinnabar" tray >/dev/null 2>&1 < /dev/null &
    disown 2>/dev/null || true
  fi
  say "tray icon enabled (autostarts at login; 'Quit' or untick 'Start at login' in its menu to disable)"
fi
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) say "note: add ~/.local/bin to your PATH to use 'cinnabar' directly";; esac
say "done. Try:  cinnabar list   |   cinnabar apply nord   |   cinnabar gui"
