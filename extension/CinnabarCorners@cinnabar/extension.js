// Cinnabar Corners — rounded corners + Hyprland-style border for every window.
// Muffin on X11 cannot clip the client area of server-side-decorated windows, so
// the bottom corners of terminals, Electron apps, etc. stay square.  This extension
// attaches a small fragment shader to each window's surface actor that rounds all
// four corners and paints the border ring, like the GNOME "rounded window corners"
// extension does.
const Clutter = imports.gi.Clutter;
const GObject = imports.gi.GObject;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Meta = imports.gi.Meta;
const Mainloop = imports.mainloop;
const Settings = imports.ui.settings;

const EFFECT_NAME = 'cinnabar-corners';
const TYPES = [Meta.WindowType.NORMAL, Meta.WindowType.DIALOG, Meta.WindowType.MODAL_DIALOG, Meta.WindowType.UTILITY];
const KEYS = ['radius', 'border', 'color-focused', 'gradient', 'color-focused-to', 'color-unfocused', 'skip-csd'];

let extension = null;

function loadShader(uuid) {
    const file = Gio.File.new_for_path(GLib.get_user_data_dir() + '/cinnamon/extensions/' + uuid + '/corners.glsl');
    const [ok, data] = file.load_contents(null);
    if (!ok) throw new Error('could not read corners.glsl');
    return new TextDecoder().decode(data) + '\n';
}

function parseColor(str) {
    const [ok, c] = Clutter.Color.from_string(str || '');
    if (!ok) return [1.0, 0.0, 1.0];
    return [c.red / 255, c.green / 255, c.blue / 255];
}

const CornerEffect = GObject.registerClass({
    GTypeName: 'CinnabarCornerEffect_' + Math.floor(Math.random() * 1000000),
}, class CornerEffect extends Clutter.ShaderEffect {
    constructor(source) {
        super({ shader_type: Clutter.ShaderType.FRAGMENT_SHADER });
        this.set_shader_source(source);
    }

    setFloat(name, v) {
        // GJS passes integral numbers as int uniforms; nudge to force a float.
        this.set_uniform_value(name, parseFloat(v + 1e-6));
    }
});

class CinnabarCorners {
    constructor(uuid) {
        this.uuid = uuid;
        this._tracked = new Map();
        this._ids = [];
        this.settings = new Settings.ExtensionSettings(this, uuid);
        for (const key of KEYS) {
            this.settings.bind(key, key.replace(/-/g, '_'), () => this._updateAll());
        }
    }

    enable() {
        this._source = loadShader(this.uuid);
        this._ids.push([global.display, global.display.connect('window-created', (d, w) => this._track(w))]);
        this._ids.push([global.display, global.display.connect('notify::focus-window', () => this._updateAll())]);
        for (const actor of global.get_window_actors()) this._track(actor.get_meta_window());
    }

    disable() {
        for (const [obj, id] of this._ids) obj.disconnect(id);
        this._ids = [];
        for (const w of Array.from(this._tracked.keys())) this._untrack(w, true);
    }

    _track(w) {
        if (!w || this._tracked.has(w)) return;
        const ids = [];
        ids.push(w.connect('size-changed', () => this._update(w)));
        ids.push(w.connect('position-changed', () => this._update(w)));
        ids.push(w.connect('notify::appears-focused', () => this._update(w)));
        ids.push(w.connect('notify::fullscreen', () => this._update(w)));
        ids.push(w.connect('unmanaged', () => this._untrack(w, false)));
        this._tracked.set(w, { ids, retries: 0 });
        this._update(w);
    }

    _untrack(w, removeEffect) {
        const t = this._tracked.get(w);
        if (!t) return;
        for (const id of t.ids) { try { w.disconnect(id); } catch (e) { } }
        if (removeEffect) {
            const surf = this._surface(w);
            if (surf) surf.remove_effect_by_name(EFFECT_NAME);
        }
        this._tracked.delete(w);
    }

    _surface(w) {
        const actor = w.get_compositor_private();
        if (!actor) return null;
        return actor.get_first_child() || actor;
    }

    _applicable(w) {
        if (TYPES.indexOf(w.window_type) < 0) return false;
        if (w.get_maximized() || w.fullscreen) return false;
        if (w.tile_mode !== undefined && w.tile_mode !== Meta.TileMode.NONE) return false;
        if (this.skip_csd && w.is_client_decorated()) return false;
        if (w.is_override_redirect && w.is_override_redirect()) return false;
        return true;
    }

    _update(w) {
        const t = this._tracked.get(w);
        if (!t) return;
        const surf = this._surface(w);
        if (!surf) {
            if (t.retries++ < 20) Mainloop.timeout_add(100, () => { this._update(w); return false; });
            return;
        }
        if (!this._applicable(w)) {
            surf.remove_effect_by_name(EFFECT_NAME);
            return;
        }
        let fx = surf.get_effect(EFFECT_NAME);
        if (!fx) {
            fx = new CornerEffect(this._source);
            surf.add_effect_with_name(EFFECT_NAME, fx);
        }
        const frame = w.get_frame_rect();
        const buf = w.get_buffer_rect();
        // ClutterOffscreenEffect renders into a target 3px larger than the actor whose
        // origin sits 2px up/left of the actor (measured; Blur Cinnamon relies on the
        // same +3).  uv coordinates span that target, so shift the bounds by 2.
        fx.setFloat('width', buf.width + 3);
        fx.setFloat('height', buf.height + 3);
        fx.setFloat('x0', frame.x - buf.x + 2);
        fx.setFloat('y0', frame.y - buf.y + 2);
        fx.setFloat('w', frame.width);
        fx.setFloat('h', frame.height);
        fx.setFloat('radius', Math.min(this.radius, frame.width / 2, frame.height / 2));
        fx.setFloat('border', this.border);
        const focused = w.appears_focused;
        const c1 = parseColor(focused ? this.color_focused : this.color_unfocused);
        const c2 = (focused && this.gradient) ? parseColor(this.color_focused_to) : c1;
        fx.setFloat('c1r', c1[0]); fx.setFloat('c1g', c1[1]); fx.setFloat('c1b', c1[2]);
        fx.setFloat('c2r', c2[0]); fx.setFloat('c2g', c2[1]); fx.setFloat('c2b', c2[2]);
    }

    _updateAll() {
        for (const w of this._tracked.keys()) this._update(w);
    }
}

function init(meta) {
    extension = new CinnabarCorners(meta.uuid);
}

function enable() {
    extension.enable();
}

function disable() {
    extension.disable();
}
