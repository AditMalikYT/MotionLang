# Motion Studio

A real-time web video editor for **Motion Language**, powered by
[Remotion](https://remotion.dev) + React + Vite.

The Python compiler turns a `.hmg` script into a `composition.json` timeline
(layers, timings, transforms, effects, blend modes, audio). The studio loads
that file, previews it live in the browser with Remotion's `<Player>`, and lets
you tweak timing, position, scale, opacity, easing, text and effects.

## Quick start

```bash
# from the repository root — compile a script and emit the timeline
.venv/bin/motion examples/modern_demo.hmg --studio
#   (or: python -m motion_lang.cli examples/modern_demo.hmg --studio)

cd studio
npm install
npm run dev          # http://localhost:5173
```

If `public/composition.json` is missing the app falls back to a small sample.

## Features

- Live Remotion `<Player>` preview with a scrubbable timeline strip.
- Layer list with z-order, duplicate and delete.
- Inspector: text, start/end, X/Y, scale, opacity, easing, blend mode.
- Effects palette (`glow`, `blur`, `drop_shadow`, `chromatic_aberration`,
  `glitch`, `vignette`, `motion_blur`) with editable JSON parameters.
- Import / Export `composition.json`.

## Rendering to MP4

The primary renderer is the dependency-light Python engine:

```bash
.venv/bin/motion examples/modern_demo.hmg --render --output output/modern_demo.mp4
```

`--render` forces MP4 output even when the script's `config:` sets
`mode = "preview"`.

You can also render the studio timeline through Remotion (headless Chrome).
`@remotion/bundler` and `@remotion/renderer` are declared as
`optionalDependencies`, so a normal `npm install` already provides them:

```bash
cd studio
npm run render       # -> studio/out/studio.mp4
```

This renders `public/composition.json`, so re-run
`motion <script>.hmg --studio` first to pick up script changes.

## Composition format

See `src/types.ts`. Highlights:

- `meta`: canvas width/height/fps/duration.
- `layers[]`: `kind` (`text` | `image` | `video`), `z`, `start`/`end`,
  `pos`/`posEnd`, `scale`/`scaleEnd`, `opacity`/`opacityEnd`, `easing`,
  `transitionIn`/`transitionOut`, `fx`, `blendMode`.
  - text layers carry `text` + `style`
  - image layers carry a `src` data URI plus `width`/`height`
- `audio[]`: `src`, `start`, `volume`.

Effects are approximated with CSS filters in the browser (`src/fx.ts`) so the
preview matches the MoviePy output closely; the Python render applies the real
pixel effects.
