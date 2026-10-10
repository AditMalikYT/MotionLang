# Motion Language Repository Structure & Developer Guide

## Overview

This document describes the repository structure, development workflow, and architectural patterns for the Motion Language (.hmg) project. It serves as a companion to `AGENT.md`, providing deeper technical insights for contributors and maintainers.

## Repository Layout

```
motion_lang/
├── AGENT.md                    # Primary AI & developer guide
├── README.md                   # Project overview, quick start
├── docs/
│   ├── REPO_STRUCTURE.md       # This file - detailed structure
│   └── DSL_SPEC.md            # Language specification
├── examples/
│   ├── modern_demo.hmg        # Modern DSL showcase
│   ├── components/
│   │   └── ui.hmg             # Reusable components
│   └── *.hmg                  # Example scripts
├── motion_lang/               # Core implementation
│   ├── __init__.py
│   ├── cli.py                 # CLI entry point
│   ├── parser.py              # Legacy syntax parser
│   ├── lang.py                # Modern DSL interpreter
│   ├── engine.py              # Video compositor
│   ├── vfx.py                 # Visual effects pipeline
│   ├── shapes.py              # Shape primitives
│   ├── style.py               # CSS styling
│   ├── export.py              # Studio export
│   └── fetcher.py             # Asset loading
├── studio/                    # Web-based editor (Remotion)
│   ├── package.json
│   ├── README.md
│   └── src/
│       └── ...               # React + Remotion code
├── tests/                     # Test suites
│   ├── test_language.py
│   └── test_ae_features.py
├── assets/                    # Static assets
│   ├── logo/
│   ├── bg_music.mp3
│   └── ...
├── output/                    # Generated output (gitignored)
├── .venv/                     # Python virtual environment
├── setup.py
├── requirements.txt
└── .gitignore
```

## Module Architecture

### 1. **motion_lang/cli.py** - Command-Line Interface

**Purpose:** Entry point for the `motion` command.

**Key Components:**
- Argument parsing (file path, output, mode)
- Script detection (modern vs legacy syntax)
- Dispatch to appropriate runner
- Error handling and user feedback

**Supported Commands:**
```bash
motion script.hmg --render --output output.mp4      # Render to MP4
motion script.hmg --preview                       # Native preview
motion script.hmg --studio                        # Export for Remotion
```

### 2. **motion_lang/lang.py** - Modern DSL Interpreter

**Purpose:** Parse and execute modern indentation-based Motion Language scripts.

**Architecture:**
- **Lark Grammar:** Defines syntax for modern DSL
- **Evaluator Class:** Core interpreter with environment management
- **AST Walkers:** Recursive evaluation of syntax tree
- **Type System:** Assets, Layers, Functions, Classes, Instances

**Key Features:**
- Variables and expressions
- Control flow (if/else, for/repeat)
- Functions with parameters and defaults
- Classes with methods
- Module system (import/export)
- Layer composition

**Integration Points:**
- Delegates to `Compositor` for rendering
- Uses `Asset` to represent media
- Passes `RenderSpec` to engine

### 3. **motion_lang/parser.py** - Legacy Syntax Parser

**Purpose:** Parse legacy brace-based syntax using Lark grammar.

**Architecture:**
- **Lark Grammar:** Defines legacy syntax
- **Transformer Classes:** Convert parse tree to render operations
- **Regex Fallbacks:** Robust parsing across Lark versions
- **FX Extraction:** Parse `fx=[...]` effect stacks

**Status:** Maintained for backward compatibility. New features should be added to both parsers or prefer the modern DSL.

### 4. **motion_lang/engine.py** - Video Compositor

**Purpose:** Compose layers, animations, and effects into video frames.

**Architecture:**
- **Compositor Class:** Manages layers, audio, and rendering
- **Clip Management:** MoviePy clip creation and manipulation
- **Animation System:** Keyframe interpolation, easing functions
- **VFX Integration:** Static and dynamic effect application
- **CSS Support:** Style-based property overrides

**Key Systems:**
- Layer Z-index ordering
- Position and scale animation
- Opacity and transition effects
- Blend mode compositing
- FX offset compensation (for canvas-expanding effects)

### 5. **motion_lang/vfx.py** - Visual Effects Pipeline

**Purpose:** Implement After Effects-style visual effects.

**Architecture:**
- **Static Effects:** Applied once to source image (blur, glow, drop_shadow, etc.)
- **Dynamic Effects:** Re-applied per frame (flash, light_sweep)
- **Transform Effects:** Modify position/scale over time (float_y, pulse)

**Effect Categories:**
1. **Canvas-Expanding:** glow, drop_shadow, reflection
   - These require position offset compensation
2. **Pixel-Modifying:** blur, chromatic_aberration, glitch, vignette
   - Modify pixels without changing dimensions
3. **Time-Based:** flash_in, light_sweep
   - Change appearance over time
4. **Motion:** float_y, pulse
   - Animate transform properties

**Integration:**
- Called by `Compositor._apply_fx_stack()`
- Returns modified PIL Image
- Tracks canvas offset for positioning

### 6. **motion_lang/shapes.py** - Shape Primitives

**Purpose:** Generate vector shapes as PIL Images.

**Supported Shapes:**
- Rectangle (rect)
- Circle
- Ellipse
- Polygon
- Star
- Line
- Path (SVG-style)

**Features:**
- Custom colors
- Stroke and fill
- Rounded corners
- Star outer/inner radius

### 7. **motion_lang/style.py** - CSS Styling

**Purpose:** Apply CSS-like styles to layers and shapes.

**Features:**
- Class and ID selectors
- Property inheritance
- Shape recoloring
- Background colors
- Border radius

### 8. **motion_lang/export.py** - Studio Export

**Purpose:** Export timeline for Remotion web editor.

**Output:** composition.json with:
- Frame-accurate specifications
- Asset manifests
- Layer properties
- Effect parameters

### 9. **motion_lang/fetcher.py** - Asset Loading

**Purpose:** Load and cache media assets.

**Supported Sources:**
- Local files (PNG, JPG, MP4, etc.)
- Wikipedia images
- Web URLs

**Features:**
- Automatic caching
- Fallback generation
- Path resolution

## Development Workflow

### 1. **Setting Up**

```bash
# Clone and setup
cd motion_lang
git submodule update --init --recursive
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .

# For studio (web editor)
cd studio
npm install
npm run dev
```

### 2. **Running Tests**

```bash
# Run all tests
python tests/test_language.py
python tests/test_ae_features.py

# Run specific test
python -m pytest tests/test_language.py::test_functions_and_defaults -v
```

### 3. **Adding Features**

**For Language Features (modern DSL):**
1. Add grammar rules in `lang.py` (DSL_GRAMMAR)
2. Add evaluation handler in `Evaluator` class
3. Add tests in `test_language.py`
4. Update documentation in `docs/DSL_SPEC.md`

**For Visual Effects:**
1. Add effect function in `vfx.py`
2. Register in `_FX_NAMES` in `lang.py`
3. Add handling in `_apply_fx_stack` in `engine.py`
4. Add offset tracking if effect expands canvas
5. Add tests in `test_ae_features.py`

**For Shapes:**
1. Add shape function in `shapes.py`
2. Register in builtins in `lang.py`
3. Add tests

### 4. **Debugging Tips**

**Logging:**
- Use `[DSL Warning]` prefix for user-facing warnings
- Use `[Engine]`, `[VFX]`, `[Style]` for debug output
- Avoid bare `print()` in production code

**Common Issues:**
1. **Parser errors:** Check Lark grammar and tree structure
2. **VFX not applying:** Verify fx list reaches compositor
3. **Positioning issues:** Check for canvas-expanding effects
4. **Module not found:** Verify base_dir and file paths

**Debug Tools:**
```python
# Patch methods to add debug output
from motion_lang import engine
original = engine.Compositor._apply_fx_stack
def debug_apply_fx_stack(self, *args, **kwargs):
    print(f"Applying FX: {kwargs.get('fx', args[1] if len(args) > 1 else '?')}")
    return original(self, *args, **kwargs)
engine.Compositor._apply_fx_stack = debug_apply_fx_stack
```

### 5. **Performance Considerations**

**General:**
- Use `@lru_cache` for pure functions
- Prefer NumPy vectorization over loops
- Cache PIL Images, not per-frame
- Batch operations where possible

**VFX Specific:**
- Static effects: Apply once to source
- Dynamic effects: Only when necessary
- Avoid per-frame PIL operations
- Use MoviePy's built-in effects when possible

**Memory:**
- Large videos consume significant RAM
- Use `skip_build=True` for testing
- Clean up temporary files
- Be mindful of clip composition order

## Architectural Patterns

### 1. **Asset Pipeline**

```
User Code: shape("rect", width=100, color="#FF0000")
    ↓
Parser/AST: call_expr node
    ↓
Evaluator._builtin_shape(): Creates Asset("image", PIL.Image)
    ↓
RenderSpec: asset, fx, pos, etc.
    ↓
Compositor._add_render(): Calls add_image_layer
    ↓
Compositor.add_image_layer(): Applies FX, creates ImageClip
    ↓
Compositor._compose_clip(): Sets up transforms, animations
    ↓
Compositor.layers: List of (z_index, clip)
    ↓
Compositor.build(): Renders to video
```

### 2. **Effect Pipeline**

```
User Code: fx=[glow(color="#FF0000"), blur(radius=5)]
    ↓
Parser: [("glow", {"color": "#FF0000"}), ("blur", {"radius": 5})]
    ↓
Compositor._split_fx(): (static=[glow, blur], dynamic=[], float=[], pulse=[])
    ↓
Compositor._apply_fx_stack():
  1. apply_glow() → image size changes, offset tracked
  2. apply_blur() → image processed
    ↓
Position adjustment: pos + offset
    ↓
ImageClip created with adjusted position
```

### 3. **Layer Composition**

```
Scene with multiple layers:
  layer(z=1): render(bg, ...)
  layer(z=2): render(text, fx=[glow(...)])
  layer(z=3): render(shape, ...)
    ↓
Compositor.layers sorted by z_index:
  [(1, bg_clip), (2, text_clip), (3, shape_clip)]
    ↓
Final composition:
  bg_clip at bottom
  text_clip (with glow) in middle
  shape_clip at top
```

## Module Dependencies

```
cli.py
  └── parser.py (legacy)
  └── lang.py (modern)
      ├── engine.py
      │   ├── vfx.py
      │   ├── shapes.py
      │   └── style.py
      ├── fetcher.py
      └── export.py

studio/
  └── motion_lang/ (via export.py)

tests/
  ├── test_language.py → lang.py, engine.py
  └── test_ae_features.py → engine.py, vfx.py, parser.py
```

## Testing Strategy

### Unit Tests
- **test_language.py:** Modern DSL features
- **test_ae_features.py:** VFX and composition

### Test Coverage
- Parse all example files
- Test each effect individually
- Test combinations of effects
- Test edge cases (empty, invalid parameters)
- Test both MoviePy 1.x and 2.x compatibility

### Regression Tests
- Add tests for all bug fixes
- Test backward compatibility
- Verify performance characteristics

## Style Guide

### Python
- **Type Hints:** Always use PEP 484 annotations
- **Naming:** snake_case for functions/vars, PascalCase for classes
- **Imports:** Grouped (stdlib, third-party, local)
- **Docstrings:** Google-style for all public APIs
- **Error Messages:** Clear, actionable, include context

### Motion Language
- **Indentation:** 4 spaces, no tabs
- **Comments:** // for single-line, /* */ for multi-line
- **Naming:** camelCase or snake_case for variables/functions
- **Strings:** Double quotes preferred
- **Line Length:** 100 characters maximum

## Version Compatibility

### Python
- **Required:** 3.13+
- **Tested:** 3.13, 3.14 (when available)

### Dependencies
- **Lark:** 1.x for parsing
- **MoviePy:** 1.x and 2.x supported
- **Pillow:** Latest stable
- **NumPy:** Latest stable
- **Remotion:** For studio (Node.js 18+)

### Backward Compatibility
- Maintain legacy parser for brace syntax
- Test with both MoviePy versions
- Document breaking changes

## Documentation Standards

### Code Documentation
- All public APIs documented
- Complex logic explained with comments
- Workarounds and limitations noted
- Examples in docstrings

### User Documentation
- Keep README.md up to date
- Update DSL_SPEC.md for language changes
- Add examples for new features
- Document known issues

## Release Process

### Versioning
- **Semantic Versioning:** MAJOR.MINOR.PATCH
- **MAJOR:** Breaking changes
- **MINOR:** New features, backward compatible
- **PATCH:** Bug fixes, backward compatible

### Release Checklist
1. Run full test suite
2. Update version in setup.py
3. Update CHANGELOG/RELEASES
4. Test with clean virtual environment
5. Build distribution packages
6. Tag release in git
7. Publish to PyPI (future)

### Branching Strategy
- **main:** Stable, tested code
- **feature/*:** New features, merged via PR
- **fix/*:** Bug fixes, merged via PR
- **release/*:** Release preparation
- **dev:** Development branch (optional)

## Contribution Guidelines

### Getting Started
1. Read AGENT.md and this file
2. Join the discussions (if applicable)
3. Look for "good first issue" labels
4. Ask questions if unsure

### Submitting Changes
1. Fork the repository
2. Create feature/fix branch
3. Make changes with tests
4. Update documentation
5. Submit PR with clear description

### Code Review
1. All PRs require review
2. Tests must pass
3. Documentation must be updated
4. Follow style guidelines
5. Address feedback promptly

## Troubleshooting

### Common Issues

**"Module not found" errors:**
- Check virtual environment activation
- Verify package is installed (`pip install -e .`)
- Check Python path

**Parser errors:**
- Verify syntax in DSL_SPEC.md
- Use modern DSL (indentation-based)
- Check for typos

**VFX not visible:**
- Verify fx list is not empty
- Check effect parameters
- Test with simple case first
- Check for canvas expansion offset issues

**Positioning issues:**
- Verify coordinate system (0,0 is top-left)
- Check for canvas-expanding effects
- Use numeric coordinates instead of keywords

**Performance problems:**
- Check video resolution and fps
- Reduce number of layers
- Use static effects instead of dynamic where possible
- Check for unnecessary computations

## Future Architecture Improvements

### Short Term (3-6 months)
1. Complete MoviePy 2.x migration
2. Add more shape types
3. Improve error messages
4. Add more blend modes
5. Performance optimizations

### Medium Term (6-12 months)
1. WASM compilation for browser
2. Type checking with mypy
3. IDE integration
4. GPU-accelerated VFX
5. Audio effects pipeline

### Long Term (1-2 years)
1. Standalone binary distribution
2. Real-time preview without MoviePy
3. Distributed rendering
4. Plugin system for effects
5. Version control for assets

## Maintenance Checklist

### Regular
- [ ] Run full test suite
- [ ] Check for dependency updates
- [ ] Review and triage issues
- [ ] Update documentation
- [ ] Clean up temporary files

### Before Release
- [ ] Run tests on all supported Python versions
- [ ] Test with MoviePy 1.x and 2.x
- [ ] Verify all examples work
- [ ] Update version numbers
- [ ] Review changelog

### After Release
- [ ] Announce release
- [ ] Update website/documentation
- [ ] Monitor for issues
- [ ] Tag version in git

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-10  
**Maintainer:** Adit Malik  
**Status:** Active Development
