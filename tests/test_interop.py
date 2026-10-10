"""Tests for Python interop, dynamic fonts and CSS imports (v1.1).

Runs with ``pytest`` or directly: ``python tests/test_interop.py``.
Network-dependent paths are mocked; no video encoding is performed.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motion_lang.lang import Evaluator, build_lang_parser  # noqa: E402
from motion_lang import text_engine as fonts  # noqa: E402
from motion_lang.parser import _is_modern_source  # noqa: E402

try:
    import numpy  # noqa: F401
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


def _run(src, base_dir="."):
    tree = build_lang_parser().parse(src if src.endswith("\n") else src + "\n")
    return Evaluator(base_dir=base_dir).run(tree)


def test_bare_import_detection():
    assert _is_modern_source('import math\nx = 1\n')
    assert _is_modern_source('import numpy as np\nx = 1\n')
    assert _is_modern_source('import math, os.path\nx = 1\n')
    # Legacy stylesheet syntax must NOT flip to modern.
    assert not _is_modern_source('init {\n}\nimport style "theme.css"\n')


def test_py_import_math():
    env = _run('import math\nangle = math.sin(math.pi / 2)\n')
    assert abs(env.get("angle") - 1.0) < 1e-9


def test_py_import_numpy_alias():
    if not _HAS_NUMPY:
        print("SKIP test_py_import_numpy_alias (numpy missing)")
        return
    env = _run('import numpy as np\nv = np.arange(4)\nn = np.pi\n')
    assert list(env.get("v")) == [0, 1, 2, 3]
    assert abs(env.get("n") - 3.141592653589793) < 1e-12


def test_py_import_dotted_binds_top():
    env = _run('import os.path\nj = os.path.join("a", "b")\n')
    assert env.get("j") == os.path.join("a", "b")


def test_py_import_missing_warns():
    env = _run('import no_such_module_xyz_123\nx = 42\n')
    assert env.get("x") == 42  # failure degrades, script continues


def test_py_file_from_import():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "helpers.py"), "w") as fh:
            fh.write('def shout(s):\n    return s.upper() + "!"\n')
        env = _run('import shout from "helpers.py"\nmsg = shout("hi")\n',
                   base_dir=tmp)
        assert env.get("msg") == "HI!"


def test_py_file_bare_import():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "calc.py"), "w") as fh:
            fh.write('FACTOR = 3\ndef triple(x):\n    return x * FACTOR\n')
        env = _run('import calc\nv = calc.triple(5)\n', base_dir=tmp)
        assert env.get("v") == 15


def test_attr_chains_and_assignment():
    if not _HAS_NUMPY:
        print("SKIP test_attr_chains_and_assignment (numpy missing)")
        return
    env = _run('import numpy as np\na = np.zeros(3)\nn = a.shape\n')
    assert tuple(env.get("n")) == (3,)


def test_css_import_loads_rules_and_syncs_config():
    with tempfile.TemporaryDirectory() as tmp:
        css = os.path.join(tmp, "theme.css")
        with open(css, "w") as fh:
            fh.write('.glow-title {\n    color: #00E5FF;\n    font-size: 80px;\n}\n')
        src = ('import styles from "theme.css"\n'
               'config:\n'
               '    resolution = 640x360\n'
               '    fps = 24\n'
               'scene:\n'
               '    t = text("Hi", class="glow-title")\n'
               '    layer(z=1):\n'
               '        render(t, time=[0, 1], pos=(10, 10))\n')
        tree = build_lang_parser().parse(src)
        ev = Evaluator(base_dir=tmp)
        env = ev.run(tree)
        assert len(ev.compositor.style_rules) == 1
        assert ev.compositor.stylesheets[0].endswith("theme.css")
        # Config applied after the import still resizes the compositor.
        assert (ev.compositor.width, ev.compositor.fps) == (640, 24)
        assert env.get("styles").path.endswith("theme.css")


def test_css_import_missing_file():
    env = _run('import styles from "nope.css"\nx = 1\n')
    assert env.get("x") == 1


def test_font_weights():
    assert fonts.weight_value("bold") == 700
    assert fonts.weight_value("regular") == 400
    assert fonts.weight_value(300) == 300


def test_find_local_font():
    path = fonts.find_local_font("DejaVuSans-Bold")
    assert path is not None and path.endswith(".ttf")
    assert fonts.find_local_font("NoSuchFontXYZ123") is None


def test_load_font_local_and_builtin():
    assert fonts.load_font("DejaVuSans-Bold").endswith(".ttf")
    env = _run('f = load_font("DejaVuSans-Bold", weight="bold")\n')
    assert env.get("f").endswith(".ttf")


def test_load_font_offline_fallback():
    orig = fonts.fetch_google_font
    fonts.fetch_google_font = lambda *a, **k: None
    try:
        assert fonts.load_font("NoSuchFontXYZ123") is None
    finally:
        fonts.fetch_google_font = orig


def test_fetch_cache_roundtrip(tmp_path=None):
    dest = fonts._cache_path("TestFam", 400)
    try:
        with open(dest, "wb") as fh:
            fh.write(b"\x00" * 2048)
        assert fonts.fetch_google_font("TestFam", 400) == dest
    finally:
        if os.path.isfile(dest):
            os.remove(dest)


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
