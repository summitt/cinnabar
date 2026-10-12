// Cinnabar Corners: rounded corners + border ring, applied to a window's surface actor.
// Coverage math adapted from rounded-window-corners / Blur my Shell (GPL).
uniform sampler2D tex;
uniform float width;
uniform float height;
uniform float x0;
uniform float y0;
uniform float w;
uniform float h;
uniform float radius;
uniform float border;
uniform float c1r;
uniform float c1g;
uniform float c1b;
uniform float c2r;
uniform float c2g;
uniform float c2b;

float circle_coverage(vec2 p, vec2 center, float r) {
    vec2 d = p - center;
    float dist2 = dot(d, d);
    float outer = r + 0.5;
    if (dist2 >= outer * outer) return 0.0;
    float inner = r - 0.5;
    if (dist2 <= inner * inner) return 1.0;
    return outer - sqrt(dist2);
}

float rrect_coverage(vec2 p, vec4 b, float r) {
    if (p.x < b.x || p.x > b.z || p.y < b.y || p.y > b.w) return 0.0;
    if (r <= 0.0) return 1.0;
    vec2 c;
    float cl = b.x + r, cr = b.z - r;
    if (p.x < cl) c.x = cl; else if (p.x > cr) c.x = cr; else return 1.0;
    float ct = b.y + r, cb = b.w - r;
    if (p.y < ct) c.y = ct; else if (p.y > cb) c.y = cb; else return 1.0;
    return circle_coverage(p, c, r);
}

void main(void) {
    vec2 uv = cogl_tex_coord_in[0].xy;
    vec2 p = uv * vec2(width, height);
    vec4 c = texture2D(tex, uv);
    vec4 bounds = vec4(x0, y0, x0 + w, y0 + h);
    if (p.x < bounds.x || p.x > bounds.z || p.y < bounds.y || p.y > bounds.w) {
        cogl_color_out = c;
        return;
    }
    float outer = rrect_coverage(p, bounds, radius);
    float inner = rrect_coverage(p, vec4(bounds.x + border, bounds.y + border, bounds.z - border, bounds.w - border), max(radius - border, 0.0));
    float t = clamp(((p.x - x0) / w + (p.y - y0) / h) * 0.5, 0.0, 1.0);
    vec3 bc = mix(vec3(c1r, c1g, c1b), vec3(c2r, c2g, c2b), t);
    vec4 ring = vec4(bc, 1.0);
    // Window texels are premultiplied.  Along the ring's inner edge the frame's own
    // anti-aliased corner leaves partially transparent texels; fill those with the
    // border color instead of letting them darken the ring.  Fully inside the window
    // the texel passes through untouched (keeps terminal transparency intact).
    vec3 straight = c.a > 0.001 ? c.rgb / c.a : bc;
    vec4 edge = vec4(mix(bc, straight, c.a), 1.0);
    vec4 win = inner > 0.999 ? c : edge;
    vec4 o = mix(ring, win, inner);
    cogl_color_out = o * outer;
}
