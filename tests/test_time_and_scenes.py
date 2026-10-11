"""$t outside render(), ternary conditionals, and named scenes."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from motion_lang.lang import (  # noqa: E402
    Env,
    Evaluator,
    Scene,
    TimeValue,
    build_lang_parser,
)
from motion_lang.math_engine import DynExpr  # noqa: E402
from motion_lang.parser import MotionSyntaxError, _is_modern_source  # noqa: E402


def _run(code: str):
    if not code.endswith("\n"):
        code += "\n"
    ev = Evaluator(base_dir=".")
    env = Env()
    ev.run(build_lang_parser().parse(code), env)
    return ev, env


def test_t_time_vars_outside_render():
    ev, env = _run("config:\n    resolution = 320x240\n    fps = 30\n"
                   "theta = $t * 0.5\n"
                   "x = 100 + cos(theta) * 50\n"
                   "scene:\n    layer(z=1):\n"
                   "        render(shape(\"rect\", width=10, height=10),\n"
                   "               pos=(x, 20), time=[0, 1])\n")
    assert isinstance(env.get("theta"), TimeValue)
    assert isinstance(env.get("x"), TimeValue)
    spec = ev.renders[0][1]
    assert isinstance(spec.pos, DynExpr)
    assert spec.pos.eval_at(0.0) == (150.0, 20)
    import math
    assert abs(spec.pos.eval_at(2.0)[0] - (100 + 50 * math.cos(1.0))) < 1e-9


def test_t_frame_and_math_lifting():
    ev, env = _run("config:\n    resolution = 320x240\n    fps = 30\n"
                   "import math\n"
                   "half = $t / 2\n"
                   "capped = max($t, 2)\n"
                   "w = math.cos($t) * 10\n"
                   "f = $frame\n"
                   "scene:\n    layer(z=1):\n"
                   "        render(shape(\"rect\", width=10, height=10),\n"
                   "               pos=(0, 0), time=[0, 2],\n"
                   "               scale=half, opacity=capped / 4,\n"
                   "               rotation=w)\n")
    assert env.get("half").eval_at(4.0) == 2.0
    assert env.get("capped").eval_at(1.0) == 2.0
    assert env.get("capped").eval_at(5.0) == 5.0
    assert env.get("f").eval_at(1.0) == 30.0
    spec = ev.renders[0][1]
    assert spec.scale.eval_at(4.0) == 2.0
    assert spec.opacity.eval_at(1.0) == 0.5
    import math
    assert abs(spec.rotation.eval_at(0.0) - 10.0) < 1e-9


def test_t_ternary_condition_per_frame():
    ev, env = _run("config:\n    resolution = 320x240\n    fps = 30\n"
                   "big = 10 if $t > 2 else 5\n"
                   "scene:\n    layer(z=1):\n"
                   "        render(shape(\"rect\", width=10, height=10),\n"
                   "               pos=(0, 0), time=[0, 4], scale=big)\n")
    assert isinstance(env.get("big"), TimeValue)
    spec = ev.renders[0][1]
    assert spec.scale.eval_at(1.0) == 5
    assert spec.scale.eval_at(3.0) == 10


def test_t_static_slots_reject():
    cases = [
        ("if-cond",
         "if $t > 1:\n    print(1)\n"),
        ("shape-size",
         "w = $t * 10\nscene:\n    layer(z=1):\n"
         "        render(shape(\"rect\", width=w, height=10),"
         " pos=(0, 0), time=[0, 1])\n"),
        ("time-window",
         "scene:\n    layer(z=1):\n"
         "        render(shape(\"rect\", width=10, height=10),"
         " pos=(0, 0), time=[$t, 2])\n"),
        ("repeat-count",
         "scene:\n    layer(z=1):\n        print(1)\n"
         "repeat $t times:\n    print(2)\n"),
        ("range",
         "scene:\n    layer(z=1):\n        print(1)\n"
         "for i in range($t):\n    print(i)\n"),
        ("fx-param",
         "k = $t\nscene:\n    layer(z=1):\n"
         "        render(shape(\"rect\", width=10, height=10),"
         " pos=(0, 0), time=[0, 1], fx=[glow(intensity=k)])\n"),
        ("bool-op",
         "v = $t and 1\n"),
    ]
    head = ("config:\n    resolution = 320x240\n    fps = 30\n")
    for name, body in cases:
        try:
            _run(head + body)
        except (MotionSyntaxError, Exception) as exc:
            assert "time" in str(exc).lower(), f"{name}: {exc}"
        else:
            raise AssertionError(f"{name} should have raised")


def test_ternary_values():
    code = ("config:\n    resolution = 320x240\n    fps = 30\n"
            "GOLD = \"G\"\nCYAN = \"C\"\nPINK = \"P\"\n"
            "a = GOLD if 1 % 2 == 0 else CYAN\n"
            "b = GOLD if 2 % 3 == 0 else (CYAN if 2 % 3 == 1 else PINK)\n"
            "c = GOLD if 3 % 3 == 0 else (CYAN if 3 % 3 == 1 else PINK)\n"
            "scene:\n    layer(z=1):\n        print(a, b, c)\n")
    _, env = _run(code)
    assert env.get("a") == "C"
    assert env.get("b") == "P"
    assert env.get("c") == "G"


def test_named_scenes_and_transition():
    ev, env = _run("config:\n    resolution = 320x240\n    fps = 30\n"
                   "scene Intro:\n    layer(z=1):\n"
                   "        render(shape(\"rect\", width=10, height=10),"
                   " pos=(0, 0), time=[0, 4])\n"
                   "        render(shape(\"circle\", radius=5),"
                   " pos=(9, 9), time=[1, 4])\n"
                   "scene Outro:\n    layer(z=2):\n"
                   "        render(shape(\"rect\", width=10, height=10),"
                   " pos=(20, 20), time=[3.5, 8])\n"
                   "transition(from=Intro, to=Outro, type=\"wipe\","
                   " duration=0.5)\n")
    intro = env.get("Intro")
    outro = env.get("Outro")
    assert isinstance(intro, Scene) and len(intro) == 2
    assert (intro.start, intro.end) == (0.0, 4.0)
    assert (outro.start, outro.end) == (3.5, 8.0)
    outs = [s.transition_out for _, s in ev.renders[:2]]
    assert outs == ["wipe_left(0.5)", "wipe_left(0.5)"]
    assert ev.renders[2][1].transition_in == "wipe_left(0.5)"
    # mixed spec + scene still works
    ev2, env2 = _run("config:\n    resolution = 320x240\n    fps = 30\n"
                     "scene A:\n    layer(z=1):\n"
                     "        la = render(shape(\"rect\", width=5,"
                     " height=5), pos=(0, 0), time=[0, 2])\n"
                     "scene B:\n    layer(z=2):\n"
                     "        lb = render(shape(\"rect\", width=5,"
                     " height=5), pos=(9, 9), time=[1.5, 4])\n"
                     "transition(from=la, to=B, type=\"crossfade\","
                     " duration=0.5)\n")
    assert env2.get("la").transition_out == "crossfade(0.5)"
    assert ev2.renders[1][1].transition_in == "crossfade(0.5)"


def test_scene_detection_and_empty():
    assert _is_modern_source("scene Intro:\n    layer(z=1):\n")
    try:
        _run("config:\n    resolution = 320x240\n    fps = 30\n"
             "scene Empty:\n    layer(z=1):\n"
             "        x = 1\n"
             "scene Full:\n    layer(z=2):\n"
             "        render(shape(\"rect\", width=5, height=5),"
             " pos=(0, 0), time=[0, 2])\n"
             "transition(from=Empty, to=Full, type=\"crossfade\","
             " duration=0.5)\n")
    except (MotionSyntaxError, Exception) as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("empty scene transition should raise")


def test_end_to_end_named_scenes(tmp_path=None):
    import tempfile
    code = ("config:\n    resolution = 320x240\n    fps = 30\n"
            "speed = $t * 30\n"
            "scene Intro:\n    layer(z=1):\n"
            "        for i in range(3):\n"
            "            col = \"#FFC24B\" if i % 2 == 0 else \"#00E5FF\"\n"
            "            render(shape(\"circle\", radius=12, color=col),"
            " pos=(80 + i * 80, 120), time=[0, 2])\n"
            "scene Outro:\n    layer(z=2):\n"
            "        render(shape(\"rect\", width=40, height=40),"
            " pos=(speed, 60), time=[1.5, 4])\n"
            "transition(from=Intro, to=Outro, type=\"wipe\", duration=0.5)\n")
    with tempfile.NamedTemporaryFile("w", suffix=".hmg",
                                     delete=False) as fh:
        fh.write(code)
        path = fh.name
    from motion_lang.lang import run_modern_script
    out = "/tmp/opencode/named_scenes_test.mp4"
    run_modern_script(path, code, output_path=out, mode_override="render")
    assert os.path.isfile(out) and os.path.getsize(out) > 1000


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
