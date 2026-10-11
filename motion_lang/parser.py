# motion_lang/parser.py
"""Lark grammar + AST interpreter with keyframes, transitions, text, diagnostics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from lark import Lark, Token, Transformer, UnexpectedInput
from lark.exceptions import VisitError

from motion_lang.fetcher import (
    get_local_transparent_image,
    get_web_transparent_image,
    prefetch_web_images,
)
from motion_lang.engine import Compositor
from motion_lang.shapes import generate_shape
from motion_lang.vfx import apply_fx_stack
from motion_lang import style as _css

dsl_grammar = r"""
    start: style_import* init_block style_import* asset_decl* scene_block audio_block?

    style_import: "import" "style" ESCAPED_STRING

    init_block: "init" "{" init_prop* "}"
    init_prop: "resolution" ":" SINT "x" SINT  -> init_res
             | "fps" ":" SINT                  -> init_fps
             | "mode" ":" IDENTIFIER           -> init_mode

    asset_decl: "asset" IDENTIFIER "=" asset_source
    ?asset_source: shape_source | web_source | file_source | video_source | audio_source | text_source
    shape_source: "shape" "(" shape_name shape_arg* ")"
    ?shape_name: ESCAPED_STRING | IDENTIFIER
    shape_arg: "," IDENTIFIER "=" shape_val
    ?shape_val: SIGNED_NUMBER | ESCAPED_STRING | point_list
    point_list: "[" point ("," point)* "]"
    point: "(" SINT "," SINT ")"

    web_source: ("web" | "wiki") "(" ESCAPED_STRING ")"
    file_source: "file" "(" ESCAPED_STRING ")"
    video_source: "video" "(" ESCAPED_STRING ")"
    audio_source: "audio" "(" ESCAPED_STRING ")"
    text_source: "text" "(" ESCAPED_STRING text_opt* ")"
    text_opt: "," IDENTIFIER "=" text_opt_value
    text_opt_value: ESCAPED_STRING | SIGNED_NUMBER | IDENTIFIER

    scene_block: "scene" "{" layer* "}"
    layer: "layer" "(" "z" "=" SINT ")" "{" render_stmt* "}"
    render_stmt: "render" "(" IDENTIFIER "," "time" "=" "[" SIGNED_NUMBER "," SIGNED_NUMBER "]" ("," "pos" "=" "(" SINT "," SINT ")")? pos_anim? render_opt* ")"
    pos_anim: ARROW "(" SINT "," SINT ")"
    ?render_opt: opt_scale | opt_size | opt_easing | opt_trans_in | opt_trans_out | opt_opacity | opt_fx | opt_class | opt_id
    opt_class: "," "class" "=" ESCAPED_STRING
    opt_id: "," "id" "=" ESCAPED_STRING
    opt_scale: "," "scale" "=" SIGNED_NUMBER scale_anim?
    opt_size: "," "size" "=" "(" SINT "," SINT ")"
    opt_easing: "," "easing" "=" ESCAPED_STRING
    opt_trans_in: "," "transition_in" "=" ESCAPED_STRING
    opt_trans_out: "," "transition_out" "=" ESCAPED_STRING
    opt_opacity: "," "opacity" "=" SIGNED_NUMBER opacity_anim?
    opt_fx: "," "fx" "=" "[" [fx_call ("," fx_call)*] "]"
    scale_anim: ARROW SIGNED_NUMBER
    opacity_anim: ARROW SIGNED_NUMBER
    // AE-style effect stack: any ``name(arg=value, ...)`` or ``name("value")``.
    fx_call: IDENTIFIER "(" [fx_arg ("," fx_arg)*] ")"
    ?fx_arg: fx_named | fx_val
    fx_named: IDENTIFIER "=" fx_val
    ?fx_val: ESCAPED_STRING | SIGNED_NUMBER | IDENTIFIER

    audio_block: "audio_scene" "{" play_stmt* "}"
    play_stmt: "play" "(" IDENTIFIER "," "start" "=" SIGNED_NUMBER ("," "volume" "=" SIGNED_NUMBER)? ")"

    ARROW: "->"
    IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_]*/
    SINT: /-?\d+/
    %import common.SIGNED_NUMBER
    %import common.ESCAPED_STRING
    %import common.WS
    %import common.CPP_COMMENT
    %ignore WS
    %ignore CPP_COMMENT
"""


class MotionSyntaxError(Exception):
    pass


def _format_lark_error(exc: UnexpectedInput, source: str) -> str:
    line = getattr(exc, "line", None) or 1
    col = getattr(exc, "column", None) or 1
    ctx = ""
    try:
        ctx = exc.get_context(source, span=60)
    except Exception:
        lines = source.splitlines()
        if 1 <= line <= len(lines):
            ctx = lines[line - 1]
    hint = ""
    expected = getattr(exc, "expected", None) or getattr(exc, "accepts", None)
    if expected:
        try:
            names = sorted(str(x) for x in expected)[:8]
            hint = "\nHint: expected one of: " + ", ".join(names)
        except Exception:
            hint = ""
    found = ""
    tok = getattr(exc, "token", None)
    if tok is not None:
        found = f"\nFound token: {tok!r}"
    return (f"[DSL Syntax Error] line {line}, column {col}\n{ctx}{found}{hint}\n"
            "Check commas, brackets, quoted strings and option names "
            "(scale/size/easing/transition_in/transition_out/opacity/fx/class/id, "
            "pos=(x, y) -> (x2, y2), scale=a -> b, import style \"...\").\n"
            "fx entries look like glow(color=\"#00E5FF\", radius=20, "
            "intensity=1.5), glitch(intensity=0.3, seed=1), "
            "motion_blur(samples=8, direction=0), blend_mode(\"screen\"), "
            "reflection(opacity=0.5, blur=5), flash_in(duration=0.2), "
            "light_sweep(angle=45, speed=1.0), pulse(amount=0.1, speed=2.0) "
            "or float_y(distance=20, speed=1.0).")


def _num(tok) -> float | int:
    s = str(tok)
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return 0


def _unquote(s: str) -> str:
    """Unquote an ESCAPED_STRING literal (with escape handling)."""
    try:
        import ast as _ast
        return _ast.literal_eval(s)
    except Exception:
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1]
        return s


def _norm_str(tok) -> str:
    """Strip quotes from ESCAPED_STRING tokens, pass IDENTIFIERs through."""
    s = str(tok)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return _unquote(s)
        except Exception:
            return s[1:-1]
    return s


def _coerce_fx_value(val) -> Any:
    """Normalise an fx argument value to str/int/float.

    Lark terminal callbacks usually hand us already-converted Python values;
    this keeps the regex/fallback and raw-token paths consistent.
    """
    if isinstance(val, Token):
        t = val.type
        if t == "ESCAPED_STRING":
            return _unquote(str(val))
        if t == "SINT":
            return int(str(val))
        if t == "SIGNED_NUMBER":
            return _num(str(val))
        return str(val)
    if isinstance(val, str):
        s = val.strip()
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            return val
    return val


# text(...) option aliases -> canonical keys consumed by the compositor.
_TEXT_OPT_ALIASES = {
    "size": "font_size",
    "stroke_color": "stroke_fill",
    "outline_color": "stroke_fill",
    "outline_width": "stroke_width",
    "stroke": "stroke_width",
    "spacing": "letter_spacing",
    "tracking": "letter_spacing",
    "style": "font",
    "fill": "color",
}


def _normalize_text_opts(opts: Dict[str, Any]) -> Dict[str, Any]:
    """Map ``text(...)`` option aliases to canonical engine keys."""
    out: Dict[str, Any] = {}
    for k, v in opts.items():
        out[_TEXT_OPT_ALIASES.get(k, k)] = v
    for key in ("font_size", "stroke_width", "letter_spacing"):
        if key in out and out[key] is not None:
            try:
                out[key] = int(float(out[key]))
            except (TypeError, ValueError):
                out.pop(key, None)
    return out


def _text_layer_kwargs(adata: Dict[str, Any]):
    """Split a text asset payload into ``(string, compositor kwargs)``."""
    d = dict(adata or {})
    txt = str(d.pop("text", ""))

    def _as_int(value, default):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    kwargs = {
        "font": str(d.pop("font", "default") or "default"),
        "color": str(d.pop("color", "#FFFFFF") or "#FFFFFF"),
        "font_size": _as_int(d.pop("font_size", 48), 48),
        "stroke_width": _as_int(d.pop("stroke_width", 0), 0),
        "stroke_fill": str(d.pop("stroke_fill", "#000000") or "#000000"),
        "letter_spacing": _as_int(d.pop("letter_spacing", 0), 0),
        "bg_color": d.pop("bg_color", None),
    }
    return txt, kwargs


class MotionInterpreter(Transformer):
    def __init__(self, base_dir: str = "."):
        super().__init__()
        self.assets: Dict[str, Tuple[str, Any]] = {}
        self.asset_origins: Dict[str, str] = {}  # asset_name -> "shape"|...
        self.pending_web: Dict[str, str] = {}   # asset_name -> query
        self.pending_local: Dict[str, str] = {}  # asset_name -> path
        self.compositor: Optional[Compositor] = None
        self.parsed_init: Optional[Tuple[int, int, int, str]] = None
        self.parsed_layers: List[Tuple[int, List[Dict[str, Any]]]] = []
        self.parsed_audio: List[Tuple[str, float, float]] = []
        self.base_dir: str = base_dir or "."
        self.style_rules: List[Dict[str, Any]] = []
        self.stylesheets: List[str] = []

    # -- terminals --------------------------------------------------------
    def SINT(self, tok):
        return int(tok.value)

    def NUMBER(self, tok):
        return float(tok.value)

    def SIGNED_NUMBER(self, tok):
        return float(tok.value)

    def ESCAPED_STRING(self, tok):
        s = tok.value
        try:
            import ast as _ast
            return _ast.literal_eval(s)
        except Exception:
            return s.strip('"')

    def IDENTIFIER(self, tok):
        return str(tok.value)

    # -- asset sources (deferred: record first, resolve concurrently later) -
    def web_source(self, args):
        return ("web", args[0])

    def file_source(self, args):
        return ("file", args[0])

    def video_source(self, args):
        return ("video", args[0])

    def audio_source(self, args):
        return ("audio", args[0])

    def shape_source(self, args):
        shape_type = args[0] if args else "rect"
        merged = {}
        for a in args[1:]:
            if isinstance(a, tuple) and len(a) == 2:
                merged[a[0]] = a[1]
            elif isinstance(a, dict):
                merged.update(a)
        return ("shape", {"type": shape_type, **merged})

    def shape_arg(self, args):
        key = args[0] if args else ""
        val = args[1] if len(args) > 1 else None
        return (str(key), val)

    def text_opt_value(self, args):
        return args[0]

    def text_opt(self, args):
        return (args[0], args[1])

    def text_source(self, args):
        text = args[0]
        opts: Dict[str, Any] = {}
        for a in args[1:]:
            if isinstance(a, tuple) and len(a) == 2:
                opts[str(a[0])] = a[1]
        return ("text", _normalize_text_opts({"text": text, **opts}))

    def asset_decl(self, args):
        asset_name, asset_tuple = args[0], args[-1]
        if not isinstance(asset_tuple, (tuple, list)) or len(asset_tuple) != 2:
            # Earley may leave an un-inlined Tree; unwrap single-child trees.
            from lark import Tree as _Tree
            node = asset_tuple
            while isinstance(node, _Tree) and len(getattr(node, "children", [])) == 1:
                node = node.children[0]
            asset_tuple = node
        kind, payload = asset_tuple
        self.asset_origins[asset_name] = kind
        if kind == "web":
            self.pending_web[asset_name] = payload
            self.assets[asset_name] = ("image", None)
        elif kind == "file":
            self.pending_local[asset_name] = payload
            self.assets[asset_name] = ("image", None)
        elif kind == "text":
            self.assets[asset_name] = ("text", payload)
        elif kind == "shape":
            # Generate the shape image
            shape_data = payload
            shape_type = shape_data.get("type", "rect")
            shape_params = {k: v for k, v in shape_data.items() if k != "type"}
            try:
                shape_image = generate_shape(shape_type, **shape_params)
                self.assets[asset_name] = ("image", shape_image)
            except Exception as e:
                print(f"[DSL Warning] Failed to generate shape '{asset_name}': {e}")
                self.assets[asset_name] = ("image", None)
        else:
            self.assets[asset_name] = (kind, payload)
        return ("asset", asset_name)

    def resolve_pending_assets(self, use_cache: bool = True, max_workers: int = 4):
        from motion_lang.fetcher import get_local_transparent_images
        if self.pending_web:
            queries = list(self.pending_web.values())
            fetched = prefetch_web_images(queries, use_cache=use_cache, max_workers=max_workers)
            for name, q in self.pending_web.items():
                img = fetched.get(q)
                if img is None:
                    img = get_web_transparent_image(q, use_cache=use_cache)
                self.assets[name] = ("image", img)
            self.pending_web.clear()
        if self.pending_local:
            paths = list(self.pending_local.values())
            fetched = get_local_transparent_images(paths, use_cache=use_cache, max_workers=max_workers)
            for name, p in self.pending_local.items():
                img = fetched.get(p)
                if img is None:
                    img = get_local_transparent_image(p, use_cache=use_cache)
                self.assets[name] = ("image", img)
            self.pending_local.clear()

    # -- init --------------------------------------------------------------
    # init_block children: [w, h, fps] or [w, h, fps, mode]
    # -- init (grammar uses aliased init_prop alternatives) -------------------
    def init_res(self, args):
        return ("resolution", int(args[0]), int(args[1]))

    def init_fps(self, args):
        return ("fps", int(args[0]))

    def init_mode(self, args):
        return ("mode", str(args[0]))

    # -- stylesheets ------------------------------------------------------
    def style_import(self, args):
        """Handle ``import style "path/to/theme.css"`` (relative to script)."""
        import os as _os
        raw = args[0] if args else ""
        path = str(raw)
        full = path if _os.path.isabs(path) else _os.path.join(self.base_dir or ".", path)
        try:
            rules = _css.parse_css_file(full)
        except FileNotFoundError:
            print(f"[DSL Warning] Stylesheet not found: '{path}' (skipped).")
            return ("style", path)
        self.style_rules = _css.merge_rules(self.style_rules, rules)
        self.stylesheets.append(full)
        print(f"[Style] Loaded {full} ({len(rules)} rule(s)).")
        if self.compositor is not None:
            # Import placed after init: push straight into the compositor.
            self.compositor.style_rules = _css.merge_rules(
                self.compositor.style_rules, rules)
            self.compositor.stylesheets.append(full)
        return ("style", path)

    def init_block(self, args):
        width, height, fps, mode = 1280, 720, 30, "render"
        for a in args:
            if isinstance(a, (tuple, list)) and len(a) >= 2:
                if a[0] == "resolution" and len(a) >= 3:
                    width, height = int(a[1]), int(a[2])
                elif a[0] == "fps":
                    fps = int(a[1])
                elif a[0] == "mode":
                    mode = str(a[1])
        self.parsed_init = (width, height, fps, mode)
        self.compositor = Compositor(width=width, height=height, fps=int(fps), mode=mode)
        # Flush stylesheets imported before init into the compositor.
        if self.style_rules:
            self.compositor.style_rules = _css.merge_rules(
                self.compositor.style_rules, self.style_rules)
            self.compositor.stylesheets.extend(self.stylesheets)
        return ("init", width, height, fps, mode)

    # -- shape leaf rules ----------------------------------------------------
    def shape_type(self, args):
        return _norm_str(args[0])

    def point(self, args):
        return (int(args[0]), int(args[1]))

    def point_list(self, args):
        return list(args)

    def shape_val(self, args):
        v = args[0]
        if isinstance(v, Token):
            t = v.type
            if t == "ESCAPED_STRING":
                return _unquote(str(v))
            if t == "SINT":
                return int(str(v))
            return _num(str(v))
        return v

    def shape_arg(self, args):
        # children: [IDENTIFIER token, value]
        # value may be a Token or already-converted (float, str, etc.)
        key = str(args[0])
        val = args[1] if len(args) > 1 else None
        if isinstance(val, Token):
            if val.type == "ESCAPED_STRING":
                val = _unquote(str(val))
            elif val.type == "SINT":
                val = int(str(val))
            elif val.type == "SIGNED_NUMBER":
                val = _num(str(val))
        elif isinstance(val, float) and val == int(val):
            val = int(val)
        return (key, val)

    def shape_args(self, args):
        return list(args)

    # -- generic AE-style fx -------------------------------------------------
    def fx_named(self, args):
        # children: [IDENTIFIER(name), value]
        return ("__arg__", str(args[0]), _coerce_fx_value(args[1]))

    def fx_call(self, args):
        """Build ``(fx_name, params)`` from ``name(a=1, "pos")`` syntax.

        Positional string args are sugar for the canonical parameter of the
        few effects that take one (``vfx_preset``/``blend_mode``); anything
        else is kept under ``_args``.
        """
        name = str(args[0])
        params: Dict[str, Any] = {}
        positionals: List[Any] = []
        for a in args[1:]:
            if (isinstance(a, tuple) and len(a) == 3 and a[0] == "__arg__"):
                params[str(a[1])] = a[2]
            else:
                positionals.append(_coerce_fx_value(a))
        if positionals:
            if name == "vfx_preset" and "preset_name" not in params:
                params["preset_name"] = positionals[0]
            elif name == "blend_mode" and "mode" not in params:
                params["mode"] = positionals[0]
            else:
                params.setdefault("_args", positionals)
        return (name, params)

    # -- render options ------------------------------------------------------
    def pos_anim(self, args):
        # args: [ARROW, SINT, SINT] -> skip ARROW
        return ("pos_end", (int(args[1]), int(args[2])))

    def scale_anim(self, args):
        # args: [ARROW, SIGNED_NUMBER] -> skip ARROW, return end scale
        return float(args[1])

    def opacity_anim(self, args):
        # args: [ARROW, SIGNED_NUMBER] -> skip ARROW, return end opacity
        return float(args[1])

    def opt_scale(self, args):
        # args: [SIGNED_NUMBER, Optional(scale_anim_result)]
        start_val = float(args[0])
        end_val = args[1] if len(args) > 1 else None
        return ("scale_pair", (start_val, end_val))

    def opt_size(self, args):
        # args: [SINT, SINT]
        return ("size", (int(args[0]), int(args[1])))

    def opt_easing(self, args):
        return ("easing", _norm_str(args[0]))

    def opt_trans_in(self, args):
        return ("transition_in", _norm_str(args[0]))

    def opt_trans_out(self, args):
        return ("transition_out", _norm_str(args[0]))

    def opt_opacity(self, args):
        # args: [SIGNED_NUMBER, Optional(opacity_anim_result)]
        start_val = float(args[0])
        end_val = args[1] if len(args) > 1 else None
        return ("opacity_pair", (start_val, end_val))

    def opt_fx(self, args):
        # args: list of (fx_name, params) tuples from fx_call
        return ("fx", list(args))

    def opt_class(self, args):
        return ("css_class", str(args[0]))

    def opt_id(self, args):
        return ("css_id", str(args[0]))

    def render_opt(self, args):
        # Lark inlines single-child rules by default, so `render_opt` may
        # never fire; kept for safety. Real handling is in render_stmt.
        return args[0] if args else None

    def render_stmt(self, args):
        # Children: asset(str), t0(float), t1(float), [pos x(int), y(int)],
        # then ("pos_end"|"scale_pair"|"opacity_pair"|"fx"|...) option tuples.
        # pos is optional so CSS left/top can supply layout.
        asset_id = args[0]
        start_t, end_t = float(args[1]), float(args[2])
        rest = list(args[3:])
        pos = None
        if len(rest) >= 2 and isinstance(rest[0], int) and isinstance(rest[1], int):
            pos = (int(rest[0]), int(rest[1]))
            rest = rest[2:]
        out: Dict[str, Any] = {"asset_id": asset_id, "start": start_t, "end": end_t,
                "pos": pos, "pos_end": None, "scale": None, "scale_end": None,
                "size": None, "easing": None, "transition_in": None,
                "transition_out": None, "opacity": None, "opacity_end": None,
                "fx": [], "css_class": None, "css_id": None}
        for extra in rest:
            if not isinstance(extra, tuple) or len(extra) != 2:
                continue
            key, val = extra
            if key == "scale_pair":
                out["scale"] = val[0]
                if val[1] is not None:
                    out["scale_end"] = val[1]
            elif key == "opacity_pair":
                out["opacity"] = val[0]
                if val[1] is not None:
                    out["opacity_end"] = val[1]
            elif key == "fx":
                # val is a list of (fx_name, params) tuples
                out["fx"] = val
            else:
                out[key] = val
        return out

    # NOTE: because render_opt alternatives are aliased inline by Lark's
    # default (maybe_placeholders/keep_all_tokens=False) handling, option
    # tuples are produced by __default_token__-level methods below via
    # explicit sub-rule methods. To keep this robust across Lark versions
    # we post-process raw children in render_stmt AND expose these helpers.
    def __default__(self, data, children, meta):
        return super().__default__(data, children, meta)

    def play_stmt(self, args):
        asset_id = args[0]
        start_time = float(args[1])
        volume = float(args[2]) if len(args) > 2 else 1.0
        return {"asset_id": asset_id, "start": start_time, "volume": volume}

    def layer(self, args):
        z_index = int(args[0])
        renders = args[1:]
        for stmt in renders:
            if not isinstance(stmt, dict):
                continue
            asset = self.assets.get(stmt["asset_id"])
            if asset is None:
                print(f"[DSL Warning] Unknown asset '{stmt['asset_id']}' (skipped).")
                continue
            asset_type, asset_data = asset
            is_shape = self.asset_origins.get(stmt["asset_id"]) == "shape"
            kw = dict(start=stmt["start"], end=stmt["end"], pos=stmt.get("pos"),
                      z_index=z_index, scale=stmt.get("scale"), size=stmt.get("size"),
                      pos_end=stmt.get("pos_end"), scale_end=stmt.get("scale_end"),
                      easing=stmt.get("easing"),
                      transition_in=stmt.get("transition_in"),
                      transition_out=stmt.get("transition_out"),
                      opacity=stmt.get("opacity"), opacity_end=stmt.get("opacity_end"),
                      fx=stmt.get("fx", []),
                      css_class=stmt.get("css_class"), css_id=stmt.get("css_id"))
            if asset_type == "image" and asset_data is not None:
                self.compositor.add_image_layer(pil_image=asset_data, is_shape=is_shape, **kw)
            elif asset_type == "video":
                self.compositor.add_video_layer(video_path=asset_data, **kw)
            elif asset_type == "text":
                txt, tkw = _text_layer_kwargs(asset_data)
                self.compositor.add_text_layer(txt, **tkw, **kw)
        return ("layer", z_index)

    def audio_block(self, args):
        for stmt in args:
            if not isinstance(stmt, dict):
                continue
            asset = self.assets.get(stmt["asset_id"])
            if asset and asset[0] == "audio":
                self.compositor.add_audio_layer(audio_path=asset[1], start=stmt["start"], volume=stmt["volume"])
            else:
                print(f"[DSL Warning] play() references unknown/non-audio asset '{stmt['asset_id']}'.")
        return ("audio_block", args)

    def scene_block(self, args):
        return ("scene", args)


def _build_parser():
    # Earley handles the `->` keyframe ambiguity better than LALR here.
    return Lark(dsl_grammar, start="start", parser="earley")


_RENDER_STMT_RE = None
_FX_CALL_RE = None
_FX_REGION_RE = r"(?<![A-Za-z_])fx\s*=\s*\["


_MODERN_SIGNS = (
    __import__("re").compile(r"(?m)^[ \t]*config[ \t]*:"),
    __import__("re").compile(
        r"(?m)^[ \t]*import[ \t]+[A-Za-z_]\w*"
        r"(?:[ \t]*,[ \t]*[A-Za-z_]\w*)*[ \t]+from\b"),
    __import__("re").compile(r"(?m)^[ \t]*(?:fn|class)[ \t]+[A-Za-z_]\w*"),
    __import__("re").compile(r"(?m)^[ \t]*(?:scene|audio)(?:[ \t]+[A-Za-z_]\w*)?[ \t]*:"),
    __import__("re").compile(r"(?m)^[ \t]*export[ \t]+[A-Za-z_]\w*"),
    __import__("re").compile(r"\brepeat\b[^\n]*\btimes\b"),
    # Bare Python imports (no `from`): `import math`, `import numpy as np`.
    # Requires end-of-line after the name list so legacy
    # `import style "theme.css"` (quoted path) never matches.
    __import__("re").compile(
        r"(?m)^[ \t]*import[ \t]+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
        r"(?:[ \t]*,[ \t]*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)*"
        r"(?:[ \t]+as[ \t]+[A-Za-z_]\w*)?[ \t]*$"),
)


def _is_modern_source(code: str) -> bool:
    """True if the script uses the modern (indentation-based) syntax."""
    return any(rx.search(code) for rx in _MODERN_SIGNS)


def _render_stmt_re():
    global _RENDER_STMT_RE
    if _RENDER_STMT_RE is None:
        import re as _re
        _RENDER_STMT_RE = _re.compile(
            r"render\s*\((?:[^()]|\([^()]*\))*\)", _re.DOTALL)
    return _RENDER_STMT_RE


def _fx_call_re():
    global _FX_CALL_RE
    if _FX_CALL_RE is None:
        import re as _re
        _FX_CALL_RE = _re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)")
    return _FX_CALL_RE


def _coerce_fx_scalar(text: str):
    """Parse a single fx argument literal into str/int/float."""
    import re as _re
    s = text.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return _unquote(s)
        except Exception:
            return s[1:-1]
    if _re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if _re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", s) and \
            ("." in s or "e" in s or "E" in s):
        return float(s)
    return s


def _split_fx_args(arg_str: str):
    """Split ``a=1, b="x,y"`` on top-level commas (quote aware)."""
    parts, buf, quote = [], [], None
    for ch in arg_str:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _extract_fx_list(stmt_text: str):
    """Extract the ``fx=[...]`` stack in source order (AE-style effects)."""
    import re as _re
    m = _re.search(_FX_REGION_RE, stmt_text)
    if not m:
        return []
    start = m.end()
    depth, i = 1, start
    while i < len(stmt_text) and depth:
        if stmt_text[i] == "[":
            depth += 1
        elif stmt_text[i] == "]":
            depth -= 1
        i += 1
    region = stmt_text[start:i - 1] if depth == 0 else stmt_text[start:]
    fx = []
    for cm in _fx_call_re().finditer(region):
        name, arg_str = cm.group(1), cm.group(2)
        params: Dict[str, Any] = {}
        positionals: List[Any] = []
        for part in _split_fx_args(arg_str):
            km = _re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", part, _re.DOTALL)
            if km:
                params[km.group(1)] = _coerce_fx_scalar(km.group(2))
            else:
                positionals.append(_coerce_fx_scalar(part))
        if positionals:
            if name == "vfx_preset" and "preset_name" not in params:
                params["preset_name"] = positionals[0]
            elif name == "blend_mode" and "mode" not in params:
                params["mode"] = positionals[0]
            else:
                params.setdefault("_args", positionals)
        fx.append((name, params))
    return fx


def _extract_option_tuples(stmt_text: str):
    """Fallback regex extractor for render options (robust across Lark versions)."""
    opts: Dict[str, Any] = {}
    m = __import__("re").search(r"scale\s*=\s*(-?[\d.]+)\s*(?:->\s*(-?[\d.]+))?", stmt_text)
    if m:
        opts["scale_pair"] = (float(m.group(1)), float(m.group(2)) if m.group(2) else None)
    m = __import__("re").search(r"size\s*=\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", stmt_text)
    if m:
        opts["size"] = (int(m.group(1)), int(m.group(2)))
    m = __import__("re").search(r"easing\s*=\s*\"([^\"]+)\"", stmt_text)
    if m:
        opts["easing"] = m.group(1)
    m = __import__("re").search(r"transition_in\s*=\s*\"([^\"]+)\"", stmt_text)
    if m:
        opts["transition_in"] = m.group(1)
    m = __import__("re").search(r"transition_out\s*=\s*\"([^\"]+)\"", stmt_text)
    if m:
        opts["transition_out"] = m.group(1)
    m = __import__("re").search(r"(?<![A-Za-z_(])opacity\s*=\s*(-?[\d.]+)\s*(?:->\s*(-?[\d.]+))?", stmt_text)
    if m:
        opts["opacity_pair"] = (float(m.group(1)), float(m.group(2)) if m.group(2) else None)
    m = __import__("re").search(r"pos\s*=\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", stmt_text)
    if m:
        opts["pos"] = (int(m.group(1)), int(m.group(2)))
    m = __import__("re").search(r"pos\s*=\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*->\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", stmt_text)
    if m:
        opts["pos_end"] = (int(m.group(3)), int(m.group(4)))
    m = __import__("re").search(r"(?<![A-Za-z_-])class\s*=\s*\"([^\"]+)\"", stmt_text)
    if m:
        opts["css_class"] = m.group(1)
    m = __import__("re").search(r"(?<![A-Za-z_-])id\s*=\s*\"([^\"]+)\"", stmt_text)
    if m:
        opts["css_id"] = m.group(1)
    fx = _extract_fx_list(stmt_text)
    if fx:
        opts["fx"] = fx
    return opts


def run_script(file_path: str, output_path: str = "output/rendered.mp4",
               mode_override: str = None, use_cache: bool = True,
               max_workers: int = 4, emit_json: str = None,
               skip_build: bool = False):
    import os as _os
    with open(file_path, "r") as f:
        code = f.read()
    # Modern scripting language (config:/fn/class/for/repeat/if/scene:) is
    # handled by a dedicated indentation-based interpreter.
    if _is_modern_source(code):
        from motion_lang.lang import run_modern_script
        return run_modern_script(file_path, code, output_path=output_path,
                                 mode_override=mode_override,
                                 use_cache=use_cache, max_workers=max_workers,
                                 emit_json=emit_json, skip_build=skip_build)
    if emit_json:
        print("[DSL Warning] --emit-json only supports the modern syntax "
              "(config:/fn/class/scene:).")
    print(f"[DSL Compiler] Parsing {file_path}...")
    parser = _build_parser()
    try:
        tree = parser.parse(code)
    except UnexpectedInput as exc:
        raise MotionSyntaxError(_format_lark_error(exc, code)) from exc
    base_dir = _os.path.dirname(_os.path.abspath(file_path))
    interpreter = MotionInterpreter(base_dir=base_dir)
    try:
        interpreter.transform(tree)
    except VisitError as exc:
        orig = getattr(exc, "orig_exc", exc)
        raise MotionSyntaxError(f"[DSL Error] {orig}") from exc
    # The Earley dynamic lexer drops inline option structure; recover the
    # keyframe/transition/easing/fx/class values with a regex pass over
    # render lines (nested-paren aware so pos/fx/class survive).
    render_lines = _render_stmt_re().findall(code)
    opt_list = [_extract_option_tuples(s) for s in render_lines]
    # Concurrent asset prefetch (web + local) before layer construction.
    interpreter.resolve_pending_assets(use_cache=use_cache, max_workers=max_workers)
    # Re-walk layers now that assets are resolved, applying regex options.
    # (layers were already queued with empty images; rebuild them.)
    interpreter.compositor.layers = []
    opt_idx = 0
    for node in tree.iter_subtrees():
        if getattr(node, "data", None) == "layer":
            z_tok = node.children[0]
            try:
                z = int(str(z_tok))
            except Exception:
                z = 0
            for rnode in node.children[1:]:
                if getattr(rnode, "data", None) != "render_stmt":
                    continue
                vals: List[Any] = []
                for ch in rnode.children:
                    if hasattr(ch, "value"):
                        vals.append(str(ch.value))
                    elif isinstance(ch, str):
                        vals.append(ch)
                # vals: [asset, t0, t1, (x, y)?, ...]; pos may be omitted
                # when CSS left/top supplies layout, so read pos from regex.
                if len(vals) < 3:
                    continue
                asset_id, t0, t1 = vals[0], float(vals[1]), float(vals[2])
                # Detect trailing "-> (x2, y2)" tokens for pos_end fallback.
                pos_end = None
                rest = vals[3:]
                if "->" in rest:
                    arrow = rest.index("->")
                    tail = []
                    for v in rest[arrow + 1:]:
                        try:
                            tail.append(int(float(v)))
                        except Exception:
                            continue
                    if len(tail) >= 2:
                        pos_end = (tail[0], tail[1])
                opts = opt_list[opt_idx] if opt_idx < len(opt_list) else {}
                opt_idx += 1
                stmt = {"asset_id": asset_id, "start": t0, "end": t1, "pos": opts.get("pos"),
                        "pos_end": opts.get("pos_end", pos_end), "scale": None,
                        "scale_end": None, "size": opts.get("size"), "easing": opts.get("easing"),
                        "transition_in": opts.get("transition_in"), "transition_out": opts.get("transition_out"),
                        "opacity": None, "opacity_end": None, "fx": opts.get("fx", []),
                        "css_class": opts.get("css_class"), "css_id": opts.get("css_id")}
                if "scale_pair" in opts:
                    stmt["scale"], stmt["scale_end"] = opts["scale_pair"]
                if "opacity_pair" in opts:
                    stmt["opacity"], stmt["opacity_end"] = opts["opacity_pair"]
                asset = interpreter.assets.get(asset_id)
                if asset is None:
                    print(f"[DSL Warning] Unknown asset '{asset_id}' (skipped).")
                    continue
                atype, adata = asset
                is_shape = interpreter.asset_origins.get(asset_id) == "shape"
                kw = dict(start=stmt["start"], end=stmt["end"], pos=stmt["pos"], z_index=z,
                          scale=stmt["scale"], size=stmt["size"], pos_end=stmt["pos_end"],
                          scale_end=stmt["scale_end"], easing=stmt["easing"],
                          transition_in=stmt["transition_in"], transition_out=stmt["transition_out"],
                          opacity=stmt["opacity"], opacity_end=stmt["opacity_end"],
                          fx=stmt.get("fx", []),
                          css_class=stmt.get("css_class"), css_id=stmt.get("css_id"))
                if atype == "image" and adata is not None:
                    interpreter.compositor.add_image_layer(pil_image=adata, is_shape=is_shape, **kw)
                elif atype == "video":
                    interpreter.compositor.add_video_layer(video_path=adata, **kw)
                elif atype == "text":
                    txt, tkw = _text_layer_kwargs(adata)
                    interpreter.compositor.add_text_layer(txt, **tkw, **kw)
    # audio (re-walk for start/volume)
    for node in tree.iter_subtrees():
        if getattr(node, "data", None) == "audio_block":
            for pnode in node.children:
                if getattr(pnode, "data", None) != "play_stmt":
                    continue
                vals = [str(ch.value) if hasattr(ch, "value") else str(ch) for ch in pnode.children]
                if len(vals) < 2:
                    continue
                aid, st = vals[0], float(vals[1])
                vol = float(vals[2]) if len(vals) > 2 else 1.0
                asset = interpreter.assets.get(aid)
                if asset and asset[0] == "audio":
                    interpreter.compositor.add_audio_layer(audio_path=asset[1], start=st, volume=vol)
                else:
                    print(f"[DSL Warning] play() references unknown/non-audio asset '{aid}'.")
    if mode_override:
        interpreter.compositor.mode = mode_override
    interpreter.compositor.build(output_path)
