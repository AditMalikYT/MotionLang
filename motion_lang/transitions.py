# motion_lang/transitions.py
"""Scene/layer transition pipeline for Motion Language.

Transitions blend two overlapping layers across a shared time window. Two
integration styles are supported, both funnelling into the same spec:

* **Statement form** (modern DSL)::
      transition(from=layer_a, to=layer_b, type="crossfade", duration=0.5)
  ``render()`` returns its spec, so layer variables can be wired directly.
  The statement stamps ``transition_out`` on the *from* spec and
  ``transition_in`` on the *to* spec.
* **Inline form** (both dialects): ``transition_in="wipe_left(0.5)"`` /
  ``transition_out="crossfade(0.8)"`` render options.

Supported ``type`` values (``duration`` in seconds, ``direction`` where
noted)::

    crossfade / dissolve   opacity blend across the overlap
    fade                    alias of crossfade
    wipe                    hard-edge reveal (left/right/up/down)
    slide                   position travel (left/right/up/down)
    zoom_in / zoom_out       scale ramp at the transition head
    glitch                  seeded RGB-split burst decaying over duration

Entrance transitions render over the first ``duration`` seconds of the *to*
clip; exit transitions over the last ``duration`` seconds of the *from* clip.
For a true blend, overlap the two layers' ``time=`` windows by ``duration``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_TRANS_RE = re.compile(r"^([a-z_]+)\s*(?:\(\s*([0-9.]+)\s*s?\s*\))?\s*$")

#: Canonical transition names (after alias normalisation).
KINDS = frozenset({
    "crossfade", "dissolve", "fade",
    "wipe_left", "wipe_right", "wipe_up", "wipe_down",
    "slide_left", "slide_right", "slide_up", "slide_down",
    "zoom_in", "zoom_out", "glitch",
})

_ALIASES = {
    "fade": "crossfade",
    "fadein": "crossfade",
    "fade_in": "crossfade",
    "fadeout": "crossfade",
    "fade_out": "crossfade",
    "dissolve": "dissolve",
    "wipe": "wipe_left",
    "wipeleft": "wipe_left",
    "wiperight": "wipe_right",
    "wipeup": "wipe_up",
    "wipedown": "wipe_down",
    "slide": "slide_right",
    "slideleft": "slide_left",
    "slideright": "slide_right",
    "slideup": "slide_up",
    "slidedown": "slide_down",
    "zoomin": "zoom_in",
    "zoomout": "zoom_out",
    "xfade": "crossfade",
    "cross_dissolve": "dissolve",
}

_DIRECTIONS = ("left", "right", "up", "down")


def _coerce_spec_value(value: str):
    s = value.strip().strip('"').strip("'")
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def parse_transition_spec(spec) -> Tuple[Optional[str], float, Dict[str, Any]]:
    """Parse ``"wipe_left(0.5)"`` -> ``("wipe_left", 0.5, {})``.

    Also accepts keyword form ``"wipe(direction=\\"left\\", duration=0.5)"``
    (a bare ``duration=`` sets the duration; other keys land in params).
    Returns ``(None, 0.0, {})`` for empty/unknown specs (with a warning for
    non-empty unknowns).
    """
    if spec is None:
        return None, 0.0, {}
    if isinstance(spec, (int, float)):
        return None, 0.0, {}
    s = str(spec).strip().lower().strip('"').strip("'")
    m = _TRANS_RE.match(s)
    if not m:
        # Fall back to a kwarg-tolerant parse for direction= forms.
        m2 = re.match(r"^([a-z_]+)\s*\(([^)]*)\)\s*$", s)
        if not m2:
            print(f"[Transitions] Unrecognised transition '{spec}'.")
            return None, 0.0, {}
        name = _ALIASES.get(m2.group(1), m2.group(1))
        dur, params = 0.5, {}
        for part in [p.strip() for p in m2.group(2).split(",") if p.strip()]:
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip()] = _coerce_spec_value(v)
            elif not params:
                try:
                    dur = float(part.rstrip("s"))
                except ValueError:
                    pass
        if "duration" in params:
            try:
                dur = float(str(params.pop("duration")).rstrip("s"))
            except ValueError:
                pass
        if "direction" in params and name in ("wipe", "slide"):
            name = f"{name}_{normalise_direction(params['direction'])}"
        if name not in KINDS:
            print(f"[Transitions] Unsupported transition '{spec}'.")
            return None, 0.0, {}
        return name, max(0.0, float(dur)), params
    name = _ALIASES.get(m.group(1), m.group(1))
    try:
        dur = float(m.group(2)) if m.group(2) else 0.5
    except ValueError:
        dur = 0.5
    if name not in KINDS:
        print(f"[Transitions] Unsupported transition '{spec}'.")
        return None, 0.0, {}
    return name, max(0.0, dur), {}


def normalise_direction(direction: Optional[str], default: str = "left") -> str:
    """Coerce a direction string; falls back to ``default`` with a warning."""
    d = str(direction or default).strip().lower()
    if d not in _DIRECTIONS:
        print(f"[Transitions] Unknown direction '{direction}', using '{default}'.")
        return default
    return d


def is_wipe(kind: Optional[str]) -> bool:
    return (kind or "").startswith("wipe_")


def is_slide(kind: Optional[str]) -> bool:
    return (kind or "").startswith("slide_")


def is_zoom(kind: Optional[str]) -> bool:
    return kind in ("zoom_in", "zoom_out")


def is_blend(kind: Optional[str]) -> bool:
    return kind in ("crossfade", "dissolve", "fade")


def is_glitch(kind: Optional[str]) -> bool:
    return kind == "glitch"


def transition_statement(from_spec: Any, to_spec: Any, type: str = "crossfade",
                         duration: float = 0.5, **params) -> Dict[str, Any]:
    """Apply a ``transition(...)`` statement to two render specs.

    Stamps ``transition_out`` on the *from* spec and ``transition_in`` on the
    *to* spec, then returns a summary record. Both specs must come from
    ``render()`` calls (anything with settable transition attributes works).
    """
    kind, dur, _ = parse_transition_spec(
        f"{type}({duration})" if duration is not None else type)
    if kind is None:
        raise ValueError(f"Unknown transition type '{type}'.")
    out_spec = f"{kind}({dur})"
    in_spec = f"{kind}({dur})"
    # A wipe/slide *into* the new layer should travel the same direction;
    # exits mirror it so the pair reads as one motion.
    try:
        from_spec.transition_out = out_spec
    except AttributeError:
        raise ValueError("transition() 'from' must be a render() layer.")
    try:
        to_spec.transition_in = in_spec
    except AttributeError:
        raise ValueError("transition() 'to' must be a render() layer.")
    record = {"from": from_spec, "to": to_spec, "type": kind,
              "duration": dur, "params": dict(params)}
    for key in ("direction", "intensity", "seed"):
        if key in params:
            record[key] = params[key]
    return record
