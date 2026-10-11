# motion_lang/math_engine.py
"""Procedural math for Motion Language: per-frame dynamic expressions.

This module provides the pure-Python side of time-bound animation:

* scalar helpers: trig/inverse-trig, rounding, ``lerp``, ``clamp``,
  ``map_range`` and deterministic value ``noise`` (all importable as DSL
  builtins, e.g. ``sin($t * 2.0)``),
* :class:`DynExpr`: a lazily-evaluated expression tree. When a ``render()``
  property (``pos``, ``scale``, ``opacity``, ...) contains ``$t``/``$frame``,
  the interpreter wraps it in a :class:`DynExpr` instead of evaluating it
  once; the compositor then calls :meth:`DynExpr.eval_at` for every frame.

``$t`` is clip-local time in seconds; ``$frame`` is ``$t * fps``.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional


# ---------------------------------------------------------------------------
# Scalar helpers (also exposed as DSL builtins)
# ---------------------------------------------------------------------------

def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation: ``a + (b - a) * t``."""
    return float(a) + (float(b) - float(a)) * float(t)


def clamp(val: float, lo: float, hi: float) -> float:
    """Limit ``val`` to the inclusive range ``[lo, hi]``."""
    v, low, high = float(val), float(lo), float(hi)
    if low > high:
        low, high = high, low
    return max(low, min(high, v))


def map_range(val: float, in_min: float, in_max: float,
              out_min: float, out_max: float, clamp_out: bool = True) -> float:
    """Remap ``val`` from ``[in_min, in_max]`` to ``[out_min, out_max]``."""
    v = float(val)
    span = float(in_max) - float(in_min)
    t = 0.0 if span == 0 else (v - float(in_min)) / span
    out = float(out_min) + (float(out_max) - float(out_min)) * t
    if clamp_out:
        lo, hi = (float(out_min), float(out_max)) \
            if float(out_min) <= float(out_max) else (float(out_max), float(out_min))
        out = max(lo, min(hi, out))
    return out


def _hash2(ix: int, iy: int, seed: int) -> float:
    """Deterministic pseudo-random in [0, 1) from integer lattice coords."""
    h = (ix * 374761393 + iy * 668265263 + seed * 974634211) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) & 0xFFFFFFFF
    h = (h * 1274126177) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF
    return h / 4294967296.0


def _fade(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def noise(x: float = 0.0, y: float = 0.0, seed: int = 0) -> float:
    """Smooth deterministic 2D value noise in [0, 1].

    Integer-lattice hash + bilinear smoothstep interpolation. Same inputs
    always give the same output, so renders are reproducible; vary ``seed``
    for independent streams.
    """
    fx, fy = float(x), float(y)
    ix, iy = math.floor(fx), math.floor(fy)
    tx, ty = _fade(fx - ix), _fade(fy - iy)
    s = int(seed)
    a = _hash2(ix, iy, s)
    b = _hash2(ix + 1, iy, s)
    c = _hash2(ix, iy + 1, s)
    d = _hash2(ix + 1, iy + 1, s)
    return lerp(lerp(a, b, tx), lerp(c, d, tx), ty)


#: DSL math namespace: name -> callable. ``pi``/``e``/``tau`` are constants
#: handled by the interpreter (see ``TIME_CONSTANTS``).
MATH_FUNCS: Dict[str, Callable[..., float]] = {
    "sin": lambda x: math.sin(float(x)),
    "cos": lambda x: math.cos(float(x)),
    "tan": lambda x: math.tan(float(x)),
    "asin": lambda x: math.asin(float(x)),
    "acos": lambda x: math.acos(float(x)),
    "atan": lambda x: math.atan(float(x)),
    "atan2": lambda y, x: math.atan2(float(y), float(x)),
    "sqrt": lambda x: math.sqrt(float(x)),
    "pow": lambda x, y: math.pow(float(x), float(y)),
    "abs": lambda x: abs(float(x)),
    "floor": lambda x: math.floor(float(x)),
    "ceil": lambda x: math.ceil(float(x)),
    "round": lambda x, n=0: round(float(x), int(n)),
    "min": lambda *a: min(float(v) for v in a),
    "max": lambda *a: max(float(v) for v in a),
    "lerp": lerp,
    "clamp": clamp,
    "map_range": map_range,
    "noise": noise,
}

#: Time variable names recognised by the grammar (``$t``, ``$frame``).
TIME_VARS = frozenset({"$t", "$frame"})

#: Mathematical constants available as bare names in expressions.
TIME_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


# ---------------------------------------------------------------------------
# Lazy per-frame expressions
# ---------------------------------------------------------------------------

class DynExpr:
    """A render() property expression containing ``$t``/``$frame``.

    Holds the raw Lark subtree plus the defining scope; :meth:`eval_at`
    re-evaluates it for a given clip-local time ``t``. The compositor calls
    this once per frame, so ``pos=(960 + cos($t*2)*300, ...)`` genuinely
    animates instead of freezing at ``t=0``.
    """

    def __init__(self, node: Any, evaluator: Any, env: Any,
                 fps: float = 30.0, label: str = "expr"):
        self.node = node
        self.evaluator = evaluator
        self.env = env
        self.fps = float(fps) if fps else 30.0
        self.label = label

    def eval_at(self, t: float) -> Any:
        from motion_lang.lang import Env  # deferred: avoids import cycle
        from lark import Token, Tree  # deferred: keeps math_engine light
        scope = Env(self.env)
        scope.define("$t", float(t))
        scope.define("$frame", float(t) * self.fps)
        node = self.node
        # TimeValue (``$t`` math bound to variables) or a plain resolver.
        if not isinstance(node, (Tree, Token)):
            if hasattr(node, "eval_at"):
                return node.eval_at(t)
            if callable(node):
                return node(t)
        return self.evaluator.eval(node, scope)

    def static_at(self, t: float = 0.0) -> Any:
        """Best-effort plain value (studio export, thumbnails)."""
        try:
            return self.eval_at(t)
        except Exception:
            return None

    def __repr__(self):
        return f"<dynamic {self.label}>"


def tree_has_time(node: Any) -> bool:
    """True if a Lark subtree references ``$t``/``$frame``."""
    from lark import Token, Tree
    if isinstance(node, Token):
        return node.type == "TIME" or str(node) in TIME_VARS
    if isinstance(node, Tree):
        if node.data == "time_var":
            return True
        return any(tree_has_time(c) for c in node.children)
    return False
