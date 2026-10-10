"""Visual Effects pipeline for Motion Language."""

import math
from typing import List, Tuple, Callable, Optional

from PIL import Image, ImageFilter, ImageEnhance
import numpy as np


def apply_blur(image: Image.Image, radius: int) -> Image.Image:
    """Apply Gaussian blur to an image.

    Args:
        image: PIL Image.
        radius: Blur radius (pixels).

    Returns:
        Blurred PIL Image.
    """
    if radius < 0:
        raise ValueError("Blur radius must be non-negative.")
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_glow(image: Image.Image, color: str, intensity: float = 1.0,
               radius: Optional[int] = None) -> Image.Image:
    """Apply an AE-style outer glow around the source alpha.

    The glow is a blurred, color-tinted copy of the source silhouette placed
    *behind* the untouched source. ``radius`` controls the blur spread and
    ``intensity`` scales the glow alpha (values > 1.0 are allowed and clamp).

    Args:
        image: PIL Image (will be duplicated internally).
        color: Glow color (hex string).
        intensity: Glow strength multiplier.
        radius: Blur radius in pixels; defaults to ``intensity * 20``.

    Returns:
        Image with glow effect applied (canvas expanded to fit the halo).
    """
    rgba = image.convert("RGBA")
    blur_r = max(1, int(radius)) if radius is not None else max(1, int(intensity * 20))
    strength = max(0.0, min(1.5, float(intensity)))
    # Build a tinted silhouette from the source alpha, then blur it.
    glow_alpha = rgba.getchannel("A").point(
        lambda v: int(min(255, v * strength)))
    tint = Image.new("RGBA", rgba.size, _hex_to_rgba(color)[:3] + (0,))
    tint.putalpha(glow_alpha)
    tint = tint.filter(ImageFilter.GaussianBlur(radius=blur_r))
    margin = blur_r * 2
    glow = Image.new("RGBA",
                     (rgba.width + margin * 2, rgba.height + margin * 2),
                     (0, 0, 0, 0))
    glow.paste(tint, (margin, margin), tint)
    glow.paste(rgba, (margin, margin), rgba)
    return glow


def _hex_to_rgba(hex_color: str) -> Tuple[int, int, int, int]:
    """Convert a hex color string to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r, g, b, 255)
    elif len(hex_color) == 8:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        a = int(hex_color[6:8], 16)
        return (r, g, b, a)
    return (255, 255, 255, 255)


def apply_drop_shadow(image: Image.Image, offset_x: int, offset_y: int, blur: int, color: str) -> Image.Image:
    """Apply a drop shadow effect.

    The source image is preserved and composited over a blurred,
    offset silhouette tinted ``color`` (whose own alpha scales the
    shadow strength).

    Args:
        image: PIL Image.
        offset_x: Horizontal offset of the shadow.
        offset_y: Vertical offset of the shadow.
        blur: Blur radius for the shadow.
        color: Shadow color (hex string).

    Returns:
        Image with drop shadow applied.
    """
    rgba = image.convert("RGBA")
    ox, oy = int(offset_x), int(offset_y)
    r, g, b, a = _hex_to_rgba(color)
    strength = a / 255.0
    # Silhouette of the source alpha, tinted with the shadow color.
    src_alpha = rgba.getchannel("A").point(lambda v: int(v * strength))
    silhouette = Image.new("RGBA", rgba.size, (r, g, b, 0))
    silhouette.putalpha(src_alpha)
    silhouette = apply_blur(silhouette, max(0, int(blur)))
    cw, ch = rgba.size[0] + abs(ox), rgba.size[1] + abs(oy)
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.paste(silhouette, (max(ox, 0), max(oy, 0)), silhouette)
    canvas.paste(rgba, (max(-ox, 0), max(-oy, 0)), rgba)
    return canvas


def apply_opacity(image: Image.Image, alpha: float) -> Image.Image:
    """Apply opacity (alpha) to an image.

    Args:
        image: PIL Image.
        alpha: Alpha value between 0.0 (fully transparent) and 1.0 (fully opaque).

    Returns:
        Image with adjusted alpha channel.
    """
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("Alpha must be between 0.0 and 1.0.")
    rgba = image.convert("RGBA")
    alpha_band = rgba.getchannel('A')
    scaled_alpha = alpha_band.point(lambda i: int(i * alpha))
    rgba.putalpha(scaled_alpha)
    return rgba


def adjust_color(image: Image.Image, brightness: float, contrast: float, saturation: float) -> Image.Image:
    """Adjust color balance using brightness, contrast, and saturation.

    Args:
        image: PIL Image.
        brightness: Brightness adjustment (-1.0 to 1.0).
        contrast: Contrast adjustment (-1.0 to 1.0).
        saturation: Saturation adjustment (-1.0 to 1.0).

    Returns:
        Image with adjusted colors.
    """
    enhancer = ImageEnhance.Brightness(image)
    brightened = enhancer.enhance(1.0 + brightness)
    contrast_enhancer = ImageEnhance.Contrast(brightened)
    contrasted = contrast_enhancer.enhance(1.0 + contrast)
    # Saturation: convert to grayscale, then blend based on saturation factor
    if saturation != 0.0:
        gray = contrasted.convert("L").convert("RGBA")
        saturated = Image.blend(gray, contrasted, 1.0 + saturation)
    else:
        saturated = contrasted
    return saturated


def apply_vfx_preset(image: Image.Image, preset_name: str, **params) -> Image.Image:
    """Apply a named visual effects preset.

    Args:
        image: PIL Image.
        preset_name: Name of the preset ("chromatic_aberration", "glitch",
            "vignette", "motion_blur", "glow", "blur").
        **params: Optional parameters forwarded to the effect.

    Returns:
        Image with the preset effect applied.
    """
    preset_map = {
        "chromatic_aberration": chromatic_aberration,
        "glitch": glitch,
        "vignette": vignette,
        "motion_blur": motion_blur,
        "glow": apply_glow,
        "blur": apply_blur,
    }
    func = preset_map.get(preset_name.lower())
    if func is None:
        print(f"[VFX] Unknown preset: {preset_name}. Skipping.")
        return image
    return func(image, **params)


def chromatic_aberration(image: Image.Image, offset: int = 3) -> Image.Image:
    """Shift the red/blue channels horizontally to fake lens dispersion.

    Args:
        image: PIL Image.
        offset: Channel displacement in pixels.

    Returns:
        Image with chromatic aberration applied.
    """
    offset = max(0, int(offset))
    rgba = image.convert("RGBA")
    r, g, b, a = rgba.split()
    shifted_r = r.transform(r.size, Image.AFFINE, (1, 0, offset, 0, 1, 0))
    shifted_b = b.transform(b.size, Image.AFFINE, (1, 0, -offset, 0, 1, 0))
    return Image.merge("RGBA", (shifted_r, g, shifted_b, a))


def glitch(image: Image.Image, intensity: float = 0.3, seed: Optional[int] = None) -> Image.Image:
    """Apply a deterministic datamosh-style glitch (RGB slice displacement).

    Args:
        image: PIL Image.
        intensity: 0..1 strength; drives slice count and displacement.
        seed: Optional RNG seed for reproducible output across frames.

    Returns:
        Image with glitch bands shifted.
    """
    import random as _random
    rng = _random.Random(seed)
    intensity = max(0.0, min(1.0, float(intensity)))
    width, height = image.size
    glitched = image.convert("RGBA")
    r, g, b, a = glitched.split()
    channels = [r, g, b]
    n_slices = max(1, int(round(intensity * 8)) + 1)
    max_shift = max(1, int(width * 0.06 * intensity) + 2)
    for _ in range(n_slices):
        y = int(rng.random() * height)
        slice_h = int(rng.random() * (height * 0.06 * intensity + 4)) + 1
        shift = int((rng.random() * 2 - 1) * max_shift)
        for ch in channels:
            piece = ch.crop((0, y, width, min(y + slice_h, height)))
            shifted = piece.transform(piece.size, Image.AFFINE,
                                      (1, 0, shift, 0, 1, 0))
            ch.paste(shifted, (0, y))
    return Image.merge("RGBA", (r, g, b, a))


def vignette(image: Image.Image, amount: float = 0.5) -> Image.Image:
    """Darken the corners/edges of the image (vectorised radial falloff).

    Args:
        image: PIL Image.
        amount: 0..1 darkening strength at the frame edges.

    Returns:
        Image with a vignette overlaid.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    amount = max(0.0, min(1.0, float(amount)))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    dist = np.sqrt(((xx - cx) / max(cx, 1)) ** 2 + ((yy - cy) / max(cy, 1)) ** 2)
    mask = np.clip(1.0 - amount * np.clip(dist, 0.0, 1.0) ** 1.5, 0.0, 1.0)
    arr = np.array(rgba, dtype=np.float32)
    arr[:, :, :3] *= mask[:, :, None]
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def motion_blur(image: Image.Image, samples: int = 8, direction: int = 0,
                distance: Optional[int] = None) -> Image.Image:
    """Average several shifted copies of the frame along a direction.

    Args:
        image: PIL Image.
        samples: Number of shifted copies to average (>=1).
        direction: Angle in degrees (0 = horizontal, 90 = vertical).
        distance: Total motion spread in pixels; defaults to 4% of the
            image's largest dimension.

    Returns:
        Motion-blurred image.
    """
    samples = max(1, int(samples))
    if samples == 1:
        return image
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if distance is None:
        distance = max(2, int(max(width, height) * 0.04))
    ang = math.radians(float(direction))
    cos_a, sin_a = math.cos(ang), math.sin(ang)
    half = (samples - 1) / 2.0
    total = np.zeros((height, width, 4), dtype=np.float32)
    for i in range(samples):
        # Offset ramps symmetrically from -distance to +distance.
        off = ((i - half) / half) * distance if half else 0.0
        dx, dy = int(round(off * cos_a)), int(round(off * sin_a))
        shifted = rgba.transform(rgba.size, Image.AFFINE,
                                 (1, 0, -dx, 0, 1, -dy))
        total += np.array(shifted, dtype=np.float32)
    return Image.fromarray((total / samples).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------------------
# Layer reflection / flash / light-sweep / floating-motion
# ---------------------------------------------------------------------------

def apply_reflection(image: Image.Image, opacity: float = 0.5, blur: int = 5,
                     gap: int = 0, fade: bool = True,
                     fade_power: float = 1.4) -> Image.Image:
    """Attach a vertically-flipped copy beneath the layer ("floor" reflection).

    The reflection is faded top→bottom so it dissolves as it moves away from
    the contact edge, then scaled by ``opacity`` and optionally blurred.

    Args:
        image: Source PIL Image.
        opacity: Reflection strength (0..1).
        blur: Gaussian blur radius applied to the reflection.
        gap: Blank pixels between the layer and its reflection.
        fade: Apply the top-to-bottom alpha falloff.
        fade_power: Exaggeration of the falloff (1 = linear).

    Returns:
        A taller RGBA image: original on top, reflection beneath.
    """
    rgba = image.convert("RGBA")
    w, h = rgba.size
    flipped = rgba.transpose(Image.FLIP_TOP_BOTTOM)  # == np.flipud
    if int(blur) > 0:
        flipped = flipped.filter(ImageFilter.GaussianBlur(int(blur)))
    if fade and h > 0:
        arr = np.array(flipped, dtype=np.float32)
        # Strongest at the contact edge (row 0 of the reflection) → 0 at the
        # far edge, so the mirror dissolves downward.
        ramp = np.linspace(1.0, 0.0, h, dtype=np.float32) ** max(0.01, float(fade_power))
        arr[:, :, 3] *= ramp[:, None]
        flipped = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    if opacity < 1.0:
        flipped = apply_opacity(flipped, max(0.0, min(1.0, float(opacity))))
    gap = max(0, int(gap))
    out = Image.new("RGBA", (w, h * 2 + gap), (0, 0, 0, 0))
    # Plain pastes (no mask): the two regions never overlap, so this copies
    # exact RGBA values. (Pasting with the image itself as mask would square
    # the alpha channel.)
    out.paste(rgba, (0, 0))
    out.paste(flipped, (0, h + gap))
    return out


def flash_overlay(image: Image.Image, progress: float,
                  color: str = "#FFFFFF") -> Image.Image:
    """Composite a solid-colour flash that decays 100% → 0% over ``progress``.

    Args:
        image: Source PIL Image.
        progress: Normalised time through the flash (0 = start, 1 = done).
        color: Flash colour.

    Returns:
        Image with the flash composited inside the layer silhouette.
    """
    rgba = image.convert("RGBA")
    p = max(0.0, min(1.0, float(progress)))
    alpha = 1.0 - p
    if alpha <= 0.0:
        return rgba
    r, g, b, _ = _hex_to_rgba(color)
    flash = Image.new("RGBA", rgba.size, (r, g, b, 0))
    src_alpha = rgba.getchannel("A").point(lambda v: int(v * alpha))
    flash.putalpha(src_alpha)
    return Image.alpha_composite(rgba, flash)


# Friendlier alias matching the DSL effect name.
apply_flash = flash_overlay


def light_sweep(image: Image.Image, progress: float, angle: float = 45.0,
                speed: float = 1.0, width: float = 0.25,
                color: str = "#FFFFFF", intensity: float = 1.0) -> Image.Image:
    """Sweep a soft diagonal sheen across the layer silhouette.

    Args:
        image: Source PIL Image.
        progress: Position of the sweep through its travel (0..1).
        angle: Sweep direction in degrees (0 = left→right, 90 = top→bottom).
        speed: Reserved for time scaling by the caller; kept for API parity.
        width: Sheen thickness as a fraction of the projected span.
        color: Sheen tint (white/gold read best).
        intensity: Additive brightness multiplier.

    Returns:
        Image with the moving highlight added (clipped inside the alpha).
    """
    rgba = image.convert("RGBA")
    w, h = rgba.size
    if w == 0 or h == 0:
        return rgba
    arr = np.array(rgba, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = math.radians(float(angle))
    dx, dy = math.cos(ang), math.sin(ang)
    proj = xx * dx + yy * dy
    pmin, pmax = float(proj.min()), float(proj.max())
    span = max(pmax - pmin, 1.0)
    band = max(span * max(0.01, float(width)), 1.0)
    center = pmin - band + max(0.0, min(1.0, float(progress))) * (span + 2.0 * band)
    prof = np.exp(-(((proj - center) / band) ** 2))
    alpha = arr[:, :, 3:4] / 255.0
    sheen = np.asarray(_hex_to_rgba(color)[:3], dtype=np.float32)
    add = prof[:, :, None] * alpha * max(0.0, float(intensity))
    arr[:, :, :3] = np.clip(arr[:, :, :3] + sheen[None, None, :] * add, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def pulse_scale(time: float, amount: float = 0.1, speed: float = 1.0) -> float:
    """Sinusoidal scale multiplier: ``1 + amount * sin(time * speed)``."""
    return 1.0 + float(amount) * math.sin(float(time) * float(speed))


def float_y_offset(time: float, distance: float = 20.0,
                   speed: float = 1.0) -> float:
    """Sinusoidal vertical offset: ``sin(time * speed) * distance``."""
    return math.sin(float(time) * float(speed)) * float(distance)


def blend_rgb(base: np.ndarray, top: np.ndarray, mode: str = "normal") -> np.ndarray:
    """Blend two uint8 RGB arrays using an AE/Photoshop blend mode.

    Args:
        base: Backdrop RGB array (H, W, 3) uint8.
        top: Source RGB array (H, W, 3) uint8.
        mode: One of "normal", "multiply", "screen", "overlay", "add",
            "difference", "lighten", "darken", "soft_light".

    Returns:
        Blended uint8 RGB array of the same shape.
    """
    mode = (mode or "normal").lower().replace("-", "_")
    if mode in ("normal", "none", "source_over"):
        return top
    b = base.astype(np.float32)
    t = top.astype(np.float32)
    if mode == "multiply":
        out = b * t / 255.0
    elif mode == "screen":
        out = 255.0 - (255.0 - b) * (255.0 - t) / 255.0
    elif mode == "overlay":
        out = np.where(b < 128.0, 2.0 * b * t / 255.0,
                       255.0 - 2.0 * (255.0 - b) * (255.0 - t) / 255.0)
    elif mode in ("add", "addition", "linear_dodge"):
        out = b + t
    elif mode == "difference":
        out = np.abs(b - t)
    elif mode == "lighten":
        out = np.maximum(b, t)
    elif mode == "darken":
        out = np.minimum(b, t)
    elif mode == "soft_light":
        out = np.where(
            t < 128.0,
            b - (255.0 - 2.0 * t) * b * (255.0 - b) / (255.0 * 255.0),
            b + (2.0 * t - 255.0) * (np.sqrt(b / 255.0) * 255.0 - b) / 255.0)
    else:
        return top
    return np.clip(out, 0, 255).astype(np.uint8)


# Backwards-compatible private aliases.
def _chromatic_aberration(image: Image.Image) -> Image.Image:
    return chromatic_aberration(image, offset=3)


def _glitch(image: Image.Image) -> Image.Image:
    return glitch(image, intensity=0.3)


def _vignette(image: Image.Image) -> Image.Image:
    return vignette(image, amount=0.5)


def apply_fx_stack(image: Image.Image, fx_stack: List[Callable[[Image.Image], Image.Image]]) -> Image.Image:
    """Apply a sequence of visual effects in order.

    Args:
        image: PIL Image.
        fx_stack: List of effect functions to apply sequentially.

    Returns:
        Image with all effects applied.
    """
    for fx_func in fx_stack:
        image = fx_func(image)
    return image