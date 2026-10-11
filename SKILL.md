# Motion Language (.hmg) - Advanced Motion Graphics Mastery (`SKILL.md`)

This guide outlines advanced engineering patterns, mathematical animation workflows, video cutting/slicing pipelines, CSS styling, Python module integration, and cinematic transition orchestration in Motion Language (`.hmg`).

---

## 1. Core Architectural Overview

Motion Language is structured as a modular DSL combining:
- **Lark-based Parser & AST Engine** (`motion_lang/grammar.lark`, `motion_lang/lang.py` for modern syntax, `motion_lang/parser.py` for legacy brace syntax)
- **Python Runtime & Math Evaluator** (`motion_lang/lang.py`, `motion_lang/math_engine.py`, `motion_lang/modules.py`)
- **Video & VFX Pipeline** (`motion_lang/engine.py`, `motion_lang/vfx.py`, `motion_lang/video_engine.py`, `motion_lang/shapes.py`, MoviePy/OpenCV integration)
- **CSS Styling + Typography** (`motion_lang/style.py`, `motion_lang/text_engine.py`)
- **Asset Loading** (`motion_lang/fetcher.py`)
- **Remotion Web Studio Frontend** (`studio/`)

---

## 2. Advanced Mathematical Motion & Procedural Animation

Motion Language evaluates `$t` (clip-local seconds) and `$frame` (`$t * fps`)
per frame, but **only inside `render()` properties** (`pos`, `scale`,
`opacity`, `rotation`, `rotation_x`, `rotation_y`, and their `*_end` pairs).
Using `$t` anywhere else is a `[DSL Error]`. You can use math functions to
create organic, physics-like, or geometric animations without keyframing manually.

### Available Math Functions & Constants
- **Trigonometry:** `sin(x)`, `cos(x)`, `tan(x)`, `asin(x)`, `acos(x)`, `atan(x)`, `atan2(y, x)`
- **Algebra & Logic:** `abs(x)`, `floor(x)`, `ceil(x)`, `round(x)`, `pow(x, y)`, `sqrt(x)`
- **Motion Utilities:** 
  - `lerp(a, b, t)` — Linear interpolation
  - `clamp(val, min_val, max_val)` — Restricts values to boundaries
  - `map_range(val, in_min, in_max, out_min, out_max)` — Remaps scales
  - `noise(x, y=0, seed=0)` — Deterministic smooth value noise in [0, 1]
- **Constants:** `pi`, `e`, `tau`

### Example: Procedural Orbit & Harmonic Scale
```hmg
config:
    resolution = 1280x720
    fps = 30

scene:
    layer(z=1):
        orb = shape("circle", radius=80, color="#00E5FF")
        // $t is legal here: pos/scale/opacity are per-frame render() props
        render(orb, time=[0, 6],
               pos=(640 + sin($t * 2.0) * 400, 360 + cos($t * 3.0) * 250),
               scale=1.0 + sin($t * 6.0) * 0.15,
               opacity=0.85)
```

---

## 3. Video Cutting, Trimming & Time Manipulation

Imported video assets can be sliced, trimmed, and time-stretched directly in the DSL script.

### Video Pipeline Methods
- `video("path/to/file.mp4", start=, end=, speed=)` (alias: `import_video(...)`)
- `.cut(start=seconds, end=seconds)` / `.trim(start=, end= / duration=)` / `.subclip(start=, end=)`
- `.speed(multiplier)` (e.g., `0.5` for slow-motion, `2.0` for timelapse; clamped to `[0.05, 16]`)
- `.pos((x, y))` — default position used when `render()` omits `pos`

### Example: Video Slicing & Slow-Motion
```hmg
config:
    resolution = 1280x720
    fps = 30

// Trim on import, then chain editorial ops (all lazy)
bstock = import_video("assets/drone_shot.mp4").cut(start=4.0, end=12.5).speed(0.75).pos((0, 0))

scene:
    layer(z=1):
        // pos/size/opacity are render() options, not video() options
        render(bstock, time=[0, 8], pos=(0, 0), size=(1280, 720), opacity=0.6)
```

---

## 4. CSS Stylesheet Integration & Google Fonts

You can decouple styling from layout by importing external `.css` stylesheets and dynamic typography.

### 1. Stylesheet (`theme.css`)
```css
.hero-title {
    font-family: "Poppins";
    font-weight: 700;
    font-size: 96px;
    color: #FFFFFF;
    fx: glow(radius=25, intensity=1.8);
}

.subtitle {
    font-family: "Inter";
    font-size: 32px;
    color: #00E5FF;
}
```

### 2. Using CSS & Google Fonts in `.hmg`
```hmg
import styles from "theme.css"

// Load Google Font dynamically (cached at ~/.cache/motion_lang/fonts/)
title_font = load_font("Poppins", weight="700")

scene:
    layer(z=2):
        // pos/class are render() options; the asset only carries styling
        render(text("MOTION LANGUAGE", font=title_font, class="hero-title"),
               pos=(640, 400), time=[0, 4])
        render(text("Next-Gen Motion Graphics DSL", class="subtitle"),
               pos=(640, 520), time=[0, 4])
```

---

## 5. Native Python Module Interoperability

Import any installed Python library (`math`, `numpy`, custom scripts) to compute complex parametric paths or procedural layouts.

```hmg
import math
import numpy as np

// Generate a spiral of particles with per-frame $t motion.
// NOTE: $t may only appear inside render() props (pos/scale/... here),
// never in plain assignments or loop bodies.
config:
    resolution = 1280x720
    fps = 30

angles = np.linspace(0, 10 * np.pi, 100)
radii = angles * 1.5

scene:
    layer(z=2):
        for i in range(100):
            r = radii[i]
            phase = angles[i]
            dot = shape("circle", radius=4, color="#FF007F")
            render(dot, time=[0, 6],
                   pos=(640 + cos(phase + $t * 0.5) * r,
                        360 + sin(phase + $t * 0.5) * r))
```

---

## 6. Cinematic Transitions & Scene Orchestration

Blend elements or scenes smoothly using built-in transition functions.

### Transition Types (inline `transition_in=` / `transition_out=` strings)
- `crossfade(0.8)` / `dissolve(0.8)` / `fade(0.5)`
- `wipe_left(0.5)` / `wipe_right` / `wipe_up` / `wipe_down`
- `slide_left` / `slide_right` / `slide_up` / `slide_down`
- `zoom_in(0.6)` / `zoom_out(0.6)`
- `glitch(0.3, intensity=0.8, seed=7)`

The `transition(from=, to=, type=, duration=)` statement wires two
`render()` layers (overlap their `time=` windows by `duration`).

### Example: Scene Composition & Transitions
```hmg
config:
    resolution = 1280x720
    fps = 30

scene:
    layer(z=1):
        la = render(image("assets/logo.png"), pos=(640, 360),
                    time=[0, 4], transition_out="crossfade(0.7)")
    layer(z=2):
        lb = render(text("Welcome to Production", size=48), pos=(640, 360),
                    time=[3.3, 8], transition_in="crossfade(0.7)")
    transition(from=la, to=lb, type="crossfade", duration=0.7)
```

---

## 7. SVG Vectors by Code + 2D/3D Transforms

`svg()` accepts a file path, inline markup, or raw path data, so multi-shape
artwork (`rect`/`polygon`/`path` with `style="fill:..."`) works with no asset
files. Without paint kwargs colours stay faithful; with `fill=`/`color=` it
renders as a recoloured icon:

```hmg
config:
    resolution = 1280x720
    fps = 30

icon = svg("assets/icons/bolt.svg", width=128, height=128, fill="#00E5FF")
mark = svg("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='42' fill='#FFC052'/></svg>",
           width=110, height=110)
box = svg("M0 0 L120 0 L120 120 L0 120 Z", width=120, height=120, fill="#FF2E88")

scene:
    layer(z=2):
        // 2D roll (+ = clockwise, centre-anchored): keyframe, ease, or $t
        render(icon, pos=(576, 296), time=[0, 4], rotation=0 -> 360)
        render(box, pos=(180, 420), time=[0, 4], rotation=sin($t * 1.5) * 12)
    layer(z=3):
        // pseudo-3D tilt (OpenCV homography; perspective= focal factor)
        render(mark, pos=(990, 120), time=[0, 4],
               rotation_x=35, rotation_y=$t * 25, perspective=2.5)
```

`rotation`, `rotation_x`, `rotation_y` (and `*_end`) compose with
`pos`/`scale`/`opacity` keyframes, easing, and `float_y`/`pulse` fx.

---

## 7. Professional Production Checklist

1. **Caching:** Always leverage the built-in caching engine (`motion script.hmg --render`) to skip unchanged frames during iterative testing.
2. **Interactive Studio:** Run `motion script.hmg --studio` to tweak positions interactively with mouse dragging and preview with spacebar play/pause.
3. **Exporting:** Render final video outputs (use `--workers N` to parallelise asset fetching):
   ```bash
   motion script.hmg --render --workers 8 --output output/master.mp4