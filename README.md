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
- **Procedural math** — `sin`/`cos`/`lerp`/`clamp`/`noise`/`pi` drive any property per frame via `$t`/`$frame`, e.g. `pos=(640 + cos($t*2)*300, 360)`.
- **Video editorial** — `video(path, start=, end=, speed=)`, chainable `.cut().speed()`, `split_video()`.
- **Transitions** — `crossfade`, directional `wipe`/`slide`, `zoom_in/out`, `glitch`, inline or via `transition(from=, to=, type=, duration=)`.
- **Live studio** — `--studio` exports a timeline the Remotion/React editor previews and tweaks in real time.

## Install

### Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/AditMalikYT/MotionLang/main/install.sh | bash
```

### Uninstall

```bash
# Remove virtual environment and dependencies
curl -fsSL https://raw.githubusercontent.com/AditMalikYT/MotionLang/main/uninstall.sh | bash
```

## Usage

```bash
motion examples/modern_demo.hmg --render --output output/modern_demo.mp4  # render MP4
motion examples/modern_demo.hmg --preview                          # native preview
motion examples/modern_demo.hmg --studio                           # export + auto-launch editor
motion examples/modern_demo.hmg --studio --no-launch               # export only
motion update                                                      # git pull + reinstall latest
motion --update                                                    # same as above
motion -v                                                          # print version
```

> `--render` forces MP4 output even if the script's `config:` sets
> `mode = "preview"`. `--studio` opens the editor at
> http://localhost:5173 automatically (export it first with `--no-launch`
> if you only need the JSON).

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
  grammar.lark   # modern DSL grammar (chain/TIME/transition rules)
  math_engine.py # procedural math + per-frame $t/$frame dynamics
  video_engine.py# video cut/trim/retime (lazy MoviePy ops)
  transitions.py # transition specs + statement wiring
  parser.py      # legacy grammar + syntax dispatch
  engine.py      # MoviePy compositor: layers, keyframes, text, blend modes
  vfx.py         # AE-style pixel effects
  shapes.py      # shape primitives
  style.py       # CSS stylesheet support
  export.py      # timeline -> composition.json (for the studio)
  cli.py         # `motion` command: render/preview/studio/update
studio/          # Remotion + React real-time editor (+ sync/render API)
examples/        # .hmg scripts + components + styles
docs/            # DSL specification
tests/           # language + interop + dynamics + AE feature test suites
```

## Tests

```bash
python tests/test_language.py
python tests/test_ae_features.py
python tests/test_interop.py
python tests/test_dynamics.py
```

All suites pass on MoviePy 1.x and 2.x.


## License
This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.
