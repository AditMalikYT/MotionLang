# AGENT.md - Motion Language (.hmg) Repository Guide

Welcome to the **Motion Language** repository. This document outlines the project architecture, module layout, syntax rules, and development guidelines for contributors and autonomous AI agents working on this independent, high-performance programming language and motion graphics engine.

## Project Metadata

- **Creator / Author:** Adit Malik
- **File Extension:** `.hmg`
- **Language Version:** Motion Language 1.2 (Modern DSL)
- **Core Stack:** Python 3.13+, Lark (Parser), MoviePy (Compositor), Pillow & OpenCV (Image/VFX Processing), Remotion (Web Studio Preview), Google Fonts (Dynamic Typography)

## New Language Features (v1.1)
- **Python Interop:** Import any Python module (`import math`, `import numpy as np`, `import os.path`) directly in `.hmg`. Dotted attribute chains and calls work natively; local `.py` helpers resolve via bare `import helpers` or `import name from "file.py"` (see `motion_lang/modules.py`).
- **Google Fonts:** Load web fonts dynamically via `load_font("Poppins", weight="bold")` or direct URLs (`url=`); system fonts first, Google Fonts fetch + cache (`~/.cache/motion_lang/fonts/`), graceful offline fallback (see `motion_lang/text_engine.py`).
- **CSS Stylesheets:** Import `.css` files (`import styles from "theme.css"`) and apply classes to shapes and text layers (`class="glow-title"`); sheets join the compositor cascade (see `motion_lang/style.py`).

## New Language Features (v1.2)
- **Procedural Math:** `sin`/`cos`/`tan`, inverse trig, `sqrt`/`pow`, `lerp`, `clamp`, `map_range`, deterministic `noise(x, y, seed)` and constants `pi`/`e`/`tau` (see `motion_lang/math_engine.py`).
- **Time Dynamics:** `$t`/`$frame` inside `render()` properties (`pos`, `scale`, `opacity`, …) re-evaluate every frame — e.g. `pos=(640 + cos($t*2)*300, 360)`; wrapped in `DynExpr`, composed with keyframes/easing/fx.
- **Video Editorial:** `video(path, start=, end=, speed=)`, chainable `.cut()`/`.trim()`/`.subclip()`/`.speed()`/`.pos()`, `split_video(src, intervals=)` (see `motion_lang/video_engine.py`; lazy MoviePy ops).
- **Transitions:** inline `transition_in/out="crossfade(0.8)"` / `"wipe_left(0.5)"` / `"slide_*"` / `"zoom_in/out"` / `"glitch(0.3, intensity=0.8)"`, or the `transition(from=, to=, type=, duration=)` statement wiring two `render()` layers (see `motion_lang/transitions.py`).
- **Grammar:** rules live in `motion_lang/grammar.lark` (general `chain` for attribute/call/mixed chains, `TIME` token, `transition_stmt`).
- **Core Stack:** Python 3.13+, Lark (Parser), MoviePy (Compositor), Pillow & OpenCV (Image/VFX Processing), Remotion (Web Studio Preview)
- **License:** Independent / Proprietary (Adit Malik)
- **Repository Structure:** Professional-grade, inspired by python/cpython, rust-lang/rust

## Repository Layout

```
motion_lang/
├── AGENT.md                    # This file - AI & developer guide
├── README.md                   # Project overview, installation, usage
├── setup.py                    # Package configuration
├── requirements.txt            # Python dependencies
├── .gitignore                  # Version control exclusions
├── stur.md                     # Structural template (legacy notes)
│
├── motion_lang/                # Core language implementation
│   ├── __init__.py             # Package initialization
│   ├── cli.py                  # Command-line interface (motion command)
│   ├── parser.py               # Legacy brace syntax parser (Lark grammar)
│   ├── grammar.lark            # Modern DSL grammar (chain/TIME/transition rules)
│   ├── lang.py                 # Modern DSL interpreter (indentation-based)
│   ├── math_engine.py          # Procedural math + per-frame DynExpr dynamics
│   ├── video_engine.py         # Video cut/trim/retime (lazy MoviePy ops)
│   ├── transitions.py          # Transition specs + statement wiring
│   ├── modules.py              # Python interop (import math/numpy/.py files)
│   ├── text_engine.py          # Dynamic typography (local + Google Fonts)
│   ├── engine.py               # MoviePy compositor & animation system
│   ├── vfx.py                  # Visual effects pipeline (AE-style fx stack)
│   ├── shapes.py               # Geometric primitives & shape rendering
│   ├── style.py                # CSS stylesheet support for layers
│   ├── export.py               # Timeline -> composition.json (Remotion studio)
│   └── fetcher.py              # Asset fetching & caching (images, wiki)
│
├── examples/                   # Sample .hmg scripts & demonstrations
│   ├── modern_demo.hmg         # Modern DSL showcase (recommended)
│   ├── components/
│   │   └── ui.hmg              # Reusable UI components (GlowCard, GlassTitle)
│   └── *.hmg                   # Legacy demo scripts
│
├── studio/                     # Remotion-based web editor
│   ├── package.json            # Node.js project configuration
│   ├── README.md               # Studio setup & usage
│   ├── vite-plugin-motion-api.ts # Dev-server backend: /api/composition, /api/render, /api/download
│   └── src/                    # React + Remotion source (spacebar play/pause,
│                               # canvas drag-reposition, Render Video button)
│
├── docs/                       # Documentation
│   └── DSL_SPEC.md             # Full language specification
│
├── tests/                      # Test suites
│   ├── test_language.py        # Modern DSL interpreter tests
│   ├── test_interop.py         # Python interop + font/CSS tests
│   ├── test_dynamics.py        # Math dynamics, video trim, transition tests
│   └── test_ae_features.py     # After Effects feature compatibility tests
│
├── assets/                     # Static assets
│   └── logo/                   # Branding & iconography
│
├── output/                     # Rendered output (generated)
└── .venv/                      # Python virtual environment
```

## Syntax & Language Features

### Core Paradigm
Motion Language is a **declarative, programmable video DSL** that compiles `.hmg` scripts to MP4 videos via MoviePy, with optional real-time preview through Remotion.

### Syntax Rules

#### 1. **Indentation-Based Blocks** (Modern DSL - Preferred)
```hmg
// Comments use double-slash
config:
    resolution = 1280x720
    fps = 30

scene:
    layer(z=1):
        render(shape("rect", width=1280, height=720, color="#0a0a10"), time=[0, 6])
```

#### 2. **Control Flow**
- **Variables:** `name = value` (no var/let/const keywords)
- **Conditionals:** `if condition: ... elif condition: ... else: ...`
- **Loops:** `for item in list: ...` or `repeat N times as i: ...`
- **Functions:** `fn name(param1, param2): ... return value`
- **Classes:** `class Name: fn method(self, ...): ...`

#### 3. **Module System**
```hmg
// Import from file
import Component1, Component2 from "path/to/file.hmg"

// Python interop (v1.1) — no `from` clause
import math
import numpy as np
import helpers                  // ./helpers.py next to the script
import shout from "helpers.py"  // symbols from a Python file

// CSS stylesheets (v1.1)
import styles from "theme.css"

// Export
export MyComponent
```

#### 4. **Rendering Primitives**
- `shape("type", ...)` - rect, circle, ellipse, polygon, line, path
- `text("content", ...)` - styled text rendering (`load_font("Poppins", weight="bold")` for web fonts)
- `image("path")` / `video("path")` - media assets
- `wiki("query")` - fetch from Wikipedia
- `audio("path")` - audio clips

#### 5. **Layer System**
```hmg
layer(z=1):
    render(asset, pos=(x, y), time=[start, end], scale=1.0, opacity=1.0)
    render(text, fx=[glow(color="#00E5FF"), blur(radius=5)])
```

#### 6. **Visual Effects (fx stack)**
After Effects-style effect pipeline. Effects are applied in order:

**Static Effects (baked once):**
- `blur(radius=5)` - Gaussian blur
- `glow(color="#FFFFFF", intensity=1.0, radius=20)` - Outer glow
- `drop_shadow(offset_x=10, offset_y=10, blur=20, color="#00000088")` - Drop shadow
- `opacity(alpha=0.5)` - Alpha transparency
- `adjust_color(brightness=0.1, contrast=0.2, saturation=0.3)` - Color grading
- `chromatic_aberration(offset=3)` - RGB channel separation
- `glitch(intensity=0.3, seed=42)` - Datamosh-style glitch
- `vignette(amount=0.5)` - Corner darkening
- `motion_blur(samples=8, direction=0, distance=10)` - Motion blur
- `reflection(opacity=0.5, blur=5, gap=0, fade=true)` - Mirror reflection
- `vfx_preset("preset_name", ...)` - Named effect presets
- `blend_mode("screen")` - Compositing blend modes

**Dynamic Effects (per-frame):**
- `flash_in(duration=0.2, color="#FFFFFF")` - Time-based flash overlay
- `light_sweep(progress=t, angle=45, speed=1.0, width=0.25, color="#FFFFFF")` - Animated light sweep

**Transform Effects:**
- `float_y(distance=20, speed=1.0)` - Sinusoidal vertical motion
- `pulse(amount=0.1, speed=1.0)` - Sinusoidal scale pulsing

#### 7. **Keyframe Animation**
```hmg
// Keyframe syntax
render(asset, scale=1.0 -> 2.0)  // Animate scale from 1.0 to 2.0
render(asset, pos=(0, 0) -> (100, 100))  // Position animation
```

#### 8. **Easing Functions**
- `linear`, `ease` (=`ease_in_out` cubic), `ease_in` / `ease_out` / `ease_in_out` (cubic default)
- `*_quad`, `*_cubic`, `*_quart`, `*_quint`, `*_sine`, `*_expo`, `*_circ`, `*_back`, `*_elastic`, `*_bounce` (each with `ease_in_*`, `ease_out_*`, `ease_in_out_*`)
- extras: `back_in`, `back_out`, `bounce` (=`ease_out_bounce`), `smooth` / `smoothstep`
- Example: `render(..., opacity=0.50 -> 0.0, ease=linear)` — swap `linear` for `ease_out_expo`, `ease_in_out_sine`, `ease_out_back`, etc.

#### 9. **Blend Modes** (via fx stack)
- normal, multiply, screen, overlay, add, difference, lighten, darken, soft_light

## Architecture Overview

### 1. **Parser (parser.py)**
- Lark-based grammar for legacy brace syntax
- Regex-based fallback for robust parsing across versions
- Extracts render statements, options, and fx stacks
- Handles both modern and legacy syntax modes

### 2. **Modern Interpreter (lang.py)**
- Indentation-based AST walker
- Implements full language semantics:
  - Variables & expressions
  - Control flow (if/else, for/repeat)
  - Functions & classes (OOP)
  - Module system (import/export)
  - Asset management
  - Layer composition
- Transforms source to RenderSpec objects
- Delegates to Compositor for final rendering

### 3. **Compositor (engine.py)**
- MoviePy-based video composition engine
- Layer management with Z-index ordering
- Keyframe interpolation
- Transform animations (position, scale, opacity)
- Transition handling (fade_in, fade_out, slide, zoom)
- VFX pipeline integration
- CSS stylesheet support
- Blend mode application
- Per-frame dynamic properties (`DynExpr` from `$t`/`$frame`)
- Transition pipeline: crossfade/dissolve, directional wipes (alpha masks),
  slides, zoom in/out, decaying glitch bursts (`motion_lang/transitions.py`)
- Video editorial: lazy cut/retime with timeline clamping
  (`motion_lang/video_engine.py`)

### 4. **VFX Pipeline (vfx.py)**
- PIL & NumPy-based effect implementations
- Static effects: blur, glow, drop_shadow, chromatic_aberration, etc.
- Dynamic effects: flash_overlay, light_sweep
- Transform effects: pulse_scale, float_y_offset
- Color grading & blending utilities
- Effect parameter parsing & validation

### 5. **Shape System (shapes.py)**
- Geometric primitive rendering
- SVG-like path support
- Shape styling & coloring
- Custom shape definitions

### 6. **Style System (style.py)**
- CSS-compatible stylesheet parser
- Class & ID selectors
- Property inheritance & cascading
- Shape recoloring support
- Rounded corners & backgrounds

### 7. **Export System (export.py)**
- Timeline serialization to composition.json
- Remotion studio compatibility
- Asset manifest generation
- Frame-accurate specification export

### 8. **CLI (cli.py)**
- `motion` command entry point (argparse)
- Modes: render, preview, studio (`--no-launch` exports JSON without serving)
- `motion update`: `git pull --ff-only` the checkout (running copy preferred,
  `~/.motion_lang_src` fallback) + `pip install -e .`
- `--studio` auto-launches the Remotion dev server (`npm run dev`) and opens
  the browser; `--debug` prints full tracebacks
- Configuration management
- File watching & development server

### 10. **Python Interop (modules.py)**
- Dotted imports via importlib, with local-file fallback against the script dir
- `import a.b.c` binds `a`; `import x as y` binds `y` (standard semantics)
- `.py` file imports via `import name from "file.py"` or bare `import file`
- Failures warn and continue; native attribute chains (`os.path.join`)

### 11. **Font Engine (text_engine.py)**
- Weight/style-aware local font search (+ verified `fc-match`)
- Google Fonts on-demand fetch (Fontsource CDN, CSS API fallback)
- Disk cache at `~/.cache/motion_lang/fonts/`; offline-safe `None` fallback

### 12. **Asset Fetcher (fetcher.py)**
- Image & video asset loading
- Wikipedia integration
- Caching mechanism
- URL resolution

## Development Guidelines

### Code Style
- **Python Version:** 3.13+ required
- **Type Hints:** Use PEP 484 type annotations extensively
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **Docstrings:** Google-style docstrings for all public APIs
- **Imports:** Grouped by source (standard lib, third-party, local)
- **Error Handling:** Graceful degradation, never crash on user input
- **Performance:** Use `@lru_cache` for expensive pure functions

### Testing
- Run full test suite: `python tests/test_language.py && python tests/test_ae_features.py`
- Tests must pass on both MoviePy 1.x and 2.x
- Add regression tests for bug fixes
- Test edge cases (empty inputs, invalid parameters)

### Debugging
- Use `[DSL Warning]` prefix for user-facing warnings
- Use `[Engine]` / `[VFX]` / `[Style]` prefixes for debug output
- Never use bare `print()` for production code (use logging module)

### Performance Considerations
- VFX effects should be cached where possible
- Avoid per-frame PIL operations when static effects suffice
- Use NumPy vectorization for image processing
- Batch operations across frames
- Respect MoviePy's clip composition model

## Module Responsibilities

| Module | Responsibility | Key Classes/Functions |
|--------|----------------|----------------------|
| cli.py | Command-line interface | `main()`, `parse_args()` |
| parser.py | Legacy syntax parsing | Lark grammar, `_extract_fx_list()` |
| lang.py | Modern DSL interpreter | `Evaluator`, `Env`, `Asset`, `VideoAsset`, `Layer` |
| math_engine.py | Procedural math + dynamics | `DynExpr`, `lerp/clamp/map_range/noise`, `MATH_FUNCS` |
| video_engine.py | Video cut/retime | `cut_clip()`, `retime_clip()`, `split_clip()`, `apply_ops()` |
| transitions.py | Transition specs | `parse_transition_spec()`, `transition_statement()` |
| modules.py | Python interop | `import_dotted()`, `load_py_file()`, `resolve_py_import()` |
| text_engine.py | Dynamic fonts | `load_font()`, `find_local_font()`, `fetch_google_font()` |
| engine.py | Video composition | `Compositor`, `_apply_fx_stack()`, `_split_fx()` |
| vfx.py | Visual effects | `apply_glow()`, `apply_blur()`, `chromatic_aberration()` |
| shapes.py | Shape rendering | `draw_rect()`, `draw_circle()`, `draw_path()` |
| style.py | CSS styling | `parse_css_file()`, `apply_shape_style()` |
| export.py | Studio export | `export_timeline()`, `compose_spec()` |
| fetcher.py | Asset loading | `load_image()`, `fetch_wiki()` |

## VFX Pipeline Deep Dive

The VFX pipeline processes effects in the following order:

### 1. **Effect Classification**
- **Static Effects:** Applied once to the source image (blur, glow, reflection, etc.)
- **Dynamic Effects:** Re-applied every frame (flash_in, light_sweep)
- **Transform Effects:** Modify position/scale over time (float_y, pulse)

### 2. **Processing Flow**

```
User Code: fx=[glow(color="#FF0000"), blur(radius=5)]
    ↓
Parser/Lang: [("glow", {"color": "#FF0000"}), ("blur", {"radius": 5})]
    ↓
Compositor._split_fx(): (static=[("glow", {...}), ("blur", {...})], dynamic=[], float=[], pulse=[])
    ↓
Compositor._apply_fx_stack():
  1. Apply glow to PIL Image
  2. Apply blur to result
    ↓
Static FX baked into layer clip
    ↓
Dynamic FX applied per-frame via _apply_dynamic_fx()
    ↓
Final composited video
```

### 3. **Effect Parameters**
All effects accept both named and positional parameters:
- Named: `glow(color="#FF0000", intensity=2.0)`
- Positional: `glow("#FF0000", 2.0)` (order matters)
- Mixed: `glow("#FF0000", intensity=2.0)`

### 4. **Blend Mode Handling**
Blend modes are special: they don't modify the layer image, but instead control how the layer composes with the backdrop. The blend mode is extracted via `_blend_mode_of()` and stored as `clip._blend_mode` for use during compositing.

## Common Issues & Debugging

### 1. **VFX Effects Not Applying**
**Symptoms:** `fx=[glow(...), blur(...)]` has no visible effect

**Check:**
- Is the fx list being parsed correctly? Check `spec.fx` in lang.py
- Is the fx list reaching the compositor? Check `kw["fx"]` in _add_render
- Are effects being classified correctly? Check `_split_fx()` output
- Are parameters being extracted? Check `_fx_param()` calls in _apply_fx_stack

**Common Causes:**
- fx list is None or empty (not being parsed)
- Effect name typo (case-sensitive)
- Parameters are None or invalid types
- Image has no alpha channel (for glow/drop_shadow)

### 2. **Modern DSL Features Not Working**
**Symptoms:** loops, conditionals, functions, classes not executing

**Check:**
- Is the script being detected as modern? Check `_is_modern_source()`
- Is the lang.py interpreter being used? Check cli.py dispatch
- Are statements being executed? Add debug prints in Evaluator.exec_stmt

**Common Causes:**
- Indentation errors (modern DSL is strict about indentation)
- Syntax errors in control flow
- Module mode enabled (skips rendering)

### 3. **Asset Not Loading**
**Symptoms:** shape/image/text not appearing

**Check:**
- Is the asset being created? Check Asset creation in lang.py
- Is the asset being passed to the compositor? Check _add_render
- Is the asset data valid? Check asset.data is not None

**Common Causes:**
- Path is relative and file not found
- Shape parameters are invalid
- Font not found for text rendering

## Best Practices

### For AI Agents
1. **Always read AGENT.md first** - This is your source of truth
2. **Check both parsers** - Modern DSL uses lang.py, legacy uses parser.py
3. **Trace the data flow** - Source → AST → RenderSpec → Compositor → Video
4. **Test incrementally** - Verify each transformation step
5. **Respect the architecture** - Don't bypass the layer system

### For Human Developers
1. **Use the modern DSL** - It's cleaner and more maintainable
2. **Write regression tests** - Bug fixes need test coverage
3. **Keep effects stateless** - VFX functions should be pure (input image → output image)
4. **Handle edge cases** - Empty images, zero durations, None values
5. **Document assumptions** - Add comments explaining non-obvious behavior

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Python modules | snake_case.py | engine.py, vfx.py |
| Classes | PascalCase | Compositor, Evaluator |
| Functions | snake_case | apply_glow, parse_config |
| Variables | snake_case | max_workers, use_cache |
| Constants | UPPER_SNAKE | _FX_CALL_RE, _MPV2 |
| Test files | test_*.py | test_language.py |
| Example files | *.hmg | modern_demo.hmg |

## Git Workflow

1. **Feature branches:** `feature/name` for new features
2. **Bug fix branches:** `fix/name` for bug fixes
3. **Release branches:** `release/vX.Y` for releases
4. **Main branch:** `main` (protected, requires PR review)
5. **Commits:** Use imperative mood, reference issue numbers

## Performance Tips

1. **Cache PIL Images:** Convert to numpy once, not per-frame
2. **Use vectorization:** NumPy operations > Python loops
3. **Batch VFX:** Apply static effects once, not per-frame
4. **Limit layers:** Each layer is a separate MoviePy clip
5. **Use integer coordinates:** Avoid float positions when possible

## Known Limitations

1. **MoviePy 1.x vs 2.x:** Some APIs differ, code handles both
2. **Real-time preview:** Requires Remotion/Chrome, not pure Python
3. **GPU acceleration:** Limited by PIL/NumPy (CPU-only)
4. **Audio sync:** Depends on MoviePy's audio handling
5. **Memory usage:** Large videos consume significant RAM

## Future Enhancements

- GPU-accelerated VFX via CUDA/OpenCL
- WASM compilation for browser execution
- Type checking via mypy
- IDE integration (VS Code extension)
- Package distribution via PyPI
- CI/CD pipeline for automated testing

## Contacts & Resources

- **Author:** Adit Malik
- **Documentation:** docs/DSL_SPEC.md
- **Examples:** examples/ directory
- **Issues:** (Repository issue tracker)
- **Discussions:** (Repository discussions)

---

**Document Version:** 1.1  
**Last Updated:** 2026-10-11  
**Maintainer:** Adit Malik  
**Status:** Active Development

*This AGENT.md serves as the canonical guide for all development work on Motion Language. Keep it updated as the project evolves.*
