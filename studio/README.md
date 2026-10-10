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
# --studio exports the timeline AND auto-launches the editor;
# add --no-launch to export only.

cd studio
npm install
npm run dev          # http://localhost:5173
```

If `public/composition.json` is missing the app falls back to a small sample.

## Features

- Live Remotion `<Player>` preview with a scrubbable timeline strip.
- **Spacebar** toggles play/pause (topbar ▶/⏸ button mirrors it).
- **Click + drag any layer directly on the canvas** to reposition it;
  keyframed `posEnd` shifts by the same delta so animations survive.
- **🚀 Render Video** button: syncs the edited timeline to disk and triggers
  a server-side Remotion render to `studio/out/studio.mp4`, with live job
  status and an MP4 download link. **Sync** saves without rendering.
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

## Studio sync/render API (dev server)

`vite-plugin-motion-api.ts` adds a backend to `vite dev` (no extra
dependencies) so the editor can persist edits and render without the CLI:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/composition` | POST `{composition}` | Save timeline to `public/composition.json` |
| `/api/render` | POST `{composition?}` | Save (if given) + start a Remotion render job → `{jobId}` |
| `/api/render` | GET | List jobs |
| `/api/render/:id` | GET | Job `{status, output, error, log}` (`queued`/`running`/`done`/`error`) |
| `/api/download/:id` | GET | Download the finished `studio.mp4` |

The UI polls the job endpoint every 2s and shows an MP4 download link on
completion. Renders run `npm run render` in the background; logs are kept
per job (last 300 lines).

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
