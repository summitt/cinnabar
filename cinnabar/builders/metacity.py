"""Generate a Muffin/Metacity-3 window decoration theme.

Look: macOS traffic lights (left by default), centered title, rounded corners,
and a Hyprland-style colored (optionally gradient) border that wraps the whole
frame.  The titlebar is drawn inset so the border reads as a ring around the
window, including along the rounded top corners.
"""
from pathlib import Path

from .. import color as C

GLYPH = {
    "close": '<path d="M3.9 3.9 L8.1 8.1 M8.1 3.9 L3.9 8.1" stroke="{g}" stroke-width="1.3" stroke-linecap="round" fill="none"/>',
    "minimize": '<path d="M3.3 6 H8.7" stroke="{g}" stroke-width="1.3" stroke-linecap="round" fill="none"/>',
    "maximize": '<path d="M3.1 8.9 V5.3 L6.7 8.9 Z M8.9 3.1 V6.7 L5.3 3.1 Z" fill="{g}"/>',
    "unmaximize": '<path d="M6.3 5.7 V2.6 L9.4 5.7 Z M5.7 6.3 V9.4 L2.6 6.3 Z" fill="{g}"/>',
    "menu": '<path d="M3.3 4.3 H8.7 M3.3 6 H8.7 M3.3 7.7 H8.7" stroke="{g}" stroke-width="1.1" stroke-linecap="round" fill="none"/>',
    "shade": '<path d="M3.5 7.2 L6 4.7 L8.5 7.2" stroke="{g}" stroke-width="1.3" stroke-linecap="round" fill="none"/>',
    "unshade": '<path d="M3.5 4.8 L6 7.3 L8.5 4.8" stroke="{g}" stroke-width="1.3" stroke-linecap="round" fill="none"/>',
    "stick": '<circle cx="6" cy="6" r="1.6" fill="{g}"/>',
    "unstick": '<circle cx="6" cy="6" r="2.2" stroke="{g}" stroke-width="1.1" fill="none"/>',
}
BUTTONS = ["close", "minimize", "maximize", "unmaximize", "menu", "shade", "unshade", "stick", "unstick"]


def _svg(size, fill, glyph_name=None, glyph_color=None):
    glyph = GLYPH[glyph_name].format(g=glyph_color) if glyph_name else ""
    ring = C.alpha("#000000", 0.18)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 12 12">'
            f'<circle cx="6" cy="6" r="5.5" fill="{fill}" stroke="{ring}" stroke-width="0.6"/>{glyph}</svg>\n')


def write_buttons(out_dir, tokens):
    c = tokens.palette
    size = int(tokens.get("window.button_size", 12))
    colors = {
        "close": c["red"], "minimize": c["yellow"], "maximize": c["green"], "unmaximize": c["green"],
        "menu": c["fg_dim"], "shade": c["fg_dim"], "unshade": c["fg_dim"], "stick": c["fg_dim"], "unstick": c["fg_dim"],
    }
    for name in BUTTONS:
        base = colors[name]
        glyph = C.darken(C.saturate(base, 0.1), 0.38)
        (out_dir / f"{name}.svg").write_text(_svg(size, base))
        (out_dir / f"{name}-hover.svg").write_text(_svg(size, C.lighten(base, 0.04), name, glyph))
        (out_dir / f"{name}-pressed.svg").write_text(_svg(size, C.darken(base, 0.10), name, glyph))
        (out_dir / f"{name}-unfocused.svg").write_text(_svg(size, c["wm_button_unfocused"]))


def _button_ops(name, state):
    fn = {"normal": f"{name}.svg", "prelight": f"{name}-hover.svg", "pressed": f"{name}-pressed.svg",
          "unfocused": f"{name}-unfocused.svg"}[state]
    return (f'<draw_ops name="{name}_{state}"><image filename="{fn}" x="(width-object_width)/2" '
            f'y="(height-object_height)/2" width="object_width" height="object_height"/></draw_ops>')


def _titlebar_fill(name, col, B, R, square=False):
    """Titlebar background inset by the border width, with rounded inner top corners."""
    ops = [f'<draw_ops name="{name}">']
    if square or R <= B:
        ops.append(f'<rectangle color="{col}" x="{B}" y="{B}" width="width-{2*B}" height="height-{B}" filled="true"/>')
    else:
        D = 2 * (R - B)
        ops.append(f'<rectangle color="{col}" x="{R}" y="{B}" width="width-{2*R}" height="height-{B}" filled="true"/>')
        ops.append(f'<rectangle color="{col}" x="{B}" y="{R}" width="width-{2*B}" height="height-{R}" filled="true"/>')
        ops.append(f'<arc color="{col}" filled="true" x="{B}" y="{B}" width="{D}" height="{D}" start_angle="270" extent_angle="90"/>')
        ops.append(f'<arc color="{col}" filled="true" x="width-{B+D}" y="{B}" width="{D}" height="{D}" start_angle="0" extent_angle="90"/>')
    ops.append("</draw_ops>")
    return "\n".join(ops)


def _border_fill(name, tokens):
    c = tokens.palette
    if tokens.get("window.border_focused") == "gradient":
        return (f'<draw_ops name="{name}"><gradient type="diagonal" x="0" y="0" width="width" height="height">'
                f'<color value="{c["wm_border_focused"]}"/><color value="{c["wm_border_gradient_to"]}"/>'
                f'</gradient></draw_ops>')
    return (f'<draw_ops name="{name}"><rectangle color="{c["wm_border_focused"]}" x="0" y="0" '
            f'width="width" height="height" filled="true"/></draw_ops>')


def _title_ops(name, col):
    return (f'<draw_ops name="{name}"><title version=">= 3.1" '
            'x="(0 `max` ((frame_x_center - title_width / 2) `min` (width - title_width)))" '
            f'y="(0 `max` ((height - title_height) / 2))" ellipsize_width="width" color="{col}"/></draw_ops>')


def _buttons_block(focused=True, maximized=False):
    out = []
    for fn in ["close", "minimize", "menu", "shade", "unshade", "stick", "unstick"]:
        st = "normal" if focused else "unfocused"
        out.append(f'<button function="{fn}" state="normal" draw_ops="{fn}_{st}"/>')
        if focused:
            out.append(f'<button function="{fn}" state="prelight" draw_ops="{fn}_prelight"/>')
            out.append(f'<button function="{fn}" state="pressed" draw_ops="{fn}_pressed"/>')
    mx = "unmaximize" if maximized else "maximize"
    st = "normal" if focused else "unfocused"
    out.append(f'<button function="maximize" state="normal" draw_ops="{mx}_{st}"/>')
    if focused:
        out.append(f'<button function="maximize" state="prelight" draw_ops="{mx}_prelight"/>')
        out.append(f'<button function="maximize" state="pressed" draw_ops="{mx}_pressed"/>')
    for fn in ["above", "unabove"]:
        out.append(f'<button function="{fn}" state="normal"><draw_ops></draw_ops></button>')
        out.append(f'<button function="{fn}" state="pressed"><draw_ops></draw_ops></button>')
    return "\n".join(out)


def _blank_buttons():
    out = []
    for fn in ["close", "maximize", "minimize", "menu", "shade", "unshade", "above", "unabove", "stick", "unstick"]:
        out.append(f'<button function="{fn}" state="normal"><draw_ops></draw_ops></button>')
        out.append(f'<button function="{fn}" state="pressed"><draw_ops></draw_ops></button>')
    return "\n".join(out)


def render(tokens):
    c = tokens.palette
    B = int(tokens.get("window.border", 2))
    R = int(tokens.get("window.radius", 12))
    RB = R
    H = int(tokens.get("window.titlebar_height", 36))
    size = int(tokens.get("window.button_size", 12))
    BW = size + 8
    E = 8
    name = tokens.get("name", "Cinnabar")

    geom = f"""
<frame_geometry name="normal" title_scale="medium" rounded_top_left="{R}" rounded_top_right="{R}" rounded_bottom_left="{RB}" rounded_bottom_right="{RB}">
  <distance name="left_width" value="{B}"/>
  <distance name="right_width" value="{B}"/>
  <distance name="bottom_height" value="{B}"/>
  <distance name="left_titlebar_edge" value="{E}"/>
  <distance name="right_titlebar_edge" value="{E}"/>
  <distance name="title_vertical_pad" value="0"/>
  <border name="title_border" left="8" right="8" top="2" bottom="2"/>
  <border name="button_border" left="0" right="0" top="0" bottom="0"/>
  <distance name="button_width" value="{BW}"/>
  <distance name="button_height" value="{H - B}"/>
</frame_geometry>
<frame_geometry name="maximized" parent="normal" rounded_top_left="false" rounded_top_right="false" rounded_bottom_left="false" rounded_bottom_right="false">
  <distance name="left_width" value="0"/>
  <distance name="right_width" value="0"/>
  <distance name="bottom_height" value="0"/>
  <distance name="button_height" value="{H}"/>
</frame_geometry>
<frame_geometry name="tiled" parent="normal" rounded_top_left="false" rounded_top_right="false" rounded_bottom_left="false" rounded_bottom_right="false">
</frame_geometry>
<frame_geometry name="utility" parent="normal" title_scale="small">
</frame_geometry>
<frame_geometry name="border" has_title="false" rounded_top_left="{R}" rounded_top_right="{R}" rounded_bottom_left="{RB}" rounded_bottom_right="{RB}">
  <distance name="left_width" value="{B}"/>
  <distance name="right_width" value="{B}"/>
  <distance name="bottom_height" value="{B}"/>
  <distance name="left_titlebar_edge" value="0"/>
  <distance name="right_titlebar_edge" value="0"/>
  <distance name="button_width" value="0"/>
  <distance name="button_height" value="0"/>
  <distance name="title_vertical_pad" value="0"/>
  <border name="title_border" left="0" right="0" top="0" bottom="0"/>
  <border name="button_border" left="0" right="0" top="0" bottom="0"/>
</frame_geometry>
<frame_geometry name="attached" parent="normal" hide_buttons="true">
</frame_geometry>
"""
    ops = [
        _border_fill("bg_focused", tokens),
        f'<draw_ops name="bg_unfocused"><rectangle color="{c["wm_border_unfocused"]}" x="0" y="0" width="width" height="height" filled="true"/></draw_ops>',
        f'<draw_ops name="bg_max_focused"><rectangle color="{c["wm_bg"]}" x="0" y="0" width="width" height="height" filled="true"/></draw_ops>',
        f'<draw_ops name="bg_max_unfocused"><rectangle color="{c["wm_bg_unfocused"]}" x="0" y="0" width="width" height="height" filled="true"/></draw_ops>',
        _titlebar_fill("titlebar_focused", c["wm_bg"], B, R),
        _titlebar_fill("titlebar_unfocused", c["wm_bg_unfocused"], B, R),
        _titlebar_fill("titlebar_sq_focused", c["wm_bg"], B, R, square=True),
        _titlebar_fill("titlebar_sq_unfocused", c["wm_bg_unfocused"], B, R, square=True),
        f'<draw_ops name="titlebar_max_focused"><rectangle color="{c["wm_bg"]}" x="0" y="0" width="width" height="height" filled="true"/></draw_ops>',
        f'<draw_ops name="titlebar_max_unfocused"><rectangle color="{c["wm_bg_unfocused"]}" x="0" y="0" width="width" height="height" filled="true"/></draw_ops>',
        _title_ops("title_focused", c["wm_title"]),
        _title_ops("title_unfocused", c["wm_title_unfocused"]),
        '<draw_ops name="blank"></draw_ops>',
    ]
    for b in BUTTONS:
        for st in ("normal", "prelight", "pressed", "unfocused"):
            ops.append(_button_ops(b, st))

    styles = f"""
<frame_style name="normal_focused" geometry="normal">
  <piece position="entire_background" draw_ops="bg_focused"/>
  <piece position="titlebar" draw_ops="titlebar_focused"/>
  <piece position="title" draw_ops="title_focused"/>
  {_buttons_block(True)}
</frame_style>
<frame_style name="normal_unfocused" geometry="normal" parent="normal_focused">
  <piece position="entire_background" draw_ops="bg_unfocused"/>
  <piece position="titlebar" draw_ops="titlebar_unfocused"/>
  <piece position="title" draw_ops="title_unfocused"/>
  {_buttons_block(False)}
</frame_style>
<frame_style name="maximized_focused" geometry="maximized" parent="normal_focused">
  <piece position="entire_background" draw_ops="bg_max_focused"/>
  <piece position="titlebar" draw_ops="titlebar_max_focused"/>
  <piece position="title" draw_ops="title_focused"/>
  {_buttons_block(True, maximized=True)}
</frame_style>
<frame_style name="maximized_unfocused" geometry="maximized" parent="normal_unfocused">
  <piece position="entire_background" draw_ops="bg_max_unfocused"/>
  <piece position="titlebar" draw_ops="titlebar_max_unfocused"/>
  <piece position="title" draw_ops="title_unfocused"/>
  {_buttons_block(False, maximized=True)}
</frame_style>
<frame_style name="tiled_focused" geometry="tiled" parent="normal_focused">
  <piece position="entire_background" draw_ops="bg_focused"/>
  <piece position="titlebar" draw_ops="titlebar_sq_focused"/>
  <piece position="title" draw_ops="title_focused"/>
</frame_style>
<frame_style name="tiled_unfocused" geometry="tiled" parent="normal_unfocused">
  <piece position="entire_background" draw_ops="bg_unfocused"/>
  <piece position="titlebar" draw_ops="titlebar_sq_unfocused"/>
  <piece position="title" draw_ops="title_unfocused"/>
</frame_style>
<frame_style name="utility_focused" geometry="utility" parent="normal_focused"></frame_style>
<frame_style name="utility_unfocused" geometry="utility" parent="normal_unfocused"></frame_style>
<frame_style name="border" geometry="border" parent="normal_focused">
  <piece position="entire_background" draw_ops="bg_focused"/>
  <piece position="titlebar" draw_ops="blank"/>
  <piece position="title" draw_ops="blank"/>
</frame_style>
<frame_style name="attached_focused" geometry="attached" parent="normal_focused">
  {_blank_buttons()}
</frame_style>
<frame_style name="attached_unfocused" geometry="attached" parent="normal_unfocused">
  {_blank_buttons()}
</frame_style>
<frame_style name="blank" geometry="normal">
  {_blank_buttons()}
</frame_style>

<frame_style_set name="normal">
  <frame focus="yes" state="normal" resize="both" style="normal_focused"/>
  <frame focus="no" state="normal" resize="both" style="normal_unfocused"/>
  <frame focus="yes" state="maximized" style="maximized_focused"/>
  <frame focus="no" state="maximized" style="maximized_unfocused"/>
  <frame focus="yes" state="shaded" style="normal_focused"/>
  <frame focus="no" state="shaded" style="normal_unfocused"/>
  <frame focus="yes" state="maximized_and_shaded" style="maximized_focused"/>
  <frame focus="no" state="maximized_and_shaded" style="maximized_unfocused"/>
  <frame version=">= 3.3" focus="yes" state="tiled_left" style="tiled_focused"/>
  <frame version=">= 3.3" focus="no" state="tiled_left" style="tiled_unfocused"/>
  <frame version=">= 3.3" focus="yes" state="tiled_right" style="tiled_focused"/>
  <frame version=">= 3.3" focus="no" state="tiled_right" style="tiled_unfocused"/>
  <frame version=">= 3.3" focus="yes" state="tiled_left_and_shaded" style="tiled_focused"/>
  <frame version=">= 3.3" focus="no" state="tiled_left_and_shaded" style="tiled_unfocused"/>
  <frame version=">= 3.3" focus="yes" state="tiled_right_and_shaded" style="tiled_focused"/>
  <frame version=">= 3.3" focus="no" state="tiled_right_and_shaded" style="tiled_unfocused"/>
</frame_style_set>
<frame_style_set name="utility">
  <frame focus="yes" state="normal" resize="both" style="utility_focused"/>
  <frame focus="no" state="normal" resize="both" style="utility_unfocused"/>
  <frame focus="yes" state="maximized" style="blank"/>
  <frame focus="no" state="maximized" style="blank"/>
  <frame focus="yes" state="shaded" style="utility_focused"/>
  <frame focus="no" state="shaded" style="utility_unfocused"/>
  <frame focus="yes" state="maximized_and_shaded" style="blank"/>
  <frame focus="no" state="maximized_and_shaded" style="blank"/>
</frame_style_set>
<frame_style_set name="border">
  <frame focus="yes" state="normal" resize="both" style="border"/>
  <frame focus="no" state="normal" resize="both" style="border"/>
  <frame focus="yes" state="maximized" style="border"/>
  <frame focus="no" state="maximized" style="border"/>
  <frame focus="yes" state="shaded" style="border"/>
  <frame focus="no" state="shaded" style="border"/>
  <frame focus="yes" state="maximized_and_shaded" style="border"/>
  <frame focus="no" state="maximized_and_shaded" style="border"/>
</frame_style_set>
<frame_style_set name="attached">
  <frame focus="yes" state="normal" resize="both" style="attached_focused"/>
  <frame focus="no" state="normal" resize="both" style="attached_unfocused"/>
  <frame focus="yes" state="maximized" style="blank"/>
  <frame focus="no" state="maximized" style="blank"/>
  <frame focus="yes" state="shaded" style="blank"/>
  <frame focus="no" state="shaded" style="blank"/>
  <frame focus="yes" state="maximized_and_shaded" style="blank"/>
  <frame focus="no" state="maximized_and_shaded" style="blank"/>
</frame_style_set>

<window type="normal" style_set="normal"/>
<window type="dialog" style_set="normal"/>
<window type="modal_dialog" style_set="normal"/>
<window type="menu" style_set="normal"/>
<window type="utility" style_set="utility"/>
<window type="border" style_set="border"/>
<window version=">= 3.2" type="attached" style_set="attached"/>
"""
    return (f'<?xml version="1.0"?>\n<metacity_theme>\n<info><name>{name}</name><author>Cinnabar</author>'
            f'<copyright>GPL</copyright><date>generated</date><description>Cinnabar generated decorations</description></info>\n'
            + geom + "\n".join(ops) + styles + "</metacity_theme>\n")


def build(theme_dir, tokens):
    out = Path(theme_dir) / "metacity-1"
    out.mkdir(parents=True, exist_ok=True)
    write_buttons(out, tokens)
    (out / "metacity-theme-3.xml").write_text(render(tokens))
    return out
