# Cinnabar

A token-driven theme engine for **Linux Mint Cinnamon** that makes the desktop look as
clean and cohesive as macOS, with **Hyprland-style window borders**. One small YAML
preset (colors, radius, border, fonts, panel geometry) is compiled into a complete
theme and applied live:

| Target | What is generated |
|---|---|
| GTK 2 / 3 / 4 + libadwaita | full theme derived from Mint-Y by palette remapping, plus overrides (radius, headerbars, traffic lights) |
| Window frames (Muffin) | rounded corners, accent/gradient border, macOS traffic lights on the left, centered title |
| Cinnamon shell | translucent top panel, floating dock pill for the window list, rounded menus/notifications/OSD/alt-tab |
| Blur Cinnamon extension | configured for panels, menus, notifications, tooltips, OSD, alt-tab |
| Terminals | kitty, Alacritty, Ghostty color schemes (included from their configs) |
| Wallpaper | generated from the palette (soft color fields or gradient) |
| Fonts | Inter (downloaded on first apply), monospace of your choice |

## Usage

```sh
./install.sh                     # symlinks ~/.local/bin/cinnabar + app menu entry
cinnabar list                    # bundled + user presets (* = currently applied)
cinnabar apply sequoia-dark      # build ~/.themes/Cinnabar and apply everything
cinnabar apply catppuccin-mocha  # gradient border, mauve accent
cinnabar gui                     # the app: presets, color pickers, live preview, Apply
cinnabar restore                 # put the desktop back exactly as it was before the first apply
```

Presets: `sequoia-dark`, `sequoia-light`, `catppuccin-mocha`, `tokyo-night`, `graphite`.
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

* Bottom window corners: on X11 the frame mask also clips the client window, so the accent
  border is interrupted at the two bottom corners. Set `window.round_bottom: false` for a
  continuous border with square bottom corners.
* Apps that were already running keep their previous GTK CSS until restarted (GTK caches it).
* Gradient borders are drawn with `border-image`, which ignores `border-radius` on the inner edge.
