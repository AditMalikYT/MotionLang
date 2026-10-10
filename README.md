# Motion Language

<p align="center">
  <img src="assets/logo/motion-icon-128.png" alt="Motion Language logo" width="128" />
</p>

Turn **text** into **motion**. Motion Language is a declarative, programmable
video DSL that compiles `.hmg` scripts to MP4 with MoviePy, and ships with a
real-time web editor powered by [Remotion](https://remotion.dev).

```hmg
config:
    resolution = 1280x720
    fps = 30

fn badge(label, x):
    return layer(z=2):
        render(shape("rect", width=200, height=60, color="#1e1e2e", radius=12), pos=(x, 600))
        render(text(label, size=24, color="#FFFFFF"), pos=(x + 20, 615))

scene:
    layer(z=1):
        render(shape("rect", width=1280, height=720, color="#0a0a10"), time=[0, 6])
    for i, word in ["FAST", "CLEAN", "MOTIONS"]:
        badge(word, x=100 + i * 220)
```

- **Cleaner than Python** — indentation blocks, no `var`, no braces, no semicolons.
- **Native operators** — `+ - * / %`, `== != > < >= <=`, `and/or/not`, `a -> b` keyframes.
- **Real language** — variables, `fn` functions, `class` OOP, `for`/`repeat`, `if/else if/else`, `import`/`export` modules.
- **Video-first** — `config:`, `scene:`, `layer(z=N):`, `render(...)`, `audio:` / `play(...)`.
- **Rich visuals** — shapes, native styled text, images, video, and an After Effects-style `fx=[...]` stack (glow, blur, chromatic aberration, glitch, vignette, motion blur, blend modes).
- **Live studio** — `--studio` exports a timeline the Remotion/React editor previews and tweaks in real time.

## Install

### Quick Install

```bash
# Using the installation script (recommended)
chmod +x install.sh && ./install.sh

# Or manually:
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Uninstall

```bash
# Remove virtual environment and dependencies
./uninstall.sh
```

## Usage

```bash
motion examples/modern_demo.hmg --render --output output/modern_demo.mp4  # render MP4
motion examples/modern_demo.hmg --preview                          # native preview
motion examples/modern_demo.hmg --studio                           # export + Remotion editor
motion examples/demo.hmg --output output/demo.mp4                  # legacy brace syntax
```

> `--render` forces MP4 output even if the script's `config:` sets
> `mode = "preview"`.

Open the studio:

```bash
cd studio && npm install && npm run dev     # http://localhost:5173
cd studio && npm run render                 # -> studio/out/studio.mp4 (Remotion/Chrome)
```

## Documentation

- **[Full DSL specification](docs/DSL_SPEC.md)** — syntax, types, functions, classes, control flow, directives, builtins, effects, modules, studio.
- **[Remotion studio](studio/README.md)** — the web editor.
- **Examples** — [`examples/modern_demo.hmg`](examples/modern_demo.hmg) (modern), [`examples/demo_ae.hmg`](examples/demo_ae.hmg), [`examples/demo_best.hmg`](examples/demo_best.hmg), [`examples/demo.hmg`](examples/demo.hmg) (legacy).

## Project layout

```
motion_lang/
  lang.py        # modern indentation-based interpreter (fn/class/loops/modules)
  parser.py      # legacy grammar + syntax dispatch
  engine.py      # MoviePy compositor: layers, keyframes, text, blend modes
  vfx.py         # AE-style pixel effects
  shapes.py      # shape primitives
  style.py       # CSS stylesheet support
  export.py      # timeline -> composition.json (for the studio)
  cli.py         # `motion` command
studio/          # Remotion + React real-time editor
examples/        # .hmg scripts + components + styles
docs/            # DSL specification
tests/           # language + AE feature test suites
```

## Tests

```bash
python tests/test_language.py
python tests/test_ae_features.py
```

Both suites pass on MoviePy 1.x and 2.x.
