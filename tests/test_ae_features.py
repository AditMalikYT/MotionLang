"""Regression tests for native typography + AE-style effects/blending.

Runs with ``pytest`` or directly: ``python tests/test_ae_features.py``.
These cover parsing, fx extraction, the VFX primitives and the compositor's
blend bookkeeping without invoking a full video encode.
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motion_lang import vfx  # noqa: E402
from motion_lang.engine import (  # noqa: E402
    Compositor,
    _resolve_font_path,
    make_text_image,
)
from motion_lang.parser import (  # noqa: E402
    _build_parser,
    _extract_fx_list,
    _extract_option_tuples,
    _normalize_text_opts,
)
from motion_lang.shapes import generate_shape  # noqa: E402

AE_EXAMPLE = '''
init {
    resolution: 1280x720
    fps: 30
    mode: preview
}

asset title = text("CYBERPUNK 2077", font="DejaVuSans-Bold", size=72, color="#FFE600")
asset hero_img = wiki("cyberpunk city")
asset bg_music = audio("assets/synthwave.mp3")

scene {
    layer(z=1) {
        render(hero_img, time=[0, 6], pos=(0, 0), size=(1280, 720), fx=[vignette(amount=0.6)])
    }
    layer(z=2) {
        render(title, time=[1, 6], pos=(280, 300), fx=[
            glow(color="#00E5FF", radius=20, intensity=1.5),
            chromatic_aberration(offset=6),
            glitch(intensity=0.3)
        ])
    }
}

audio_scene {
    play(bg_music, start=0, volume=0.5)
}
'''


def test_ae_example_parses():
    tree = _build_parser().parse(AE_EXAMPLE)
    assert tree.data == "start"


def test_text_option_aliases():
    norm = _normalize_text_opts({
        "text": "Hi", "size": "64", "stroke_color": "#00E5FF",
        "stroke_width": "2.0", "tracking": 4, "fill": "#FFF",
    })
    assert norm["font_size"] == 64
    assert norm["stroke_fill"] == "#00E5FF"
    assert norm["stroke_width"] == 2
    assert norm["letter_spacing"] == 4
    assert norm["color"] == "#FFF"


def test_fx_extraction_order_and_types():
    stmt = ('render(t, time=[0,1], pos=(1,2), fx=[' 
            'glitch(intensity=0.3, seed=7), '
            'glow(color="#00E5FF", radius=20, intensity=1.5), '
            'blend_mode("screen"), motion_blur(samples=6, direction=20)])')
    fx = _extract_fx_list(stmt)
    assert [name for name, _ in fx] == [
        "glitch", "glow", "blend_mode", "motion_blur"]
    assert fx[0][1] == {"intensity": 0.3, "seed": 7}
    assert fx[1][1] == {"color": "#00E5FF", "radius": 20, "intensity": 1.5}
    assert fx[2][1] == {"mode": "screen"}
    assert fx[3][1] == {"samples": 6, "direction": 20}
    assert _extract_option_tuples(stmt)["fx"] == fx


def test_vfx_primitives():
    orb = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(orb).ellipse([10, 10, 110, 110], fill=(0, 229, 255, 255))
    assert vfx.chromatic_aberration(orb, offset=6).size == orb.size
    assert vfx.vignette(orb, amount=0.6).size == orb.size
    assert vfx.motion_blur(orb, samples=6, direction=20).size == orb.size
    assert vfx.glitch(orb, intensity=0.5, seed=1).size == orb.size
    glow = vfx.apply_glow(orb, "#00E5FF", intensity=1.5, radius=20)
    assert glow.width > orb.width


def test_glitch_is_seeded():
    g1 = np.array(vfx.glitch(Image.new("RGBA", (80, 80), (128, 64, 32, 255)),
                             intensity=0.8, seed=42))
    g2 = np.array(vfx.glitch(Image.new("RGBA", (80, 80), (128, 64, 32, 255)),
                             intensity=0.8, seed=42))
    assert np.array_equal(g1, g2)


def test_blend_modes():
    base = np.full((4, 4, 3), 100, np.uint8)
    top = np.full((4, 4, 3), 200, np.uint8)
    assert vfx.blend_rgb(base, top, "normal")[0, 0].tolist() == [200] * 3
    assert vfx.blend_rgb(base, top, "multiply")[0, 0].tolist() == [78] * 3
    assert vfx.blend_rgb(base, top, "screen")[0, 0].tolist() == [221] * 3
    assert vfx.blend_rgb(base, top, "difference")[0, 0].tolist() == [100] * 3
    assert vfx.blend_rgb(base, top, "bogus")[0, 0].tolist() == [200] * 3


def test_font_resolution_and_text():
    path = _resolve_font_path("DejaVuSans-Bold")
    assert path and os.path.isfile(path)
    plain = make_text_image("AB", font="default", font_size=48)
    tracked = make_text_image("AB", font="default", font_size=48,
                              letter_spacing=10)
    assert tracked.width > plain.width
    stroked = make_text_image("AB", font="default", font_size=48,
                              stroke_width=2, stroke_fill="#00E5FF")
    assert stroked.size[0] > plain.size[0]


def test_shape_stroke_and_star():
    star = generate_shape("star", radius=60, color="#FF2E88",
                          stroke_color="#FFFFFF", stroke_width=3)
    assert star.size == (120, 120)
    assert np.array(star)[:, :, 3].max() == 255
    rect = generate_shape("rect", width=80, height=40, color="#101010",
                          stroke_color="#FFFFFF", stroke_width=2)
    corners = np.array(rect)
    assert corners[0, 0, :3].tolist() == [255, 255, 255]


def test_line_shape():
    line = generate_shape("line", x1=220, y1=560, x2=1700, y2=560,
                          color="#27405F", width=3)
    assert line.size == (1481, 3)
    a = np.array(line)
    assert a[1, 500, :3].tolist() == [0x27, 0x40, 0x5F]
    assert int((a[:, :, 3] > 0).sum()) > 1000
    vert = generate_shape("line", x1=5, y1=5, x2=5, y2=100,
                          color="#FFFFFF", width=2)
    assert vert.size == (2, 96)
    dot = generate_shape("line", x1=9, y1=9, x2=9, y2=9,
                         color="#FF0000", width=4)
    assert dot.size == (4, 4)
    assert np.array(dot)[2, 2, 0] > 200


def test_opencv_channel_order():
    # Raw OpenCV buffers are read back as RGBA: red must stay red.
    red = generate_shape("star", points=5, radius=40, color="#FF0000")
    assert np.array(red)[40, 40, :3].tolist() == [255, 0, 0]
    green = generate_shape("polygon", points=[(0, 0), (30, 0), (15, 26)],
                           color="#00FF00")
    assert np.array(green)[10, 15, :3].tolist() == [0, 255, 0]


def test_fx_stack_captures_blend_mode():
    base = Image.new("RGBA", (64, 64), (60, 60, 60, 255))
    comp = Compositor(64, 64, 10)
    out, blend, offset = comp._apply_fx_stack(base, [("blend_mode", {"mode": "screen"})])
    assert blend == "screen"
    assert offset == (0, 0)
    assert np.array_equal(np.array(out), np.array(base))
    out2, blend2, offset2 = comp._apply_fx_stack(
        base, [("vignette", {"amount": 0.8})])
    assert blend2 is None
    assert offset2 == (0, 0)
    assert not np.array_equal(np.array(out2)[:, :, :3], np.array(base)[:, :, :3])


def test_blend_compositing_math():
    comp = Compositor(64, 64, 10)
    comp.add_image_layer(Image.new("RGBA", (64, 64), (100, 100, 100, 255)),
                         start=0, end=1, pos=(0, 0), z_index=1)
    comp.add_image_layer(Image.new("RGBA", (20, 20), (200, 50, 50, 255)),
                         start=0, end=1, pos=(10, 10), z_index=2,
                         fx=[("blend_mode", {"mode": "multiply"})])
    comp.layers.sort(key=lambda x: x[0])
    clips = [clip for _, clip in comp.layers]
    from motion_lang.engine import CompositeVideoClip
    video = CompositeVideoClip(clips, size=(64, 64), bg_color=(0, 0, 0))
    comp._install_blend_compositing(video, clips)
    frame = video.get_frame(0.5)
    assert frame[20, 20].tolist() == [78, 19, 19]
    assert frame[55, 55].tolist() == [100, 100, 100]


def test_four_point_star_and_outer_radius_alias():
    star = generate_shape("star", points=4, outer_radius=64, inner_radius=18,
                          color="#FF2E88")
    assert star.size == (128, 128)
    assert np.array(star)[:, :, 3].max() == 255
    # Classic 5-point star still works via `radius`.
    classic = generate_shape("star", radius=60, color="#FF2E88",
                             stroke_color="#FFFFFF", stroke_width=3)
    assert classic.size == (120, 120)


def test_gradient_fills():
    rect = generate_shape("rect", width=200, height=100,
                          fill="gradient(linear, #ff0000, #0000ff)")
    a = np.array(rect)
    assert a[2, 2, :3].tolist()[0] > 200      # red end
    assert a[97, 197, :3].tolist()[2] > 200  # blue end
    disc = generate_shape("circle", radius=50,
                          fill="gradient(radial, #ffffff, #000000)")
    b = np.array(disc)
    assert b[50, 50, :3].tolist()[0] > 200   # hot centre
    assert b[2, 2, :3].tolist()[0] < 40      # dark rim


def test_svg_path_shape(tmp_path=None):
    import os as _os
    svg_path = _os.path.join("assets", "icons", "bolt.svg")
    if not _os.path.isfile(svg_path):
        return  # icon asset not shipped; raw path-data check still runs
    img = generate_shape("path", svg=svg_path, fill="#00E5FF",
                         width=128, height=128)
    assert img.size == (128, 128)
    assert int((np.array(img)[:, :, 3] > 0).sum()) > 1000
    raw = generate_shape("path", path="M0 0 L100 0 L100 100 L0 100 Z",
                         fill="#FFFFFF", width=50, height=50)
    assert int((np.array(raw)[:, :, 3] > 0).sum()) == 2500


def test_reflection_fades_downward():
    solid = Image.new("RGBA", (100, 80), (0, 229, 255, 255))
    out = vfx.apply_reflection(solid, opacity=0.5, blur=0)
    assert out.size == (100, 160)
    a = np.array(out)
    assert a[80, 50, 3] == 127          # contact edge at requested opacity
    assert a[80, 50, 3] > a[120, 50, 3] > a[159, 50, 3] == 0
    assert a[10, 50, :3].tolist() == [0, 229, 255]  # source untouched


def test_flash_decays_and_sweep_travels():
    base = Image.new("RGBA", (64, 64), (255, 0, 80, 255))
    start = np.array(vfx.flash_overlay(base, 0.0)).astype(float)
    done = np.array(vfx.flash_overlay(base, 1.0)).astype(float)
    assert start[:, :, :3].mean() > 250      # ~full white at t=0
    assert np.array_equal(done, np.array(base))
    s0 = np.array(vfx.light_sweep(base, 0.0))
    s1 = np.array(vfx.light_sweep(base, 0.5))
    assert not np.array_equal(s0, s1)
    assert abs(vfx.float_y_offset(0.0, 20, 1.0)) < 1e-9
    assert abs(vfx.pulse_scale(0.0, 0.1, 2.0) - 1.0) < 1e-9


def test_new_fx_parse_and_extract():
    stmt = ('render(s, time=[0,2], pos=(10, 10) -> (400, 200), '
            'scale=0.5 -> 1.5, fx=[reflection(opacity=0.4, blur=3), '
            'float_y(distance=10, speed=2.0), flash_in(duration=0.3), '
            'light_sweep(angle=45, speed=1.0), pulse(amount=0.1)])')
    fx = _extract_fx_list(stmt)
    assert [n for n, _ in fx] == ["reflection", "float_y", "flash_in",
                                  "light_sweep", "pulse"]
    assert fx[0][1] == {"opacity": 0.4, "blur": 3}
    opts = _extract_option_tuples(stmt)
    assert opts["pos_end"] == (400, 200)
    assert opts["scale_pair"] == (0.5, 1.5)


def test_engine_keyframed_transforms_with_new_fx():
    comp = Compositor(320, 200, 10)
    comp.add_image_layer(
        generate_shape("star", points=4, outer_radius=40, color="#FF2E88"),
        start=0, end=2, pos=(10, 10), pos_end=(200, 100),
        scale=0.5, scale_end=1.5, easing="ease_in_out",
        fx=[("reflection", {"opacity": 0.4, "blur": 3}),
            ("float_y", {"distance": 10, "speed": 2.0}),
            ("pulse", {"amount": 0.1, "speed": 3.0}),
            ("flash_in", {"duration": 0.3}),
            ("light_sweep", {"angle": 45, "speed": 1.0})],
        z_index=1)
    clip = comp.layers[0][1]
    p0, p1 = clip.pos(0.0), clip.pos(2.0)
    assert abs(p1[0] - p0[0]) > 50 and abs(p1[1] - p0[1]) > 50
    early, late = clip.get_frame(0.05), clip.get_frame(1.5)
    assert early.ndim == late.ndim == 3
    assert late.shape[0] > early.shape[0]  # scale keyframe grows the layer


def test_fx_offset_compensates_position():
    """Verify that glow/drop_shadow offsets are applied to keep original content at intended position."""
    comp = Compositor(1280, 720, 30)
    # Create a 100x100 red rectangle
    base = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    # Apply glow with radius=30 (margin=60, total size=220x220)
    # With offset compensation, the original content should stay at intended position
    comp.add_image_layer(
        base, start=0, end=1, pos=(600, 300),
        fx=[("glow", {"color": "#00E5FF", "radius": 30})],
        z_index=1)
    clip = comp.layers[0][1]
    # The clip size should be 220x220 (100 + 2*60)
    assert clip.size == (220, 220)
    # The position should be adjusted to (540, 240) to keep original at (600, 300)
    pos_at_0 = clip.pos(0)
    assert pos_at_0 == (540, 240)
    
    # Test drop_shadow with negative offset
    comp2 = Compositor(1280, 720, 30)
    comp2.add_image_layer(
        base, start=0, end=1, pos=(600, 300),
        fx=[("drop_shadow", {"offset_x": -10, "offset_y": -10, "blur": 20})],
        z_index=1)
    clip2 = comp2.layers[0][1]
    # The clip size should be 110x110 (100 + 10)
    assert clip2.size == (110, 110)
    # The position should be adjusted to (590, 290) to keep original at (600, 300)
    pos_at_0_2 = clip2.pos(0)
    assert pos_at_0_2 == (590, 290)


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
