# motion_lang/style.py
"""Native CSS styling for Motion Language (.css / .hmsc stylesheets).

Parses standard CSS files (dependency-free) and resolves class/id based
styles into compositor-ready layer properties (layout, colors, FX stacks).

Supported selectors: ``*`` (universal), ``.class``, ``#id`` (comma lists,
compound ``.a.b`` and simple ``tag.class`` / ``tag#id`` forms).

Supported properties (standard + small ``hmsc`` extension set):

Layout / transform
    left, top, x, y, pos-x, pos-y  -> position (px)
    width, height                  -> size (px)
    scale                          -> scale factor
    transform: scale(s)             -> scale factor
    transform: translate(x, y)     -> position (only when left/top absent)

Appearance
    opacity                        -> layer opacity 0..1
    background-color / background  -> shape recolor (shape assets) + text bg
    color                          -> text color
    font-size                      -> text font size (px)
    font-family                    -> text font
    border-radius / radius         -> rounded corners (px, all layers)

Effects (-> compositor ``fx`` stack, in declaration order)
    box-shadow: ox oy blur color   -> drop_shadow fx
    glow: <color> <intensity>      -> glow fx (extension)
    blur: <radius>px               -> blur fx (extension)
    filter: blur() drop-shadow() glow() brightness() contrast()
            saturate()/saturation() grayscale() opacity() -> fx list
    vfx-preset / vfx: <name>       -> vfx_preset fx (extension)

Motion (extension, map onto engine transitions/easing)
    easing / animation-timing-function -> easing name
    transition-in / transition_in      -> e.g. "fade(0.5s)"
    transition-out / transition_out    -> e.g. "slide_right(0.5s)"

Cascade: ``*`` < ``.class`` (in class-attribute order) < ``#id``;
within the same level later rules win; later stylesheets win.
Explicit DSL attributes in ``render()`` always override style values,
while ``fx`` stacks concatenate (style fx first, explicit fx last).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Raw CSS parsing (no third-party dependency)
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_FILTER_FN_RE = re.compile(r"([\w-]+)\s*\(\s*([^)]*)\s*\)")
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{8}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(
    r"rgba?\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
    r"(?:\s*,\s*([0-9.]+))?\s*\)"
)


def _strip_important(value: str) -> str:
    return re.sub(r"\s*!important\s*$", "", value.strip(), flags=re.IGNORECASE)


def _split_declarations(body: str) -> List[str]:
    """Split a declaration block on ';' respecting parens/quotes."""
    parts, depth, quote, cur = [], 0, None, []
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_css_text(css: str) -> List[Dict[str, Any]]:
    """Parse CSS text into an ordered rule list.

    Returns a list of ``{"selectors": [...], "props": {...}, "order": i}``.
    """
    css = _COMMENT_RE.sub("", css)
    rules: List[Dict[str, Any]] = []
    for i, m in enumerate(_BLOCK_RE.finditer(css)):
        selector_raw, body = m.group(1).strip(), m.group(2).strip()
        if not selector_raw or not body:
            continue
        # Skip at-rules (@media, @keyframes, ...) — not applicable to video.
        if selector_raw.startswith("@"):
            continue
        selectors = [s.strip() for s in selector_raw.split(",") if s.strip()]
        props: Dict[str, str] = {}
        for decl in _split_declarations(body):
            if ":" not in decl:
                continue
            name, _, value = decl.partition(":")
            name, value = name.strip().lower(), _strip_important(value)
            if name and value:
                props[name] = value
        if selectors and props:
            rules.append({"selectors": selectors, "props": props, "order": i})
    return rules


def parse_css_file(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Stylesheet not found: '{path}'")
    with open(path, "r", encoding="utf-8") as fh:
        return parse_css_text(fh.read())


def merge_rules(base: List[Dict[str, Any]],
                extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Concatenate rule lists, re-stamping order so later sheets win ties."""
    merged = list(base)
    offset = len(merged)
    for r in extra:
        merged.append({"selectors": list(r["selectors"]),
                       "props": dict(r["props"]),
                       "order": offset + int(r.get("order", 0))})
        offset += 1
    return merged


# ---------------------------------------------------------------------------
# Selector matching / cascade
# ---------------------------------------------------------------------------

def _selector_specificity(selector: str) -> int:
    sel = selector.strip()
    if sel == "*":
        return 0
    spec = 0
    spec += 100 * sel.count("#")
    spec += 10 * sel.count(".")
    return spec


def _selector_matches(selector: str, classes: List[str],
                      element_id: Optional[str]) -> bool:
    sel = selector.strip()
    if not sel:
        return False
    if sel == "*":
        return True
    class_names = re.findall(r"\.([A-Za-z_][\w-]*)", sel)
    id_names = re.findall(r"#([A-Za-z_][\w-]*)", sel)
    # Pure tag selector (e.g. "rect", "text") — no class/id info; ignore.
    if not class_names and not id_names:
        return False
    for c in class_names:
        if c not in classes:
            return False
    for i in id_names:
        if element_id != i:
            return False
    return True


def resolve_raw_props(rules: List[Dict[str, Any]], classes: List[str],
                      element_id: Optional[str]) -> Dict[str, str]:
    """Merge matching declarations honoring specificity then file order."""
    hits: List[Tuple[int, int, Dict[str, str]]] = []
    for r in rules:
        best = -1
        for sel in r["selectors"]:
            if _selector_matches(sel, classes, element_id):
                best = max(best, _selector_specificity(sel))
        if best >= 0:
            hits.append((best, int(r.get("order", 0)), r["props"]))
    hits.sort(key=lambda h: (h[0], h[1]))
    merged: Dict[str, str] = {}
    for _, _, props in hits:
        merged.update(props)
    return merged


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------

def parse_px(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    s = re.sub(r"(px|pt|%)$", "", s).strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_px_int(value: Any) -> Optional[int]:
    v = parse_px(value)
    return None if v is None else int(round(v))


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def parse_opacity(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s.endswith("%"):
        try:
            return max(0.0, min(1.0, float(s[:-1]) / 100.0))
        except ValueError:
            return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v > 1.0:  # e.g. "80" treated as percent
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _rgb_to_hex(r: int, g: int, b: int, a: Optional[float] = None) -> str:
    r, g, b = (max(0, min(255, v)) for v in (r, g, b))
    if a is None:
        return f"#{r:02X}{g:02X}{b:02X}"
    alpha = int(round(max(0.0, min(1.0, a)) * 255))
    return f"#{r:02X}{g:02X}{b:02X}{alpha:02X}"


def normalize_color(value: Any) -> str:
    """Normalise rgb()/rgba() to hex; pass hex/named colors through."""
    s = str(value).strip()
    m = _RGB_RE.match(s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = None
        if m.group(4) is not None:
            try:
                av = float(m.group(4))
                a = av / 255.0 if av > 1.0 else av
                if a >= 1.0:
                    a = None
            except ValueError:
                a = None
        return _rgb_to_hex(r, g, b, a)
    # Bare `background: #hex ...` shorthand — keep the color token.
    if s.startswith("#"):
        tok = s.split()[0]
        if _HEX_RE.match(tok):
            if len(tok) == 4:  # #rgb -> #rrggbb
                tok = "#" + "".join(c * 2 for c in tok[1:])
            return tok.upper() if len(tok) in (7, 9) else tok
    return s


def _split_ws_tokens(value: str) -> List[str]:
    """Split on whitespace respecting parens (for rgba() colors)."""
    toks, depth, cur = [], 0, []
    for ch in value.strip():
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch.isspace() and depth == 0:
            if cur:
                toks.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        toks.append("".join(cur))
    return toks


def _looks_like_color(tok: str) -> bool:
    t = tok.strip().lower()
    return bool(_HEX_RE.search(t) or _RGB_RE.match(t)
                or re.match(r"^[a-z]+$", t))


def parse_box_shadow(value: str) -> Optional[Dict[str, Any]]:
    """Parse ``box-shadow: ox oy blur [spread] color`` (px, CSS order)."""
    toks = [t for t in _split_ws_tokens(value) if t.lower() not in ("inset",)]
    if len(toks) < 2:
        return None
    color = "#00000088"
    nums: List[str] = []
    for t in toks:
        if _looks_like_color(t) and not re.match(r"^-?[\d.]+", t):
            color = normalize_color(t)
        else:
            nums.append(t)
    # A trailing/leading hex token may have been misclassified above only if
    # numeric-looking; re-check: last token non-numeric -> color.
    if nums and not re.match(r"^-?[\d.]+", nums[-1]):
        color = normalize_color(nums.pop())
    if len(nums) < 2:
        return None
    try:
        ox = int(round(float(nums[0].lower().rstrip("px"))))
        oy = int(round(float(nums[1].lower().rstrip("px"))))
        blur = int(round(float(nums[2].lower().rstrip("px")))) if len(nums) > 2 else 10
    except ValueError:
        return None
    return {"offset_x": ox, "offset_y": oy, "blur": max(0, blur),
            "color": color}


def parse_glow_shorthand(value: str) -> Optional[Dict[str, Any]]:
    toks = _split_ws_tokens(value)
    if not toks:
        return None
    color, intensity = "#FFFFFF", 1.0
    if _looks_like_color(toks[0]):
        color = normalize_color(toks[0])
        if len(toks) > 1:
            intensity = parse_float(toks[1]) or 1.0
    else:
        intensity = parse_float(toks[0]) or 1.0
        if len(toks) > 1 and _looks_like_color(toks[1]):
            color = normalize_color(toks[1])
    return {"color": color, "intensity": float(intensity)}


def _filter_len_px(token: str) -> int:
    return int(round(parse_px(token) or 0.0))


def _filter_factor(token: str, base: float = 1.0) -> float:
    """brightness/contrast/saturate: 120% / 1.2 -> delta vs base (for fx)."""
    t = token.strip()
    try:
        if t.endswith("%"):
            return float(t[:-1]) / 100.0 - base
        return float(t) - base
    except ValueError:
        return 0.0


def parse_filter(value: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Parse a CSS ``filter:`` chain into compositor fx tuples."""
    fx: List[Tuple[str, Dict[str, Any]]] = []
    bright = contr = sat = 0.0
    touched = False
    for m in _FILTER_FN_RE.finditer(value):
        name, arg = m.group(1).lower().replace("-", "_"), m.group(2).strip()
        if name == "blur":
            fx.append(("blur", {"radius": _filter_len_px(arg)}))
        elif name in ("drop_shadow", "drop-shadow", "dropshadow"):
            sh = parse_box_shadow(arg.replace(",", " "))
            if sh:
                fx.append(("drop_shadow", sh))
        elif name == "glow":
            g = parse_glow_shorthand(arg.replace(",", " "))
            if g:
                fx.append(("glow", g))
        elif name == "opacity":
            a = parse_opacity(arg)
            if a is not None:
                fx.append(("opacity", {"alpha": a}))
        elif name == "brightness":
            bright += _filter_factor(arg); touched = True
        elif name == "contrast":
            contr += _filter_factor(arg); touched = True
        elif name in ("saturate", "saturation"):
            sat += _filter_factor(arg); touched = True
        elif name == "grayscale":
            try:
                g = float(arg.rstrip("%")) / (100.0 if "%" in arg else 1.0)
                sat += -max(0.0, min(1.0, g)); touched = True
            except ValueError:
                pass
    if touched:
        fx.append(("adjust_color", {"brightness": bright, "contrast": contr,
                                   "saturation": sat}))
    return fx


def parse_transform(value: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for m in _FILTER_FN_RE.finditer(value):
        name, arg = m.group(1).lower(), m.group(2).strip()
        if name == "scale":
            try:
                out["scale"] = float(arg.split(",")[0])
            except ValueError:
                pass
        elif name in ("translate", "translate3d"):
            nums = [parse_px(t) for t in re.split(r"[, ]+", arg) if t]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2:
                out["pos"] = (int(nums[0]), int(nums[1]))
        elif name == "translatex":
            v = parse_px(arg)
            if v is not None:
                out.setdefault("pos_x", int(v))
        elif name == "translatey":
            v = parse_px(arg)
            if v is not None:
                out.setdefault("pos_y", int(v))
    return out


# ---------------------------------------------------------------------------
# Props -> engine kwargs
# ---------------------------------------------------------------------------

def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def style_props_to_engine(props: Dict[str, str]) -> Dict[str, Any]:
    """Normalise merged CSS declarations to compositor kwargs.

    Keys: pos, size, scale, opacity, easing, transition_in/out, fx,
    text{color,font,font_size}, shape{color,radius}, background_color,
    border_radius.
    """
    eng: Dict[str, Any] = {"fx": [], "text": {}, "shape": {}}
    pos_x = pos_y = None
    size_w = size_h = None

    for raw_name, raw_val in props.items():
        name = raw_name.strip().lower().replace("_", "-")
        val = raw_val.strip()
        if name in ("left", "x", "pos-x"):
            pos_x = parse_px_int(val)
        elif name in ("top", "y", "pos-y"):
            pos_y = parse_px_int(val)
        elif name == "width":
            size_w = parse_px_int(val)
        elif name == "height":
            size_h = parse_px_int(val)
        elif name == "size":
            toks = _split_ws_tokens(val)
            if len(toks) >= 2:
                size_w = parse_px_int(toks[0]) or size_w
                size_h = parse_px_int(toks[1]) or size_h
        elif name == "scale":
            f = parse_float(val)
            if f is not None:
                eng["scale"] = f
        elif name == "opacity":
            o = parse_opacity(val)
            if o is not None:
                eng["opacity"] = o
        elif name in ("easing", "animation-timing-function"):
            eng["easing"] = _unquote(val)
        elif name in ("transition-in", "transitionin"):
            eng["transition_in"] = _unquote(val)
        elif name in ("transition-out", "transitionout"):
            eng["transition_out"] = _unquote(val)
        elif name == "color":
            eng["text"]["color"] = normalize_color(val)
        elif name == "font-size":
            fs = parse_px_int(val)
            if fs is not None:
                eng["text"]["font_size"] = fs
        elif name == "font-family":
            eng["text"]["font"] = _unquote(val).split(",")[0].strip()
        elif name in ("background-color", "background"):
            col = normalize_color(val.split()[0])
            eng["background_color"] = col
            eng["shape"]["color"] = col
        elif name in ("border-radius", "borderradius", "radius"):
            r = parse_px_int(val.split()[0])
            if r is not None:
                eng["border_radius"] = r
                eng["shape"]["radius"] = r
        elif name == "box-shadow":
            sh = parse_box_shadow(val)
            if sh:
                eng["fx"].append(("drop_shadow", sh))
        elif name == "glow":
            g = parse_glow_shorthand(val)
            if g:
                eng["fx"].append(("glow", g))
        elif name in ("blur", "blur-radius"):
            eng["fx"].append(("blur", {"radius": _filter_len_px(val)}))
        elif name == "filter":
            eng["fx"].extend(parse_filter(val))
        elif name in ("vfx-preset", "vfx"):
            eng["fx"].append(("vfx_preset",
                              {"preset_name": _unquote(val)}))
        elif name == "transform":
            t = parse_transform(val)
            if "scale" in t and "scale" not in eng:
                eng["scale"] = t["scale"]
            if "pos" in t and pos_x is None and pos_y is None:
                pos_x, pos_y = t["pos"][0], t["pos"][1]
            if "pos_x" in t and pos_x is None:
                pos_x = t["pos_x"]
            if "pos_y" in t and pos_y is None:
                pos_y = t["pos_y"]
        # Unknown properties are ignored (forward-compatible).

    if pos_x is not None or pos_y is not None:
        eng["pos"] = (pos_x or 0, pos_y or 0)
    else:
        eng.pop("pos", None)
    if size_w is not None or size_h is not None:
        eng["size"] = (size_w, size_h)
    if not eng["text"]:
        eng.pop("text")
    if not eng["shape"]:
        eng.pop("shape")
    # Drop partial Nones from size (engine needs concrete pairs).
    if "size" in eng and (eng["size"][0] is None or eng["size"][1] is None):
        eng.pop("size")
    eng.pop("pos", None) if eng.get("pos") is None else None
    return eng


def resolve_style(rules: List[Dict[str, Any]],
                  css_class: Optional[str] = None,
                  css_id: Optional[str] = None) -> Dict[str, Any]:
    """Resolve ``class``/``id`` (space-separated classes) to engine kwargs."""
    classes = [c for c in (css_class or "").split() if c]
    raw = resolve_raw_props(rules, classes, css_id or None)
    if not raw:
        return {"fx": []}
    eng = style_props_to_engine(raw)
    eng.setdefault("fx", [])
    return eng


def split_class_attr(value: Optional[str]) -> List[str]:
    return [c for c in (value or "").split() if c]


# ---------------------------------------------------------------------------
# PIL helpers: recolor shapes + rounded corners
# ---------------------------------------------------------------------------

def recolor_image(image, color: str):
    """Refill RGB channels with ``color``, preserving the alpha mask."""
    from PIL import Image as _Image
    rgba = image.convert("RGBA")
    r, g, b, _a = _hex_to_rgba(color)
    solid = _Image.new("RGBA", rgba.size, (r, g, b, 255))
    solid.putalpha(rgba.getchannel("A"))
    return solid


def _hex_to_rgba(hex_color: str) -> Tuple[int, int, int, int]:
    s = str(hex_color).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16),
                int(s[6:8], 16))
    # Named color fallback — resolve via a small table, else white.
    named = {"black": (0, 0, 0, 255), "white": (255, 255, 255, 255),
             "red": (255, 0, 0, 255), "green": (0, 128, 0, 255),
             "blue": (0, 0, 255, 255), "transparent": (0, 0, 0, 0)}
    return named.get(str(hex_color).strip().lower(), (255, 255, 255, 255))


def round_corners(image, radius: int):
    """Apply a rounded-rectangle alpha mask (radius in px)."""
    from PIL import Image as _Image, ImageDraw as _Draw
    radius = max(0, int(radius))
    if radius <= 0:
        return image
    rgba = image.convert("RGBA")
    w, h = rgba.size
    radius = min(radius, w // 2, h // 2)
    mask = _Image.new("L", (w, h), 0)
    d = _Draw.Draw(mask)
    d.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    out = _Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(rgba, (0, 0), mask)
    return out


def apply_shape_style(image, resolved: Dict[str, Any],
                      allow_recolor: bool = False):
    """Apply CSS box decorations to a layer image.

    ``border-radius`` rounds any layer; ``background-color`` recolors only
    shape-generated assets (``allow_recolor``) so photos are never tinted.
    """
    out = image
    bg = resolved.get("background_color") or (resolved.get("shape") or {}).get("color")
    if allow_recolor and bg:
        try:
            out = recolor_image(out, bg)
        except Exception:
            pass
    radius = resolved.get("border_radius")
    if radius is None and isinstance(resolved.get("shape"), dict):
        radius = resolved["shape"].get("radius")
    if radius:
        try:
            out = round_corners(out, int(radius))
        except Exception:
            pass
    return out
