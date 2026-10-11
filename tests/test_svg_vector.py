"""SVG-by-code + 2D/3D vector transform tests (modern DSL)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from motion_lang.lang import Evaluator, run_modern_script  # noqa: E402
from motion_lang.engine import (  # noqa: E402
    _keyframed_float,
    _rotated_size,
    _roll_pil,
    _tilt_pil,
    resolve_easing,
)
from motion_lang.math_engine import DynExpr  # noqa: E402


def _ev():
    return Evaluator(base_dir=".")


def test_svg_builtin_modes():
    ev = _ev()
    icon = ev._builtin_svg(["assets/icons/bolt.svg"],
                           {"width": 64, "height": 64, "fill": "#00E5FF"})
    assert icon.data.size == (64, 64) and icon.is_shape
    mk = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
          '<circle cx="50" cy="50" r="40" fill="#FF0000"/></svg>')
    faithful = ev._builtin_svg([mk], {"width": 100, "height": 100})
    assert faithful.data.size == (100, 100) and not faithful.is_shape
    assert faithful.data.getpixel((50, 50))[:3] == (255, 0, 0)
    raw = ev._builtin_svg(["M0 0 L100 0 L100 100 L0 100 Z"],
                          {"width": 50, "height": 50, "fill": "#FFFFFF"})
    assert raw.data.size == (50, 50)
    kw = ev._builtin_svg([], {"path": "M0 0 L60 0 L60 60 Z",
                              "width": 60, "height": 60,
                              "fill": "#00FF00"})
    assert kw.data.size == (60, 60)
    try:
        ev._builtin_svg([], {})
    except Exception as exc:
        assert "svg()" in str(exc)
    else:
        raise AssertionError("svg() with no source should raise")


def test_rotation_math_helpers():
    w, h = _rotated_size(100, 50, 0)
    assert (round(w), round(h)) == (100, 50)
    w, h = _rotated_size(100, 50, 90)
    assert (round(w), round(h)) == (50, 100)
    fn = _keyframed_float(0, 180, 2.0, resolve_easing("linear"))
    assert fn is not None and abs(fn(0.0)) < 1e-9 and abs(fn(2.0) - 180) < 1e-6
    assert _keyframed_float(None, None, 1.0, resolve_easing("linear")) is None


def test_roll_and_tilt_identity():
    from PIL import Image
    img = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
    assert _roll_pil(img, 0).size == (64, 32)
    assert _tilt_pil(img, 0, 0).size == (64, 32)
    rolled = _roll_pil(img, 90)
    assert rolled.size == (32, 64)
    tilted = _tilt_pil(img, 30, 0)
    assert tilted.size == (64, 32)


def test_render_rotation_dyn_keys():
    from motion_lang.lang import Env, Evaluator, build_lang_parser
    code = ("config:\n    resolution = 320x240\n    fps = 30\n\nscene:\n"
            "    layer(z=1):\n"
            "        render(shape(\"rect\", width=10, height=10), "
            "pos=(0, 0), time=[0, 1], rotation=$t * 90)\n")
    ev = Evaluator(base_dir=".")
    ev.run(build_lang_parser().parse(code), Env())
    assert len(ev.renders) == 1
    spec = ev.renders[0][1]
    assert isinstance(spec.rotation, DynExpr)
    assert abs(float(spec.rotation.eval_at(1.0)) - 90) < 1e-6


def test_svg_multishape_markup():
    """Pasted-style SVG: rect/polygon/path + style="" fills stay faithful."""
    import numpy as np
    mk = (
        '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 460 460">'
        '<polygon style="fill:#3C261B;" '
        'points="320,415 264,415 264,282.5 320,295"/>'
        '<rect x="88" y="305" style="fill:#AF2B12;" width="56" height="110"/>'
        '<path style="fill:#DA521B;" d="M176,93.46L60.23,128.67C25.37,139.28,'
        '0,171.67,0,210v87.5H0v115h56V322h120l20-115.77L176,93.46z"/>'
        '<path style="fill:#FFC052;" d="M405,300c-30.327,0-55-24.673-55-55'
        'v-20h30v20c0,13.785,11.215,25,25,25s25-11.215,25-25v-90h30v90'
        'C460,275.327,435.327,300,405,300z"/>'
        '</svg>')
    ev = _ev()
    asset = ev._builtin_svg([mk], {"width": 230, "height": 230})
    assert asset.data.size == (230, 230) and not asset.is_shape
    a = np.array(asset.data)
    n = a.shape[0] * a.shape[1]
    assert 0 < int((a[:, :, 3] > 0).sum()) < n  # transparent bg kept
    seen = {tuple(p) for p in a.reshape(-1, 4)[::97][:, :3].tolist()}

    def _has(rgb):
        return any(abs(p[0] - rgb[0]) < 30 and abs(p[1] - rgb[1]) < 30
                   and abs(p[2] - rgb[2]) < 30 for p in seen)
    assert _has((218, 82, 27))    # path fill #DA521B
    assert _has((175, 43, 18))    # rect fill #AF2B12
    assert _has((60, 38, 27))     # polygon fill #3C261B
    assert _has((255, 192, 82))   # path fill #FFC052


def test_end_to_end_svg_rotation(tmp_path=None):
    code = ("config:\n    resolution = 320x240\n    fps = 30\n\nscene:\n"
            "    layer(z=1):\n"
            "        render(svg(\"assets/icons/bolt.svg\", width=64, "
            "height=64, fill=\"#00E5FF\"), pos=(128, 88), time=[0, 1],\n"
            "               rotation=0 -> 90, rotation_y=0 -> 30)\n")
    out = "/tmp/opencode/svg_vector_test.mp4"
    run_modern_script("svg_vector_test.hmg", code, output_path=out,
                      mode_override="render")
    assert os.path.isfile(out) and os.path.getsize(out) > 1000


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
