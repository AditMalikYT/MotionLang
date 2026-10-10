"""Tests for the modern Motion Language (lang.py).

Covers variables/operators, functions, classes, control flow, modules,
builtins (fx + render/layer) and the legacy/modern syntax dispatch.

Runs with ``pytest`` or directly: ``python tests/test_language.py``.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lark import UnexpectedInput  # noqa: E402

from motion_lang.lang import (  # noqa: E402
    Evaluator,
    Range,
    build_lang_parser,
)
from motion_lang.parser import _is_modern_source  # noqa: E402


def _run(src: str, base_dir: str = "."):
    parser = build_lang_parser()
    tree = parser.parse(src if src.endswith("\n") else src + "\n")
    ev = Evaluator(base_dir=base_dir)
    env = ev.run(tree)
    return ev, env


def _val(src: str, name: str, base_dir: str = "."):
    _, env = _run(src, base_dir=base_dir)
    return env.get(name)


def test_operators_and_literals():
    src = """
a = 2 + 3 * 4
b = (2 + 3) * 4
c = 10 % 3
d = 2 > 1
s = "x" + "y"
lst = [1, 2, 3]
n = len(lst)
neg = -5
sq = 3 * 3
cmp = 1 <= 2 and 3 != 4
rng = a -> b
"""
    assert _val(src, "a") == 14
    assert _val(src, "b") == 20
    assert _val(src, "c") == 1
    assert _val(src, "d") is True
    assert _val(src, "s") == "xy"
    assert _val(src, "n") == 3
    assert _val(src, "neg") == -5
    assert _val(src, "sq") == 9
    assert _val(src, "cmp") is True
    r = _val(src, "rng")
    assert isinstance(r, Range) and r.start == 14 and r.end == 20


def test_division_and_trailing_comments():
    src = (
        "a = 10 / 4 // quartered\n"
        "b = 10/2 // halved\n"
        "c = 7 / 2 // trailing comment with // slashes // inside\n"
        "// a full-line comment\n"
        "vari = 1 // this commit is not working\n"
    )
    assert _val(src, "a") == 2.5
    assert _val(src, "b") == 5.0
    assert _val(src, "c") == 3.5
    assert _val(src, "vari") == 1


def test_functions_and_defaults():
    src = """
fn double(x):
    return x * 2

fn add(a, b=10):
    return a + b

r1 = double(21)
r2 = add(5)
r3 = add(5, 1)
"""
    assert _val(src, "r1") == 42
    assert _val(src, "r2") == 15
    assert _val(src, "r3") == 6


def test_recursion_and_nested_calls():
    src = """
fn fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)

r = fact(5)
"""
    assert _val(src, "r") == 120


def test_classes_and_methods():
    src = """
class Box:
    fn init(self, w):
        self.w = w

    fn area(self, h):
        return self.w * h

b = Box(3)
a = b.area(4)
"""
    ev, env = _run(src)
    b = env.get("b")
    assert b.attrs["w"] == 3
    assert env.get("a") == 12


def test_conditionals_else_if_else():
    src = """
x = 5
r = 0
if x > 10:
    r = 1
else if x > 3:
    r = 2
else:
    r = 3
"""
    assert _val(src, "r") == 2
    src2 = src.replace("x = 5", "x = 1")
    assert _val(src2, "r") == 3
    src3 = src.replace("x = 5", "x = 99")
    assert _val(src3, "r") == 1


def test_for_loops_and_enumerate_sugar():
    src = """
total = 0
for i in range(5):
    total = total + i
last = -1
for idx, item in ["A", "B", "C"]:
    last = idx
"""
    assert _val(src, "total") == 10
    assert _val(src, "last") == 2


def test_repeat_times():
    src = """
count = 0
repeat 4 times as i:
    count = count + i
"""
    assert _val(src, "count") == 6


def test_fx_calls_return_tuples():
    src = """
f = glow(color="#00E5FF", radius=20)
g = blend_mode("screen")
h = vignette(amount=0.4)
"""
    assert _val(src, "f") == ("glow", {"color": "#00E5FF", "radius": 20})
    assert _val(src, "g") == ("blend_mode", {"mode": "screen"})
    assert _val(src, "h") == ("vignette", {"amount": 0.4})


def test_text_aliases():
    src = 't = text("Hi", size=30, stroke_color="#0FF", tracking=4)\n'
    _, env = _run(src)
    data = env.get("t").data
    assert data["font_size"] == 30
    assert data["stroke_fill"] == "#0FF"
    assert data["letter_spacing"] == 4


def test_scene_layers_and_config():
    src = """
config:
    resolution = 320x240
    fps = 10

scene:
    layer(z=2):
        render(shape("rect", width=50, height=50, color="#ffffff"), time=[0, 1], pos=(0, 0))
    layer(z=1):
        render(shape("circle", radius=20, color="#ff0000"), time=[0, 2], pos=(10, 10))
"""
    ev, _ = _run(src)
    comp = ev.compositor
    assert comp is not None
    assert (comp.width, comp.height, comp.fps) == (320, 240, 10)
    assert len(comp.layers) == 2
    zs = sorted(z for z, _ in comp.layers)
    assert zs == [1, 2]


def test_module_import_and_export():
    with tempfile.TemporaryDirectory() as tmp:
        mod = os.path.join(tmp, "mod.hmg")
        with open(mod, "w") as fh:
            fh.write('export foo\nfn foo(x):\n    return x + 100\n')
        main = """
import foo from "mod.hmg"
r = foo(1)
"""
        assert _val(main, "r", base_dir=tmp) == 101


def test_modern_source_detection():
    modern = "config:\n    fps = 30\nscene:\n    x = 1\n"
    assert _is_modern_source(modern)
    assert _is_modern_source("fn foo():\n    return 1\n")
    legacy = 'init {\n    resolution: 1280x720\n}\nasset a = shape("rect", width=1, height=1)\n'
    assert not _is_modern_source(legacy)


def test_modern_demo_parses():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "examples", "modern_demo.hmg")
    with open(path) as fh:
        code = fh.read()
    tree = build_lang_parser().parse(code)
    assert tree.data == "start"


def test_module_function_and_class_invocation():
    examples = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "examples")
    src = """
import GlowCard, GlassTitle from "components/ui.hmg"

title = GlassTitle("HELLO MODULES", size=72)

scene:
    GlowCard("Fast", "Modules work", x=80, y=80)
    title.build(pos=(300, 400))
"""
    ev, env = _run(src, base_dir=examples)
    comp = ev.compositor
    assert comp is not None
    assert len(comp.layers) == 4
    assert sorted(z for z, _ in comp.layers) == [4, 4, 4, 6]


def test_export_composition_structure():
    from motion_lang.export import build_composition
    src = """
config:
    resolution = 640x360
    fps = 24

scene:
    layer(z=1):
        render(text("HELLO", size=32, color="#FFFFFF"), time=[0, 2], pos=(10, 20), fx=[glow(color="#00E5FF", radius=10)])
"""
    ev, _ = _run(src)
    comp = build_composition(ev, title="demo.hmg", out_dir="/tmp")
    assert comp["meta"]["width"] == 640
    assert comp["meta"]["height"] == 360
    assert comp["meta"]["fps"] == 24
    assert comp["meta"]["duration"] == 2.0
    assert len(comp["layers"]) == 1
    layer = comp["layers"][0]
    assert layer["kind"] == "text"
    assert layer["text"] == "HELLO"
    assert layer["style"]["fontSize"] == 32
    assert layer["fx"][0][0] == "glow"
    assert layer["pos"] == [10, 20]


def test_syntax_error_reports_line():
    parser = build_lang_parser()
    try:
        parser.parse("config:\nfps = = 30\n")
    except UnexpectedInput as exc:
        assert getattr(exc, "line", 0) >= 1
    else:
        raise AssertionError("expected a syntax error")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                import traceback
                print(f"FAIL {name}: {exc}")
                traceback.print_exc()
    sys.exit(1 if failures else 0)
