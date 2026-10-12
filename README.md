<p align="center"><img src="data/logo.svg" alt="Cinnabar" width="640"></p>

# Cinnabar

A token-driven theme engine for **Linux Mint Cinnamon** that makes the desktop look as
clean and cohesive as macOS, with **Hyprland-style window borders**. One small YAML
preset (colors, radius, border, fonts, panel geometry) is compiled into a complete
theme and applied live:

| Target | What is generated |
|---|---|
| GTK 2 / 3 / 4 + libadwaita | full theme derived from Mint-Y by palette remapping, plus overrides (radius, headerbars, traffic lights) |
| Window frames (Muffin) | rounded corners, accent/gradient border ring, macOS traffic lights on the left, centered title |
| Cinnabar Corners extension | GLSL compositor effect that rounds **all four** corners of every window and draws the border (optionally a rotating two-tone gradient, Hyprland style), plus expand/contract open and close animations |
| Cinnamon shell | translucent top panel, floating dock pill for the window list, rounded menus/notifications/OSD/alt-tab |
| Blur Cinnamon extension | configured for panels, menus, notifications, tooltips, OSD, alt-tab |
| Terminals | kitty, Alacritty, Ghostty color schemes (included from their configs); Terminator default profile recolored in place |
| Wallpaper | generated from the palette (soft color fields or gradient) |
| Fonts | Inter (downloaded on first apply), monospace of your choice |
| Login screen | LightDM/slick-greeter: the preset's GTK theme, background (desktop wallpaper, generated, file or solid color), fonts, icons and greeter options, installed system-wide via pkexec/sudo with a backup |

## Usage

```sh
./install.sh                     # apt deps, Inter font, Blur Cinnamon, CLI, app entries, tray autostart
./install.sh --no-apt --no-tray  # skip package installation / the tray icon
cinnabar list                    # bundled + user presets (* = currently applied)
cinnabar apply sequoia-dark      # build ~/.themes/Cinnabar and apply everything
cinnabar apply catppuccin-mocha  # gradient border, mauve accent
cinnabar gui                     # the app: presets, color pickers, live preview, Apply
cinnabar tray                    # panel status icon: switch presets from a menu (autostarts after install)
cinnabar login [preset]          # theme the LightDM login screen (asks for the admin password)
cinnabar login --restore         # put the original slick-greeter.conf back
cinnabar restore                 # put the desktop back exactly as it was before the first apply
```

Presets (dark): `ayu-dark`, `ayu-mirage`, `catppuccin-frappe`, `catppuccin-macchiato`, `catppuccin-mocha`, `dracula`, `everforest-dark`, `flexoki-dark`, `github-dark`, `graphite`, `gruvbox-dark`, `kanagawa`, `monokai-pro`, `night-owl`, `nord`, `one-dark`, `oxocarbon`, `palenight`, `rose-pine-moon`, `rose-pine`, `sequoia-dark`, `sequoia-green`, `sequoia-midnight`, `sequoia-orange`, `sequoia-pink`, `sequoia-purple`, `sequoia-teal`, `solarized-dark`, `synthwave`, `tokyo-night-storm`, `tokyo-night`, `vesper`.

Presets (light): `catppuccin-latte`, `everforest-light`, `flexoki-light`, `github-light`, `gruvbox-light`, `rose-pine-dawn`, `sequoia-light-purple`, `sequoia-light`, `solarized-light`, `tokyo-night-day`.

Your own go in `~/.config/cinnabar/presets/*.yaml` (the app's *Save as preset…* writes there).
Any key you omit falls back to `cinnabar/tokens.py:DEFAULTS`.

```yaml
name: My Rice
variant: dark
colors: { bg: "#1e1e2e", fg: "#cdd6f4", accent: "#cba6f7", red: "#f38ba8", yellow: "#f9e2af", green: "#a6e3a1", purple: "#cba6f7" }
window: { radius: 10, border: 2, border_focused: gradient, border_gradient_to: "#f5c2e7", buttons: left }
panel:  { top_height: 28, top_opacity: 0.6, dock: true, dock_height: 52, dock_icon_size: 36, blur: true }
fonts:  { ui: "Inter 10", title: "Inter Semi-Bold 10", mono: "JetBrainsMono Nerd Font 11" }
```

## How it works

* `cinnabar/recolor.py` classifies every color literal in the Mint-Y base theme (neutral,
  accent, red/orange/yellow/green/teal/blue/purple) and re-targets it onto the preset
  palette while preserving the base theme's lightness structure. The same mapping is run
  over CSS, SVG and PNG assets, so the result is a complete theme, not a pile of overrides.
* `templates/*.j2` add the macOS/Hyprland layer on top: `.ssd decoration` border + radius
  (Muffin on Cinnamon ≥ 5.4 renders frames with the GTK theme), traffic-light
  `button.titlebutton`s, translucent `#panel`, the `.panel-bottom .panelCenter` dock pill, etc.
* `cinnabar/apply.py` snapshots dconf to `~/.config/cinnabar/backup-original-*.dconf`
  before touching anything, sets gsettings, configures Blur Cinnamon, adds flatpak overrides,
  and soft-restarts Cinnamon when re-applying (GTK caches a theme's CSS per process by name,
  so Muffin would otherwise keep the previous build).

## Known limits

* Muffin on X11 only rounds the top corners of server-side-decorated windows and draws its
  frame from the GTK `decoration` *background* (the compositor mask ignores CSS borders).
  The bundled `extension/CinnabarCorners@cinnabar` fixes the bottom corners with a fragment
  shader on each window's surface actor; `window.corners_extension: false` turns it off.
* GTK4/libadwaita windows (Ghostty, GNOME apps) have no `decoration` node; their ring and
  radius are set on `window.csd` / `window.csd:backdrop` in the libadwaita-1.x stylesheet.
  Already-running GTK apps keep their old CSS until relaunched.
* Maximized, tiled and fullscreen windows are left square (as in Hyprland). GTK client-side
  decorated windows are skipped by the extension because the GTK theme already rounds them.
* Apps that were already running keep their previous GTK CSS until restarted (GTK caches it).
* Gradient borders are drawn with `border-image`, which ignores `border-radius` on the inner edge.
