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
const Main = imports.ui.main;

const EFFECT_NAME = 'cinnabar-corners';
const TYPES = [Meta.WindowType.NORMAL, Meta.WindowType.DIALOG, Meta.WindowType.MODAL_DIALOG, Meta.WindowType.UTILITY];
const KEYS = ['radius', 'border', 'color-focused', 'gradient', 'color-focused-to', 'color-unfocused', 'skip-csd', 'animate', 'speed', 'fps',
              'window-effects', 'effect-duration', 'pop-scale', 'overshoot'];
const STATIC_ANGLE = Math.PI / 4;

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

/* Expand / contract window animations (Hyprland "popin" style).  Cinnamon's own map and
 * close effects call actor.ease() exactly once with an onStopped callback that finishes the
 * compositor hand-off, so while the original handler runs we swap in our animation and
 * let it fire that same callback. */
class WindowEffects {
    constructor(owner) {
        this.owner = owner;
        this._orig = {};
    }

    enable() {
        const wm = Main.wm;
        const self = this;
        this._orig.map = wm._mapWindow;
        this._orig.destroy = wm._destroyWindow;
        wm._mapWindow = function (cinnamonwm, actor) {
            if (!self.owner.window_effects || this.desktop_effects_map_type === 'none' || !this._shouldAnimate(actor))
                return self._orig.map.call(this, cinnamonwm, actor);
            const saved = this.desktop_effects_map_type;
            this.desktop_effects_map_type = 'traditional';
            actor.ease = (params) => { delete actor.ease; self._expand(actor, params); };
            try { return self._orig.map.call(this, cinnamonwm, actor); }
            finally { this.desktop_effects_map_type = saved; delete actor.ease; }
        };
        wm._destroyWindow = function (cinnamonwm, actor) {
            if (!self.owner.window_effects || this.desktop_effects_close_type === 'none')
                return self._orig.destroy.call(this, cinnamonwm, actor);
            const saved = this.desktop_effects_close_type;
            this.desktop_effects_close_type = 'traditional';
            actor.ease = (params) => { delete actor.ease; self._contract(actor, params); };
            try { return self._orig.destroy.call(this, cinnamonwm, actor); }
            finally { this.desktop_effects_close_type = saved; delete actor.ease; }
        };
    }

    disable() {
        if (this._orig.map) Main.wm._mapWindow = this._orig.map;
        if (this._orig.destroy) Main.wm._destroyWindow = this._orig.destroy;
        this._orig = {};
    }

    _duration() {
        const mult = Main.wm.window_effect_multiplier || 1.0;
        return Math.max(60, (this.owner.effect_duration || 220) * mult);
    }

    _scale() {
        return Math.min(1, Math.max(0.3, (this.owner.pop_scale || 80) / 100));
    }

    _expand(actor, params) {
        const target = params.opacity !== undefined ? params.opacity : 255;
        actor.set_pivot_point(0.5, 0.5);
        actor.scale_x = actor.scale_y = this._scale();
        actor.opacity = 0;
        actor.show();
        actor.ease({
            scale_x: 1, scale_y: 1, opacity: target,
            x: params.x !== undefined ? params.x : actor.x,
            duration: this._duration(),
            mode: this.owner.overshoot ? Clutter.AnimationMode.EASE_OUT_BACK : Clutter.AnimationMode.EASE_OUT_CUBIC,
            onStopped: params.onStopped,
        });
    }

    _contract(actor, params) {
        actor.set_pivot_point(0.5, 0.5);
        actor.ease({
            scale_x: this._scale(), scale_y: this._scale(), opacity: 0,
            duration: this._duration() * 0.85,
            mode: this.owner.overshoot ? Clutter.AnimationMode.EASE_IN_BACK : Clutter.AnimationMode.EASE_IN_CUBIC,
            onStopped: params.onStopped,
        });
    }
}

class CinnabarCorners {
    constructor(uuid) {
        this.uuid = uuid;
        this._tracked = new Map();
        this._ids = [];
        this._animId = 0;
        this._angle = STATIC_ANGLE;
        this._lastTick = 0;
        this.effects = new WindowEffects(this);
        this.settings = new Settings.ExtensionSettings(this, uuid);
        for (const key of KEYS) {
            this.settings.bind(key, key.replace(/-/g, '_'), () => this._updateAll());
        }
    }

    enable() {
        this.effects.enable();
        this._source = loadShader(this.uuid);
        this._ids.push([global.display, global.display.connect('window-created', (d, w) => this._track(w))]);
        this._ids.push([global.display, global.display.connect('notify::focus-window', () => this._updateAll())]);
        for (const actor of global.get_window_actors()) this._track(actor.get_meta_window());
    }

    disable() {
        this.effects.disable();
        this._stopAnim();
        for (const [obj, id] of this._ids) obj.disconnect(id);
        this._ids = [];
        for (const w of Array.from(this._tracked.keys())) this._untrack(w, true);
    }

    _track(w) {
        if (!w || this._tracked.has(w)) return;
        const ids = [];
        ids.push(w.connect('size-changed', () => this._update(w)));
        ids.push(w.connect('position-changed', () => this._update(w)));
        ids.push(w.connect('notify::appears-focused', () => { this._update(w); this._syncAnim(); }));
        ids.push(w.connect('notify::fullscreen', () => this._update(w)));
        ids.push(w.connect('unmanaged', () => this._untrack(w, false)));
        this._tracked.set(w, { ids, retries: 0 });
        this._update(w);
    }

    _untrack(w, removeEffect) {
        const t = this._tracked.get(w);
        if (!t) return;
        for (const id of t.ids) { try { w.disconnect(id); } catch (e) { } }
        if (removeEffect && t.surf) {
            try { t.surf.remove_effect_by_name(EFFECT_NAME); } catch (e) { }
        }
        this._tracked.delete(w);
    }

    _surface(w) {
        // Only ever attach to the MetaSurfaceActor child: its texture is exactly the
        // window buffer.  Right after 'window-created' it may not exist yet, so callers
        // retry; never fall back to the MetaWindowActor (shadow + different geometry).
        const actor = w.get_compositor_private();
        if (!actor) return null;
        for (const c of actor.get_children()) {
            if (GObject.type_name(c).indexOf('SurfaceActor') >= 0) return c;
        }
        return null;
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
            if (t.retries++ < 30) Mainloop.timeout_add(100, () => { this._update(w); return false; });
            return;
        }
        if (t.surf && t.surf !== surf) {
            try { t.surf.remove_effect_by_name(EFFECT_NAME); } catch (e) { }
        }
        t.surf = surf;
        if (!this._applicable(w)) {
            surf.remove_effect_by_name(EFFECT_NAME);
            t.animated = false;
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
        // the frame's bottom edge is at least 3px (so Muffin rounds its shadow); cover all of it
        fx.setFloat('bottom', this.border > 0 ? Math.max(this.border, 3) : 0);
        const focused = w.appears_focused;
        const animated = focused && this.gradient && this.animate;
        fx.setFloat('angle', animated ? this._angle : STATIC_ANGLE);
        t.animated = animated;
        const c1 = parseColor(focused ? this.color_focused : this.color_unfocused);
        const c2 = (focused && this.gradient) ? parseColor(this.color_focused_to) : c1;
        fx.setFloat('c1r', c1[0]); fx.setFloat('c1g', c1[1]); fx.setFloat('c1b', c1[2]);
        fx.setFloat('c2r', c2[0]); fx.setFloat('c2g', c2[1]); fx.setFloat('c2b', c2[2]);
    }

    _updateAll() {
        for (const w of this._tracked.keys()) this._update(w);
        this._syncAnim();
    }

    // ---- animated border: rotate the gradient angle on the focused window only
    _syncAnim() {
        let want = false;
        for (const t of this._tracked.values()) if (t.animated && t.surf && t.surf.get_effect(EFFECT_NAME)) want = true;
        if (want && !this._animId) this._startAnim();
        else if (!want && this._animId) this._stopAnim();
    }

    _startAnim() {
        const fps = Math.max(5, Math.min(60, this.fps || 30));
        this._lastTick = GLib.get_monotonic_time();
        this._animId = Mainloop.timeout_add(Math.round(1000 / fps), () => this._tick());
    }

    _stopAnim() {
        if (this._animId) { Mainloop.source_remove(this._animId); this._animId = 0; }
    }

    _tick() {
        const now = GLib.get_monotonic_time();
        const dt = (now - this._lastTick) / 1e6;
        this._lastTick = now;
        const period = Math.max(1, this.speed || 8);
        this._angle = (this._angle + 2 * Math.PI * dt / period) % (2 * Math.PI);
        let any = false;
        for (const [w, t] of this._tracked) {
            if (!t.animated || !t.surf) continue;
            const fx = t.surf.get_effect(EFFECT_NAME);
            if (!fx) continue;
            fx.setFloat('angle', this._angle);
            any = true;
        }
        if (!any) { this._animId = 0; return false; }
        return true;
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
