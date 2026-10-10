import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
  Video,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Composition, Layer } from "./types";
import { resolveLayer } from "./animate";
import { fxStyle } from "./fx";

/**
 * Resolve a media reference for both the browser Player and the Remotion
 * renderer. Bundled files (e.g. ``media/foo.mp3`` copied into ``public/``)
 * must go through ``staticFile`` so the render server finds them; inline
 * data-URIs and absolute URLs are passed through untouched.
 */
export const resolveSrc = (src: string): string =>
  /^(data:|https?:|blob:)/.test(src) ? src : staticFile(src);

export interface TimelineProps {
  data: Composition;
  selectedId?: string | null;
}

const LayerView: React.FC<{ layer: Layer; t: number; selected: boolean }> = ({
  layer,
  t,
  selected,
}) => {
  const { visible, x, y, scale, opacity } = resolveLayer(layer, t);
  if (!visible) return null;
  const fx = fxStyle(layer.fx);
  const base: React.CSSProperties = {
    position: "absolute",
    left: x,
    top: y,
    transform: `scale(${scale})`,
    transformOrigin: "top left",
    opacity: Math.min(1, Math.max(0, opacity * fx.opacity)),
    filter: fx.filter || undefined,
    mixBlendMode: fx.mixBlendMode,
    WebkitBoxReflect: (fx as any).boxReflect || undefined,
    outline: selected ? "2px dashed #00E5FF" : undefined,
    outlineOffset: 2,
  };

  let inner: React.ReactNode = null;
  if (layer.kind === "text") {
    const s = layer.style || {};
    const commonShadow =
      (s.strokeWidth || 0) > 0
        ? [
            `-${s.strokeWidth}px 0 0 ${s.strokeColor}`,
            `${s.strokeWidth}px 0 0 ${s.strokeColor}`,
            `0 -${s.strokeWidth}px 0 ${s.strokeColor}`,
            `0 ${s.strokeWidth}px 0 ${s.strokeColor}`,
          ].join(", ")
        : undefined;
    inner = (
      <div
        style={{
          color: s.color || "#fff",
          fontSize: s.fontSize || 48,
          fontFamily: s.font || "Inter, Helvetica, Arial, sans-serif",
          fontWeight: 700,
          letterSpacing: s.letterSpacing || 0,
          lineHeight: 1.1,
          whiteSpace: "pre",
          textShadow: [commonShadow, fx.textShadow].filter(Boolean).join(", ") || undefined,
          background: s.background || undefined,
        }}
      >
        {layer.text}
      </div>
    );
  } else if (layer.kind === "video" && layer.src) {
    inner = (
      <Video
        src={resolveSrc(layer.src)}
        style={{ width: layer.width || "auto", height: layer.height || "auto" }}
      />
    );
  } else if (layer.src) {
    inner = (
      <img
        src={resolveSrc(layer.src)}
        width={layer.width}
        height={layer.height}
        style={{ display: "block" }}
        draggable={false}
      />
    );
  }

  return (
    <div style={base}>
      {inner}
      {fx.vignette > 0 && layer.width && layer.height ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            width: layer.width,
            height: layer.height,
            pointerEvents: "none",
            background: `radial-gradient(ellipse at center, rgba(0,0,0,0) ${Math.round(
              (1 - fx.vignette) * 100
            )}%, rgba(0,0,0,${fx.vignette}) 100%)`,
          }}
        />
      ) : null}
    </div>
  );
};

export const Timeline: React.FC<TimelineProps> = ({ data, selectedId }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const layers = [...(data?.layers || [])].sort((a, b) => a.z - b.z);
  return (
    <AbsoluteFill style={{ backgroundColor: "#05050a", overflow: "hidden" }}>
      {layers.map((layer) => (
        <LayerView
          key={layer.id}
          layer={layer}
          t={t}
          selected={layer.id === selectedId}
        />
      ))}
      {(data?.audio || []).map((track, i) => (
        <Sequence key={i} from={Math.round(track.start * fps)}>
          <Audio src={resolveSrc(track.src)} volume={track.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
