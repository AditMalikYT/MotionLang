import type { Fx } from "./types";

export interface FxStyle {
  filter: string;
  textShadow: string;
  mixBlendMode: any;
  vignette: number;
  opacity: number;
  boxReflect?: string;
}

const num = (v: any, d: number): number => {
  const n = typeof v === "number" ? v : parseFloat(v);
  return Number.isFinite(n) ? n : d;
};

const color = (v: any, d: string): string =>
  typeof v === "string" && v.length ? v : d;

/**
 * Translate the compiler's fx stack into approximate CSS so the browser
 * preview closely mirrors the MoviePy render. Final MP4s are still produced
 * by the Python engine with the real pixel effects.
 */
export function fxStyle(fx: Fx[] | undefined): FxStyle {
  const out: FxStyle = {
    filter: "",
    textShadow: "",
    mixBlendMode: "normal",
    vignette: 0,
    opacity: 1,
  };
  const filters: string[] = [];
  const shadows: string[] = [];
  for (const item of fx || []) {
    if (!item) continue;
    const [name, raw] = item;
    const p = raw || {};
    switch (name) {
      case "blur":
        filters.push(`blur(${num(p.radius ?? p._args?.[0], 4)}px)`);
        break;
      case "glow": {
        const c = color(p.color, "#00E5FF");
        const r = num(p.radius, 16) * Math.max(0.4, num(p.intensity, 1));
        shadows.push(`drop-shadow(0 0 ${r}px ${c})`);
        shadows.push(`drop-shadow(0 0 ${r * 1.8}px ${c})`);
        break;
      }
      case "drop_shadow": {
        const c = color(p.color, "#000");
        const ox = num(p.offset_x, 4);
        const oy = num(p.offset_y, 4);
        const b = num(p.blur, 8);
        shadows.push(`drop-shadow(${ox}px ${oy}px ${b}px ${c})`);
        break;
      }
      case "chromatic_aberration": {
        const o = num(p.offset ?? p._args?.[0], 3);
        shadows.push(`drop-shadow(${o}px 0 1px rgba(255,0,60,0.8))`);
        shadows.push(`drop-shadow(${-o}px 0 1px rgba(0,220,255,0.8))`);
        break;
      }
      case "glitch": {
        const amt = num(p.intensity ?? p._args?.[0], 2);
        shadows.push(`drop-shadow(${amt}px 0 0 rgba(255,0,80,0.55))`);
        shadows.push(`drop-shadow(${-amt}px 0 0 rgba(0,220,255,0.55))`);
        break;
      }
      case "motion_blur":
        filters.push(`blur(${Math.max(0.5, num(p.samples, 2) / 3)}px)`);
        break;
      case "adjust_color": {
        if (p.brightness != null) filters.push(`brightness(${num(p.brightness, 1)})`);
        if (p.contrast != null) filters.push(`contrast(${num(p.contrast, 1)})`);
        if (p.saturation != null) filters.push(`saturate(${num(p.saturation, 1)})`);
        break;
      }
      case "vignette":
        out.vignette = Math.min(1, num(p.amount ?? p._args?.[0], 0.3));
        break;
      case "reflection": {
        // -webkit-box-reflect mirrors below with a fading mask in Chromium.
        const op = Math.min(1, Math.max(0, num(p.opacity ?? p._args?.[0], 0.5)));
        out.boxReflect = `below 0px linear-gradient(transparent 60%, rgba(0,0,0,${op}))`;
        break;
      }
      case "flash_in":
        filters.push(`brightness(${1 + num(p.intensity, 0.6)})`);
        break;
      case "light_sweep":
        filters.push(`brightness(1.15) saturate(1.2)`);
        break;
      case "blend_mode":
        out.mixBlendMode = String(p.mode ?? p._args?.[0] ?? "normal");
        break;
      case "opacity":
        out.opacity = num(p.alpha ?? p._args?.[0], 1);
        break;
      default:
        break;
    }
  }
  out.filter = [...filters, ...shadows].join(" ").trim();
  out.textShadow = shadows.map((s) => s.replace("drop-shadow(", "").replace(/\)$/, "")).join(", ");
  return out;
}
