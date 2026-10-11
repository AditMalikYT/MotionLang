"""Shape generation engine for Motion Language.

Generators are pure Pillow/NumPy (with an optional OpenCV anti-aliased
rasteriser) and return transparent ``RGBA`` images:

* primitives: ``rect``, ``circle``, ``polygon``, ``star`` (N-point)
* ``path``: SVG files / inline markup / raw path data
* gradient paints: ``fill="gradient(linear, #a, #b[, angle])"`` and
  ``fill="gradient(radial, #a, #b)"``
"""

import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter  # noqa: F401 (ImageFilter re-exported)

try:  # OpenCV is used for anti-aliased polygon/ellipse rasterisation.
    import cv2  # type: ignore
    _CV2 = True
except Exception:  # pragma: no cover - Pillow fallback below
    cv2 = None  # type: ignore
    _CV2 = False


# ---------------------------------------------------------------------------
# Colour + gradient helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(color) -> Tuple[int, int, int, int]:
    """Coerce ``"#RGB"``/``"#RRGGBB"``/``"#RRGGBBAA"``/tuple to an RGBA tuple."""
    if isinstance(color, (tuple, list)):
        vals = [int(c) for c in color]
        if len(vals) == 3:
            return (vals[0], vals[1], vals[2], 255)
        if len(vals) >= 4:
            return (vals[0], vals[1], vals[2], vals[3])
        return (255, 255, 255, 255)
    s = str(color or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    if isinstance(color, str) and color.strip().lower() in _NAMED_COLORS:
        return _NAMED_COLORS[color.strip().lower()]
    return (255, 255, 255, 255)


_NAMED_COLORS = {
    "white": (255, 255, 255, 255),
    "black": (0, 0, 0, 255),
    "red": (255, 0, 0, 255),
    "green": (0, 128, 0, 255),
    "blue": (0, 0, 255, 255),
    "cyan": (0, 255, 255, 255),
    "magenta": (255, 0, 255, 255),
    "yellow": (255, 255, 0, 255),
    "gold": (255, 215, 0, 255),
    "none": (0, 0, 0, 0),
    "transparent": (0, 0, 0, 0),
}


_GRADIENT_RE = re.compile(
    r"^\s*gradient\s*\(\s*(?P<kind>[A-Za-z]+)\s*,(?P<body>.*)\)\s*$", re.S)
_COLOR_RE = re.compile(r"^\s*(#[0-9a-fA-F]{3,8}|[A-Za-z]+)\s*$")


def is_gradient(spec) -> bool:
    """True if ``spec`` is a ``gradient(...)`` paint description."""
    return bool(isinstance(spec, str) and _GRADIENT_RE.match(spec))


def _split_top_commas(text: str) -> List[str]:
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def parse_gradient(spec: str) -> Optional[Dict[str, Any]]:
    """Parse ``gradient(linear, #a, #b[, angle])`` into a paint descriptor.

    The kind is ``linear`` or ``radial``.  Stops are the colour arguments in
    order; a stray numeric argument is treated as the linear direction angle
    (degrees, 0 = left→right, 90 = top→bottom).
    """
    if not isinstance(spec, str):
        return None
    m = _GRADIENT_RE.match(spec)
    if not m:
        return None
    kind = m.group("kind").strip().lower()
    if kind not in ("linear", "radial"):
        kind = "linear"
    stops: List[Tuple[int, int, int, int]] = []
    angle = 90.0
    for part in _split_top_commas(m.group("body")):
        if _COLOR_RE.match(part):
            stops.append(_hex_to_rgba(part))
        else:
            try:
                angle = float(part)
            except ValueError:
                pass
    if not stops:
        stops = [(255, 255, 255, 255)]
    if len(stops) == 1:
        stops = [stops[0], stops[0]]
    return {"kind": kind, "stops": stops, "angle": angle}


def _sample_stops(stops: Sequence[Tuple[int, int, int, int]], t: np.ndarray) -> np.ndarray:
    """Sample a piecewise-linear colour ramp ``stops`` at ``t`` in [0, 1]."""
    t = np.clip(np.asarray(t, np.float32), 0.0, 1.0)
    arr = np.asarray(stops, dtype=np.float32)[:, :3]
    n = len(arr)
    if n == 1:
        return np.broadcast_to(arr[0], t.shape + (3,)).copy()
    scaled = t * (n - 1)
    lo = np.floor(scaled).astype(np.int32)
    hi = np.minimum(lo + 1, n - 1)
    frac = (scaled - lo)[..., None]
    return arr[lo] * (1.0 - frac) + arr[hi] * frac


def gradient_image(width: int, height: int, grad: Dict[str, Any]) -> Image.Image:
    """Rasterise a gradient paint to an opaque RGBA image of ``width``×``height``."""
    width = max(1, int(width))
    height = max(1, int(height))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    stops = grad.get("stops") or [(255, 255, 255, 255), (255, 255, 255, 255)]
    if grad.get("kind") == "radial":
        cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        radius = max(cx, cy, 1.0)
        t = np.clip(dist / radius, 0.0, 1.0)
    else:
        ang = math.radians(float(grad.get("angle", 90.0)))
        proj = xx * math.cos(ang) + yy * math.sin(ang)
        span = proj.max() - proj.min()
        t = (proj - proj.min()) / span if span > 1e-6 else np.zeros_like(proj)
    rgb = _sample_stops(stops, t)
    rgba = np.concatenate([rgb, np.full((height, width, 1), 255.0, np.float32)], axis=2)
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")


def _apply_gradient(shape: Image.Image, grad: Dict[str, Any]) -> Image.Image:
    """Repaint the non-transparent pixels of ``shape`` with a gradient."""
    base = shape.convert("RGBA")
    grad_img = np.asarray(gradient_image(base.width, base.height, grad), dtype=np.float32)
    arr = np.asarray(base, dtype=np.float32).copy()
    alpha = arr[:, :, 3:4] / 255.0
    arr[:, :, :3] = grad_img[:, :, :3] * alpha + arr[:, :, :3] * (1.0 - alpha)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------------------
# Anti-aliased rasterisation primitives
# ---------------------------------------------------------------------------

def _polygon_aa(size: Tuple[int, int], verts: Sequence[Tuple[float, float]],
                fill: Tuple[int, int, int, int]) -> Image.Image:
    """Anti-aliased filled polygon (OpenCV when available, Pillow otherwise)."""
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    if _CV2:
        canvas = np.zeros((height, width, 4), np.uint8)
        pts = np.round(np.asarray(verts, np.float64)).astype(np.int32).reshape(-1, 1, 2)
        # NOTE: raw channel order — the buffer is read back as RGBA below,
        # so write (R, G, B, A), not OpenCV's BGR convention.
        rgba = (int(fill[0]), int(fill[1]), int(fill[2]), int(fill[3]))
        cv2.fillPoly(canvas, [pts], rgba, lineType=cv2.LINE_AA)
        return Image.fromarray(canvas, "RGBA")
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(float(x), float(y)) for x, y in verts], fill=fill)
    return img


def _stroke_poly(img: Image.Image, verts: Sequence[Tuple[float, float]],
                 color: Tuple[int, int, int, int], width: int) -> None:
    """Draw an anti-aliased closed outline of ``verts`` in place."""
    if width <= 0 or color[3] == 0:
        return
    if _CV2:
        arr = np.array(img.convert("RGBA"), dtype=np.uint8)
        pts = np.round(np.asarray(verts, np.float64)).astype(np.int32).reshape(-1, 1, 2)
        rgba = (int(color[0]), int(color[1]), int(color[2]), int(color[3]))
        cv2.polylines(arr, [pts], True, rgba, thickness=int(width),
                      lineType=cv2.LINE_AA)
        img.paste(Image.fromarray(arr, "RGBA"), (0, 0))
        return
    ImageDraw.Draw(img).line(list(verts) + [verts[0]], fill=color,
                             width=int(width), joint="curve")


def _paint_shape(size: Tuple[int, int], verts: Optional[Sequence[Tuple[float, float]]],
                 color: str, gradient: Optional[Dict[str, Any]],
                 stroke_color: Optional[str], stroke_width: int,
                 shape_order: str = "rect",
                 ellipse: Optional[Tuple[int, int, int, int]] = None,
                 round_rect: Optional[Tuple[Tuple[int, int, int, int], int]] = None,
                 draw_text: bool = False) -> Image.Image:
    """Generic fill + optional gradient + outline renderer.

    ``shape_order`` selects the fill mask: ``polygon`` (uses ``verts``),
    ``ellipse`` or ``round_rect``.
    """
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    fill_rgba = _hex_to_rgba(color)

    if shape_order == "polygon":
        img = _polygon_aa((width, height), verts or [], fill_rgba)
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if shape_order == "ellipse" and ellipse is not None:
            d.ellipse(ellipse, fill=fill_rgba)
        elif shape_order == "round_rect" and round_rect is not None:
            box, radius = round_rect
            d.rounded_rectangle(box, radius=radius, fill=fill_rgba)
        else:
            d.rectangle([0, 0, width - 1, height - 1], fill=fill_rgba)

    if gradient is not None:
        img = _apply_gradient(img, gradient)

    sw = int(stroke_width or 0)
    if sw > 0 and stroke_color:
        sc = _hex_to_rgba(stroke_color)
        if shape_order == "polygon" and verts:
            _stroke_poly(img, verts, sc, sw)
        else:
            d = ImageDraw.Draw(img)
            if shape_order == "ellipse" and ellipse is not None:
                d.ellipse(ellipse, outline=sc, width=sw)
            elif shape_order == "round_rect" and round_rect is not None:
                box, radius = round_rect
                d.rounded_rectangle(box, radius=radius, outline=sc, width=sw)
            else:
                d.rectangle([0, 0, width - 1, height - 1], outline=sc, width=sw)
    return img


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def draw_rect(width: int, height: int, color: str, radius: Optional[int] = None,
              stroke_color: Optional[str] = None, stroke_width: int = 0,
              gradient: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Generate a rectangle shape with optional rounded corners and outline."""
    box = [0, 0, max(0, width - 1), max(0, height - 1)]
    if radius is not None:
        return _paint_shape((width, height), None, color, gradient, stroke_color,
                            stroke_width, shape_order="round_rect",
                            round_rect=(box, int(radius)))
    return _paint_shape((width, height), None, color, gradient, stroke_color,
                        stroke_width, shape_order="rect")


def draw_circle(radius: int, color: str, stroke_color: Optional[str] = None,
                stroke_width: int = 0,
                gradient: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Generate a circular shape with given radius and optional outline."""
    size = int(radius) * 2
    box = [0, 0, size - 1, size - 1]
    return _paint_shape((size, size), None, color, gradient, stroke_color,
                        stroke_width, shape_order="ellipse", ellipse=box)


def draw_polygon(points: List[Tuple[float, float]], color: str,
                 stroke_color: Optional[str] = None, stroke_width: int = 0,
                 gradient: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Generate a polygon shape from a list of (x, y) points."""
    if not points or len(points) < 3:
        raise ValueError("At least three points are required to define a polygon.")
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    width = max(1, int(max(x_coords) - min(x_coords)))
    height = max(1, int(max(y_coords) - min(y_coords)))
    min_x, min_y = min(x_coords), min(y_coords)
    adjusted = [(x - min_x, y - min_y) for x, y in points]
    return _paint_shape((width, height), adjusted, color, gradient, stroke_color,
                        stroke_width, shape_order="polygon")


def draw_line(x1: float = 0, y1: float = 0, x2: float = 0, y2: float = 0,
              color: str = "#FFFFFF", width: int = 1) -> Image.Image:
    """Generate an anti-aliased line segment as a transparent RGBA image.

    The canvas is the segment's bounding box, grown so the ``width``-thick
    stroke always fits: a horizontal line gets ``height == width``, a point
    degrades to a filled dot. Render it at ``pos=(min(x1, x2), min(y1, y2))``
    to place the segment at absolute coordinates.
    """
    thickness = max(1, int(width))
    fx1, fy1, fx2, fy2 = float(x1), float(y1), float(x2), float(y2)
    min_x, max_x = min(fx1, fx2), max(fx1, fx2)
    min_y, max_y = min(fy1, fy2), max(fy1, fy2)
    cw = max(int(round(max_x - min_x)) + 1, thickness)
    ch = max(int(round(max_y - min_y)) + 1, thickness)
    ox = (cw - 1 - (max_x - min_x)) / 2.0
    oy = (ch - 1 - (max_y - min_y)) / 2.0
    p1 = (fx1 - min_x + ox, fy1 - min_y + oy)
    p2 = (fx2 - min_x + ox, fy2 - min_y + oy)
    rgba = _hex_to_rgba(color)
    if _CV2:
        canvas = np.zeros((ch, cw, 4), np.uint8)
        # Raw channel order: read back as RGBA below, so write (R, G, B, A).
        rgba8 = (int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
        cv2.line(canvas,
                 (int(round(p1[0])), int(round(p1[1]))),
                 (int(round(p2[0])), int(round(p2[1]))),
                 rgba8, thickness=thickness, lineType=cv2.LINE_AA)
        return Image.fromarray(canvas, "RGBA")
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([p1, p2], fill=rgba, width=thickness)
    return img


def star_vertices(points: int = 5, radius: int = 100,
                  inner_radius: Optional[int] = None,
                  rotation: float = -90.0) -> List[Tuple[float, float]]:
    """Compute the ``2 * points`` vertices of an N-point star centered at (r, r)."""
    points = max(3, int(points))
    radius = int(radius)
    inner = int(inner_radius) if inner_radius else int(radius * 0.45)
    cx = cy = radius
    verts: List[Tuple[float, float]] = []
    for i in range(points * 2):
        ang = math.radians(rotation + i * 180.0 / points)
        r = radius if i % 2 == 0 else inner
        verts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return verts


def draw_star(points: int = 5, radius: int = 100,
              inner_radius: Optional[int] = None, color: str = "#FFFFFF",
              rotation: float = -90.0, stroke_color: Optional[str] = None,
              stroke_width: int = 0,
              gradient: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Generate an anti-aliased N-point star.

    ``radius`` is the outer radius (``outer_radius`` is accepted as an
    alias).  ``inner_radius`` defaults to ``radius * 0.45``; 4-point stars
    read as "sparkles", 5-point as classic stars.
    """
    radius = int(radius)
    size = radius * 2
    verts = star_vertices(points=points, radius=radius,
                          inner_radius=inner_radius, rotation=rotation)
    return _paint_shape((size, size), verts, color, gradient, stroke_color,
                        stroke_width, shape_order="polygon")


# ---------------------------------------------------------------------------
# SVG path rasterisation
# ---------------------------------------------------------------------------

_SVG_CMD_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)")


def _svg_number(tok: str) -> float:
    try:
        return float(tok)
    except ValueError:
        return 0.0


def parse_svg_path(d: str) -> List[List[Tuple[float, float]]]:
    """Flatten an SVG ``d`` attribute into a list of polyline sub-paths.

    Supports ``M/L/H/V/C/S/Q/T/A/Z`` (absolute + relative).  Curves are
    flattened into line segments; arcs are approximated with a quadratic
    control-point shortcut (adequate for icon glyphs).
    """
    tokens = [(m.group(1), m.group(2)) for m in _SVG_CMD_RE.finditer(d or "")]
    subpaths: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    prev_ctrl: Optional[Tuple[float, float]] = None
    i = 0
    cmd = None

    def nums(n: int) -> List[float]:
        nonlocal i
        vals = []
        while len(vals) < n and i < len(tokens):
            if tokens[i][0] is not None:
                break
            vals.append(_svg_number(tokens[i][1]))
            i += 1
        return vals

    def add_pt(x, y):
        nonlocal cx, cy
        cx, cy = float(x), float(y)
        current.append((cx, cy))

    def cubic(p0, p1, p2, p3, steps=16):
        for s in range(1, steps + 1):
            t = s / steps
            mt = 1 - t
            x = (mt ** 3) * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
            y = (mt ** 3) * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
            add_pt(x, y)

    def quad(p0, p1, p2, steps=12):
        for s in range(1, steps + 1):
            t = s / steps
            mt = 1 - t
            x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
            y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
            add_pt(x, y)

    while i < len(tokens):
        if tokens[i][0] is not None:
            cmd = tokens[i][0]
            i += 1
        if cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        C = cmd.upper()
        if C == "M":
            vals = nums(2)
            if len(vals) < 2:
                break
            x, y = vals
            if rel:
                x, y = cx + x, cy + y
            if current:
                subpaths.append(current)
            current = []
            add_pt(x, y)
            start_x, start_y = cx, cy
            cmd = "l" if rel else "L"  # subsequent pairs are lineto
        elif C == "L":
            vals = nums(2)
            if len(vals) < 2:
                break
            x, y = vals
            add_pt(cx + x, cy + y) if rel else add_pt(x, y)
        elif C == "H":
            vals = nums(1)
            if not vals:
                break
            add_pt(cx + vals[0], cy) if rel else add_pt(vals[0], cy)
        elif C == "V":
            vals = nums(1)
            if not vals:
                break
            add_pt(cx, cy + vals[0]) if rel else add_pt(cx, vals[0])
        elif C == "C":
            vals = nums(6)
            if len(vals) < 6:
                break
            p0 = (cx, cy)
            if rel:
                p1 = (cx + vals[0], cy + vals[1])
                p2 = (cx + vals[2], cy + vals[3])
                p3 = (cx + vals[4], cy + vals[5])
            else:
                p1, p2, p3 = (vals[0], vals[1]), (vals[2], vals[3]), (vals[4], vals[5])
            cubic(p0, p1, p2, p3)
            prev_ctrl = p2
        elif C == "S":
            vals = nums(4)
            if len(vals) < 4:
                break
            p0 = (cx, cy)
            p1 = (2 * cx - prev_ctrl[0], 2 * cy - prev_ctrl[1]) if prev_ctrl else p0
            if rel:
                p2 = (cx + vals[0], cy + vals[1])
                p3 = (cx + vals[2], cy + vals[3])
            else:
                p2, p3 = (vals[0], vals[1]), (vals[2], vals[3])
            cubic(p0, p1, p2, p3)
            prev_ctrl = p2
        elif C == "Q":
            vals = nums(4)
            if len(vals) < 4:
                break
            p0 = (cx, cy)
            if rel:
                p1 = (cx + vals[0], cy + vals[1])
                p2 = (cx + vals[2], cy + vals[3])
            else:
                p1, p2 = (vals[0], vals[1]), (vals[2], vals[3])
            quad(p0, p1, p2)
            prev_ctrl = p1
        elif C == "T":
            vals = nums(2)
            if len(vals) < 2:
                break
            p0 = (cx, cy)
            p1 = (2 * cx - prev_ctrl[0], 2 * cy - prev_ctrl[1]) if prev_ctrl else p0
            p2 = (cx + vals[0], cy + vals[1]) if rel else (vals[0], vals[1])
            quad(p0, p1, p2)
            prev_ctrl = p1
        elif C == "A":
            vals = nums(7)
            if len(vals) < 7:
                break
            x, y = vals[5], vals[6]
            add_pt(cx + x, cy + y) if rel else add_pt(x, y)
            prev_ctrl = None
        elif C == "Z":
            if current:
                add_pt(start_x, start_y)
                subpaths.append(current)
                current = []
            prev_ctrl = None
        else:
            i += 1
        if C not in ("C", "S", "Q", "T"):
            prev_ctrl = None
    if current:
        subpaths.append(current)
    return [sp for sp in subpaths if len(sp) >= 2]


def _extract_svg_markup(svg: str) -> Tuple[str, Optional[Tuple[float, float, float, float]]]:
    """Return ``(markup, viewBox)`` for a file path, inline markup, or raw ``d``."""
    markup = svg
    if isinstance(svg, str) and not svg.lstrip().startswith("<") and os.path.isfile(svg):
        with open(svg, "r", encoding="utf-8") as fh:
            markup = fh.read()
    viewbox = None
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', markup or "")
    if m:
        parts = [float(p) for p in re.split(r"[ ,]+", m.group(1).strip()) if p]
        if len(parts) == 4:
            viewbox = (parts[0], parts[1], parts[2], parts[3])
    return markup, viewbox


def _recolor(image: Image.Image, fill, gradient: Optional[Dict[str, Any]]) -> Image.Image:
    """Recolour an RGBA raster's opaque pixels (preserving its alpha)."""
    if gradient is not None:
        return _apply_gradient(image, gradient)
    rgba = _hex_to_rgba(fill)
    arr = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
    arr[:, :, 0] = rgba[0]
    arr[:, :, 1] = rgba[1]
    arr[:, :, 2] = rgba[2]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def render_svg(svg: str, fill="#FFFFFF", width: Optional[int] = None,
               height: Optional[int] = None,
               gradient: Optional[Dict[str, Any]] = None,
               d: Optional[str] = None) -> Image.Image:
    """Rasterise an SVG file/markup/path-data into an RGBA image.

    Uses ``cairosvg`` when installed (best fidelity, honours gradients and
    strokes), otherwise falls back to a built-in path flattener that
    supports the common ``M/L/H/V/C/S/Q/T/A/Z`` command set.
    """
    markup, viewbox = _extract_svg_markup(svg) if svg else ("", None)
    vb_w = vb_h = 0.0
    if viewbox:
        vb_w, vb_h = viewbox[2], viewbox[3]
    if not vb_w or not vb_h:
        vb_w = float(re.search(r'width\s*=\s*"([\d.]+)', markup).group(1)) \
            if re.search(r'width\s*=\s*"([\d.]+)', markup) else 256.0
        vb_h = float(re.search(r'height\s*=\s*"([\d.]+)', markup).group(1)) \
            if re.search(r'height\s*=\s*"([\d.]+)', markup) else vb_w or 256.0
    out_w = int(width) if width else int(round(vb_w))
    out_h = int(height) if height else int(round(vb_h))

    # Prefer cairosvg when present.
    try:  # pragma: no cover - optional dependency
        import cairosvg  # type: ignore
        if markup and markup.lstrip().startswith("<"):
            png = cairosvg.svg2png(bytestring=markup.encode("utf-8"),
                                   output_width=out_w, output_height=out_h)
            img = Image.open(__import__("io").BytesIO(png)).convert("RGBA")
            return _recolor(img, fill, gradient)
    except Exception:
        pass

    # Fallback: flatten every <path d="..."> (or a raw d string).
    ds: List[str] = []
    if d:
        ds.append(d)
    if markup:
        ds.extend(re.findall(r'\bd\s*=\s*"([^"]+)"', markup))
    if not ds and svg and not os.path.isfile(str(svg)):
        ds.append(str(svg))
    if not ds:
        return Image.new("RGBA", (max(1, out_w), max(1, out_h)), (0, 0, 0, 0))

    all_pts: List[List[Tuple[float, float]]] = []
    for one in ds:
        all_pts.extend(parse_svg_path(one))
    if not all_pts:
        return Image.new("RGBA", (max(1, out_w), max(1, out_h)), (0, 0, 0, 0))

    flat = [p for sp in all_pts for p in sp]
    min_x = min(p[0] for p in flat)
    min_y = min(p[1] for p in flat)
    max_x = max(p[0] for p in flat)
    max_y = max(p[1] for p in flat)
    src_w = max(max_x - min_x, 1e-6)
    src_h = max(max_y - min_y, 1e-6)
    scale = min(out_w / src_w, out_h / src_h)
    off_x = (out_w - src_w * scale) / 2.0 - min_x * scale
    off_y = (out_h - src_h * scale) / 2.0 - min_y * scale

    canvas = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (0, 0, 0, 0))
    mask = Image.new("L", canvas.size, 0)
    md = ImageDraw.Draw(mask)
    for sp in all_pts:
        poly = [(x * scale + off_x, y * scale + off_y) for x, y in sp]
        md.polygon(poly, fill=255)
    if gradient is not None:
        paint = gradient_image(out_w, out_h, gradient)
    else:
        paint = Image.new("RGBA", canvas.size, _hex_to_rgba(fill))
    canvas.paste(paint, (0, 0), mask)
    return canvas


def rasterize_svg_image(svg: str, width: Optional[int] = None,
                        height: Optional[int] = None) -> Image.Image:
    """Rasterise an SVG file/markup to RGBA, preserving its own colours.

    Unlike :func:`render_svg` (which recolours the silhouette for icon
    shapes), this keeps gradients, fills and strokes intact — it is the
    loader behind ``image("icon.svg")`` / ``file("icon.svg")``.

    Backend order: ``cairosvg`` (best fidelity) -> ``rsvg-convert`` /
    ``resvg`` / ``inkscape`` / ImageMagick ``convert`` CLIs (if installed)
    -> built-in path flattener (single-colour fallback with a warning).
    """
    import io as _io
    import shutil as _shutil
    import subprocess as _sp

    markup, viewbox = _extract_svg_markup(svg) if svg else ("", None)
    vb_w = vb_h = 0.0
    if viewbox:
        vb_w, vb_h = viewbox[2], viewbox[3]
    if not vb_w or not vb_h:
        mw = re.search(r'width\s*=\s*"([\d.]+)', markup or "")
        mh = re.search(r'height\s*=\s*"([\d.]+)', markup or "")
        vb_w = float(mw.group(1)) if mw else 256.0
        vb_h = float(mh.group(1)) if mh else vb_w or 256.0
    out_w = int(width) if width else int(round(vb_w))
    out_h = int(height) if height else int(round(vb_h))
    out_w, out_h = max(1, out_w), max(1, out_h)

    if markup and markup.lstrip().startswith("<"):
        # 1. cairosvg: faithful, honours gradients/strokes, no recolour.
        try:
            import cairosvg  # type: ignore
            png = cairosvg.svg2png(bytestring=markup.encode("utf-8"),
                                   output_width=out_w, output_height=out_h)
            return Image.open(_io.BytesIO(png)).convert("RGBA")
        except Exception:
            pass
        # 2. External rasterisers (faithful colours, no extra pip deps).
        src_file = svg if isinstance(svg, str) and os.path.isfile(svg) else None
        data = markup.encode("utf-8")
        cli_variants = []
        if _shutil.which("rsvg-convert"):
            cli_variants.append(["rsvg-convert", "-w", str(out_w),
                                 "-h", str(out_h)])
        if _shutil.which("resvg"):
            cli_variants.append(["resvg", "stdin", "/dev/stdout",
                                 "-w", str(out_w), "-h", str(out_h)])
        if _shutil.which("inkscape"):
            cli_variants.append(["inkscape", "/dev/stdin", "--export-type=png",
                                 "--export-filename=/dev/stdout",
                                 f"--export-width={out_w}",
                                 f"--export-height={out_h}"])
        if _shutil.which("convert"):
            cli_variants.append(["convert", "-background", "none", "svg:-",
                                 f"-resize", f"{out_w}x{out_h}!", "png:-"])
        if _shutil.which("ksvgtopng"):
            # ksvgtopng <in> <out> <w> <h>; needs real files.
            pass
        for cli in cli_variants:
            try:
                if src_file and cli[0] in ("rsvg-convert", "resvg", "inkscape",
                                           "convert"):
                    if cli[0] == "rsvg-convert":
                        proc = _sp.run(["rsvg-convert", "-w", str(out_w),
                                        "-h", str(out_h), "-o", "-",
                                        src_file],
                                       capture_output=True, timeout=30)
                    elif cli[0] == "convert":
                        proc = _sp.run(["convert", "-background", "none",
                                        src_file, "-resize",
                                        f"{out_w}x{out_h}!", "png:-"],
                                       capture_output=True, timeout=30)
                    else:
                        continue
                else:
                    proc = _sp.run(cli, input=data,
                                   capture_output=True, timeout=30)
                if proc.returncode == 0 and proc.stdout:
                    return Image.open(_io.BytesIO(proc.stdout)) \
                        .convert("RGBA")
            except Exception:
                continue
        # 3. ksvgtopng via temp files (last CLI resort).
        if _shutil.which("ksvgtopng"):
            import tempfile as _tf
            try:
                with _tf.TemporaryDirectory() as td:
                    src = src_file
                    if src is None:
                        src = os.path.join(td, "in.svg")
                        with open(src, "w", encoding="utf-8") as fh:
                            fh.write(markup)
                    dst = os.path.join(td, "out.png")
                    proc = _sp.run(["ksvgtopng", src, dst,
                                    str(out_w), str(out_h)],
                                   capture_output=True, timeout=30)
                    if proc.returncode == 0 and os.path.isfile(dst):
                        return Image.open(dst).convert("RGBA")
            except Exception:
                pass

    # Fallback: single-colour path flatten (icons only; gradients lost).
    print("[DSL Warning] No faithful SVG backend found (pip install "
          "'cairosvg' for best fidelity); using flat icon fallback.")
    return render_svg(svg, fill="#FFFFFF", width=out_w, height=out_h)


def draw_path(svg: Optional[str] = None, path: Optional[str] = None,
              fill: str = "#FFFFFF", color: Optional[str] = None,
              width: Optional[int] = None, height: Optional[int] = None,
              gradient: Optional[Dict[str, Any]] = None,
              stroke_color: Optional[str] = None,
              stroke_width: int = 0) -> Image.Image:
    """Render an SVG path/icon (``svg=`` file or ``path=`` data) to RGBA."""
    paint = fill if fill is not None else (color or "#FFFFFF")
    grad = gradient or (parse_gradient(paint) if is_gradient(paint) else None)
    img = render_svg(svg or path or "", fill=(color or paint),
                     width=width, height=height, gradient=grad, d=path)
    if stroke_color and int(stroke_width or 0) > 0:
        # Outline the alpha silhouette for a faux-stroke on the raster.
        from PIL import ImageFilter as _IF
        alpha = img.getchannel("A")
        edge = alpha.filter(_IF.MaxFilter(3))
        edge = Image.fromarray(
            np.clip(np.asarray(edge, np.int16) - np.asarray(alpha, np.int16), 0, 255)
            .astype(np.uint8), "L").filter(_IF.GaussianBlur(int(stroke_width) / 2.0))
        stroke = Image.new("RGBA", img.size, _hex_to_rgba(stroke_color))
        stroke.putalpha(edge)
        img = Image.alpha_composite(stroke, img)
    return img


# ---------------------------------------------------------------------------
# Front door
# ---------------------------------------------------------------------------

def _slug(v) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def generate_shape(shape_type: str, **kwargs) -> Image.Image:
    """Generate a shape from a type specification.

    Supported types: ``rect``, ``circle``, ``polygon``, ``star``, ``path``,
    ``line`` (``x1``/``y1``/``x2``/``y2`` endpoints, ``width`` = thickness).

    Paint options:
        * ``color`` / ``fill``: solid hex colour, or a
          ``gradient(linear|radial, c1, c2[, angle])`` string.
        * ``stroke_color`` / ``stroke_width``: outline.
    """
    kwargs = {k: _slug(v) for k, v in kwargs.items()}
    fill_opt = kwargs.pop("fill", None)
    # `fill` may be a gradient spec, a solid colour, or (for path) a colour.
    gradient = None
    if isinstance(fill_opt, str) and is_gradient(fill_opt):
        gradient = parse_gradient(fill_opt)
    elif fill_opt is not None and not kwargs.get("color"):
        kwargs["color"] = fill_opt

    color = kwargs.get("color") or kwargs.get("colour") or "#FFFFFF"
    if isinstance(color, str) and is_gradient(color):
        gradient = parse_gradient(color)
        color = "#FFFFFF"

    stroke_color = kwargs.get("stroke_color")
    stroke_width = int(float(kwargs.get("stroke_width", 0) or 0))

    if shape_type in ("rect", "rectangle"):
        width = kwargs.get("width")
        height = kwargs.get("height")
        if width is None or height is None:
            raise ValueError("Rectangle requires 'width' and 'height'.")
        return draw_rect(int(width), int(height), color,
                         radius=kwargs.get("radius"), stroke_color=stroke_color,
                         stroke_width=stroke_width, gradient=gradient)

    if shape_type in ("circle", "ellipse"):
        radius = kwargs.get("radius")
        if radius is None:
            # Allow width/height diameter form for ellipses.
            if kwargs.get("width") and kwargs.get("height"):
                radius = int(min(kwargs["width"], kwargs["height"]) / 2)
            else:
                raise ValueError("Circle requires 'radius'.")
        return draw_circle(int(radius), color, stroke_color=stroke_color,
                           stroke_width=stroke_width, gradient=gradient)

    if shape_type == "polygon":
        points = kwargs.get("points", [])
        if not points:
            raise ValueError("Polygon requires 'points' list of (x, y) tuples.")
        return draw_polygon(points, color, stroke_color=stroke_color,
                            stroke_width=stroke_width, gradient=gradient)

    if shape_type in ("line", "segment"):
        # `width` is the stroke thickness here (not a dimension).
        thickness = kwargs.get("width", stroke_width or 1)
        return draw_line(float(kwargs.get("x1", 0)), float(kwargs.get("y1", 0)),
                         float(kwargs.get("x2", kwargs.get("x1", 0))),
                         float(kwargs.get("y2", kwargs.get("y1", 0))),
                         color=color, width=thickness)

    if shape_type == "star":
        radius = kwargs.get("outer_radius", kwargs.get("radius"))
        if radius is None:
            raise ValueError("Star requires 'radius' or 'outer_radius'.")
        return draw_star(
            points=int(kwargs.get("points_count", kwargs.get("points", 5))),
            radius=int(radius),
            inner_radius=kwargs.get("inner_radius"),
            color=color,
            rotation=float(kwargs.get("rotation", -90.0) or -90.0),
            stroke_color=stroke_color, stroke_width=stroke_width,
            gradient=gradient)

    if shape_type in ("path", "svg", "icon"):
        return draw_path(
            svg=kwargs.get("svg"), path=kwargs.get("path") or kwargs.get("d"),
            fill=color, width=kwargs.get("width"), height=kwargs.get("height"),
            gradient=gradient, stroke_color=stroke_color,
            stroke_width=stroke_width)

    raise ValueError(f"Unknown shape type: {shape_type}")
