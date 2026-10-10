# motion_lang/lang.py
"""Modern Motion Language interpreter.

A small, Python-like but cleaner language on top of the MoviePy compositor:
variables, operators, ``fn`` functions, ``class`` OOP, ``for`` / ``repeat``
loops, ``if`` / ``else if`` / ``else`` conditionals, module ``import`` /
``export`` and the ``config`` / ``scene`` / ``audio`` directives.

The grammar is indentation based (Lark ``Indenter``) and is intentionally
generic: ``render(...)``, ``shape(...)``, ``text(...)``, ``glow(...)`` and
friends are ordinary builtin calls, so the language itself stays tiny while
the runtime surface stays rich.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lark import Lark, Token, Tree, UnexpectedInput
from lark.indenter import Indenter

from motion_lang.engine import Compositor, EASING_FUNCTIONS
from motion_lang.fetcher import create_fallback_image, get_web_transparent_image
from motion_lang.parser import MotionSyntaxError
from motion_lang.shapes import generate_shape

try:  # Pillow >= 9
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

def _grammar_path() -> str:
    import os as _os
    return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                         "grammar.lark")


def _load_grammar() -> str:
    with open(_grammar_path(), "r", encoding="utf-8") as _fh:
        return _fh.read()


# Inline grammar source (kept importable; canonical source is grammar.lark).
DSL_GRAMMAR = _load_grammar()


class _Indenter(Indenter):
    NL_type = "_NL"
    OPEN_PAREN_types = ["LPAR", "LSQB", "LBRACE"]
    CLOSE_PAREN_types = ["RPAR", "RSQB", "RBRACE"]
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 4


_PARSER: Optional[Lark] = None


def build_lang_parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        _PARSER = Lark(DSL_GRAMMAR, start="start", parser="lalr",
                       postlex=_Indenter(), maybe_placeholders=False)
    return _PARSER


def _format_lang_error(exc: UnexpectedInput, source: str) -> str:
    line = getattr(exc, "line", None) or 1
    col = getattr(exc, "column", None) or 1
    try:
        ctx = exc.get_context(source, span=60)
    except Exception:
        lines = source.splitlines()
        ctx = lines[line - 1] if 1 <= line <= len(lines) else ""
    expected = getattr(exc, "expected", None) or getattr(exc, "accepts", None)
    hint = ""
    if expected:
        try:
            names = sorted(str(x) for x in expected)[:8]
            hint = "\nHint: expected one of: " + ", ".join(names)
        except Exception:
            hint = ""
    return (f"[DSL Syntax Error] line {line}, column {col}\n{ctx}{hint}\n"
            "Modern syntax: `config:`, `import A, B from \"file.hmg\"`, "
            "`import math` / `import numpy as np`, `fn name(args):`, "
            "`class Name:`, `scene:`, `audio:`, "
            "`layer(z=1):`, `for x in items:`, `repeat 3 times as i:`, "
            "`if cond:` / `else if` / `else`, "
            "`transition(from=, to=, type=, duration=)`, `$t`/`$frame` in "
            "render() properties.")


# ---------------------------------------------------------------------------
# Runtime values
# ---------------------------------------------------------------------------

class Asset:
    __slots__ = ("kind", "data", "is_shape")

    def __init__(self, kind: str, data: Any, is_shape: bool = False):
        self.kind = kind
        self.data = data
        self.is_shape = is_shape

    def __repr__(self):
        return f"<{self.kind} asset>"


class VideoAsset:
    """A video file plus accumulated editorial ops (cut + speed + default pos).

    Returned by ``video(...)`` / ``import_video(...)``. Chainable methods
    (``.cut()`` / ``.trim()`` / ``.subclip()`` / ``.speed()`` / ``.pos()``)
    each return a *new* VideoAsset, so intermediate grades can be reused.
    ``kind`` mirrors :class:`Asset` so export/render dispatch keeps working.
    """
    kind = "video"

    def __init__(self, path: str, source_start=None, source_end=None,
                 speed=None, default_pos=None):
        self.path = path
        self.source_start = source_start
        self.source_end = source_end
        self.speed_factor = speed
        self.default_pos = default_pos

    def _clone(self, **over):
        kw = dict(path=self.path, source_start=self.source_start,
                  source_end=self.source_end, speed=self.speed_factor,
                  default_pos=self.default_pos)
        kw.update(over)
        return VideoAsset(**kw)

    def cut(self, start=None, end=None, duration=None):
        if duration is not None and end is None:
            s = self.source_start if start is None else float(start)
            end = s + float(duration)
        return self._clone(source_start=start, source_end=end)

    def trim(self, start=None, end=None, duration=None):
        return self.cut(start=start, end=end, duration=duration)

    def subclip(self, start=None, end=None):
        return self.cut(start=start, end=end)

    def speed(self, factor=1.0):
        return self._clone(speed=float(factor))

    def pos(self, x, y=None):
        if y is None and isinstance(x, (list, tuple)):
            x, y = x[0], x[1]
        return self._clone(default_pos=(float(x), float(y)))

    def split(self, intervals):
        from motion_lang.video_engine import normalise_interval
        return [self.cut(start=s, end=e)
                for s, e in (normalise_interval(iv) for iv in intervals)]

    @property
    def ops_key(self) -> str:
        from motion_lang.video_engine import cache_key
        return cache_key(self.path, self.source_start, self.source_end,
                         self.speed_factor)

    def __repr__(self):
        return (f"<video {self.path} "
                f"[{self.source_start}:{self.source_end} @{self.speed_factor}]>")


class Layer:
    __slots__ = ("z", "opts", "renders")

    def __init__(self, z: int = 0, **opts):
        self.z = int(z)
        self.opts = opts
        self.renders: List["RenderSpec"] = []

    def __repr__(self):
        return f"<layer z={self.z} renders={len(self.renders)}>"


class RenderSpec:
    __slots__ = ("asset", "start", "end", "pos", "pos_end", "scale",
                 "scale_end", "size", "easing", "transition_in",
                 "transition_out", "opacity", "opacity_end", "fx",
                 "css_class", "css_id")

    def __init__(self, asset: Asset, **kw):
        self.asset = asset
        self.start = kw.get("start", 0.0)
        self.end = kw.get("end", 6.0)
        self.pos = kw.get("pos")
        self.pos_end = kw.get("pos_end")
        self.scale = kw.get("scale")
        self.scale_end = kw.get("scale_end")
        self.size = kw.get("size")
        self.easing = kw.get("easing")
        self.transition_in = kw.get("transition_in")
        self.transition_out = kw.get("transition_out")
        self.opacity = kw.get("opacity")
        self.opacity_end = kw.get("opacity_end")
        self.fx = kw.get("fx") or []
        self.css_class = kw.get("css_class")
        self.css_id = kw.get("css_id")


class Range:
    """Result of ``a -> b``; interpreted per-option at render time."""
    __slots__ = ("start", "end")

    def __init__(self, start, end):
        self.start, self.end = start, end

    def __repr__(self):
        return f"{self.start} -> {self.end}"


class Stylesheet:
    """Value bound by ``import x from "theme.css"`` (rules + source path)."""

    def __init__(self, path: str, rules: List[Dict[str, Any]]):
        self.path = path
        self.rules = rules

    @property
    def classes(self) -> List[str]:
        out: List[str] = []
        for rule in self.rules or []:
            for sel in (rule.get("selectors") or rule.get("selector") or []):
                s = str(sel).strip()
                if s.startswith(".") and s not in out:
                    out.append(s)
        return out

    def __repr__(self):
        return f"<stylesheet {os.path.basename(self.path)} ({len(self.rules)} rules)>"


class Function:
    def __init__(self, name: str, params, body, env):
        self.name = name
        self.params = params          # list of (name, default_expr|None)
        self.body = body
        self.env = env


class BoundMethod:
    def __init__(self, fn: Function, instance):
        self.fn = fn
        self.instance = instance


class Class:
    def __init__(self, name: str, methods: Dict[str, Function], env):
        self.name = name
        self.methods = methods
        self.env = env

    def __repr__(self):
        return f"<class {self.name}>"


class Instance:
    def __init__(self, cls: Class):
        self.cls = cls
        self.attrs: Dict[str, Any] = {}

    def __repr__(self):
        return f"<{self.cls.name} object>"


class _Return(Exception):
    def __init__(self, value):
        super().__init__("return")
        self.value = value


class LangRuntimeError(Exception):
    pass


class Env:
    def __init__(self, parent: Optional["Env"] = None):
        self.vars: Dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str):
        env: Optional[Env] = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise LangRuntimeError(f"Undefined name '{name}'.")

    def has(self, name: str) -> bool:
        env: Optional[Env] = self
        while env is not None:
            if name in env.vars:
                return True
            env = env.parent
        return False

    def set(self, name: str, value: Any):
        env: Optional[Env] = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        self.vars[name] = value

    def define(self, name: str, value: Any):
        self.vars[name] = value


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_TEXT_ALIASES = {
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

_TEXT_DEFAULTS = {
    "font": "default",
    "color": "#FFFFFF",
    "font_size": 48,
    "stroke_width": 0,
    "stroke_fill": "#000000",
    "letter_spacing": 0,
    "bg_color": None,
}


def _normalize_text(text: str, opts: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"text": text}
    for k, v in opts.items():
        out[_TEXT_ALIASES.get(k, k)] = v
    for key in ("font_size", "stroke_width", "letter_spacing"):
        if out.get(key) is not None:
            try:
                out[key] = int(float(out[key]))
            except (TypeError, ValueError):
                out.pop(key, None)
    merged = {k: out.get(k, d) for k, d in _TEXT_DEFAULTS.items()}
    merged["text"] = text
    return merged


_FX_NAMES = {
    "blur", "glow", "drop_shadow", "opacity", "adjust_color", "vfx_preset",
    "chromatic_aberration", "glitch", "vignette", "motion_blur", "blend_mode",
    "reflection", "flash_in", "light_sweep", "pulse", "float_y",
}


def _fx_tuple(name: str, pos: List[Any], kw: Dict[str, Any]) -> Tuple[str, Dict]:
    params: Dict[str, Any] = dict(kw)
    if pos:
        if name == "vfx_preset" and "preset_name" not in params:
            params["preset_name"] = pos[0]
        elif name == "blend_mode" and "mode" not in params:
            params["mode"] = pos[0]
        else:
            params.setdefault("_args", list(pos))
    return (name, params)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class Evaluator:
    def __init__(self, base_dir: str = ".", use_cache: bool = True,
                 max_workers: int = 4, module_mode: bool = False):
        self.base_dir = base_dir or "."
        self.use_cache = use_cache
        self.max_workers = max_workers
        self.module_mode = module_mode
        self.config = {"width": 1280, "height": 720, "fps": 30, "mode": "render"}
        self.compositor: Optional[Compositor] = None
        self.layer_stack: List[Layer] = []
        self.exports: List[str] = []
        self.defined: set = set()
        self._module_cache: Dict[str, Dict[str, Any]] = {}
        # Recorded timeline (for the Remotion studio export).
        self.renders: List[Tuple[int, "RenderSpec"]] = []
        self.audio_specs: List[Dict[str, Any]] = []
        # transition() statement records (from_spec, to_spec, kind, ...).
        self.transitions: List[Dict[str, Any]] = []

    # -- orchestration ----------------------------------------------------
    def run(self, tree: Tree, env: Optional[Env] = None) -> Env:
        if env is None:
            env = Env()
        # Bare easing names (ease=linear, ease=ease_out, ...) evaluate
        # to their string form, so .hmg files don't need quotes.
        for _ename in EASING_FUNCTIONS:
            if not env.has(_ename):
                env.define(_ename, _ename)
        for stmt in tree.children:
            self.exec_stmt(stmt, env)
        self._reapply_transitions()
        return env

    def _ensure_compositor(self) -> Optional[Compositor]:
        if self.module_mode:
            return None
        if self.compositor is None:
            self.compositor = Compositor(
                width=int(self.config["width"]), height=int(self.config["height"]),
                fps=int(self.config["fps"]), mode=str(self.config["mode"]))
        return self.compositor

    # -- statements -------------------------------------------------------
    def exec_stmts(self, body: List[Tree], env: Env):
        for stmt in body:
            self.exec_stmt(stmt, env)

    def exec_stmt(self, node, env: Env):
        if not isinstance(node, Tree):
            return None
        data = node.data
        handler = getattr(self, f"_stmt_{data}", None)
        if handler is None:
            # Fall back: treat as an expression statement.
            self._commit_if_layer(self.eval(node, env))
            return None
        return handler(node, env)

    def _commit_if_layer(self, value):
        if isinstance(value, Layer) and not self.module_mode:
            self.commit_layer(value)

    # config -----------------------------------------------------------------
    def _stmt_config_block(self, node, env):
        for prop in node.children:
            if not isinstance(prop, Tree) or prop.data != "config_prop":
                continue
            name = str(prop.children[0])
            value = prop.children[1]
            if isinstance(value, Tree) and value.data == "res_value":
                raw = str(value.children[0])
                w, h = re.split(r"[xX]", raw)
                self.config["width"], self.config["height"] = int(w), int(h)
            else:
                val = self.eval(value, env)
                if name in ("resolution", "size"):
                    if isinstance(val, (list, tuple)) and len(val) >= 2:
                        self.config["width"], self.config["height"] = int(val[0]), int(val[1])
                elif name == "fps":
                    self.config["fps"] = int(val)
                elif name == "mode":
                    self.config["mode"] = str(val)
        # If a stylesheet import already materialised the compositor, keep it
        # in sync while nothing has been committed to it yet.
        comp = self.compositor
        if comp is not None and not comp.layers and not comp.audio_layers:
            comp.width = int(self.config["width"])
            comp.height = int(self.config["height"])
            comp.fps = int(self.config["fps"])
            comp.mode = str(self.config["mode"])
        return None

    # imports / exports ------------------------------------------------------
    def _stmt_import_stmt(self, node, env):
        items: List[Tuple[str, Optional[str]]] = []
        path: Optional[str] = None
        for ch in node.children:
            if isinstance(ch, Tree) and ch.data == "imp_list":
                for item in ch.children:
                    dotted_parts: List[str] = []
                    alias: Optional[str] = None
                    if isinstance(item, Tree) and item.data == "imp_item":
                        for sub in item.children:
                            if isinstance(sub, Tree) and sub.data == "dotted":
                                dotted_parts = [str(t) for t in sub.children]
                            elif isinstance(sub, Token):
                                alias = str(sub)
                    elif isinstance(item, Token):
                        dotted_parts = [str(item)]
                    if dotted_parts:
                        items.append((".".join(dotted_parts), alias))
            elif isinstance(ch, Token) and ch.type == "ESCAPED_STRING":
                path = str(ch)
        if path is not None and (
                path.startswith('"') or path.startswith("'")):
            path = path[1:-1]
        if path is None:
            # Bare ``import math`` / ``import numpy as np``: Python interop.
            from motion_lang.modules import resolve_py_import
            for bind, module in resolve_py_import(items, self.base_dir).items():
                env.define(bind, module)
                self.defined.add(bind)
            return None
        low = path.lower()
        if low.endswith((".css", ".hmsc")):
            self._import_stylesheet(path, items, env)
        elif low.endswith(".py"):
            self._import_py_file(path, items, env)
        else:
            module = self._load_module(path)
            for dotted, alias in items:
                name = alias or dotted
                if "." in dotted:
                    print(f"[DSL Warning] Dotted name '{dotted}' cannot be "
                          f"imported from '{path}'.")
                    continue
                if name in module:
                    env.define(name, module[name])
                    self.defined.add(name)
                else:
                    print(f"[DSL Warning] '{name}' not found in module '{path}'.")
        return None

    def _import_stylesheet(self, path: str,
                           items: List[Tuple[str, Optional[str]]], env: Env):
        """``import styles from "theme.css"``: load rules into the compositor.

        The sheet applies globally through the normal cascade (explicit
        ``render()`` attributes still win); each imported name is also bound
        to a :class:`Stylesheet` value for introspection.
        """
        from motion_lang import style as _css
        full = path if os.path.isabs(path) else os.path.join(self.base_dir, path)
        try:
            rules = _css.parse_css_file(full)
        except FileNotFoundError:
            print(f"[DSL Warning] Stylesheet not found: '{path}' (skipped).")
            return
        comp = self._ensure_compositor()
        if comp is not None:
            comp.style_rules = _css.merge_rules(comp.style_rules, rules)
            comp.stylesheets.append(os.path.abspath(full))
            print(f"[Style] Loaded {full} ({len(rules)} rule(s)).")
        sheet = Stylesheet(path=os.path.abspath(full), rules=rules)
        for dotted, alias in items:
            env.define(alias or dotted.split(".")[0], sheet)
            self.defined.add(alias or dotted.split(".")[0])

    def _import_py_file(self, path: str,
                        items: List[Tuple[str, Optional[str]]], env: Env):
        """``import name from "helpers.py"``: bind names from a Python file."""
        from motion_lang.modules import load_py_file
        full = path if os.path.isabs(path) else os.path.join(self.base_dir, path)
        if not os.path.isfile(full):
            print(f"[DSL Warning] Python file not found: '{path}'.")
            return
        try:
            module = load_py_file(full)
        except Exception as exc:
            print(f"[DSL Warning] Failed to import '{path}': {exc}")
            return
        stem = os.path.splitext(os.path.basename(full))[0]
        for dotted, alias in items:
            name = alias or dotted
            if hasattr(module, name):
                env.define(name, getattr(module, name))
                self.defined.add(name)
            elif len(items) == 1 and "." not in dotted and dotted == stem:
                env.define(name, module)
                self.defined.add(name)
            else:
                print(f"[DSL Warning] '{name}' not found in '{path}'.")

    def _stmt_export_stmt(self, node, env):
        name = str(node.children[0])
        self.exports.append(name)
        return None

    # definitions ------------------------------------------------------------
    def _stmt_fn_def(self, node, env):
        name, params, body = self._parse_fn(node)
        env.define(name, Function(name, params, body, env))
        self.defined.add(name)
        return None

    def _parse_fn(self, node):
        name = str(node.children[0])
        params: List[Tuple[str, Any]] = []
        body: List[Tree] = []
        for ch in node.children[1:]:
            if isinstance(ch, Tree) and ch.data == "params":
                for p in ch.children:
                    pname = str(p.children[0])
                    default = p.children[1] if len(p.children) > 1 else None
                    params.append((pname, default))
            elif isinstance(ch, Tree):
                body.append(ch)
        return name, params, body

    def _stmt_class_def(self, node, env):
        name = str(node.children[0])
        methods: Dict[str, Function] = {}
        for ch in node.children[1:]:
            if isinstance(ch, Tree) and ch.data == "fn_def":
                mname, params, body = self._parse_fn(ch)
                methods[mname] = Function(mname, params, body, env)
        cls = Class(name, methods, env)
        env.define(name, cls)
        self.defined.add(name)
        return None

    # directives -------------------------------------------------------------
    def _stmt_scene_block(self, node, env):
        if self.module_mode:
            return None
        self._ensure_compositor()
        self.exec_stmts(node.children, env)
        return None

    def _stmt_audio_block(self, node, env):
        if self.module_mode:
            return None
        self._ensure_compositor()
        self.exec_stmts(node.children, env)
        return None

    def _stmt_layer_block(self, node, env):
        layer = self.eval_layer_block(node, env)
        self._commit_if_layer(layer)
        return None

    # control flow -----------------------------------------------------------
    def _stmt_if_stmt(self, node, env):
        # children: [cond, if-body..., elif_clause*, else_clause?]
        if_body: List[Tree] = []
        elifs: List[Tree] = []
        else_body: Optional[List[Tree]] = None
        for ch in node.children[1:]:
            if isinstance(ch, Tree) and ch.data == "elif_clause":
                elifs.append(ch)
            elif isinstance(ch, Tree) and ch.data == "else_clause":
                else_body = [c for c in ch.children if isinstance(c, Tree)]
            else:
                if_body.append(ch)
        if self._truthy(self.eval(node.children[0], env)):
            self.exec_stmts(if_body, env)
            return None
        for clause in elifs:
            if self._truthy(self.eval(clause.children[0], env)):
                self.exec_stmts([c for c in clause.children[1:] if isinstance(c, Tree)], env)
                return None
        if else_body is not None:
            self.exec_stmts(else_body, env)
        return None

    def _stmt_for_stmt(self, node, env):
        target = node.children[0]
        iterable = self.eval(node.children[1], env)
        body = [c for c in node.children[2:] if isinstance(c, Tree)]
        names = [str(c) for c in target.children]
        for index, item in enumerate(self._iterate(iterable)):
            local = Env(env)
            if len(names) == 1:
                local.define(names[0], item)
            elif len(names) == 2 and not isinstance(item, (list, tuple)):
                # Cleaner-than-Python sugar: `for i, x in items` = enumerate.
                local.define(names[0], index)
                local.define(names[1], item)
            else:
                values = list(item) if isinstance(item, (list, tuple)) else [item]
                for i, n in enumerate(names):
                    local.define(n, values[i] if i < len(values) else None)
            self.exec_stmts(body, local)
        return None

    def _stmt_repeat_stmt(self, node, env):
        children = list(node.children)
        count = self.eval(children[0], env)
        var_name = None
        rest = children[1:]
        if rest and isinstance(rest[0], Token) and rest[0].type == "NAME":
            var_name = str(rest[0])
            rest = rest[1:]
        body = [c for c in rest if isinstance(c, Tree)]
        for i in range(int(count)):
            local = Env(env)
            if var_name:
                local.define(var_name, i)
            self.exec_stmts(body, local)
        return None

    # return -----------------------------------------------------------------
    def _stmt_return_layer(self, node, env):
        raise _Return(self.eval_layer_block(node.children[0], env))

    def _stmt_return_expr(self, node, env):
        raise _Return(self.eval(node.children[0], env))

    def _stmt_return_none(self, node, env):
        raise _Return(None)

    # assignment / expressions ----------------------------------------------
    def _stmt_assign_stmt(self, node, env):
        target, value_node = node.children[0], node.children[1]
        value = self.eval(value_node, env)
        self._assign(target, value, env)
        return None

    def _stmt_expr_stmt(self, node, env):
        value = self.eval(node.children[0], env)
        self._commit_if_layer(value)
        return None

    def _assign(self, target, value, env):
        if not isinstance(target, Tree):
            raise LangRuntimeError("Invalid assignment target.")
        if target.data == "var":
            env.set(str(target.children[0]), value)
        elif target.data == "chain":
            parts = []
            for c in target.children:
                if isinstance(c, Tree):
                    raise LangRuntimeError("Cannot assign to a call.")
                parts.append(str(c))
            obj = env.get(parts[0])
            for name in parts[1:-1]:
                obj = self._get_attr(obj, name)
            name = parts[-1]
            if isinstance(obj, Instance):
                obj.attrs[name] = value
            else:
                setattr(obj, name, value)
        elif target.data == "index":
            obj = self.eval(target.children[0], env)
            idx = self.eval(target.children[1], env)
            obj[idx] = value
        else:
            raise LangRuntimeError("Invalid assignment target.")

    # -- layer evaluation ----------------------------------------------------
    def eval_layer_block(self, node, env) -> Layer:
        args_node = None
        body: List[Tree] = []
        for ch in node.children:
            if isinstance(ch, Token):
                continue
            if isinstance(ch, Tree) and ch.data == "args":
                args_node = ch
            elif isinstance(ch, Tree):
                body.append(ch)
        pos, kw = self.eval_args(args_node, env)
        z = int(kw.get("z", pos[0] if pos else 0))
        layer = Layer(z=z)
        self.layer_stack.append(layer)
        try:
            self.exec_stmts(body, env)
        finally:
            self.layer_stack.pop()
        return layer

    def commit_layer(self, layer: Layer):
        comp = self._ensure_compositor()
        if comp is None:
            return
        for spec in layer.renders:
            self.renders.append((layer.z, spec))
            self._add_render(spec, layer.z)

    def _reapply_transitions(self):
        """Rebuild clips after transition() statements mutated specs.

        Layer clips are committed the moment their ``layer:`` block executes,
        but ``transition(from=, to=)`` statements run later and only stamp
        ``transition_in/out`` on the specs. Replaying the recorded timeline
        through the compositor applies them without duplicating records.
        """
        comp = self.compositor
        if comp is None or not self.transitions:
            return
        comp.layers = []
        for z, spec in self.renders:
            self._add_render(spec, z)

    def _add_render(self, spec: RenderSpec, z: int):
        comp = self._ensure_compositor()
        if comp is None or spec.asset is None:
            return
        kw = dict(start=float(spec.start), end=float(spec.end), pos=spec.pos,
                  z_index=int(z), scale=spec.scale, size=spec.size,
                  pos_end=spec.pos_end, scale_end=spec.scale_end,
                  easing=spec.easing, transition_in=spec.transition_in,
                  transition_out=spec.transition_out, opacity=spec.opacity,
                  opacity_end=spec.opacity_end, fx=spec.fx,
                  css_class=spec.css_class, css_id=spec.css_id)
        asset = spec.asset
        if asset.kind == "image" and asset.data is not None:
            comp.add_image_layer(pil_image=asset.data, is_shape=asset.is_shape, **kw)
        elif asset.kind == "video":
            if isinstance(asset, VideoAsset):
                comp.add_video_layer(video_path=asset.path,
                                     source_start=asset.source_start,
                                     source_end=asset.source_end,
                                     speed=asset.speed_factor, **kw)
            else:
                comp.add_video_layer(video_path=asset.data, **kw)
        elif asset.kind == "text":
            data = dict(asset.data)
            text = data.pop("text", "")
            comp.add_text_layer(text, **data, **kw)

    # -- expression evaluation ----------------------------------------------
    def eval(self, node, env: Env):
        if isinstance(node, Token):
            return self._eval_token(node, env)
        if not isinstance(node, Tree):
            return node
        data = node.data
        handler = getattr(self, f"_eval_{data}", None)
        if handler is not None:
            return handler(node, env)
        if len(node.children) == 1:
            return self.eval(node.children[0], env)
        return [self.eval(c, env) for c in node.children]

    def _eval_token(self, tok: Token, env: Env):
        if tok.type == "NUMBER":
            s = str(tok)
            try:
                return int(s)
            except ValueError:
                return float(s)
        if tok.type == "ESCAPED_STRING":
            s = str(tok)
            try:
                import ast
                return ast.literal_eval(s)
            except Exception:
                return s.strip('"')
        if tok.type == "NAME":
            return env.get(str(tok))
        return str(tok)

    # literals / leaves
    def _eval_var(self, node, env):
        name = str(node.children[0])
        try:
            return env.get(name)
        except LangRuntimeError:
            from motion_lang.math_engine import TIME_CONSTANTS
            if name in TIME_CONSTANTS:
                return TIME_CONSTANTS[name]
            raise

    def _eval_time_var(self, node, env):
        name = str(node.children[0])
        try:
            return env.get(name)
        except LangRuntimeError:
            raise LangRuntimeError(
                f"{name} is only available inside animated render() properties "
                f"(pos, scale, opacity, ...), where it is evaluated per frame.")

    def _eval_paren(self, node, env):
        return self.eval(node.children[0], env)

    def _eval_true_lit(self, node, env):
        return True

    def _eval_false_lit(self, node, env):
        return False

    def _eval_tuple_lit(self, node, env):
        return tuple(self.eval(c, env) for c in node.children)

    def _eval_list_lit(self, node, env):
        return [self.eval(c, env) for c in node.children]

    def _eval_neg(self, node, env):
        # children include the kept MINUS terminal, so the operand is last.
        return -self.eval(node.children[-1], env)

    def _eval_not_op(self, node, env):
        return not self._truthy(self.eval(node.children[0], env))

    # binary chains
    def _fold(self, node, env, fn, initial=None):
        values = [self.eval(c, env) for c in node.children]
        if not values:
            return initial
        acc = values[0]
        for v in values[1:]:
            acc = fn(acc, v)
        return acc

    def _eval_or_expr(self, node, env):
        for ch in node.children:
            v = self.eval(ch, env)
            if self._truthy(v):
                return v
        return self.eval(node.children[-1], env) if node.children else False

    def _eval_and_expr(self, node, env):
        result = True
        for ch in node.children:
            result = self.eval(ch, env)
            if not self._truthy(result):
                return result
        return result

    def _eval_arrow_expr(self, node, env):
        operands = [self.eval(node.children[i], env)
                    for i in range(0, len(node.children), 2)]
        if len(operands) == 2:
            return Range(operands[0], operands[1])
        return [Range(operands[i], operands[i + 1])
                for i in range(len(operands) - 1)]

    def _eval_comparison(self, node, env):
        operands = [self.eval(node.children[i], env)
                    for i in range(0, len(node.children), 2)]
        ops = [str(node.children[i]) for i in range(1, len(node.children), 2)]
        if not ops:
            return operands[0]
        for i, op in enumerate(ops):
            if not self._compare(op, operands[i], operands[i + 1]):
                return False
        return True

    def _eval_arith(self, node, env):
        operands = [self.eval(node.children[i], env)
                    for i in range(0, len(node.children), 2)]
        ops = [str(node.children[i]) for i in range(1, len(node.children), 2)]
        acc = operands[0]
        for op, rhs in zip(ops, operands[1:]):
            acc = self._arith(op, acc, rhs)
        return acc

    def _eval_term(self, node, env):
        operands = [self.eval(node.children[i], env)
                    for i in range(0, len(node.children), 2)]
        ops = [str(node.children[i]) for i in range(1, len(node.children), 2)]
        acc = operands[0]
        for op, rhs in zip(ops, operands[1:]):
            acc = self._arith(op, acc, rhs)
        return acc

    @staticmethod
    def _truthy(v) -> bool:
        return bool(v)

    @staticmethod
    def _compare(op, a, b):
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == ">":
            return a > b
        if op == "<":
            return a < b
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
        return False

    @staticmethod
    def _arith(op, a, b):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "%":
            return a % b
        raise LangRuntimeError(f"Unknown operator '{op}'.")

    # calls / attributes
    def _get_attr(self, obj, name):
        if isinstance(obj, Instance):
            if name in obj.attrs:
                return obj.attrs[name]
            if name in obj.cls.methods:
                return BoundMethod(obj.cls.methods[name], obj)
            raise LangRuntimeError(
                f"'{name}' is not a member of {obj.cls.name}.")
        # Native Python interop: modules, numpy, os.path, ...
        try:
            return getattr(obj, name)
        except AttributeError:
            pass
        raise LangRuntimeError(f"Cannot read attribute '{name}'.")

    def _eval_index(self, node, env):
        obj = self.eval(node.children[0], env)
        idx = self.eval(node.children[1], env)
        return obj[idx]

    def _eval_method_call(self, node, env):
        # Legacy single-link shape (grammar now produces `chain` instead).
        names = [str(c) for c in node.children if isinstance(c, Token)]
        args_node = next((c for c in node.children
                          if isinstance(c, Tree) and c.data == "args"), None)
        obj = env.get(names[0])
        for name in names[1:-1]:
            obj = self._get_attr(obj, name)
        pos, kw = self.eval_args(args_node, env)
        return self._call_link(obj, names[-1], pos, kw)

    def _eval_chain(self, node, env):
        """Evaluate attribute/call chains left to right.

        Three head shapes (a link with a ``call_args`` child is invoked,
        otherwise it is an attribute read):

        * ``a.b.c`` — ``[a, b, c]``; pure attribute path.
        * ``a.b(..).c`` / ``os.path.join(..)`` — ``[a, b, call_args?, ...]``.
        * ``video(..).cut(..)`` — ``[video, args, cut, call_args, ...]``;
          the head is a call evaluated first.
        """
        children = node.children
        if len(children) > 1 and isinstance(children[1], Tree) \
                and children[1].data == "args":
            head_pos, head_kw = self.eval_args(children[1], env)
            obj = self._invoke(str(children[0]), head_pos, head_kw, env)
            i = 2
        else:
            obj = env.get(str(children[0]))
            i = 1
        while i < len(children):
            name = str(children[i])
            i += 1
            if i < len(children) and isinstance(children[i], Tree) \
                    and children[i].data == "call_args":
                inner = children[i].children
                args_node = inner[0] if inner else None
                i += 1
                pos, kw = self.eval_args(args_node, env)
                obj = self._call_link(obj, name, pos, kw)
            else:
                obj = self._get_attr(obj, name)
        return obj

    def _call_link(self, obj, name: str, pos, kw):
        method = self._get_attr(obj, name)
        if isinstance(method, BoundMethod):
            return self.call_function(method.fn, [method.instance] + pos, kw)
        if callable(method):
            return method(*pos, **kw)
        raise LangRuntimeError(f"'{name}' is not callable.")

    def _eval_call(self, node, env):
        name = str(node.children[0])
        args_node = node.children[1] if len(node.children) > 1 else None
        if name == "render":
            return self._eval_render_call(args_node, env)
        pos, kw = self.eval_args(args_node, env)
        return self._invoke(name, pos, kw, env)

    #: render() properties evaluated per frame when they mention $t/$frame.
    _DYN_KEYS = frozenset({"pos", "pos_end", "scale", "scale_end",
                           "opacity", "opacity_end"})

    def _eval_render_call(self, args_node, env):
        """Evaluate render() args, wrapping $t-bearing props in DynExpr."""
        from motion_lang.math_engine import DynExpr, tree_has_time
        pos, kw = [], {}
        if args_node is None:
            return self._invoke("render", pos, kw, env)
        for a in args_node.children:
            if isinstance(a, Tree) and a.data == "kwarg":
                key = str(a.children[0])
                if key in self._DYN_KEYS and tree_has_time(a.children[1]):
                    kw[key] = DynExpr(a.children[1], self, env,
                                     fps=self.config.get("fps", 30),
                                     label=key)
                else:
                    kw[key] = self.eval(a.children[1], env)
            elif isinstance(a, Tree) and a.data == "posarg":
                # Positional args (the asset, time lists) must be static;
                # a $t here raises the helpful time_var error.
                pos.append(self.eval(a.children[0], env))
            else:
                pos.append(self.eval(a, env))
        return self._invoke("render", pos, kw, env)

    def _eval_audio_call(self, node, env):
        args_node = next((c for c in node.children
                          if isinstance(c, Tree) and c.data == "args"), None)
        pos, kw = self.eval_args(args_node, env)
        return self._builtin_audio(pos, kw)

    def eval_args(self, args_node, env) -> Tuple[List[Any], Dict[str, Any]]:
        pos: List[Any] = []
        kw: Dict[str, Any] = {}
        if args_node is None:
            return pos, kw
        for a in args_node.children:
            if isinstance(a, Tree) and a.data == "kwarg":
                kw[str(a.children[0])] = self.eval(a.children[1], env)
            elif isinstance(a, Tree) and a.data == "posarg":
                pos.append(self.eval(a.children[0], env))
            else:
                pos.append(self.eval(a, env))
        return pos, kw

    # -- dispatch ------------------------------------------------------------
    def _invoke(self, name: str, pos: List[Any], kw: Dict[str, Any], env: Env):
        if name in _FX_NAMES:
            return _fx_tuple(name, pos, kw)
        builtin = getattr(self, f"_builtin_{name}", None)
        if builtin is not None:
            return builtin(pos, kw)
        from motion_lang.math_engine import MATH_FUNCS
        if name in MATH_FUNCS:
            try:
                return MATH_FUNCS[name](*pos, **kw)
            except TypeError as exc:
                raise LangRuntimeError(f"{name}(): {exc}")
        if env.has(name):
            target = env.get(name)
            return self._call_value(target, pos, kw)
        raise LangRuntimeError(f"Unknown function '{name}'.")

    def _call_value(self, target, pos, kw):
        if isinstance(target, Function):
            return self.call_function(target, pos, kw)
        if isinstance(target, Class):
            return self.instantiate(target, pos, kw)
        if isinstance(target, BoundMethod):
            return self.call_function(target.fn, [target.instance] + pos, kw)
        if callable(target):
            return target(*pos, **kw)
        raise LangRuntimeError("Value is not callable.")

    def call_function(self, fn: Function, pos: List[Any], kw: Dict[str, Any]):
        local = Env(fn.env)
        names = [p[0] for p in fn.params]
        for i, (pname, default) in enumerate(fn.params):
            if i < len(pos):
                local.define(pname, pos[i])
            elif pname in kw:
                local.define(pname, kw[pname])
            elif default is not None:
                local.define(pname, self.eval(default, fn.env))
            else:
                local.define(pname, None)
        try:
            self.exec_stmts(fn.body, local)
        except _Return as ret:
            return ret.value
        return None

    def instantiate(self, cls: Class, pos: List[Any], kw: Dict[str, Any]):
        inst = Instance(cls)
        init = cls.methods.get("init") or cls.methods.get("__init__")
        if init is not None:
            self.call_function(init, [inst] + pos, kw)
        return inst

    # -- modules -------------------------------------------------------------
    def _load_module(self, rel_path: str) -> Dict[str, Any]:
        base = self.base_dir
        full = rel_path if os.path.isabs(rel_path) else os.path.join(base, rel_path)
        full = os.path.abspath(full)
        if full in self._module_cache:
            return self._module_cache[full]
        if not os.path.isfile(full):
            print(f"[DSL Warning] Module not found: '{rel_path}'.")
            self._module_cache[full] = {}
            return {}
        with open(full, "r", encoding="utf-8") as fh:
            code = fh.read()
        if not code.endswith("\n"):
            code += "\n"
        parser = build_lang_parser()
        try:
            tree = parser.parse(code)
        except UnexpectedInput as exc:
            raise MotionSyntaxError(_format_lang_error(exc, code)) from exc
        sub = Evaluator(base_dir=os.path.dirname(full), use_cache=self.use_cache,
                        max_workers=self.max_workers, module_mode=True)
        sub._module_cache = self._module_cache
        env = Env()
        sub.run(tree, env)
        exported: Dict[str, Any] = {}
        names = sub.exports or sorted(sub.defined)
        for name in names:
            if env.has(name):
                exported[name] = env.get(name)
        self._module_cache[full] = exported
        return exported

    # -- builtins: assets ----------------------------------------------------
    def _builtin_shape(self, pos, kw):
        stype = str(pos[0]) if pos else str(kw.pop("type", "rect"))
        params = {k: v for k, v in kw.items() if k != "type"}
        params = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                  for k, v in params.items()}
        try:
            img = generate_shape(stype, **params)
        except Exception as exc:
            print(f"[DSL Warning] shape('{stype}') failed: {exc}")
            img = create_fallback_image(stype)
        return Asset("image", img, is_shape=True)

    def _builtin_text(self, pos, kw):
        if pos:
            s = str(pos[0])
        else:
            s = str(kw.pop("text", kw.pop("value", "")))
        return Asset("text", _normalize_text(s, kw))

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        local = os.path.join(self.base_dir, path)
        if os.path.exists(local):
            return local
        if os.path.exists(path):
            return path
        return local

    def _builtin_file(self, pos, kw):
        path = self._resolve_path(str(pos[0]))
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            print(f"[DSL Warning] file('{pos[0]}') not found ({exc}); using placeholder.")
            img = create_fallback_image(os.path.basename(str(pos[0])))
        return Asset("image", img, is_shape=False)

    def _builtin_wiki(self, pos, kw):
        return self._web_image(str(pos[0]))

    def _builtin_web(self, pos, kw):
        return self._web_image(str(pos[0]))

    def _web_image(self, query: str) -> Asset:
        roots = (os.path.join(self.base_dir, "assets"), self.base_dir,
                 os.path.join(os.getcwd(), "assets"), os.getcwd())
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            for root in roots:
                cand = os.path.join(root, query + ext)
                if os.path.isfile(cand):
                    try:
                        return Asset("image", Image.open(cand).convert("RGBA"))
                    except Exception:
                        pass
        try:
            img = get_web_transparent_image(query, use_cache=self.use_cache)
        except Exception as exc:
            print(f"[DSL Warning] web('{query}') failed: {exc}")
            img = create_fallback_image(query)
        return Asset("image", img, is_shape=False)

    def _builtin_video(self, pos, kw):
        path = self._resolve_path(str(pos[0]))
        return VideoAsset(path, source_start=kw.get("start"),
                          source_end=kw.get("end", kw.get("stop")),
                          speed=kw.get("speed"))

    def _builtin_import_video(self, pos, kw):
        return self._builtin_video(pos, kw)

    def _builtin_split_video(self, pos, kw):
        from motion_lang.video_engine import normalise_interval
        if not pos:
            raise LangRuntimeError("split_video() requires a video asset.")
        source = pos[0]
        intervals = kw.get("intervals", pos[1] if len(pos) > 1 else [])
        if not isinstance(source, VideoAsset):
            raise LangRuntimeError("split_video() expects a video() asset.")
        return [source.cut(start=s, end=e)
                for s, e in (normalise_interval(iv) for iv in intervals)]

    def _builtin_audio(self, pos, kw):
        return Asset("audio", self._resolve_path(str(pos[0])))

    def _builtin_load_font(self, pos, kw):
        """``load_font("Poppins", weight="bold", url=...)`` -> .ttf path.

        Returns ``None`` when the font cannot be resolved (offline, unknown
        family); ``text()`` then falls back to the default font.
        """
        from motion_lang.text_engine import load_font
        if pos:
            name = str(pos[0])
        else:
            name = str(kw.get("name", kw.get("family", "")))
        return load_font(name, weight=kw.get("weight", "regular"),
                         url=kw.get("url"), style=kw.get("style", "normal"))

    # -- builtins: scene ops -------------------------------------------------
    def _stmt_transition_stmt(self, node, env):
        """``transition(from=a, to=b, type="crossfade", duration=0.5)``.

        Stamps ``transition_out`` on the *from* spec and ``transition_in``
        on the *to* spec; overlap the layers' ``time=`` windows by
        ``duration`` for a true blend.
        """
        from motion_lang.transitions import transition_statement
        args_node = next((c for c in node.children
                          if isinstance(c, Tree) and c.data == "args"), None)
        pos, kw = self.eval_args(args_node, env)
        from_spec = kw.get("from", pos[0] if pos else None)
        to_spec = kw.get("to", pos[1] if len(pos) > 1 else None)
        if from_spec is None or to_spec is None:
            raise LangRuntimeError(
                "transition() needs from= and to= render() layers.")
        kind = kw.get("type", kw.get("kind", "crossfade"))
        duration = float(kw.get("duration", 0.5))
        params = {k: v for k, v in kw.items()
                  if k not in ("from", "to", "type", "kind", "duration")}
        record = transition_statement(from_spec, to_spec, type=str(kind),
                                      duration=duration, **params)
        self.transitions.append(record)
        return record

    def _builtin_render(self, pos, kw):
        if not pos:
            raise LangRuntimeError("render() requires an asset argument.")
        asset = pos[0]
        if not isinstance(asset, (Asset, VideoAsset)):
            raise LangRuntimeError("render() expects an asset (shape/text/image/video).")
        kw = dict(kw)
        time = kw.pop("time", None)
        start, end = 0.0, 6.0
        if isinstance(time, (list, tuple)) and len(time) >= 2:
            start, end = float(time[0]), float(time[1])
        start = float(kw.pop("start", start))
        end = float(kw.pop("end", end))
        posv = kw.pop("pos", None)
        if posv is None and isinstance(asset, VideoAsset) \
                and asset.default_pos is not None:
            posv = asset.default_pos
        pos_end = kw.pop("pos_end", None)
        scale = kw.pop("scale", None)
        scale_end = kw.pop("scale_end", None)
        opacity = kw.pop("opacity", None)
        opacity_end = kw.pop("opacity_end", None)
        if isinstance(posv, Range):
            pos_end = posv.end
            posv = posv.start
        if isinstance(scale, Range):
            scale_end = scale.end
            scale = scale.start
        if isinstance(opacity, Range):
            opacity_end = opacity.end
            opacity = opacity.start
        fx = kw.pop("fx", None) or []
        spec = RenderSpec(
            asset, start=start, end=end,
            pos=tuple(posv) if isinstance(posv, (list, tuple)) else posv,
            pos_end=tuple(pos_end) if isinstance(pos_end, (list, tuple)) else pos_end,
            scale=scale, scale_end=scale_end,
            size=tuple(kw.pop("size")) if isinstance(kw.get("size"), (list, tuple)) else None,
            easing=kw.pop("easing", kw.pop("ease", None)),
            transition_in=kw.pop("transition_in", None),
            transition_out=kw.pop("transition_out", None),
            opacity=opacity, opacity_end=opacity_end, fx=fx,
            css_class=kw.pop("class", None), css_id=kw.pop("id", None))
        if self.layer_stack:
            self.layer_stack[-1].renders.append(spec)
        else:
            layer = Layer(z=int(kw.get("z", 0)))
            layer.renders.append(spec)
            self._commit_if_layer(layer)
        return spec

    def _builtin_play(self, pos, kw):
        if not pos:
            print("[DSL Warning] play() requires an audio asset.")
            return None
        asset = pos[0]
        start = float(kw.get("start", 0.0))
        volume = float(kw.get("volume", 1.0))
        path = asset.data if isinstance(asset, Asset) else asset
        comp = self._ensure_compositor()
        if comp is None:
            return None
        if not isinstance(path, str) or not os.path.isfile(path):
            print(f"[DSL Warning] audio file not found: '{path}' (skipped).")
            return None
        try:
            comp.add_audio_layer(audio_path=path, start=start, volume=volume)
            self.audio_specs.append({"path": path, "start": start,
                                     "volume": volume})
        except Exception as exc:
            print(f"[DSL Warning] play() failed: {exc}")
        return None

    # -- builtins: generic ---------------------------------------------------
    def _builtin_print(self, pos, kw):
        print(*pos)
        return None

    def _builtin_len(self, pos, kw):
        return len(pos[0])

    def _builtin_range(self, pos, kw):
        return list(range(*(int(p) for p in pos)))

    def _builtin_abs(self, pos, kw):
        return abs(pos[0])

    def _builtin_min(self, pos, kw):
        return min(pos)

    def _builtin_max(self, pos, kw):
        return max(pos)

    def _builtin_round(self, pos, kw):
        return round(*pos)

    def _builtin_int(self, pos, kw):
        return int(pos[0])

    def _builtin_float(self, pos, kw):
        return float(pos[0])

    def _builtin_str(self, pos, kw):
        return str(pos[0])

    def _builtin_bool(self, pos, kw):
        return bool(pos[0])

    def _builtin_sum(self, pos, kw):
        return sum(pos[0])

    def _builtin_list(self, pos, kw):
        return list(pos[0]) if pos else []

    def _builtin_sin(self, pos, kw):
        return math.sin(pos[0])

    def _builtin_cos(self, pos, kw):
        return math.cos(pos[0])

    @staticmethod
    def _iterate(value):
        if isinstance(value, (list, tuple, range)):
            return value
        if isinstance(value, str):
            return value
        try:
            return list(value)
        except TypeError:
            raise LangRuntimeError("Value is not iterable.")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_modern_script(file_path: str, code: str,
                      output_path: str = "output/rendered.mp4",
                      mode_override: str = None, use_cache: bool = True,
                      max_workers: int = 4, emit_json: str = None,
                      skip_build: bool = False):
    print(f"[DSL Compiler] Parsing {file_path} (modern syntax)...")
    parser = build_lang_parser()
    parse_src = code if code.endswith("\n") else code + "\n"
    try:
        tree = parser.parse(parse_src)
    except UnexpectedInput as exc:
        raise MotionSyntaxError(_format_lang_error(exc, code)) from exc
    base_dir = os.path.dirname(os.path.abspath(file_path))
    evaluator = Evaluator(base_dir=base_dir, use_cache=use_cache,
                          max_workers=max_workers)
    try:
        evaluator.run(tree)
    except _Return:
        pass
    except LangRuntimeError as exc:
        raise MotionSyntaxError(f"[DSL Error] {exc}") from exc
    comp = evaluator._ensure_compositor()
    if comp is None:
        raise MotionSyntaxError("[DSL Error] No `scene:` block found.")
    if emit_json:
        from motion_lang.export import export_composition
        export_composition(evaluator, emit_json, title=os.path.basename(file_path))
    if skip_build:
        return emit_json or output_path
    if not comp.layers and not comp.audio_layers:
        print("[DSL Warning] Script produced no layers.")
    if mode_override:
        comp.mode = mode_override
    comp.build(output_path)
    return output_path
