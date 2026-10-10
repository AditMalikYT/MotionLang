// Shared types for the Motion Language composition format.
// Produced by `python -m ... --emit-json` / `motion script.hmg --studio`.

export type FxName =
  | "blur"
  | "glow"
  | "drop_shadow"
  | "opacity"
  | "adjust_color"
  | "vfx_preset"
  | "chromatic_aberration"
  | "glitch"
  | "vignette"
  | "motion_blur"
  | "blend_mode"
  | string;

export type Fx = [FxName, Record<string, any>];

export interface TextStyle {
  font?: string;
  color?: string;
  fontSize?: number;
  strokeColor?: string;
  strokeWidth?: number;
  letterSpacing?: number;
  background?: string | null;
}

export interface Layer {
  id: string;
  z: number;
  kind: "image" | "text" | "video" | string;
  start: number;
  end: number;
  pos: [number, number];
  posEnd?: [number, number] | null;
  scale?: number | null;
  scaleEnd?: number | null;
  opacity: number;
  opacityEnd?: number | null;
  easing?: string;
  transitionIn?: string | null;
  transitionOut?: string | null;
  fx: Fx[];
  blendMode?: string;
  cssClass?: string | null;
  cssId?: string | null;
  // text
  text?: string;
  style?: TextStyle;
  // image / video
  src?: string;
  fileName?: string;
  width?: number;
  height?: number;
  isShape?: boolean;
}

export interface AudioTrack {
  src: string;
  start: number;
  volume: number;
}

export interface Composition {
  meta: {
    title: string;
    width: number;
    height: number;
    fps: number;
    duration: number;
  };
  layers: Layer[];
  audio: AudioTrack[];
}

export const EMPTY_COMPOSITION: Composition = {
  meta: { title: "untitled", width: 1280, height: 720, fps: 30, duration: 5 },
  layers: [],
  audio: [],
};
