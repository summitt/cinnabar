#!/usr/bin/env bash
# Install the cinnabar CLI/app for the current user (no root needed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -sf "$HERE/bin/cinnabar" ~/.local/bin/cinnabar
cp "$HERE/data/cinnabar.svg" ~/.local/share/icons/hicolor/scalable/apps/cinnabar.svg
sed "s|@HERE@|$HERE|g" "$HERE/data/cinnabar.desktop" > ~/.local/share/applications/cinnabar.desktop
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "Installed: ~/.local/bin/cinnabar and an app-menu entry 'Cinnabar'."
echo "Try:  cinnabar list   |   cinnabar apply sequoia-dark   |   cinnabar gui"
