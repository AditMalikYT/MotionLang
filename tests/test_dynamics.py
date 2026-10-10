"""Tests for procedural math ($t dynamics), video trimming and transitions.

Runs with ``pytest`` or directly: ``python tests/test_dynamics.py``.
Frame-level checks build composites in memory; a single tiny MP4 encode
covers the full video-trim + dynamics + transition pipeline.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motion_lang.lang import Evaluator, LangRuntimeError, build_lang_parser  # noqa: E402
from motion_lang.math_engine import (  # noqa: E402
    MATH_FUNCS,
    TIME_CONSTANTS,
    clamp,
    lerp,
    map_range,
    noise,
    tree_has_time,
)
from motion_lang.transitions import (  # noqa: E402
    normalise_direction,
    parse_transition_spec,
    transition_statement,
)
from motion_lang.video_engine import (  # noqa: E402
    apply_ops,
    cache_key,
    normalise_interval,
    retime_clip,
)
from motion_lang.engine import Compositor, parse_transition  # noqa: E402


def _run(src, base_dir="."):
    tree = build_lang_parser().parse(src if src.endswith("\n") else src + "\n")
    ev = Evaluator(base_dir=base_dir)
    return ev, ev.run(tree)


def _val(src, name, base_dir="."):
    _, env = _run(src, base_dir=base_dir)
    return env.get(name)


def test_math_helpers():
    assert abs(MATH_FUNCS["sin"](0.0)) < 1e-12
    assert abs(MATH_FUNCS["cos"](0.0) - 1.0) < 1e-12
    assert abs(MATH_FUNCS["tan"](0.0)) < 1e-12
    assert abs(MATH_FUNCS["sqrt"](16.0) - 4.0) < 1e-12
    assert MATH_FUNCS["pow"](2.0, 10.0) == 1024.0
    assert lerp(10.0, 20.0, 0.25) == 12.5
    assert clamp(99.0, 0.0, 1.0) == 1.0
    assert clamp(-5.0, 0.0, 1.0) == 0.0
    assert map_range(5.0, 0.0, 10.0, 0.0, 100.0) == 50.0
    assert abs(TIME_CONSTANTS["pi"] - 3.141592653589793) < 1e-15
    assert abs(TIME_CONSTANTS["e"] - 2.718281828459045) < 1e-15


def test_noise_deterministic_bounded():
    a = noise(1.7, 4.2)
    assert noise(1.7, 4.2) == a
    assert 0.0 <= a <= 1.0
    assert noise(1.7, 4.2, seed=7) != noise(1.7, 4.2, seed=8)
    # Smoothness: neighbours stay close.
    assert abs(noise(0.05, 0.0) - noise(0.0, 0.0)) < 0.2


def test_math_builtins_in_dsl():
    assert _val("x = sqrt(49.0)\n", "x") == 7.0
    assert _val("x = lerp(0, 100, 0.3)\n", "x") == 30.0
    assert _val("x = clamp(5, 0, 1)\n", "x") == 1
    assert _val("x = map_range(2.5, 0, 5, 10, 20)\n", "x") == 15.0
    assert abs(_val("x = pi * 2\n", "x") - 6.283185307179586) < 1e-12
    assert abs(_val("x = sin(pi / 2) + cos(0)\n", "x") - 2.0) < 1e-12
    assert _val("x = atan2(1, 1)\n", "x") == MATH_FUNCS["atan2"](1, 1)
    assert _val("x = noise(3.0, 4.0)\n", "x") == noise(3.0, 4.0)


def test_time_var_rejected_outside_render():
    try:
        _run("x = 960 + cos($t * 2.0)\n")
    except LangRuntimeError as exc:
        assert "$t" in str(exc) and "render()" in str(exc)
    else:
        raise AssertionError("expected $t outside render() to fail")


def test_tree_has_time():
    tree = build_lang_parser().parse("x = 1 + $frame\n")
    assert tree_has_time(tree)
    plain = build_lang_parser().parse("x = 1 + 2\n")
    assert not tree_has_time(plain)


def test_dynamic_pos_animates_per_frame():
    ev, _ = _run(
        "config:\n"
        "    resolution = 640x360\n"
        "    fps = 30\n"
        "scene:\n"
        "    s = shape(\"rect\", width=40, height=40, color=\"#00E5FF\")\n"
        "    layer(z=1):\n"
        "        render(s, time=[0, 2], pos=(320 + cos($t * 2.0) * 100, 100))\n")
    assert len(ev.compositor.layers) == 1
    clip = ev.compositor.layers[0][1]
    x0, _ = clip.pos(0.0)
    x1, _ = clip.pos(0.7853981633974483)  # t=pi/4 -> cos(pi/2)=0
    assert abs(x0 - 420.0) < 1.0, x0
    assert abs(x1 - 320.0) < 1.0, x1


def test_dynamic_scale_and_opacity():
    ev, _ = _run(
        "scene:\n"
        "    s = shape(\"rect\", width=50, height=50, color=\"#FFFFFF\")\n"
        "    layer(z=1):\n"
        "        render(s, time=[0, 2], pos=(10, 10),\n"
        "               scale=1.0 + sin($t * 5.0) * 0.2,\n"
        "               opacity=0.5 + 0.5 * sin($t * 3.0))\n")
    clip = ev.compositor.layers[0][1]
    f0 = clip.get_frame(0.0)
    f1 = clip.get_frame(0.3141592653589793)  # sin terms move
    # Dynamic scale resizes the layer itself, so shapes may differ.
    assert f0.ndim == f1.ndim == 3 and f0.shape[2] == f1.shape[2] == 3
    assert f0.shape != f1.shape or not np.array_equal(f0, f1)


def _make_clip(path, duration=4.0, size=(320, 180)):
    from moviepy.video.VideoClip import ColorClip
    ColorClip(size, color=(10, 120, 200), duration=duration).write_videofile(
        path, fps=15, codec="libx264", audio=False, logger=None)


def test_video_cut_and_speed_ops(tmp_path=None):
    import tempfile
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "src.mp4")
    _make_clip(src)
    src_txt = (
        f'v = video("{src}", start=1.0, end=3.0)\n'
        f'v2 = v.cut(start=0.5, end=1.5).speed(2.0)\n'
        f'parts = split_video(v, intervals=[(0, 1), (2, 3)])\n'
        f'scene:\n'
        f'    layer(z=1):\n'
        f'        render(v2, time=[0, 2], pos=(0, 0))\n')
    ev, env = _run(src_txt)
    assert env.get("v").source_start == 1.0
    assert env.get("v").source_end == 3.0
    assert env.get("v2").speed_factor == 2.0
    assert len(env.get("parts")) == 2
    # 1s of media at 2x speed over a 2s window clamps to ~0.5s of footage.
    clip = ev.compositor.layers[0][1]
    assert abs(clip.duration - 0.5) < 0.05, clip.duration
    frame = clip.get_frame(0.1)
    assert frame.shape[2] == 3


def test_video_method_chain_and_pos_default():
    import tempfile
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "src.mp4")
    _make_clip(src)
    env = _run(f'v = video("{src}").cut(start=1.0, end=2.0).pos((7, 9))\n')[1]
    v = env.get("v")
    assert (v.source_start, v.source_end) == (1.0, 2.0)
    assert v.default_pos == (7.0, 9.0)
    assert src in v.ops_key and "1.0:2.0" in v.ops_key


def test_video_engine_pure_ops():
    import tempfile
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "src.mp4")
    _make_clip(src)
    from moviepy.video.io.VideoFileClip import VideoFileClip
    clip = VideoFileClip(src)
    cut, used = apply_ops(clip, 1.0, 3.0, None)
    assert abs(cut.duration - 2.0) < 0.05
    assert used == {"start": 1.0, "end": 3.0, "speed": None}
    fast = retime_clip(clip, 2.0)
    assert abs(fast.duration - 2.0) < 0.05
    assert normalise_interval([0, 3]) == (0.0, 3.0)
    assert normalise_interval({"start": 1, "end": 2}) == (1.0, 2.0)
    assert cache_key(src, 0, 1, 2.0) == cache_key(src, 0, 1, 2.0)


def test_transition_spec_parsing():
    assert parse_transition_spec("crossfade(0.8)") == ("crossfade", 0.8, {})
    assert parse_transition_spec("wipe(direction=\"left\", duration=0.5)") == \
        ("wipe_left", 0.5, {"direction": "left"})
    kind, dur, _ = parse_transition_spec("slide(0.4)")
    assert (kind, dur) == ("slide_right", 0.4)
    assert parse_transition_spec("glitch(0.3, intensity=0.8, seed=7)") == \
        ("glitch", 0.3, {"intensity": 0.8, "seed": 7})
    assert parse_transition_spec("bogus(1)")[0] is None
    assert normalise_direction("up") == "up"
    assert normalise_direction("diagonal") == "left"
    # Engine-level strings (inline form) agree.
    assert parse_transition("wipe_right(0.5)") == ("wipe_right", 0.5, {})
    assert parse_transition("fade(0.5)") == ("fade_in", 0.5, {})


def test_transition_statement_wires_specs():
    ev, env = _run(
        "scene:\n"
        "    a = text(\"Scene 1\")\n"
        "    b = text(\"Scene 2\")\n"
        "    layer(z=1):\n"
        "        render(a, time=[0, 3], pos=(10, 10))\n"
        "    layer(z=2):\n"
        "        render(b, time=[2.5, 5.5], pos=(10, 10))\n"
        "    la = render(a, time=[0, 1], pos=(0, 0))\n"
        "    lb = render(b, time=[0, 1], pos=(0, 0))\n"
        "    transition(from=la, to=lb, type=\"crossfade\", duration=0.5)\n")
    assert len(ev.transitions) == 1
    assert ev.transitions[0]["type"] == "crossfade"
    assert env.get("la").transition_out == "crossfade(0.5)"
    assert env.get("lb").transition_in == "crossfade(0.5)"
    assert transition_statement(env.get("la"), env.get("lb"),
                               type="wipe", duration=0.4)["type"] == "wipe_left"
    # The statement runs after layer commit, so clips are rebuilt from the
    # stamped specs: the crossfade must be live on the top clip itself
    # (1.x fades the mask, 2.x fades frame luminance — accept either).
    top = ev.compositor.layers[-1][1]
    f0 = float(top.get_frame(0.05).astype(float).mean())
    f1 = float(top.get_frame(2.0).astype(float).mean())
    frame_ok = f0 < f1 * 0.5
    mask_ok = False
    if top.mask is not None:
        try:
            m0 = float(np.asarray(top.mask.get_frame(0.05)).mean())
            m1 = float(np.asarray(top.mask.get_frame(2.0)).mean())
            mask_ok = m0 < m1 * 0.5
        except Exception:
            pass
    assert mask_ok or frame_ok, (f0, f1)


def test_transition_frames_render():
    from motion_lang.engine import CompositeVideoClip
    ev, _ = _run(
        "config:\n"
        "    resolution = 320x180\n"
        "    fps = 15\n"
        "scene:\n"
        "    a = shape(\"rect\", width=320, height=180, color=\"#102030\")\n"
        "    b = shape(\"rect\", width=320, height=180, color=\"#402010\")\n"
        "    layer(z=1):\n"
        "        render(a, time=[0, 3], pos=(0, 0), transition_out=\"crossfade(0.5)\")\n"
        "    layer(z=2):\n"
        "        render(b, time=[2.5, 5.5], pos=(0, 0),\n"
        "               transition_in=\"wipe_left(0.5)\")\n")
    comp = ev.compositor
    comp.layers.sort(key=lambda x: x[0])
    clips = [c for _, c in comp.layers]
    video = CompositeVideoClip(clips, size=(320, 180), bg_color=(0, 0, 0))
    comp._install_blend_compositing(video, clips)
    for t in (0.1, 2.6, 2.9, 4.0):
        assert video.get_frame(t).shape == (180, 320, 3)


def test_all_transition_kinds_render():
    ev, _ = _run(
        "config:\n"
        "    resolution = 160x90\n"
        "    fps = 10\n"
        "scene:\n"
        "    s = shape(\"rect\", width=160, height=90, color=\"#223344\")\n"
        "    layer(z=1):\n"
        "        render(s, time=[0, 1], pos=(0, 0), transition_in=\"slide_up(0.4)\")\n"
        "        render(s, time=[1, 2], pos=(0, 0), transition_in=\"zoom_out(0.4)\")\n"
        "        render(s, time=[2, 3], pos=(0, 0), transition_in=\"glitch(0.3, intensity=0.6, seed=3)\")\n"
        "        render(s, time=[3, 4], pos=(0, 0), transition_out=\"wipe_down(0.4)\")\n"
        "        render(s, time=[4, 5], pos=(0, 0), transition_in=\"dissolve(0.4)\")\n")
    assert len(ev.compositor.layers) == 5
    for _, clip in ev.compositor.layers:
        f = clip.get_frame(0.05)
        assert f.ndim == 3 and f.shape[2] == 3


def test_full_pipeline_encodes(tmp_path=None):
    import tempfile
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "src.mp4")
    _make_clip(src, duration=4.0)
    out = os.path.join(tmp, "out.mp4")
    script = os.path.join(tmp, "demo.hmg")
    with open(script, "w") as fh:
        fh.write(
            "config:\n"
            "    resolution = 320x180\n"
            "    fps = 15\n"
            "scene:\n"
            f"    v = video(\"{src}\", start=0.5, end=3.5).speed(1.5)\n"
            "    s = shape(\"rect\", width=320, height=60, color=\"#00E5FF\")\n"
            "    layer(z=1):\n"
            "        render(v, time=[0, 2], pos=(0, 0))\n"
            "    layer(z=2):\n"
            "        render(s, time=[0.5, 2.5],\n"
            "               pos=(160 + cos($t * 4.0) * 100, 60 + sin($t * 3.0) * 30),\n"
            "               transition_in=\"slide_right(0.4)\")\n")
    from motion_lang.parser import run_script
    run_script(script, output_path=out)
    assert os.path.isfile(out) and os.path.getsize(out) > 1000


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
