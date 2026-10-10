import { interpolate } from "remotion";
import type { Layer } from "./types";

// Easing curves mirroring the Python engine's named easings.
const _outBounce = (t: number): number => {
  const n1 = 7.5625, d1 = 2.75;
  if (t < 1 / d1) return n1 * t * t;
  if (t < 2 / d1) { const u = t - 1.5 / d1; return n1 * u * u + 0.75; }
  if (t < 2.5 / d1) { const u = t - 2.25 / d1; return n1 * u * u + 0.9375; }
  const u = t - 2.625 / d1; return n1 * u * u + 0.984375;
};
const EASINGS: Record<string, (t: number) => number> = {
  linear: (t) => t,
  ease: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  ease_in: (t) => t * t * t,
  ease_out: (t) => 1 - Math.pow(1 - t, 3),
  ease_in_out: (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
  ease_in_quad: (t) => t * t,
  ease_out_quad: (t) => 1 - (1 - t) * (1 - t),
  ease_in_out_quad: (t) =>
    t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
  ease_in_cubic: (t) => t * t * t,
  ease_out_cubic: (t) => 1 - Math.pow(1 - t, 3),
  ease_in_out_cubic: (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
  ease_in_quart: (t) => t * t * t * t,
  ease_out_quart: (t) => 1 - Math.pow(1 - t, 4),
  ease_in_out_quart: (t) =>
    t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2,
  ease_in_quint: (t) => t * t * t * t * t,
  ease_out_quint: (t) => 1 - Math.pow(1 - t, 5),
  ease_in_out_quint: (t) =>
    t < 0.5 ? 16 * t * t * t * t * t : 1 - Math.pow(-2 * t + 2, 5) / 2,
  ease_in_sine: (t) => 1 - Math.cos((t * Math.PI) / 2),
  ease_out_sine: (t) => Math.sin((t * Math.PI) / 2),
  ease_in_out_sine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  ease_in_expo: (t) => (t <= 0 ? 0 : Math.pow(2, 10 * t - 10)),
  ease_out_expo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  ease_in_out_expo: (t) => {
    if (t <= 0) return 0; if (t >= 1) return 1;
    return t < 0.5 ? Math.pow(2, 20 * t - 10) / 2 : (2 - Math.pow(2, -20 * t + 10)) / 2;
  },
  ease_in_circ: (t) => 1 - Math.sqrt(Math.max(0, 1 - t * t)),
  ease_out_circ: (t) => Math.sqrt(Math.max(0, 1 - Math.pow(t - 1, 2))),
  ease_in_out_circ: (t) =>
    t < 0.5
      ? (1 - Math.sqrt(Math.max(0, 1 - Math.pow(2 * t, 2)))) / 2
      : (Math.sqrt(Math.max(0, 1 - Math.pow(-2 * t + 2, 2))) + 1) / 2,
  ease_in_back: (t) => { const c1 = 1.70158, c3 = c1 + 1; return c3 * t * t * t - c1 * t * t; },
  ease_out_back: (t) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
  ease_in_out_back: (t) => {
    const c1 = 1.70158, c2 = c1 * 1.525;
    return t < 0.5
      ? (Math.pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
      : (Math.pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2;
  },
  back_in: (t) => { const c1 = 1.70158, c3 = c1 + 1; return c3 * t * t * t - c1 * t * t; },
  back_out: (t) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
  ease_in_elastic: (t) => {
    if (t <= 0) return 0; if (t >= 1) return 1;
    return -Math.pow(2, 10 * t - 10) * Math.sin((t * 10 - 10.75) * ((2 * Math.PI) / 3));
  },
  ease_out_elastic: (t) => {
    if (t <= 0) return 0; if (t >= 1) return 1;
    return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
  },
  ease_in_out_elastic: (t) => {
    if (t <= 0) return 0; if (t >= 1) return 1;
    return t < 0.5
      ? -(Math.pow(2, 20 * t - 10) * Math.sin((20 * t - 11.125) * ((2 * Math.PI) / 4.5))) / 2
      : (Math.pow(2, -20 * t + 10) * Math.sin((20 * t - 11.125) * ((2 * Math.PI) / 4.5))) / 2 + 1;
  },
  bounce: _outBounce,
  ease_out_bounce: _outBounce,
  ease_in_bounce: (t) => 1 - _outBounce(1 - t),
  ease_in_out_bounce: (t) =>
    t < 0.5 ? (1 - _outBounce(1 - 2 * t)) / 2 : (1 + _outBounce(2 * t - 1)) / 2,
  smooth: (t) => t * t * (3 - 2 * t),
  smoothstep: (t) => t * t * (3 - 2 * t),
};

export function applyEasing(name: string | undefined, t: number): number {
  const raw = (name || "linear").toLowerCase().replace(/[-\s]/g, "_");
  const nosep = raw.replace(/_/g, "");
  let fn = EASINGS[raw];
  if (!fn) {
    for (const k of Object.keys(EASINGS)) {
      if (k.replace(/_/g, "") === nosep) { fn = EASINGS[k]; break; }
    }
  }
  fn = fn || EASINGS.linear;
  return fn(Math.min(1, Math.max(0, t)));
}

/** Progress of a layer at time `t` (seconds), 0..1. */
export function layerProgress(layer: Layer, t: number): number {
  const span = Math.max(1e-6, layer.end - layer.start);
  return Math.min(1, Math.max(0, (t - layer.start) / span));
}

export interface Resolved {
  visible: boolean;
  x: number;
  y: number;
  scale: number;
  opacity: number;
}

/** Resolve a layer's animated transform/opacity at time `t`. */
export function resolveLayer(layer: Layer, t: number): Resolved {
  const visible = t >= layer.start && t < layer.end;
  let p = applyEasing(layer.easing, layerProgress(layer, t));

  const [x0, y0] = layer.pos || [0, 0];
  let x = x0;
  let y = y0;
  if (layer.posEnd) {
    x = interpolate(p, [0, 1], [x0, layer.posEnd[0]]);
    y = interpolate(p, [0, 1], [y0, layer.posEnd[1]]);
  }
  // Time-based transform fx: float_y (sinusoidal Y) and pulse (scale throb).
  // These mirror motion_lang/vfx.py float_y_offset / pulse_scale with
  // clip-local time, matching the Python engine's per-frame modulation.
  const lt = Math.max(0, t - layer.start);
  for (const item of layer.fx || []) {
    if (!item) continue;
    const [name, raw] = item;
    const p = raw || {};
    if (name === "float_y") {
      const dist = typeof p.distance === "number" ? p.distance : parseFloat(p.distance ?? p._args?.[0] ?? 20);
      const spd = typeof p.speed === "number" ? p.speed : parseFloat(p.speed ?? p._args?.[1] ?? 1);
      if (Number.isFinite(dist) && Number.isFinite(spd)) y += Math.sin(lt * spd) * dist;
    }
  }
  const s0 = layer.scale == null ? 1 : layer.scale;
  const s1 = layer.scaleEnd == null ? s0 : layer.scaleEnd;
  let scale = interpolate(p, [0, 1], [s0, s1]);
  for (const item of layer.fx || []) {
    if (!item) continue;
    const [name, raw] = item;
    const p = raw || {};
    if (name === "pulse") {
      const amt = typeof p.amount === "number" ? p.amount : parseFloat(p.amount ?? p._args?.[0] ?? 0.1);
      const spd = typeof p.speed === "number" ? p.speed : parseFloat(p.speed ?? p._args?.[1] ?? 1);
      if (Number.isFinite(amt) && Number.isFinite(spd)) scale *= 1 + amt * Math.sin(lt * spd);
    }
  }

  const o0 = layer.opacity == null ? 1 : layer.opacity;
  const o1 = layer.opacityEnd == null ? o0 : layer.opacityEnd;
  let opacity = interpolate(p, [0, 1], [o0, o1]);

  // Transition-in / transition-out windows (e.g. "fade(0.5s)").
  opacity *= transitionAlpha(layer, t);

  return { visible, x, y, scale, opacity };
}

const TRANSITION_RE = /^([a-z_]+)\(\s*([\d.]+)\s*s?\s*\)$/i;

function transitionAlpha(layer: Layer, t: number): number {
  let alpha = 1;
  if (layer.transitionIn) {
    const m = TRANSITION_RE.exec(layer.transitionIn.trim());
    const dur = m ? parseFloat(m[2]) : 0.5;
    if (t < layer.start + dur) {
      alpha *= Math.max(0, (t - layer.start) / Math.max(1e-6, dur));
    }
  }
  if (layer.transitionOut) {
    const m = TRANSITION_RE.exec(layer.transitionOut.trim());
    const dur = m ? parseFloat(m[2]) : 0.5;
    if (t > layer.end - dur) {
      alpha *= Math.max(0, (layer.end - t) / Math.max(1e-6, dur));
    }
  }
  return Math.min(1, Math.max(0, alpha));
}
