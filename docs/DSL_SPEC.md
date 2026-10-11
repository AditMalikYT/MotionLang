# Motion Language — DSL Specification

> A declarative-to-imperative video language that is **cleaner than Python**:
> no `var`/`let`, no braces, no boilerplate punctuation — just indentation,
> native operators, first-class functions, classes and modules, compiled to
> MP4 by MoviePy and previewable/edited in a real-time Remotion web studio.

This document specifies the **modern syntax** (`config:` / `fn` / `class` /
`scene:`). The original brace syntax (`init { }` / `asset` / `scene { }`) is
still fully supported; the compiler auto-detects which one a file uses.

---

## 1. Design goals

| Goal | How |
| --- | --- |
| Expressive & terse | Indentation blocks, no `var`, no braces, no semicolons |
| Familiar & learnable | Python-ish reading, JavaScript-ish `import ... from` |
| Real programming | Variables, operators, functions, classes, modules, loops |
| Video-first | `scene:` / `layer(z=)` / `render(...)` / `audio:` directives |
| Deterministic renders | Seeded effects, pure function evaluation |
| Live editing | `--studio` exports a timeline for the Remotion editor |

---

## 2. Lexical structure

- **Indentation** defines blocks (4 spaces recommended; tabs = 4 spaces).
  A block opens after a `:` at the end of a line.
- **Comments** start with `//` and run to end of line — including trailing
  comments (`vari = 1 // note`). Single `/` remains the division operator.
- **Statements** are newline-terminated; no semicolons.
- **Identifiers**: `[A-Za-z_][A-Za-z0-9_]*`.
- **Strings**: double-quoted, standard escapes (`"he said \"hi\""`).
- **Numbers**: integers and floats (`42`, `0.8`). Resolution literals use
  the `WxH` form (`1280x720`).
- **Booleans**: `true`, `false`.

---

## 3. Operators

Precedence, low → high:

| Level | Operators | Notes |
| --- | --- | --- |
| conditional | `x if c else y` | Python-style ternary, right-nested; only `c` runs at build time, the winning arm runs (per frame when `c` varies with `$t`) |
| range | `a -> b` | keyframe range, evaluated per option |
| logical or | `or` | short-circuits, returns operand |
| logical and | `and` | short-circuits |
| not | `not x` | unary |
| comparison | `== != > < >= <=` | chainable: `0 < x < 10` |
| additive | `+ -` | numbers or string concat |
| multiplicative | `* / %` | `/` yields float, `%` modulo |
| unary | `-x` | negation |
| call / member | `f(...)`, `self.x`, `a.b(...)`, `a[i]` | |

```hmg
base_duration = 5
card_scale = 0.8 + 0.1
total = (units * 2) + 10
inside = 0 < offset < 100
fade = 1 - (idx / 3)
grow = 0.4 -> 1.2          // Range object: start -> end
col = GOLD if i % 2 == 0 else CYAN                  // ternary
tone = GOLD if i % 3 == 0 else (CYAN if i % 3 == 1 else PINK)  // nested
```

Values flow through expressions; `->` produces a `Range` that `render(...)`
interprets as a start→end animation (see §9).

---

## 4. Types

| Type | Literal / constructor | Example |
| --- | --- | --- |
| Number | `42`, `3.14` | `x = 10.5` |
| String | `"text"` | `s = "FAST"` |
| Boolean | `true`, `false` | `on = true` |
| List | `[a, b, c]` | `items = ["A", "B"]` |
| Tuple | `(x, y)` | `pos = (100, 200)` |
| Range | `a -> b` | `scale = 0.2 -> 0.8` |
| Asset | `shape/text/file/wiki/video/audio` | `bg = shape("rect", ...)` |
| Layer | `layer(z=):` block | `return layer(z=2): ...` |
| Function | `fn` | `fn f(x): ...` |
| Class / Instance | `class` | `b = Box(3)` |
| `null` | implicit (missing return / `print`) | — |

---

## 5. Variables

Assignment binds a name; no keyword required. Targets may be a name, an
attribute (`self.x`), or an index (`arr[0]`).

```hmg
base_duration = 5
card_scale = 0.8 + 0.1
self.title = text("HELLO")
items[0] = "NEW"
```

Names resolve lexically (function bodies see their defining scope). Undefined
names raise a runtime error.

---

## 6. Functions

```hmg
fn name(param, other=default):
    // body
    return value
```

- `return` is optional; a function with no `return` yields `null`.
- Default parameter values are evaluated in the defining scope.
- Recursion is supported.
- Parameters without a matching argument become `null`.

```hmg
fn create_badge(text_val, x, y):
    bg = shape("rect", width=200, height=60, color="#1e1e2e", radius=12)
    label = text(text_val, font="Helvetica", size=24, color="#FFFFFF")
    return layer(z=3):
        render(bg, pos=(x, y))
        render(label, pos=(x + 20, y + 15))

fn fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)
```

---

## 7. Classes (OOP)

```hmg
class Name:
    fn init(self, ...):      // constructor (also accepts __init__)
        self.field = ...
    fn method(self, ...):
        return ...
```

- `init` runs on construction; `self` is the instance.
- Attribute access `obj.field`; method calls `obj.method(...)`.
- Undefined members raise a runtime error.

```hmg
class HeroWidget:
    fn init(self, title_text, asset_query):
        self.title = text(title_text, size=48, color="#00E5FF")
        self.avatar = wiki(asset_query)

    fn build(self, start_t):
        return layer(z=2):
            render(self.avatar, time=[start_t, start_t + 4], pos=(450, 200), scale=0.6)
            render(self.title, time=[start_t + 0.5, start_t + 4], pos=(400, 450), fx=[glow(color="#00E5FF")])

hero = HeroWidget("EAGLE VISION", "eagle")
```

---

## 8. Control flow

### if / else if / else

```hmg
if show_hero == true:
    hero.build(start_t=0.5)
else if alt_hero:
    other.build()
else:
    layer(z=2):
        render(shape("circle", radius=100, color="#FF0055"), time=[0, 5], pos=(540, 260))
```

`elif` is also accepted as an alias for `else if`. Comparison chains work:
`if 0 <= score < 10:`.

### Ternary `x if c else y`

For value selection, Python-style ternaries nest to the right; only the
condition runs eagerly, and the winning arm runs afterwards — so a
time-varying condition (`10 if $t > 2 else 5`) re-selects every frame:

```hmg
for i in range(6):
    col = GOLD if i % 2 == 0 else CYAN
    tone = GOLD if i % 3 == 0 else (CYAN if i % 3 == 1 else PINK)
```

### for ... in

Iterates lists, tuples, ranges and strings.

```hmg
for item in ["FAST", "CLEAN", "MOTIONS"]:
    print(item)

for i in range(5):
    print(i)
```

**Enumerate sugar (cleaner than Python):** a two-name target over a
non-pair iterable yields `(index, value)`:

```hmg
for idx, item in items:
    create_badge(item, x=100 + (idx * 220), y=600)
```

When the elements *are* pairs (`[[1, "a"], [2, "b"]]`), they are unpacked.

### repeat N times as i

```hmg
repeat 3 times as i:
    bg = shape("rect", width=1280, height=720, color="#0a0a10")
    layer(z=1):
        render(bg, time=[i * 2, (i + 1) * 2])
```

`as i` is optional (`repeat 3 times:`); `i` is the 0-based counter.

---

## 9. Directives

### config:

Declares canvas/frame/output settings. Placed at the top of a script.

```hmg
config:
    resolution = 1280x720
    fps = 30
    mode = "preview"        // "preview" | "render"
```

`resolution` may also be a tuple `(1280, 720)`. Defaults: `1280x720`, `30`, `render`.

### scene:

The composition timeline. Executed top-to-bottom; every `layer(...)` block
(and every expression statement that returns a `Layer`) is committed to the
render stack.

A scene can take a **name** (`scene Intro:`) — the body still renders at its
absolute times, and the name binds to the committed layers so whole scenes
can be wired by `transition()`:

```hmg
scene Intro:
    layer(z=1):
        render(title, time=[0, 4], pos=(100, 100))
scene Outro:
    layer(z=2):
        render(badge, time=[3.5, 8], pos=(100, 100))
transition(from=Intro, to=Outro, type="wipe", duration=0.5)
```

`Scene` handles expose `.start` (earliest layer start), `.end` (latest
layer end) and `len()` (layer count).

### layer(z=N):

Opens a layer scope with z-order `N`. `render(...)` calls inside append to it.

```hmg
scene:
    layer(z=1):
        render(bg, time=[0, 6], pos=(0, 0), size=(1280, 720))
    layer(z=2):
        render(title, time=[0, 4], pos=(100, 100), transition_in="fade(0.5s)")
```

A `layer(...)` block used inside a function is returned and committed by the
caller:

```hmg
fn card(x, y):
    return layer(z=3):
        render(shape("rect", width=100, height=100), pos=(x, y))
```

### render(asset, ...)

Places an asset on the current layer.

| Option | Type | Meaning |
| --- | --- | --- |
| `time` | `[start, end]` | visible window in seconds (default `[0, 6]`) |
| `start`, `end` | number | alternative to `time` |
| `pos` | `(x, y)` or `a -> b` | top-left position / keyframe |
| `pos_end` | `(x, y)` | explicit end position |
| `scale` | number or `a -> b` | scale / keyframe |
| `scale_end` | number | explicit end scale |
| `size` | `(w, h)` | explicit pixel size |
| `opacity` | number or `a -> b` | alpha / keyframe |
| `opacity_end` | number | explicit end alpha |
| `rotation` | number or `a -> b` | 2D roll in degrees (`+` = clockwise; centre-anchored) / keyframe |
| `rotation_end` | number | explicit end roll |
| `rotation_x` / `rotation_y` | number or `a -> b` | pseudo-3D tilt in degrees / keyframe |
| `rotation_x_end` / `rotation_y_end` | number | explicit end tilts |
| `perspective` | number | focal factor for tilt projection (default `3.0`; larger = flatter) |
| `easing` | string | `linear`, `ease`, `ease_in`, `ease_out`, `ease_in_out`, `ease_in_quad`, `ease_out_quad`, `ease_in_out_quad`, `ease_in_cubic`, `ease_out_cubic`, `ease_in_out_cubic`, `ease_in_quart`, `ease_out_quart`, `ease_in_out_quart`, `ease_in_quint`, `ease_out_quint`, `ease_in_out_quint`, `ease_in_sine`, `ease_out_sine`, `ease_in_out_sine`, `ease_in_expo`, `ease_out_expo`, `ease_in_out_expo`, `ease_in_circ`, `ease_out_circ`, `ease_in_out_circ`, `ease_in_back` / `back_in`, `ease_out_back` / `back_out`, `ease_in_out_back`, `ease_in_elastic`, `ease_out_elastic`, `ease_in_out_elastic`, `bounce` / `ease_out_bounce`, `ease_in_bounce`, `ease_in_out_bounce`, `smooth` / `smoothstep` |
| `transition_in` / `transition_out` | string | `fade(0.5s)`, `slide_left(0.5s)`, `zoom_in(0.5s)`, … |
| `fx` | `[ ... ]` | effect stack (see §11) |
| `class`, `id` | string | CSS class/id styling |
| `z` | int | only when `render` is used without a `layer` block |

### audio:

```hmg
audio:
    play(audio("assets/bg_music.mp3"), start=0, volume=0.3)
    for t in [1.0, 3.0, 5.0]:
        play(audio("assets/swoosh.wav"), start=t, volume=0.8)
```

`play(clip, start=0, volume=1.0)` mixes an audio asset onto the timeline.

---

## 10. Builtins

### Assets

| Call | Returns | Notes |
| --- | --- | --- |
| `shape(type, **opts)` | image | `type` ∈ `rect`, `circle`, `polygon`, `star`, `path`, `line`; opts: `width`, `height`, `radius` (stars also accept `outer_radius` + `inner_radius`, `points`), `color`/`fill` (solid hex or `gradient(linear\|radial, c1, c2[, angle])`), `stroke_color`, `stroke_width`, `points`, `svg`/`path` (for `path`), `x1`/`y1`/`x2`/`y2` + `width` = thickness (for `line`), … |
| `text(str, **opts)` | text | see text options below |
| `file(path)` | image | local image, loaded relative to the script (falls back to the working dir) |
| `image(path, width=, height=)` | image | local raster (`png`/`jpg`/`webp`) or SVG (`svg`/`svgz`, faithful colours via `cairosvg` when installed, else system rasteriser/fallback); `width=`/`height=` set SVG raster resolution |
| `svg(src, ...)` | image | vector defined **by code**: file path (`svg("icons/bolt.svg")`), inline markup (`svg("<svg...>...</svg>")`), raw path data (`svg("M0 0 L...Z")`), or `file=`/`markup=`/`path=` keywords. Without paint kwargs colours stay faithful; with `fill=`/`color=`/`gradient()`/`stroke_color=`/`stroke_width=` it renders as a recoloured icon (`width=`/`height=` set raster size) |
| `wiki(query)` / `web(query)` | image | local match first (`assets/<query>.*`), then web search |
| `video(path)` | video | local video file; accepts `start=`/`end=`/`speed=` trim kwargs |
| `import_video(path)` | video | alias of `video()` |
| `split_video(src, intervals=[…])` | list of video | subclips per `(start, end)` interval |
| `audio(path)` | audio | local audio file (for `play`) |

**Text options** (aliases normalize to canonical keys):

| Alias | Canonical | Meaning |
| --- | --- | --- |
| `size` | `font_size` | pixel size |
| `stroke_color` / `outline_color` | `stroke_fill` | outline color |
| `stroke` / `outline_width` | `stroke_width` | outline thickness |
| `spacing` / `tracking` | `letter_spacing` | tracking in px |
| `style` | `font` | font family |
| `fill` | `color` | fill color |

Plus `font` (system name, font file path, or a `load_font(...)` result;
uninstalled families are fetched from Google Fonts and cached) and `bg_color`.

### Typography — `load_font`

```hmg
head = load_font("Poppins", weight="bold")
title = text("WAVE RIDER", font=head, size=56)

inline = text("Direct", font="Inter")   // fetched automatically if missing
```

`load_font(name, weight="regular", style="normal", url=None)` returns a
`.ttf` path (or `None`, falling back to the default font). Resolution order:
explicit `url=` (direct font file or Google Fonts `css2` link) → installed
system fonts (weight-aware) → Google Fonts download, cached at
`~/.cache/motion_lang/fonts/`. Offline machines degrade gracefully with a
warning. `weight` accepts names (`"thin"`…`"black"`) or numbers (`400`…`900`).

### Utilities

`print`, `len`, `range`, `abs`, `min`, `max`, `round`, `int`, `float`, `str`,
`bool`, `sum`, `list`, `load_font`.

### Math

Trigonometry, rounding, powers and remapping helpers — all usable with `$t`
(see §10.1) or statically:

`sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2(y, x)`, `sqrt`, `pow`,
`abs`, `floor`, `ceil`, `round`, `min`, `max`, `lerp(a, b, t)`,
`clamp(v, lo, hi)`, `map_range(v, in_min, in_max, out_min, out_max)`,
`noise(x, y=0, seed=0)` (deterministic smooth value noise in [0, 1]),
plus the constants `pi`, `e`, `tau`.

### 10.1 Procedural animation with `$t` / `$frame`

`$t` (clip-local seconds) and `$frame` (`$t * fps`) mark an expression as
*time-varying*. Two equivalent forms:

1. **Directly** inside `render()` properties (`pos`, `pos_end`, `scale`,
   `scale_end`, `opacity`, `opacity_end`, `rotation`, `rotation_end`,
   `rotation_x`, `rotation_x_end`, `rotation_y`, `rotation_y_end`) — the
   expression is re-evaluated every frame instead of once.
2. **Bound to a variable** anywhere (top level, loops, functions, class
   attributes) and combined with math (`sin`/`cos`/`lerp`/`clamp`/`min`/
   `max`/`math.*`/`np.*`...), then consumed by a `render()` property:

```hmg
theta = $t * 0.5                    // time-varying value, no error
orbit_x = 640 + cos(theta) * 300    // composes: still time-varying
speed = max($t * 60, 20)            // math builtins lift too

scene:
    orb = shape("circle", radius=50, color="#00E5FF")
    layer(z=1):
        render(orb, time=[0, 6],
               pos=(orbit_x, 360 + sin($t * 3.0) * 150),
               scale=1.0 + sin($t * 5.0) * 0.2,
               rotation=$t * 45,
               opacity=0.6 + 0.4 * noise($t * 0.8, seed=3))
```

A per-frame ternary selects between values over time
(`10 if $t > 2 else 5`). Time-varying values compose with keyframe ranges
(`pos=(x0, y0), pos_end=...`), easing, `float_y`/`pulse` modulators and
transitions. They **cannot** freeze into static slots — `time=[...]`
windows, `size=`, shape geometry, file paths, `fx=[...]` parameters — nor
drive `if`/`repeat`/`range` conditions or boolean (`and`/`or`/`not`) logic;
those raise a `[DSL Error]` naming the animated properties instead. The
Remotion studio export bakes the start pose (`t=0`).

### 10.1.1 Vectors in 2D and 3D

Any asset — including `svg()` vectors — takes `rotation` (2D roll,
`+` = clockwise, centre-anchored), `rotation_x` / `rotation_y` (pseudo-3D
tilt with `perspective=` focal factor) and all three keyframe with `->`,
ease, or `$t`:

```hmg
scene:
    layer(z=1):
        // 2D: full spin over the shot
        render(svg("assets/icons/bolt.svg", width=128, height=128,
                   fill="#00E5FF"),
               pos=(576, 296), time=[0, 4], rotation=0 -> 360)
    layer(z=2):
        // 3D: tilt onto the floor plane + continuous yaw
        render(svg("M0 0 L100 0 L100 100 L0 100 Z", width=120, height=120,
                   fill="#FF2E88"),
               pos=(200, 300), time=[0, 4],
               rotation_x=0 -> 55, rotation_y=$t * 30, perspective=2.5)
```

Dynamics compose with keyframe ranges (`pos=(x0, y0), pos_end=...`),
easing, `float_y`/`pulse` modulators and transitions (see §10.1). The
Remotion studio export bakes the start pose (`t=0`).

### 10.2 Video cutting, trimming and retiming

```hmg
v = video("assets/input.mp4", start=2.5, end=10.0)   // trim on import
v1 = v.cut(start=0.5, end=4.2).speed(1.2)             // chainable grade
slow = v.trim(start=1.0, duration=2.0).speed(0.5)     // slow-motion
parts = split_video(v, intervals=[(0, 3), (5, 8)])    // splice selects

scene:
    layer(z=1):
        render(v1, time=[0, 4], pos=(0, 0))
```

`.cut()` / `.trim()` / `.subclip()` take `start=`/`end=` (or `duration=`);
`.speed(f)` retimes (`> 1` faster, `< 1` slow-motion, clamped to
`[0.05, 16]`); `.pos(x, y)` stores a default position used when
`render()` omits `pos`. Cutting is lazy (shared frames, cache-friendly);
if trimmed media is shorter than its timeline window the window is
clamped with a warning.

### 10.3 Transitions

Inline form (both dialects accept these strings as `transition_in=` /
`transition_out=` render options):

```
crossfade(0.8) / dissolve(0.8) / fade(0.5)
wipe_left(0.5) / wipe_right / wipe_up / wipe_down
slide_left / slide_right / slide_up / slide_down (durations in seconds)
zoom_in(0.6) / zoom_out(0.6)
glitch(0.3, intensity=0.8, seed=7)
```

Statement form (modern DSL) wires two `render()` layers — or two named
`scene Name:` blocks (every committed layer on each side) — entrances play
over the first `duration` seconds of the *to* layer(s), exits over the last
`duration` of the *from* layer(s); overlap the `time=` windows by `duration`
for a true blend:

```hmg
scene:
    layer(z=1):
        la = render(text("Scene 1"), time=[0, 3], pos=(100, 100))
    layer(z=2):
        lb = render(text("Scene 2"), time=[2.5, 5.5], pos=(100, 100))
    transition(from=la, to=lb, type="crossfade", duration=0.5)

scene Intro:
    layer(z=1):
        render(text("Title"), time=[0, 4], pos=(100, 100))
scene Outro:
    layer(z=2):
        render(text("Finale"), time=[3.5, 8], pos=(100, 100))
transition(from=Intro, to=Outro, type="wipe", duration=0.5)
```

`type=` also accepts `wipe(direction="left", duration=0.5)` and
`slide(direction="right", duration=0.5)` keyword forms.

---

## 11. Effects (`fx`)

The `fx=[...]` stack is an ordered list of calls applied to the layer's pixels
before compositing:

```
glow(color="#00E5FF", radius=20, intensity=1.3)
blur(radius=6)
drop_shadow(offset_x=8, offset_y=12, blur=20, color="#000000")
chromatic_aberration(offset=4)
glitch(intensity=3, seed=1)          // deterministic when seed is given
vignette(amount=0.4)
motion_blur(samples=8, direction=0)
adjust_color(brightness=1.1, contrast=1.0, saturation=1.2)
opacity(alpha=0.8)
blend_mode("screen")                  // "normal|screen|multiply|overlay|add|difference|lighten|darken|soft_light"
vfx_preset("cinematic")
reflection(opacity=0.5, blur=5)       // floor mirror: flipped copy + downward fade beneath the layer
flash_in(duration=0.2)                // white flash decaying 100% -> 0% (re-renders every frame)
light_sweep(angle=45, speed=1.0)      // travelling diagonal sheen (re-renders every frame)
pulse(amount=0.1, speed=2.0)          // sinusoidal scale throb (transform effect)
float_y(distance=20, speed=1.0)       // sinusoidal Y drift: sin(t*speed)*distance (transform effect)
```

`blend_mode(...)` composites the layer against everything beneath it using the
chosen Photoshop-style mode; other effects transform the layer's own pixels.

`flash_in` / `light_sweep` are time-dependent and re-render each frame;
`pulse` / `float_y` modulate the keyframed scale / position functions, so they
compose with `pos=(x, y) -> (x2, y2)`, `scale=a -> b` and easing. Keyframed
property interpolation runs per frame across position, scale and opacity.

---

## 12. Modules

Split reusable components across `.hmg` files.

**`components/ui.hmg`**

```hmg
export GlowCard
export GlassTitle

fn GlowCard(title, subtitle, x, y, w=360, h=180):
    ...
    return layer(z=4):
        render(panel, pos=(x, y))

class GlassTitle:
    fn init(self, label, size=64):
        self.image = text(label, size=size)
    fn build(self, pos=(400, 120)):
        return layer(z=6):
            render(self.image, pos=pos)
```

**Main script**

```hmg
import GlowCard, GlassTitle from "components/ui.hmg"

title = GlassTitle("HELLO MODULES", size=72)

scene:
    GlowCard("Fast", "Modules work", x=80, y=80)
    title.build(pos=(300, 400))
```

- Paths resolve relative to the importing file (then the working dir).
- Modules are evaluated once and cached.
- `export <symbol>` marks the public surface; without any `export`, all
  top-level definitions are exported.
- Module functions/classes run in the caller's evaluator, so their `layer`
  blocks commit normally.

### Python interop

Any installed Python library (plus local `.py` helpers) is importable
directly — no `from` clause means a Python import:

```hmg
import math
import numpy as np
import os.path
import helpers                  // ./helpers.py next to the script
import shout from "helpers.py"  // symbols from a Python file

angle = math.sin(np.pi / 2)
dest = os.path.join("frames", "out.mp4")
```

Rules: `import a.b.c` binds `a` (standard Python semantics);
`import x as y` binds `y`; dotted attribute chains (`os.path.join`,
`arr.shape`) and calls work natively. A failed import warns and the script
continues. Note: imports execute real Python code — only import code you
trust, as with Python itself.

### CSS stylesheets

```hmg
import styles from "theme.css"

text("Hello World", class="glow-title", pos=(100, 200))
```

```css
/* theme.css */
.glow-title {
    font-family: "Poppins";
    font-size: 80px;
    color: #00E5FF;
    glow: #00E5FF 1.5;
}
```

The sheet loads into the compositor cascade (explicit `render()` attributes
still win; `fx` stacks concatenate, style first). Each imported name binds a
stylesheet value (`styles.classes` lists its classes). Supported selectors:
`*`, `.class`, `#id`; supported properties include layout (`left`/`top`,
`width`/`height`, `scale`), appearance (`color`, `font-size`, `font-family`,
`background-color`, `border-radius`, `opacity`), effects (`glow`, `blur`,
`box-shadow`, `filter`, `vfx`) and motion (`easing`, `transition-in/out`).
Legacy brace syntax keeps its own form: `import style "theme.css"`.

---

## 13. Errors

Syntax errors report `line`, `column`, a source excerpt and expected tokens,
plus a compact reminder of the modern syntax. Runtime errors (undefined name,
non-callable value, bad iterable, unknown function) surface as
`[DSL Error] ...` with the same class (`MotionSyntaxError`).

---

## 14. Complete example — `examples/modern_demo.hmg`

```hmg
// Language Configuration
config:
    resolution = 1280x720
    fps = 30
    mode = "preview"

// Module Import
import GlowCard, GlassTitle from "components/ui.hmg"

// Global Variables & Operators
base_duration = 5
card_scale = 0.8 + 0.1

// Custom Function Definition
fn create_badge(text_val, x, y):
    bg = shape("rect", width=200, height=60, color="#1e1e2e", radius=12)
    label = text(text_val, font="Helvetica", size=24, color="#FFFFFF")
    return layer(z=3):
        render(bg, pos=(x, y))
        render(label, pos=(x + 20, y + 15))

// Class Definition (OOP)
class HeroWidget:
    fn init(self, title_text, asset_query):
        self.title = text(title_text, size=48, color="#00E5FF")
        self.avatar = wiki(asset_query)

    fn build(self, start_t):
        return layer(z=2):
            render(self.avatar, time=[start_t, start_t + 4], pos=(450, 200), scale=0.6)
            render(self.title, time=[start_t + 0.5, start_t + 4], pos=(400, 450), fx=[glow(color="#00E5FF")])

// Instantiation & Usage
hero = HeroWidget("EAGLE VISION", "eagle")

// Composition Timeline
scene:
    // Background loop
    repeat 3 times as i:
        bg = shape("rect", width=1280, height=720, color="#0a0a10")
        layer(z=1):
            render(bg, time=[i * 2, (i + 1) * 2])

    // Conditional Layer Logic
    show_hero = true
    if show_hero == true:
        hero.build(start_t=0.5)
    else:
        layer(z=2):
            render(shape("circle", radius=100, color="#FF0055"), time=[0, 5], pos=(540, 260))

    // Functional Component Loop
    items = ["FAST", "CLEAN", "MOTIONS"]
    for idx, item in items:
        create_badge(item, x=100 + (idx * 220), y=600)

audio:
    play(audio("assets/bg_music.mp3"), start=0, volume=0.3)
    for t in [1.0, 3.0, 5.0]:
        play(audio("assets/swoosh.wav"), start=t, volume=0.8)
```

---

## 15. Compiling & the studio

```bash
# render a final MP4 (dependency-light Python engine)
.venv/bin/motion examples/modern_demo.hmg --render --output output/modern_demo.mp4

# export the timeline and open the real-time Remotion editor
.venv/bin/motion examples/modern_demo.hmg --studio
cd studio && npm install && npm run dev        # http://localhost:5173
```

`--render` forces MP4 output (overriding a `mode = "preview"` config);
`--emit-json PATH` writes the timeline to an arbitrary path; `--preview`
launches the native preview player; `--no-cache` bypasses the asset cache.

---

## 16. Legacy syntax

The original brace syntax is unchanged and still dispatched automatically:

```hmg
init {
    resolution: 1280x720
    fps: 30
    mode: render
}

asset title = text("Old style", font="Helvetica", size=48)
asset bg = video("assets/sample_background.mp4")

scene {
    layer(z=1) {
        render(bg, time=[0, 6], pos=(0, 0), size=(1280, 720))
    }
}
```

Detection: a file is treated as modern if it contains `config:`, a
`import ... from`, `fn`/`class` definitions, `scene:`/`audio:` (colon form),
`export`, or `repeat ... times`. Otherwise the legacy interpreter runs.
