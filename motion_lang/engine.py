# motion_lang/engine.py
"""Compositor: layers, keyframe animation, easing, transitions, text."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
try:  # moviepy >= 2.0 (with_* API)
    from moviepy import (
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        AudioFileClip,
    )
    from moviepy.video.fx import FadeIn as _FadeIn, FadeOut as _FadeOut, Resize as _Resize
    _MPV2 = True
except ImportError:  # moviepy 1.x (set_* / fx API)
    from moviepy.editor import (
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
    )
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.fx.fadein import fadein as _fadein1
    from moviepy.video.fx.fadeout import fadeout as _fadeout1
    from moviepy.video.fx.resize import resize as _resize1, resizer as _resizer1
    _MPV2 = False
from PIL import Image, ImageDraw, ImageFont


def _timed(clip, start: float, duration: float):
    return clip.with_start(start).with_duration(duration) if _MPV2 \
        else clip.set_start(start).set_duration(duration)


def _positioned(clip, pos_fn):
    return clip.with_position(pos_fn) if _MPV2 else clip.set_position(pos_fn)


def _with_opacity(clip, value: float):
    return clip.with_opacity(value) if _MPV2 else clip.set_opacity(value)


def _static_resize(clip, scale=None, size=None):
    if size is not None:
        return clip.resized(new_size=tuple(size)) if _MPV2 \
            else clip.fx(_resize1, tuple(size))
    if scale is not None:
        return clip.resized(float(scale)) if _MPV2 \
            else clip.fx(_resize1, float(scale))
    return clip


def _dynamic_resize(clip, scale_fn):
    if _MPV2:
        return clip.with_effects([_Resize(scale_fn)])
    # moviepy 1.x: resize(fn) zeroes clip masks (the image-only fun is
    # applied to 0..1 mask floats, truncating them to uint8 0), which makes
    # animated clips vanish in composites. Transform image and mask each
    # with a range-correct fun instead.
    w, h = clip.size
    def _wh(base_w, base_h, s):
        return (max(1, int(round(base_w * s))), max(1, int(round(base_h * s))))

    def img_fun(gf, t):
        s = max(0.01, float(scale_fn(t)))
        return _resizer1(gf(t).astype("uint8"), _wh(w, h, s))

    newclip = clip.fl(img_fun, keep_duration=True)
    if clip.mask is not None:
        mw, mh = clip.mask.size

        def mask_fun(gf, t):
            s = max(0.01, float(scale_fn(t)))
            mf = gf(t).astype(float)
            if mf.max() > 1.5:
                mf /= 255.0
            return (1.0 * _resizer1((255.0 * mf).astype("uint8"),
                                    _wh(mw, mh, s))) / 255.0

        newclip.mask = clip.mask.fl(mask_fun, keep_duration=True)
    return newclip


def _faded(clip, which: str, duration: float):
    if _MPV2:
        return clip.with_effects([_FadeIn(duration) if which == "in"
                                  else _FadeOut(duration)])
    # moviepy 1.x fades RGB toward black, which leaves an opaque fading box
    # on masked layers. Fade the mask instead so transparency is honored.
    fx = _fadein1 if which == "in" else _fadeout1
    if clip.mask is not None:
        mask = clip.mask
        if mask.duration is None and clip.duration:
            mask = mask.set_duration(clip.duration)
        newclip = clip.copy()
        newclip.mask = mask.fx(fx, duration)
        return newclip
    return clip.fx(fx, duration)


def _frame_mapped(clip, func):
    """Per-frame transform; func(get_frame, t) -> frame."""
    return clip.transform(func) if _MPV2 else clip.fl(func)


def _audio_placed(clip, start: float, duration=None, volume: float = 1.0):
    if _MPV2:
        if duration:
            clip = clip.with_duration(duration)
        clip = clip.with_start(start)
        if volume != 1.0:
            clip = clip.with_volume_scaled(volume)
        return clip
    if duration:
        clip = clip.set_duration(duration)
    clip = clip.set_start(start)
    if volume != 1.0:
        clip = clip.volumex(volume)
    return clip


def _with_audio(video, audio):
    return video.with_audio(audio) if _MPV2 else video.set_audio(audio)

# Import VFX utilities
from motion_lang.vfx import (
    apply_blur,
    apply_glow,
    apply_drop_shadow,
    apply_opacity,
    adjust_color,
    apply_vfx_preset,
    chromatic_aberration,
    glitch,
    vignette,
    motion_blur,
    blend_rgb,
    apply_reflection,
    flash_overlay,
    light_sweep,
    pulse_scale,
    float_y_offset,
)

# Effects that live in the ``fx=[...]`` stack but are not applied to a single
# still frame: transform effects modulate position/scale across time, while the
# "dynamic pixel" effects re-render the layer every frame.
_TRANSFORM_FX = frozenset({"float_y", "pulse"})
_DYNAMIC_PIXEL_FX = frozenset({"flash_in", "light_sweep"})

# Native CSS styling (import style "..." + class/id targeting)
from motion_lang import style as _css

# ---------------------------------------------------------------------------
# Easing functions: t in [0,1] -> eased progress in [0,1]
# ---------------------------------------------------------------------------

def _linear(t: float) -> float:
    return t

def _ease_in(t: float) -> float:
    return t * t * t

def _ease_out(t: float) -> float:
    return 1.0 - pow(1.0 - t, 3)

def _ease_in_out(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1.0 - pow(-2 * t + 2, 3) / 2.0

def _bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375

EASING_FUNCTIONS: Dict[str, Callable[[float], float]] = {
    "linear": _linear,
    "ease_in": _ease_in,
    "ease-in": _ease_in,
    "easein": _ease_in,
    "ease_out": _ease_out,
    "ease-out": _ease_out,
    "easeout": _ease_out,
    "ease_in_out": _ease_in_out,
    "ease-in-out": _ease_in_out,
    "easeinout": _ease_in_out,
    "ease": _ease_in_out,
    "bounce": _bounce,
}

def resolve_easing(name: Optional[str]) -> Callable[[float], float]:
    if not name:
        return _linear
    key = str(name).strip().lower()
    fn = EASING_FUNCTIONS.get(key)
    if fn is None:
        print(f"[Engine] Unknown easing '{name}', falling back to linear.")
        return _linear
    return fn

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def _parse_seconds(spec) -> float:
    if spec is None:
        return 0.0
    if isinstance(spec, (int, float)):
        return float(spec)
    s = str(spec).strip().lower().rstrip("s")
    try:
        s = float(s)
        return s
    except ValueError:
        return 0.0

_TRANS_RE = re.compile(r"^(\w+)\s*(?:\(\s*([0-9.]+)\s*s?\s*\))?\s*$")

def parse_transition(spec) -> Tuple[Optional[str], float]:
    if spec is None:
        return None, 0.0
    if isinstance(spec, (int, float)):
        return None, 0.0
    s = str(spec).strip().lower().strip('"').strip("'")
    m = _TRANS_RE.match(s)
    if not m:
        print(f"[Engine] Unrecognised transition '{spec}'.")
        return None, 0.0
    name, dur = m.group(1), _parse_seconds(m.group(2) or 0.5 if m.group(2) else 0.5)
    # normalise aliases
    aliases = {"fade": "fade_in", "fadein": "fade_in", "fadeout": "fade_out",
               "slideleft": "slide_left", "slideright": "slide_right",
               "zoomin": "zoom_in", "slide": "slide_right"}
    name = aliases.get(name, name)
    if name not in ("fade_in", "fade_out", "slide_left", "slide_right", "zoom_in"):
        print(f"[Engine] Unsupported transition '{name}'.")
        return None, 0.0
    return name, float(dur)

# ---------------------------------------------------------------------------
# Text layer helper (Pillow -> RGBA, no ImageMagick dependency)
# ---------------------------------------------------------------------------

_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    ".",
)


@lru_cache(maxsize=256)
def _resolve_font_path(name: str) -> Optional[str]:
    """Resolve a font family name or path to a real font file.

    Search order: literal path -> filename in known font dirs -> normalized
    filename match (e.g. ``DejaVuSans-Bold`` -> ``DejaVuSans-Bold.ttf``) ->
    fontconfig ``fc-match`` family substitution.
    """
    if not name:
        return None
    if os.path.isfile(name):
        return name
    suffixes = ("", ".ttf", ".otf", ".ttc")
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for suf in suffixes:
            cand = os.path.join(d, name + suf)
            if os.path.isfile(cand):
                return cand
    target = re.sub(r"[^a-z0-9]", "", name.lower())
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fname in files:
                if not fname.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                stem = re.sub(r"[^a-z0-9]", "",
                              os.path.splitext(fname)[0].lower())
                if stem == target:
                    return os.path.join(root, fname)
    if shutil.which("fc-match"):
        try:
            out = subprocess.check_output(
                ["fc-match", "-f", "%{file}", name],
                stderr=subprocess.DEVNULL).decode().strip()
            if out and os.path.isfile(out):
                return out
        except Exception:
            pass
    return None


def make_text_image(text: str, font: str = "default", color: str = "#FFFFFF",
                    font_size: int = 48, stroke_width: int = 0,
                    stroke_fill: str = "#000000", bg_color=None,
                    letter_spacing: int = 0) -> Image.Image:
    _DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    img_font = None
    font_path = None
    if font and font.lower() not in ("default", "none", ""):
        font_path = _resolve_font_path(font)
        if font_path is None:
            # Google Fonts / custom typography: fetch on demand (cached).
            try:
                from motion_lang.text_engine import load_font as _load_font
                font_path = _load_font(font)
            except Exception:
                font_path = None
    if font_path is None:
        font_path = _DEFAULT_FONT
    try:
        img_font = ImageFont.truetype(font_path, font_size)
    except Exception:
        try:
            img_font = ImageFont.truetype(_DEFAULT_FONT, font_size)
        except Exception:
            img_font = ImageFont.load_default()

    # measure
    probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    letter_spacing = int(letter_spacing or 0)
    try:
        if letter_spacing:
            widths = [_text_len(d, ch, img_font) for ch in text]
            tw = int(sum(widths) + letter_spacing * max(0, len(text) - 1))
            bbox = d.textbbox((0, 0), "Ag", font=img_font,
                              stroke_width=stroke_width)
            th = bbox[3] - bbox[1]
        else:
            bbox = d.textbbox((0, 0), text, font=img_font,
                              stroke_width=stroke_width)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = (len(text) * font_size // 2, font_size + 8)
    pad = 20 + stroke_width * 2
    img = Image.new("RGBA", (max(1, tw + pad * 2), max(1, th + pad * 2)),
                    (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg_color:
        d.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=12,
                            fill=bg_color)
    if letter_spacing:
        x, y = pad, pad
        for ch in text:
            d.text((x, y), ch, font=img_font, fill=color,
                   stroke_width=stroke_width, stroke_fill=stroke_fill)
            x += _text_len(d, ch, img_font) + letter_spacing
    else:
        d.text((pad, pad), text, font=img_font, fill=color,
               stroke_width=stroke_width, stroke_fill=stroke_fill)
    return img


def _text_len(draw: ImageDraw.ImageDraw, ch: str, font) -> float:
    """Per-character advance width (compatible across Pillow versions)."""
    try:
        return draw.textlength(ch, font=font)
    except Exception:
        try:
            return draw.textsize(ch, font=font)[0]
        except Exception:
            return font.size * 0.5


def _fx_param(params: Dict, key: str, default=None, index: int = 0):
    """Read an fx parameter by name, falling back to positional ``_args``."""
    if params and key in params:
        return params[key]
    args = (params or {}).get("_args")
    if args and index < len(args):
        return args[index]
    return default


def _resolve_pos_xy(pos, clip_size, canvas_size) -> Tuple[int, int]:
    """Resolve a moviepy position (tuple or keyword string) to pixels."""
    cw, ch = canvas_size
    w, h = clip_size
    if isinstance(pos, str):
        pos = {"center": ["center", "center"], "left": ["left", "center"],
               "right": ["right", "center"], "top": ["center", "top"],
               "bottom": ["center", "bottom"]}.get(pos, ["center", "center"])
    try:
        x, y = pos[0], pos[1]
    except (TypeError, IndexError):
        return 0, 0
    if x == "left":
        x = 0
    elif x == "right":
        x = cw - w
    elif x == "center":
        x = (cw - w) / 2.0
    if y == "top":
        y = 0
    elif y == "bottom":
        y = ch - h
    elif y == "center":
        y = (ch - h) / 2.0
    return int(x), int(y)


def _blit_clip(canvas: np.ndarray, clip, t: float, mode: str = "normal") -> np.ndarray:
    """Alpha-composite (optionally blend-mode) one clip onto a float canvas."""
    ct = t - clip.start
    raw = clip.get_frame(ct)
    if raw.ndim == 2:
        raw = np.stack([raw] * 3, axis=-1)
    embedded_alpha = None
    if raw.shape[2] >= 4:
        embedded_alpha = raw[:, :, 3].astype(np.float32) / 255.0
    img = raw[:, :, :3].astype(np.float32)
    h, w = img.shape[:2]

    mask = None
    if getattr(clip, "mask", None) is not None:
        mask = np.asarray(clip.mask.get_frame(ct), dtype=np.float32)
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.shape[0] != h or mask.shape[1] != w:
            mask = np.asarray(
                Image.fromarray((np.clip(mask, 0, 1) * 255).astype("uint8"))
                .resize((w, h)), dtype=np.float32) / 255.0
    elif embedded_alpha is not None:
        mask = embedded_alpha

    pos = clip.pos(ct) if callable(getattr(clip, "pos", None)) else getattr(clip, "pos", (0, 0))
    H, W = canvas.shape[:2]
    x, y = _resolve_pos_xy(pos, (w, h), (W, H))

    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return canvas
    sx0, sy0 = x0 - x, y0 - y
    src = img[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    if mask is None:
        a = np.float32(1.0)
    else:
        a = mask[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)][:, :, None]

    dst = canvas[y0:y1, x0:x1]
    name = (mode or "normal").lower()
    if name in ("normal", "none", "source-over", "source_over"):
        blended = src
    else:
        blended = blend_rgb(dst.astype(np.uint8), src.astype(np.uint8), name).astype(np.float32)
    canvas[y0:y1, x0:x1] = dst * (1.0 - a) + blended * a
    return canvas

# ---------------------------------------------------------------------------
# Compositor
# ---------------------------------------------------------------------------

class Compositor:
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30, mode: str = "render"):
        self.width = width
        self.height = height
        self.fps = fps
        self.mode = mode.lower() if mode else "render"
        self.layers: List = []
        self.audio_layers: List = []
        # Native CSS styling: ordered rule list + loaded sheet paths.
        self.style_rules: List[Dict] = []
        self.stylesheets: List[str] = []

    # -- stylesheets ------------------------------------------------------
    def load_stylesheet(self, path: str, base_dir: str = "."):
        """Load a ``.css``/``.hmsc`` sheet; later sheets win cascade ties."""
        import os as _os
        full = path if _os.path.isabs(path) else _os.path.join(base_dir or ".", path)
        rules = _css.parse_css_file(full)
        self.style_rules = _css.merge_rules(self.style_rules, rules)
        self.stylesheets.append(full)
        print(f"[Style] Loaded {full} ({len(rules)} rule(s)).")
        return len(rules)

    def style_for(self, css_class=None, css_id=None) -> Dict:
        """Resolve class/id targeting to engine kwargs (empty fx if none)."""
        if not self.style_rules:
            return {"fx": []}
        if isinstance(css_class, (list, tuple)):
            css_class = " ".join(str(c) for c in css_class)
        return _css.resolve_style(self.style_rules, css_class, css_id)

    @staticmethod
    def _merge_style(explicit: Dict, styled: Dict) -> Dict:
        """Explicit DSL attrs win; fx stacks concatenate (style first)."""
        merged = dict(explicit)
        for key in ("pos", "size", "scale", "opacity", "easing",
                    "transition_in", "transition_out"):
            if merged.get(key) is None and styled.get(key) is not None:
                merged[key] = styled[key]
        merged["fx"] = list(styled.get("fx", [])) + list(explicit.get("fx") or [])
        return merged

    # -- static transforms --------------------------------------------------
    def _apply_static(self, clip, scale=None, size=None):
        return _static_resize(clip, scale=scale, size=size)

    def _apply_transitions(self, clip, duration: float, transition_in=None, transition_out=None):
        tin, din = parse_transition(transition_in) if transition_in else (None, 0.0)
        tout, dout = parse_transition(transition_out) if transition_out else (None, 0.0)
        if tin in ("fade_in",) and din > 0:
            clip = _faded(clip, "in", min(din, duration))
        if tout in ("fade_out",) and dout > 0:
            clip = _faded(clip, "out", min(dout, duration))
        # store slide/zoom specs for position/scale composition
        clip._slide_in = (tin, din) if tin in ("slide_left", "slide_right") else (None, 0.0)
        clip._slide_out = (tout, dout) if tout in ("slide_left", "slide_right") else (None, 0.0)
        clip._zoom_in = (tin == "zoom_in", din) if tin == "zoom_in" else (False, 0.0)
        return clip

    def _keyframed_pos(self, base_pos, pos_end, duration, easing_fn,
                       slide_in, slide_out, float_fx=None):
        has_anim = pos_end is not None or slide_in[0] or slide_out[0] or float_fx
        if not has_anim:
            return lambda t: base_pos
        x0, y0 = base_pos
        x1, y1 = (pos_end if pos_end is not None else base_pos)
        float_specs = list(float_fx or [])
        def _pos(t: float):
            tt = max(0.0, min(1.0, t / duration if duration > 0 else 1.0))
            e = easing_fn(tt)
            x, y = lerp(x0, x1, e), lerp(y0, y1, e)
            for params in float_specs:
                dist = float(_fx_param(params, "distance", 20.0, index=0))
                spd = float(_fx_param(params, "speed", 1.0, index=1))
                y += float_y_offset(t, dist, spd)
            W = self.width
            if slide_in[0] == "slide_left":
                d = slide_in[1] or 0.5
                if t < d:
                    k = 1.0 - (t / d)
                    x += W * k
            elif slide_in[0] == "slide_right":
                d = slide_in[1] or 0.5
                if t < d:
                    k = 1.0 - (t / d)
                    x -= W * k
            if slide_out[0] == "slide_left":
                d = slide_out[1] or 0.5
                if t > duration - d:
                    k = (t - (duration - d)) / d
                    x -= W * k
            elif slide_out[0] == "slide_right":
                d = slide_out[1] or 0.5
                if t > duration - d:
                    k = (t - (duration - d)) / d
                    x += W * k
            return (x, y)
        return _pos

    def _keyframed_scale(self, base_scale, scale_end, duration, easing_fn, zoom_in,
                         pulse_fx=None):
        has_anim = scale_end is not None or zoom_in[0] or pulse_fx
        if not has_anim:
            return None
        s0 = float(base_scale) if base_scale is not None else 1.0
        s1 = float(scale_end) if scale_end is not None else s0
        pulse_specs = list(pulse_fx or [])
        def _sc(t: float):
            tt = max(0.0, min(1.0, t / duration if duration > 0 else 1.0))
            e = easing_fn(tt)
            v = lerp(s0, s1, e)
            for params in pulse_specs:
                amount = float(_fx_param(params, "amount", 0.1, index=0))
                spd = float(_fx_param(params, "speed", 1.0, index=1))
                v *= pulse_scale(t, amount, spd)
            if zoom_in[0]:
                d = zoom_in[1] or 0.5
                if t < d:
                    k = t / d
                    v = lerp(0.2, v, k)
            return max(0.01, v)
        return _sc

    def _compose_clip(self, clip, *, start, duration, pos, pos_end=None,
                      scale=None, scale_end=None, size=None, easing="linear",
                      transition_in=None, transition_out=None, opacity=None,
                      opacity_end=None, float_fx=None, pulse_fx=None):
        easing_fn = resolve_easing(easing)
        clip = _timed(clip, start, duration)
        clip = self._apply_transitions(clip, duration, transition_in, transition_out)
        slide_in = getattr(clip, "_slide_in", (None, 0.0))
        slide_out = getattr(clip, "_slide_out", (None, 0.0))
        zoom_in = getattr(clip, "_zoom_in", (False, 0.0))
        # scale: keyframed wins; else static (scale xor size)
        sc_fn = self._keyframed_scale(scale, scale_end, duration, easing_fn,
                                      zoom_in, pulse_fx=pulse_fx)
        if sc_fn is not None:
            clip = _dynamic_resize(clip, sc_fn)
        else:
            clip = self._apply_static(clip, scale=scale, size=size)
        # position (always a function so slides/keyframes compose)
        pos_fn = self._keyframed_pos(tuple(pos), tuple(pos_end) if pos_end else None,
                                     duration, easing_fn, slide_in, slide_out,
                                     float_fx=float_fx)
        clip = _positioned(clip, pos_fn)
        # opacity keyframes via with_opacity (static only; for animated, modulate mask)
        if opacity is not None and opacity_end is not None and opacity != opacity_end:
            o0 = float(opacity)
            o1 = float(opacity_end)
            def _op(t: float, _o0=o0, _o1=o1):
                tt = max(0.0, min(1.0, t / duration if duration > 0 else 1.0))
                return lerp(_o0, _o1, easing_fn(tt))
            # Apply per-frame opacity via transform (needs time access)
            def _opacity_tf(gf, t):
                pic = gf(t).copy()
                alpha = _op(t)
                if pic.ndim == 3 and pic.shape[2] >= 4:
                    pic[:, :, 3] = (pic[:, :, 3].astype(float) * alpha).astype(np.uint8)
                return pic
            clip = _frame_mapped(clip, _opacity_tf)
        elif opacity is not None:
            clip = _with_opacity(clip, float(opacity))
        elif opacity_end is not None and opacity_end != 1.0:
            clip = _with_opacity(clip, float(opacity_end))
        return clip

    # -- AE-style layer effects ---------------------------------------------
    def _apply_fx_stack(self, image: Image.Image, fx) -> Tuple[Image.Image, Optional[str], Tuple[int, int]]:
        """Apply an fx stack to a still image.

        Returns ``(image, blend_mode, offset)`` where:
        - ``blend_mode`` is the last ``blend_mode(...)`` seen (handled at
          composite time, not as a filter).
        - ``offset`` is the (dx, dy) pixel shift introduced by effects that expand
          the canvas (e.g., glow, drop_shadow). This offset needs to be
          compensated for in layer positioning so that the original content
          appears at the intended position.
        """
        blend_mode: Optional[str] = None
        offset_x, offset_y = 0, 0
        if not fx:
            return image, blend_mode, (offset_x, offset_y)
        image = image.copy()
        for fx_name, params in fx:
            params = params or {}
            try:
                if fx_name == "blur":
                    image = apply_blur(image, int(_fx_param(params, "radius", 5)))
                elif fx_name == "glow":
                    # Calculate the margin that glow will add
                    intensity = float(_fx_param(params, "intensity", 1.0, index=1))
                    radius = _fx_param(params, "radius", None, index=2)
                    blur_r = max(1, int(radius)) if radius is not None else max(1, int(intensity * 20))
                    margin = blur_r * 2
                    # Glow centers the original image in the expanded canvas
                    # The original content is at (margin, margin) in the new image
                    # To keep the content at the intended position, we need to shift
                    # the layer position by (-margin, -margin)
                    offset_x -= margin
                    offset_y -= margin
                    image = apply_glow(
                        image,
                        str(_fx_param(params, "color", "#FFFFFF", index=0)),
                        intensity,
                        radius=radius,
                    )
                elif fx_name == "drop_shadow":
                    ox = int(_fx_param(params, "offset_x", 10))
                    oy = int(_fx_param(params, "offset_y", 10, index=1))
                    blur_r = int(_fx_param(params, "blur", 20, index=2))
                    # drop_shadow expands canvas to fit shadow offset and blur
                    # The original image is pasted at (max(-ox, 0), max(-oy, 0))
                    # We need to offset by the negative of that to keep original content at intended position
                    offset_x -= max(-ox, 0)
                    offset_y -= max(-oy, 0)
                    image = apply_drop_shadow(
                        image,
                        ox, oy,
                        blur_r,
                        str(_fx_param(params, "color", "#00000088", index=3)),
                    )
                elif fx_name == "opacity":
                    image = apply_opacity(image, float(_fx_param(params, "alpha", 1.0)))
                elif fx_name == "adjust_color":
                    image = adjust_color(
                        image,
                        float(_fx_param(params, "brightness", 0.0)),
                        float(_fx_param(params, "contrast", 0.0, index=1)),
                        float(_fx_param(params, "saturation", 0.0, index=2)),
                    )
                elif fx_name == "vfx_preset":
                    extra = {k: v for k, v in params.items()
                             if k not in ("preset_name", "_args")}
                    preset_name = str(_fx_param(params, "preset_name", "vignette"))
                    # Handle presets that may expand canvas
                    if preset_name.lower() in ("glow", "drop_shadow"):
                        # For presets, we'd need to know the parameters, but this is complex
                        # For now, skip offset tracking for presets
                        pass
                    image = apply_vfx_preset(
                        image, preset_name,
                        **extra)
                elif fx_name == "chromatic_aberration":
                    image = chromatic_aberration(
                        image, int(_fx_param(params, "offset", 3)))
                elif fx_name == "glitch":
                    seed = _fx_param(params, "seed", None, index=1)
                    image = glitch(image,
                                   float(_fx_param(params, "intensity", 0.3)),
                                   seed=None if seed is None else int(seed))
                elif fx_name == "vignette":
                    image = vignette(image, float(_fx_param(params, "amount", 0.5)))
                elif fx_name == "motion_blur":
                    distance = _fx_param(params, "distance", None, index=2)
                    image = motion_blur(
                        image, int(_fx_param(params, "samples", 8)),
                        int(_fx_param(params, "direction", 0, index=1)),
                        distance=None if distance is None else int(distance))
                elif fx_name == "reflection":
                    gap = int(_fx_param(params, "gap", 0, index=2))
                    # Reflection adds a mirrored copy below the original
                    # The final image height is original_height * 2 + gap
                    # The original content is at y=0, so to keep it at the intended y position,
                    # we don't need to offset (the reflection extends downward from the original position)
                    # If we wanted to center the whole reflected image, we would offset by:
                    # offset_y -= image.size[1] + gap / 2
                    # But for now, keep the original content at the intended position
                    # offset_y -= image.size[1]  # Uncomment this if you want the center at the position
                    image = apply_reflection(
                        image,
                        opacity=float(_fx_param(params, "opacity", 0.5, index=0)),
                        blur=int(_fx_param(params, "blur", 5, index=1)),
                        gap=gap,
                        fade=bool(_fx_param(params, "fade", True, index=3)),
                    )
                elif fx_name in _DYNAMIC_PIXEL_FX or fx_name in _TRANSFORM_FX:
                    # Handled per-frame elsewhere; nothing to bake here.
                    pass
                elif fx_name == "blend_mode":
                    blend_mode = str(_fx_param(params, "mode", "normal"))
                else:
                    print(f"[VFX] Unknown effect '{fx_name}' (skipped).")
            except Exception as exc:  # never let one effect kill a render
                print(f"[VFX] Failed to apply '{fx_name}': {exc}")
        return image, blend_mode, (offset_x, offset_y)

    @staticmethod
    def _blend_mode_of(fx) -> Optional[str]:
        mode = None
        for fx_name, params in (fx or []):
            if fx_name == "blend_mode":
                mode = str(_fx_param(params or {}, "mode", "normal"))
        return mode

    @staticmethod
    def _split_fx(fx):
        """Partition an fx stack into (static, dynamic-pixel, float, pulse).

        * static: baked once into the layer image (blur, glow, reflection, …)
        * dynamic: re-applied every frame (flash_in, light_sweep)
        * float: sinusoidal Y modifiers (float_y)
        * pulse: sinusoidal scale modifiers (pulse)
        """
        static, dynamic, floats, pulses = [], [], [], []
        for name, params in (fx or []):
            params = params or {}
            if name in _TRANSFORM_FX:
                (floats if name == "float_y" else pulses).append(params)
            elif name in _DYNAMIC_PIXEL_FX:
                dynamic.append((name, params))
            else:
                static.append((name, params))
        return static, dynamic, floats, pulses

    def _apply_dynamic_fx(self, clip, dynamic_fx, duration):
        """Re-render time-dependent pixel effects each frame (flash/sweep)."""
        if not dynamic_fx:
            return clip

        def _tf(gf, t):
            frame = gf(t)
            if frame.ndim == 2:
                frame = np.stack([frame] * 3, axis=-1)
            if frame.dtype != np.uint8:
                frame = np.clip(frame, 0, 255).astype(np.uint8)
            has_alpha = frame.shape[2] == 4 if frame.ndim == 3 else False
            img = Image.fromarray(frame)
            for name, params in dynamic_fx:
                if name == "flash_in":
                    dur = max(1e-6, float(_fx_param(params, "duration", 0.2)))
                    img = flash_overlay(
                        img, t / dur if dur > 0 else 1.0,
                        str(_fx_param(params, "color", "#FFFFFF", index=0)))
                elif name == "light_sweep":
                    speed = max(1e-6, float(_fx_param(params, "speed", 1.0)))
                    period = max(1e-6, float(_fx_param(params, "period", 1.5))) / speed
                    prog = (t % period) / period
                    img = light_sweep(
                        img, prog,
                        angle=float(_fx_param(params, "angle", 45.0, index=0)),
                        speed=speed,
                        width=float(_fx_param(params, "width", 0.25)),
                        color=str(_fx_param(params, "color", "#FFFFFF")),
                        intensity=float(_fx_param(params, "intensity", 1.0)),
                    )
            out = np.array(img)
            if not has_alpha and out.shape[2] == 4:
                out = out[:, :, :3]
            return out

        return _frame_mapped(clip, _tf)

    # -- public layer APIs ---------------------------------------------------
    def add_image_layer(self, pil_image: Image.Image, start: float, end: float,
                        pos=(0, 0), z_index: int = 0, scale=None, size=None,
                        pos_end=None, scale_end=None, easing: str = None,
                        transition_in=None, transition_out=None,
                        opacity=None, opacity_end=None,
                        fx: Optional[List[tuple]] = None,
                        css_class=None, css_id=None, is_shape: bool = False):
        """Add an image layer with optional visual effects stack.

        Args:
            pil_image: PIL Image to render.
            start: Start time (seconds).
            end: End time (seconds).
            pos: Position (x, y). ``None`` falls back to CSS ``left``/``top``.
            z_index: Z-order index.
            scale: Optional scale factor.
            size: Optional target size (width, height).
            pos_end: End position for animation.
            scale_end: End scale for animation.
            easing: Easing function name.
            transition_in: Optional transition-in effect.
            transition_out: Optional transition-out effect.
            opacity: Optional opacity (0.0 to 1.0).
            opacity_end: Optional end opacity for animation.
            fx: Optional list of FX tuples from parser (e.g., [("blur", {"radius":5}), ...]).
            css_class: Space-separated CSS class(es) from ``class="..."``.
            css_id: CSS id from ``id="..."``.
            is_shape: True for shape-generated assets (allows CSS
                ``background-color`` recolor; photos are never recolored).
        """
        styled = self.style_for(css_class, css_id)
        merged = self._merge_style(
            {"pos": pos, "size": size, "scale": scale, "opacity": opacity,
             "easing": easing, "transition_in": transition_in,
             "transition_out": transition_out, "fx": fx}, styled)
        pos = merged["pos"] if merged["pos"] is not None else (0, 0)
        size, scale = merged["size"], merged["scale"]
        easing = merged["easing"] or "linear"
        transition_in, transition_out = merged["transition_in"], merged["transition_out"]
        opacity, fx = merged["opacity"], merged["fx"]
        # CSS box decorations: rounded corners (all layers), recolor (shapes).
        static_fx, dynamic_fx, float_fx, pulse_fx = self._split_fx(fx)
        processed_image = _css.apply_shape_style(pil_image, styled,
                                                 allow_recolor=is_shape)
        processed_image, blend_mode, fx_offset = self._apply_fx_stack(processed_image, static_fx)
        np_img = np.array(processed_image)
        duration = max(0.1, end - start)
        
        # Apply offset to position to compensate for VFX effects that expand the canvas
        # The offset is the amount to add to the position
        if fx_offset != (0, 0):
            offset_x, offset_y = fx_offset
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                pos = (pos[0] + offset_x, pos[1] + offset_y)
            elif isinstance(pos, str):
                # For keyword positions like "center", we can't easily adjust
                # This is a limitation - FX with canvas expansion don't work well with keyword positions
                print(f"[Engine] Warning: FX offset {fx_offset} cannot be applied to keyword position '{pos}'. Consider using numeric coordinates.")
        
        clip = ImageClip(np_img)
        clip = self._compose_clip(clip, start=start, duration=duration, pos=pos,
                                  pos_end=pos_end, scale=scale, scale_end=scale_end,
                                  size=size, easing=easing, transition_in=transition_in,
                                  transition_out=transition_out, opacity=opacity,
                                  opacity_end=opacity_end, float_fx=float_fx,
                                  pulse_fx=pulse_fx)
        clip = self._apply_dynamic_fx(clip, dynamic_fx, duration)
        if blend_mode:
            clip._blend_mode = blend_mode
        self.layers.append((z_index, clip))

    def add_video_layer(self, video_path: str, start: float, end: float,
                        pos=(0, 0), z_index: int = 0, scale=None, size=None,
                        pos_end=None, scale_end=None, easing: str = None,
                        transition_in=None, transition_out=None,
                        opacity=None, opacity_end=None,
                        fx: Optional[List[tuple]] = None,
                        css_class=None, css_id=None):
        styled = self.style_for(css_class, css_id)
        merged = self._merge_style(
            {"pos": pos, "size": size, "scale": scale, "opacity": opacity,
             "easing": easing, "transition_in": transition_in,
             "transition_out": transition_out, "fx": fx}, styled)
        pos = merged["pos"] if merged["pos"] is not None else (0, 0)
        size, scale = merged["size"], merged["scale"]
        easing = merged["easing"] or "linear"
        transition_in, transition_out = merged["transition_in"], merged["transition_out"]
        opacity = merged["opacity"]
        fx = merged["fx"]
        clip = VideoFileClip(video_path)
        duration = max(0.1, end - start)
        static_fx, dynamic_fx, float_fx, pulse_fx = self._split_fx(fx)
        clip = self._compose_clip(clip, start=start, duration=duration, pos=pos,
                                  pos_end=pos_end, scale=scale, scale_end=scale_end,
                                  size=size, easing=easing, transition_in=transition_in,
                                  transition_out=transition_out, opacity=opacity,
                                  opacity_end=opacity_end, float_fx=float_fx,
                                  pulse_fx=pulse_fx)
        clip = self._apply_dynamic_fx(clip, dynamic_fx, duration)
        blend_mode = self._blend_mode_of(fx)
        if blend_mode:
            clip._blend_mode = blend_mode
        self.layers.append((z_index, clip))

    def add_text_layer(self, text: str, start: float, end: float, pos=(0, 0),
                       z_index: int = 0, font: str = "default", color: str = "#FFFFFF",
                       font_size: int = 48, scale=None, size=None,
                       pos_end=None, scale_end=None, easing: str = None,
                       transition_in=None, transition_out=None,
                       opacity=None, opacity_end=None,
                       stroke_width: int = 0, stroke_fill: str = "#000000",
                       bg_color=None, letter_spacing: int = 0,
                       fx: Optional[List[tuple]] = None,
                       css_class=None, css_id=None):
        styled = self.style_for(css_class, css_id)
        merged = self._merge_style(
            {"pos": pos, "size": size, "scale": scale, "opacity": opacity,
             "easing": easing, "transition_in": transition_in,
             "transition_out": transition_out, "fx": fx}, styled)
        pos = merged["pos"] if merged["pos"] is not None else (0, 0)
        size, scale = merged["size"], merged["scale"]
        easing = merged["easing"] or "linear"
        transition_in, transition_out = merged["transition_in"], merged["transition_out"]
        opacity, fx = merged["opacity"], merged["fx"]
        # CSS text overrides (color / font / size / background / radius).
        st_text = styled.get("text") or {}
        if st_text.get("color"):
            color = st_text["color"]
        if st_text.get("font"):
            font = st_text["font"]
        if st_text.get("font_size"):
            font_size = int(st_text["font_size"])
        if styled.get("background_color") and not bg_color:
            bg_color = styled["background_color"]
        pil = make_text_image(text, font=font, color=color, font_size=font_size,
                              stroke_width=stroke_width, stroke_fill=stroke_fill,
                              bg_color=bg_color, letter_spacing=letter_spacing)
        if styled.get("border_radius"):
            pil = _css.round_corners(pil, int(styled["border_radius"]))
        self.add_image_layer(pil, start=start, end=end, pos=pos, z_index=z_index,
                             scale=scale, size=size, pos_end=pos_end, scale_end=scale_end,
                             easing=easing, transition_in=transition_in,
                             transition_out=transition_out, opacity=opacity,
                             opacity_end=opacity_end, fx=fx)

    def add_audio_layer(self, audio_path: str, start: float, duration: float = None,
                        volume: float = 1.0):
        """Loads and positions audio clips with volume control."""
        audio_clip = AudioFileClip(audio_path)
        self.audio_layers.append(
            _audio_placed(audio_clip, start, duration, volume))

    def _install_blend_compositing(self, comp, clips):
        """Route compositing through a manual blender if any layer blends.

        moviepy's stock compositor only does source-over. When at least one
        layer requests ``blend_mode(...)`` we install a version-agnostic frame
        function that composites bottom-up and applies the AE blend math
        before the alpha-over step.
        """
        if not any(getattr(c, "_blend_mode", None) for c in clips):
            return
        width, height = self.width, self.height

        def _frame(t):
            bg = getattr(comp, "bg", None)
            if bg is None:
                canvas = np.zeros((height, width, 3), dtype=np.float32)
            else:
                bg_start = getattr(bg, "start", 0) or 0.0
                arr = np.asarray(bg.get_frame(t - bg_start), dtype=np.float32)
                if arr.ndim == 2:
                    arr = np.stack([arr] * 3, axis=-1)
                if arr.shape[2] == 4:
                    # Flatten the (transparent) background over black.
                    arr = arr[:, :, :3] * (arr[:, :, 3:4] / 255.0)
                else:
                    arr = arr[:, :, :3]
                canvas = arr
            for clip in comp.playing_clips(t):
                mode = getattr(clip, "_blend_mode", None) or "normal"
                canvas = _blit_clip(canvas, clip, t, mode)
            return np.clip(canvas, 0, 255).astype(np.uint8)

        # 1.x reads ValueClip.make_frame; 2.x calls self.frame_function.
        try:
            comp.make_frame = _frame
        except Exception:
            pass
        try:
            comp.frame_function = _frame
        except Exception:
            pass

    def build(self, output_path: str = "output/rendered.mp4"):
        self.layers.sort(key=lambda x: x[0])
        sorted_clips = [clip for z, clip in self.layers]
        # Explicit opaque background: video output has no alpha, so this avoids
        # moviepy building a full-size composite mask (which also crashes on
        # some 2.x versions when layer masks differ in size).
        final_video = CompositeVideoClip(sorted_clips, size=(self.width, self.height),
                                         bg_color=(0, 0, 0))
        self._install_blend_compositing(final_video, sorted_clips)
        if self.audio_layers:
            final_audio = CompositeAudioClip(self.audio_layers)
            final_video = _with_audio(final_video, final_audio)
        if self.mode == "preview":
            print("[Engine] Launching preview window with audio via ffplay...")
            ffplay_cmd = ['ffplay', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                          '-video_size', f'{self.width}x{self.height}',
                          '-framerate', str(self.fps),
                          '-window_title', 'Motion Lang Preview', '-i', 'pipe:0']
            try:
                process = subprocess.Popen(ffplay_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                for t in np.arange(0, final_video.duration, 1.0 / self.fps):
                    frame = final_video.get_frame(t)
                    process.stdin.write(frame.tobytes())
                process.stdin.close()
                process.wait()
            except Exception as e:
                print(f"[Preview Error] {e}")
        else:
            print(f"[Engine] Rendering video + audio to {output_path}...")
            final_video.write_videofile(output_path, fps=self.fps, codec="libx264", audio_codec="aac", logger="bar")
