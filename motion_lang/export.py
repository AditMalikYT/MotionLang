# motion_lang/export.py
"""Export an evaluated modern-language timeline to ``composition.json``.

The JSON is consumed by the Remotion studio (``studio/``) for real-time
editing/preview in the browser. Image layers are embedded as data URIs
(downscaled for preview); video/audio files are copied into the studio's
``public/media`` folder when small enough.
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
from typing import Any, Dict, List

from motion_lang.lang import Evaluator, RenderSpec


def _pil_to_data_uri(image, max_dim: int = 720) -> str:
    from PIL import Image
    img = image.convert("RGBA")
    w, h = img.size
    scale = min(1.0, float(max_dim) / max(w, h, 1))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _blend_mode(fx) -> str:
    mode = "normal"
    for item in fx or []:
        if item and item[0] == "blend_mode":
            params = item[1] if len(item) > 1 else {}
            mode = str(params.get("mode", "normal"))
    return mode


def _static(value, t: float = 0.0):
    """Studio-export fallback: evaluate a DynExpr at ``t`` (start pose)."""
    if hasattr(value, "eval_at"):
        try:
            return value.static_at(t)
        except Exception:
            return None
    return value


def _pair(value, t: float = 0.0):
    value = _static(value, t)
    if value is None:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except Exception:
        return None


def _layer_dict(idx: int, z: int, spec: RenderSpec, out_dir: str) -> Dict[str, Any]:
    asset = spec.asset
    start = float(spec.start)
    layer: Dict[str, Any] = {
        "id": f"L{idx}",
        "z": int(z),
        "kind": asset.kind if asset else "image",
        "start": start,
        "end": float(spec.end),
        "pos": _pair(spec.pos, start) or [0, 0],
        "posEnd": _pair(spec.pos_end, start),
        "scale": _static(spec.scale, start),
        "scaleEnd": _static(spec.scale_end, start),
        "opacity": _static(spec.opacity, start) if spec.opacity is not None else 1.0,
        "opacityEnd": _static(spec.opacity_end, start),
        "rotation": _static(spec.rotation, start) if spec.rotation is not None else 0.0,
        "rotationEnd": _static(spec.rotation_end, start),
        "rotationX": _static(spec.rotation_x, start) if spec.rotation_x is not None else 0.0,
        "rotationXEnd": _static(spec.rotation_x_end, start),
        "rotationY": _static(spec.rotation_y, start) if spec.rotation_y is not None else 0.0,
        "rotationYEnd": _static(spec.rotation_y_end, start),
        "perspective": spec.perspective if spec.perspective is not None else 3.0,
        "easing": spec.easing or "linear",
        "transitionIn": spec.transition_in,
        "transitionOut": spec.transition_out,
        "fx": [[name, params] for name, params in (spec.fx or [])],
        "blendMode": _blend_mode(spec.fx),
        "cssClass": spec.css_class,
        "cssId": spec.css_id,
    }
    if asset is None:
        return layer
    if asset.kind == "text":
        data = dict(asset.data)
        layer["text"] = data.pop("text", "")
        style = {
            "font": data.get("font", "default"),
            "color": data.get("color", "#FFFFFF"),
            "fontSize": data.get("font_size", 48),
            "strokeColor": data.get("stroke_fill", "#000000"),
            "strokeWidth": data.get("stroke_width", 0),
            "letterSpacing": data.get("letter_spacing", 0),
            "background": data.get("bg_color"),
        }
        layer["style"] = style
    elif asset.kind == "image" and asset.data is not None:
        w, h = asset.data.size
        layer["width"], layer["height"] = w, h
        layer["src"] = _pil_to_data_uri(asset.data)
        layer["isShape"] = bool(asset.is_shape)
    elif asset.kind == "video":
        path = getattr(asset, "path", asset.data)
        layer["fileName"] = os.path.basename(str(path))
        layer["src"] = _copy_media(str(path), out_dir)
    return layer


def _copy_media(path: str, out_dir: str) -> str:
    """Copy a media file into ``<out_dir>/media`` and return a URL path."""
    if not path or not os.path.isfile(path):
        return path
    try:
        size = os.path.getsize(path)
    except OSError:
        return path
    if size > 30 * 1024 * 1024:
        return path
    media_dir = os.path.join(out_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    name = os.path.basename(path)
    dest = os.path.join(media_dir, name)
    try:
        if not os.path.exists(dest) or os.path.getsize(dest) != size:
            shutil.copy2(path, dest)
        return f"media/{name}"
    except OSError:
        return path


def build_composition(evaluator: Evaluator, title: str = "composition",
                      out_dir: str = ".") -> Dict[str, Any]:
    """Build the JSON-serialisable composition dict (no file write)."""
    layers: List[Dict[str, Any]] = []
    max_end = 1.0
    for i, (z, spec) in enumerate(evaluator.renders):
        layers.append(_layer_dict(i, z, spec, out_dir))
        max_end = max(max_end, float(spec.end))
    audio = []
    for a in evaluator.audio_specs:
        audio.append({
            "src": _copy_media(a["path"], out_dir),
            "start": float(a["start"]),
            "volume": float(a.get("volume", 1.0)),
        })
        max_end = max(max_end, float(a["start"]) + 1.0)
    layers.sort(key=lambda l: l["z"])
    return {
        "meta": {
            "title": os.path.basename(title) if title.endswith(".hmg") else title,
            "width": int(evaluator.config["width"]),
            "height": int(evaluator.config["height"]),
            "fps": int(evaluator.config["fps"]),
            "duration": round(max_end, 3),
        },
        "layers": layers,
        "audio": audio,
    }


def export_composition(evaluator: Evaluator, out_path: str,
                       title: str = "composition") -> str:
    """Write the evaluator's recorded timeline to ``out_path`` as JSON."""
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    comp = build_composition(evaluator, title, os.path.dirname(out_path))
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(comp, fh, indent=2)
    print(f"[Studio] Exported composition -> {out_path} "
          f"({len(comp['layers'])} layer(s))")
    return out_path
