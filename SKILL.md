# Motion Language (.hmg) - Advanced Motion Graphics Mastery (`SKILL.md`)

This guide outlines advanced engineering patterns, mathematical animation workflows, video cutting/slicing pipelines, CSS styling, Python module integration, and cinematic transition orchestration in Motion Language (`.hmg`).

---

## 1. Core Architectural Overview

Motion Language is structured as a modular DSL combining:
- **Lark-based Parser & AST Engine** (`motion_lang/grammar.lark`)
- **Python Runtime & Math Evaluator** (`motion_lang/interpreter.py`, `math_engine.py`)
- **Video & VFX Pipeline** (`motion_lang/video_engine.py`, MoviePy/OpenCV integration)
- **CSS Styling Parser** (`motion_lang/css_parser.py`)
- **Remotion Web Studio Frontend** (`studio/`)

---

## 2. Advanced Mathematical Motion & Procedural Animation

Motion Language evaluates expressions per frame (`$t` or `frame`) to drive properties dynamically. You can use math functions to create organic, physics-like, or geometric animations without keyframing manually.

### Available Math Functions & Constants
- **Trigonometry:** `sin(x)`, `cos(x)`, `tan(x)`, `asin(x)`, `acos(x)`, `atan2(y, x)`
- **Algebra & Logic:** `abs(x)`, `floor(x)`, `ceil(x)`, `round(x)`, `pow(x, y)`, `sqrt(x)`
- **Motion Utilities:** 
  - `lerp(a, b, t)` — Linear interpolation: $a + (b - a) \times t$
  - `clamp(val, min_val, max_val)` — Restricts values to boundaries
  - `map_range(val, in_min, in_max, out_min, out_max)` — Remaps scales
  - `noise(x, y)` — 2D Perlin noise for organic shaking/floating effects
- **Constants:** `pi`, `e`

### Example: Procedural Orbit & Harmonic Scale
```hmg
# Lissajous Orbit with Harmonic Pulsing
freq_x = 2.0
freq_y = 3.0

cx = 960 + sin($t * freq_x) * 400
cy = 540 + cos($t * freq_y) * 250
pulse = 1.0 + sin($t * 6.0) * 0.15

circle(pos=(cx, cy), radius=80 * pulse, fill="#00E5FF", opacity=0.85)
```

---

## 3. Video Cutting, Trimming & Time Manipulation

Imported video assets can be sliced, trimmed, and time-stretched directly in the DSL script.

### Video Pipeline Methods
- `import_video("path/to/file.mp4")`
- `.cut(start=seconds, end=seconds)` or `.trim(start, duration)`
- `.speed(multiplier)` (e.g., `0.5` for slow-motion, `2.0` for timelapse)
- `.loop(count)` or `.hold(duration)`

### Example: Video Slicing & Slow-Motion
```hmg
# Import background plate, trim unwanted frames, and slow down
bstock = import_video("assets/drone_shot.mp4")
         .cut(start=4.0, end=12.5)
         .speed(0.75)
         .pos((0, 0))
         .opacity(0.6)
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

# Load Google Font dynamically
title_font = load_font("Poppins", weight="700", url="https://fonts.googleapis.com/css2?family=Poppins:wght@700&display=swap")

text("MOTION LANGUAGE", class="hero-title", pos=(960, 400), anchor="center")
text("Next-Gen Motion Graphics DSL", class="subtitle", pos=(960, 520), anchor="center")
```

---

## 5. Native Python Module Interoperability

Import any installed Python library (`math`, `numpy`, custom scripts) to compute complex parametric paths or procedural layouts.

```hmg
import math
import numpy as np

# Generate a spiral particle coordinate array using NumPy
angles = np.linspace(0, 10 * np.pi, 100)
radii = angles * 15

for i in range(100):
    r = radii[i]
    theta = angles[i] + ($t * 0.5)
    px = 960 + r * math.cos(theta)
    py = 540 + r * math.sin(theta)
    
    circle(pos=(px, py), radius=4, fill="#FF007F")
```

---

## 6. Cinematic Transitions & Scene Orchestration

Blend elements or scenes smoothly using built-in transition functions.

### Transition Types
- `crossfade(duration=0.8)`
- `wipe(direction="left"|"right"|"up"|"down", duration=0.5)`
- `slide(direction="left"|"right", duration=0.5)`
- `zoom_in(duration=0.6)` / `zoom_out(duration=0.6)`

### Example: Scene Composition & Transitions
```hmg
scene IntroScene {
    logo = image("assets/logo.png", pos=(960, 540), duration=4.0)
    fade_in(logo, duration=1.0)
}

scene MainScene {
    content = text("Welcome to Production", pos=(960, 540), duration=5.0)
}

transition(from=IntroScene, to=MainScene, type="crossfade", duration=0.7)
```

---

## 7. Professional Production Checklist

1. **Caching:** Always leverage the built-in caching engine (`motion script.hmg --render`) to skip unchanged frames during iterative testing.
2. **Interactive Studio:** Run `motion script.hmg --studio` to tweak positions interactively with mouse dragging and preview with spacebar play/pause.
3. **Exporting:** Render final high-framerate video outputs using multi-core workers:
   ```bash
   motion script.hmg --render --workers 8 --output output/master.mp4