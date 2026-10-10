import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Timeline } from "./Timeline";
import type { Composition, Fx, Layer } from "./types";
import { EMPTY_COMPOSITION } from "./types";

const EASINGS = [
  "linear",
  "ease",
  "ease_in",
  "ease_out",
  "ease_in_out",
  "ease_in_quad",
  "ease_out_quad",
  "back_out",
];

const BLEND_MODES = [
  "normal",
  "screen",
  "multiply",
  "overlay",
  "add",
  "difference",
  "lighten",
  "darken",
];

const FX_PRESETS: Record<string, Record<string, any>> = {
  glow: { color: "#00E5FF", radius: 20, intensity: 1.2 },
  blur: { radius: 6 },
  drop_shadow: { offset_x: 8, offset_y: 12, blur: 20, color: "#000000" },
  chromatic_aberration: { offset: 4 },
  glitch: { intensity: 3, seed: 1 },
  vignette: { amount: 0.35 },
  motion_blur: { samples: 8, direction: 0 },
};

function download(name: string, text: string) {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const SAMPLE: Composition = {
  meta: { title: "welcome", width: 1280, height: 720, fps: 30, duration: 4 },
  layers: [
    {
      id: "L0",
      z: 1,
      kind: "text",
      start: 0,
      end: 4,
      pos: [80, 90],
      posEnd: [420, 90],
      scale: 1,
      opacity: 1,
      easing: "ease_in_out",
      fx: [["glow", { color: "#00E5FF", radius: 24, intensity: 1.3 }]],
      blendMode: "normal",
      text: "MOTION STUDIO",
      style: { color: "#FFFFFF", fontSize: 84, letterSpacing: 2 },
    },
    {
      id: "L1",
      z: 2,
      kind: "text",
      start: 0.5,
      end: 4,
      pos: [80, 220],
      scale: 1,
      opacity: 0,
      opacityEnd: 1,
      easing: "ease_out",
      fx: [["vignette", { amount: 0 }]],
      blendMode: "normal",
      text: "Edit in real time. Render with Remotion.",
      style: { color: "#9BE7FF", fontSize: 34, letterSpacing: 4 },
    },
  ],
  audio: [],
};

export default function App() {
  const playerRef = useRef<PlayerRef>(null);
  const [comp, setComp] = useState<Composition>(EMPTY_COMPOSITION);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [frame, setFrame] = useState(0);
  const [status, setStatus] = useState("Loading composition…");
  const fileInput = useRef<HTMLInputElement>(null);

  // Track the playhead via the Player's frameupdate event.
  useEffect(() => {
    const p: any = playerRef.current;
    if (!p) return;
    const onFrame = (e: any) => setFrame(e.detail?.frame ?? 0);
    p.addEventListener("frameupdate", onFrame);
    return () => p.removeEventListener("frameupdate", onFrame);
  }, []);

  // Load the compiler-generated composition.json from the public folder.
  useEffect(() => {
    fetch("/composition.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("not found"))))
      .then((data: Composition) => {
        setComp(data);
        setSelectedId(data.layers?.[0]?.id ?? null);
        setStatus(
          `Loaded ${data.layers?.length || 0} layer(s) — ${data.meta.width}×${data.meta.height} @ ${data.meta.fps}fps`
        );
      })
      .catch(() => {
        setComp(SAMPLE);
        setSelectedId(SAMPLE.layers[0].id);
        setStatus("No composition.json found — showing a sample. Run `motion script.hmg --studio`.");
      });
  }, []);

  const durationInFrames = Math.max(
    1,
    Math.round(comp.meta.duration * comp.meta.fps)
  );

  const selected = useMemo(
    () => comp.layers.find((l) => l.id === selectedId) || null,
    [comp.layers, selectedId]
  );

  const update = useCallback(
    (id: string, patch: Partial<Layer>) => {
      setComp((c) => ({
        ...c,
        layers: c.layers.map((l) => (l.id === id ? { ...l, ...patch } : l)),
      }));
    },
    []
  );

  const updateMeta = (patch: Partial<Composition["meta"]>) =>
    setComp((c) => ({ ...c, meta: { ...c.meta, ...patch } }));

  const seekTo = (seconds: number) => {
    const f = Math.round(seconds * comp.meta.fps);
    playerRef.current?.seekTo(f);
  };

  const addText = () => {
    const id = "T" + Math.random().toString(36).slice(2, 7);
    const layer: Layer = {
      id,
      z: Math.max(0, ...comp.layers.map((l) => l.z)) + 1,
      kind: "text",
      start: 0,
      end: comp.meta.duration,
      pos: [comp.meta.width / 2 - 150, comp.meta.height / 2],
      scale: 1,
      opacity: 1,
      easing: "linear",
      fx: [],
      blendMode: "normal",
      text: "New Text",
      style: { color: "#FFFFFF", fontSize: 64, letterSpacing: 0 },
    };
    setComp((c) => ({ ...c, layers: [...c.layers, layer] }));
    setSelectedId(id);
  };

  const duplicate = (layer: Layer) => {
    const copy: Layer = {
      ...layer,
      id: "D" + Math.random().toString(36).slice(2, 7),
      z: layer.z + 1,
      pos: [layer.pos[0] + 30, layer.pos[1] + 30],
    };
    setComp((c) => ({ ...c, layers: [...c.layers, copy] }));
    setSelectedId(copy.id);
  };

  const remove = (id: string) => {
    setComp((c) => ({ ...c, layers: c.layers.filter((l) => l.id !== id) }));
    if (selectedId === id) setSelectedId(null);
  };

  const setFx = (layer: Layer, fx: Fx[]) => update(layer.id, { fx });

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="logo.svg" alt="Motion Language logo" className="logo" /> Motion Studio
          <span className="muted"> — Remotion</span>
        </div>
        <input
          className="title-input"
          value={comp.meta.title}
          onChange={(e) => updateMeta({ title: e.target.value })}
        />
        <div className="spacer" />
        <span className="status">{status}</span>
        <button onClick={addText}>+ Text</button>
        <button onClick={() => download(`${comp.meta.title || "composition"}.json`, JSON.stringify(comp, null, 2))}>
          Export JSON
        </button>
        <button onClick={() => fileInput.current?.click()}>Import</button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            f.text().then((t) => {
              try {
                const data = JSON.parse(t) as Composition;
                setComp(data);
                setSelectedId(data.layers?.[0]?.id ?? null);
                setStatus(`Imported ${data.layers?.length || 0} layer(s)`);
              } catch {
                setStatus("Import failed: invalid JSON");
              }
            });
          }}
        />
      </header>

      <div className="main">
        <aside className="left panel">
          <h3>Layers</h3>
          <div className="layer-list">
            {[...comp.layers]
              .sort((a, b) => b.z - a.z)
              .map((l) => (
                <div
                  key={l.id}
                  className={"layer-row" + (l.id === selectedId ? " active" : "")}
                  onClick={() => {
                    setSelectedId(l.id);
                    seekTo(l.start);
                  }}
                >
                  <span className="z">z{l.z}</span>
                  <span className="kind">{l.kind}</span>
                  <span className="name">{l.text || l.fileName || l.id}</span>
                  <span className="spacer" />
                  <button
                    className="mini"
                    title="Duplicate"
                    onClick={(e) => {
                      e.stopPropagation();
                      duplicate(l);
                    }}
                  >
                    ⧉
                  </button>
                  <button
                    className="mini danger"
                    title="Delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(l.id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            {comp.layers.length === 0 && <div className="muted pad">No layers</div>}
          </div>
        </aside>

        <section className="stage">
          <div className="player-wrap">
            <Player
              ref={playerRef}
              component={Timeline as any}
              inputProps={{ data: comp, selectedId }}
              durationInFrames={durationInFrames}
              fps={comp.meta.fps}
              compositionWidth={comp.meta.width}
              compositionHeight={comp.meta.height}
              style={{ width: "100%", height: "100%" }}
              controls
              clickToPlay
              doubleClickToFullscreen
              acknowledgeRemotionLicense
            />
          </div>
          <TimelineStrip
            comp={comp}
            frame={frame}
            selectedId={selectedId}
            onSelect={(id, start) => {
              setSelectedId(id);
              seekTo(start);
            }}
            onSeekFrames={(f) => playerRef.current?.seekTo(f)}
          />
        </section>

        <aside className="right panel">
          <h3>Inspector</h3>
          {!selected && <div className="muted pad">Select a layer</div>}
          {selected && (
            <div className="inspector">
              <label>
                Name / text
                {selected.kind === "text" ? (
                  <input
                    value={selected.text || ""}
                    onChange={(e) => update(selected.id, { text: e.target.value })}
                  />
                ) : (
                  <input value={selected.fileName || selected.id} disabled />
                )}
              </label>

              <div className="grid2">
                <label>
                  Start (s)
                  <input
                    type="number"
                    step="0.1"
                    value={selected.start}
                    onChange={(e) =>
                      update(selected.id, { start: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  End (s)
                  <input
                    type="number"
                    step="0.1"
                    value={selected.end}
                    onChange={(e) =>
                      update(selected.id, { end: Number(e.target.value) })
                    }
                  />
                </label>
              </div>

              <div className="grid2">
                <label>
                  X
                  <input
                    type="number"
                    value={selected.pos?.[0] ?? 0}
                    onChange={(e) =>
                      update(selected.id, {
                        pos: [Number(e.target.value), selected.pos?.[1] ?? 0],
                      })
                    }
                  />
                </label>
                <label>
                  Y
                  <input
                    type="number"
                    value={selected.pos?.[1] ?? 0}
                    onChange={(e) =>
                      update(selected.id, {
                        pos: [selected.pos?.[0] ?? 0, Number(e.target.value)],
                      })
                    }
                  />
                </label>
              </div>

              <div className="grid2">
                <label>
                  Scale
                  <input
                    type="number"
                    step="0.05"
                    value={selected.scale ?? 1}
                    onChange={(e) =>
                      update(selected.id, { scale: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  Opacity
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={selected.opacity ?? 1}
                    onChange={(e) =>
                      update(selected.id, { opacity: Number(e.target.value) })
                    }
                  />
                </label>
              </div>

              <label>
                Easing
                <select
                  value={selected.easing || "linear"}
                  onChange={(e) => update(selected.id, { easing: e.target.value })}
                >
                  {EASINGS.map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Blend mode
                <select
                  value={selected.blendMode || "normal"}
                  onChange={(e) => {
                    const others = (selected.fx || []).filter(
                      ([n]) => n !== "blend_mode"
                    );
                    const fx: Fx[] = [...others, ["blend_mode", { mode: e.target.value }]];
                    update(selected.id, { blendMode: e.target.value, fx });
                  }}
                >
                  {BLEND_MODES.map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </label>

              {selected.kind === "text" && (
                <div className="grid2">
                  <label>
                    Color
                    <input
                      type="color"
                      value={selected.style?.color || "#ffffff"}
                      onChange={(e) =>
                        update(selected.id, {
                          style: { ...selected.style, color: e.target.value },
                        })
                      }
                    />
                  </label>
                  <label>
                    Size
                    <input
                      type="number"
                      value={selected.style?.fontSize ?? 64}
                      onChange={(e) =>
                        update(selected.id, {
                          style: {
                            ...selected.style,
                            fontSize: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </label>
                </div>
              )}

              <h4>Effects</h4>
              <div className="fx-add">
                {Object.keys(FX_PRESETS).map((name) => (
                  <button
                    key={name}
                    className="mini"
                    onClick={() =>
                      setFx(selected, [
                        ...(selected.fx || []),
                        [name, { ...FX_PRESETS[name] }],
                      ])
                    }
                  >
                    + {name}
                  </button>
                ))}
              </div>
              <ul className="fx-list">
                {(selected.fx || []).map((item, i) => (
                  <li key={i}>
                    <code>{item[0]}</code>
                    <input
                      value={JSON.stringify(item[1])}
                      onChange={(e) => {
                        try {
                          const params = JSON.parse(e.target.value);
                          const fx = [...selected.fx];
                          fx[i] = [item[0], params];
                          setFx(selected, fx);
                        } catch {
                          /* ignore incomplete JSON while typing */
                        }
                      }}
                    />
                    <button
                      className="mini danger"
                      onClick={() =>
                        setFx(
                          selected,
                          selected.fx.filter((_, j) => j !== i)
                        )
                      }
                    >
                      ✕
                    </button>
                  </li>
                ))}
                {(!selected.fx || selected.fx.length === 0) && (
                  <li className="muted">No effects</li>
                )}
              </ul>

              <h4>Composition</h4>
              <div className="grid2">
                <label>
                  Width
                  <input
                    type="number"
                    value={comp.meta.width}
                    onChange={(e) => updateMeta({ width: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Height
                  <input
                    type="number"
                    value={comp.meta.height}
                    onChange={(e) => updateMeta({ height: Number(e.target.value) })}
                  />
                </label>
              </div>
              <div className="grid2">
                <label>
                  FPS
                  <input
                    type="number"
                    value={comp.meta.fps}
                    onChange={(e) => updateMeta({ fps: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Duration (s)
                  <input
                    type="number"
                    step="0.1"
                    value={comp.meta.duration}
                    onChange={(e) =>
                      updateMeta({ duration: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

const TimelineStrip: React.FC<{
  comp: Composition;
  frame: number;
  selectedId: string | null;
  onSelect: (id: string, start: number) => void;
  onSeekFrames: (f: number) => void;
}> = ({ comp, frame, selectedId, onSelect, onSeekFrames }) => {
  const total = Math.max(0.001, comp.meta.duration);
  const t = frame / comp.meta.fps;
  return (
    <div className="strip">
      <div className="strip-ruler">
        <span>0s</span>
        <span>{total.toFixed(1)}s</span>
      </div>
      <div
        className="strip-body"
        onClick={(e) => {
          const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          const ratio = (e.clientX - rect.left) / rect.width;
          onSeekFrames(Math.round(ratio * total * comp.meta.fps));
        }}
      >
        {comp.layers.map((l) => {
          const left = (l.start / total) * 100;
          const width = Math.max(0.5, ((l.end - l.start) / total) * 100);
          return (
            <div
              key={l.id}
              className={"bar" + (l.id === selectedId ? " active" : "")}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                top: Math.min(160, 8 + l.z * 6),
              }}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(l.id, l.start);
              }}
              title={`${l.id} · ${l.start}s–${l.end}s`}
            />
          );
        })}
        <div className="playhead" style={{ left: `${(t / total) * 100}%` }} />
      </div>
    </div>
  );
};
