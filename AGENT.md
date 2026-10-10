# AGENT.md - Motion Language (.hmg) Repository Guide

Welcome to the **Motion Language** repository. This document outlines the project architecture, module layout, syntax rules, and development guidelines for contributors and autonomous AI agents working on this independent, high-performance programming language and motion graphics engine.

## Project Metadata

- **Creator / Author:** Adit Malik
- **File Extension:** `.hmg`
- **Language Version:** Motion Language 1.0 (Modern DSL)
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
│   ├── lang.py                 # Modern DSL interpreter (indentation-based)
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
│   └── src/                    # React + Remotion source
│
├── docs/                       # Documentation
│   └── DSL_SPEC.md             # Full language specification
│
├── tests/                      # Test suites
│   ├── test_language.py        # Modern DSL interpreter tests
│   └── test_ae_features.py      # After Effects feature compatibility tests
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

// Export
export MyComponent
```

#### 4. **Rendering Primitives**
- `shape("type", ...)` - rect, circle, ellipse, polygon, line, path
- `text("content", ...)` - styled text rendering
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
- `linear`, `ease_in`, `ease_out`, `ease_in_out`, `bounce`

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
- `motion` command entry point
- Modes: render, preview, studio
- Configuration management
- File watching & development server

### 9. **Asset Fetcher (fetcher.py)**
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
| lang.py | Modern DSL interpreter | `Evaluator`, `Env`, `Asset`, `Layer` |
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

**Document Version:** 1.0  
**Last Updated:** 2026-10-10  
**Maintainer:** Adit Malik  
**Status:** Active Development

*This AGENT.md serves as the canonical guide for all development work on Motion Language. Keep it updated as the project evolves.*
