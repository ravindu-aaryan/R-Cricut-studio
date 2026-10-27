from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.models.layer import Layer, move_layer
from app.models.sticker import StickerDoc
from app.services.asset_service import AssetLibrary
from app.services.sticker_service import RenderContext, render_artboard, render_background, render_sticker
from app.services.text_service import FontRegistry

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    lib = AssetLibrary(ROOT / "assets", tmp_path_factory.mktemp("lib"), ROOT / "assets" / "fonts")
    fonts = FontRegistry(ROOT / "assets" / "fonts", include_system=False)
    return RenderContext(tmp_path_factory.mktemp("proj"), {}, lib, fonts)


def doc_with(*layers, **kw):
    return StickerDoc(width_mm=20, height_mm=20, layers=list(layers), **kw)  # 236 x 236 px


def test_layer_order_top_wins(ctx):
    red = Layer(type="shape", shape="rect", fill="#ff0000", x=118, y=118, width=100, height=100)
    blue = Layer(type="shape", shape="rect", fill="#0000ff", x=118, y=118, width=60, height=60)
    img = render_artboard(doc_with(red, blue), ctx)
    assert img.getpixel((118, 118))[:3] == (0, 0, 255)
    img2 = render_artboard(doc_with(blue, red), ctx)
    assert img2.getpixel((118, 118))[:3] == (255, 0, 0)


def test_transforms_rotation_flip_opacity(ctx):
    bar = Layer(type="shape", shape="rect", fill="#00ff00", x=118, y=118, width=200, height=20, rotation=90)
    img = render_artboard(doc_with(bar), ctx)
    assert img.getpixel((118, 30))[1] > 200 and img.getpixel((30, 118))[3] == 0
    half = Layer(type="shape", shape="rect", fill="#000000", x=118, y=118, width=100, height=100, opacity=0.5)
    a = render_artboard(doc_with(half), ctx).getpixel((118, 118))[3]
    assert 120 < a < 135


def test_group_transform_matches_children(ctx):
    child = Layer(type="shape", shape="rect", fill="#ff00ff", x=40, y=0, width=20, height=20)
    group = Layer(type="group", x=118, y=118, width=100, height=100, rotation=90, children=[child])
    img = render_artboard(doc_with(group), ctx)
    # Child at +40 x rotated 90° clockwise ends up at +40 y.
    assert img.getpixel((118, 158))[:3] == (255, 0, 255)
    assert img.getpixel((158, 118))[3] == 0


def test_text_and_asset_render(ctx):
    text = Layer(type="text", text="Hi", font_family="Luckiest Guy", font_size=60, fill="#123456", x=118, y=118)
    asset = Layer(type="asset", asset_id="star_basic", x=118, y=118, width=150, height=150, colors={"primary": "#00ff00"})
    img = render_artboard(doc_with(asset, text), ctx)
    arr = np.asarray(img)
    assert arr[..., 3].max() == 255
    green = (arr[..., 1] > 200) & (arr[..., 0] < 80) & (arr[..., 3] > 200)
    assert green.sum() > 500  # recoloured asset


def test_curved_text_and_badges(ctx):
    for curve in (120, -120):
        t = Layer(type="text", text="Happy Birthday", font_size=30, x=118, y=118, curve=curve, stroke_width=3,
                  background={"color": "#ffff00", "padding": 4}, shadow={"color": "#00000080", "blur": 2, "offsetX": 2, "offsetY": 2})
        img = render_artboard(doc_with(t), ctx)
        assert np.asarray(img)[..., 3].sum() > 0


def test_finished_sticker_size_includes_border(ctx):
    rect = Layer(type="shape", shape="rect", fill="#ff0000", x=118, y=118, width=118, height=118)
    doc = doc_with(rect)
    doc.border.width_mm = 2
    doc.border.outlines = []
    res = render_sticker(doc, ctx)
    w_mm, h_mm = res.size_mm
    assert w_mm == pytest.approx(10 + 4, abs=0.4)


def test_scaled_render_is_proportional(ctx):
    rect = Layer(type="shape", shape="circle", fill="#ff0000", x=118, y=118, width=150, height=150)
    doc = doc_with(rect)
    a = render_sticker(doc, ctx, 1.0)
    b = render_sticker(doc, ctx, 2.0)
    assert b.image.width == pytest.approx(a.image.width * 2, rel=0.01)
    assert a.size_mm[0] == pytest.approx(b.size_mm[0], abs=0.2)


def test_backgrounds(ctx):
    for bg in ({"type": "solid", "color": "#ff0000"}, {"type": "gradient", "color": "#000000", "color2": "#ffffff", "angle": 90},
               {"type": "pattern", "patternId": "dots", "color": "#ff8800", "patternColor": "#ffffff"}):
        img = render_background(bg, (100, 60), ctx.assets)
        assert img.size == (100, 60) and img.mode == "RGBA"
    g = render_background({"type": "gradient", "color": "#000000", "color2": "#ffffff", "angle": 90}, (100, 10), None)
    assert g.getpixel((2, 5))[0] < 30 and g.getpixel((97, 5))[0] > 225
    assert render_background({"type": "none"}, (10, 10), None) is None


def test_move_layer_order():
    a, b, c = Layer(id="a"), Layer(id="b"), Layer(id="c")
    assert [l.id for l in move_layer([a, b, c], "a", 2)] == ["b", "c", "a"]
    with pytest.raises(KeyError):
        move_layer([a], "zz", 0)


def test_image_layers_scale_uniformly():
    l = Layer.from_dict({"type": "image", "scaleX": 2.0, "scaleY": 1.0, "keepAspect": True})
    assert l.scale_x == l.scale_y == 1.5


def test_effective_dpi_is_independent_of_render_scale(tmp_path):
    from app.services.photo_service import Limits, import_photo
    from tests.fixtures.synthetic import figure_image, jpeg_bytes

    lib = AssetLibrary(ROOT / "assets", tmp_path / "lib")
    photo = import_photo(jpeg_bytes(figure_image((400, 500))), "f.jpg", tmp_path, Limits(10**8, 10**8, 10**5))
    ctx = RenderContext(tmp_path, {photo["id"]: photo}, lib, FontRegistry(ROOT / "assets" / "fonts", include_system=False))
    # 400 px photo shown 50 mm wide -> 400 / (50 / 25.4) = 203 DPI
    w = 50 / 25.4 * 300
    layer = Layer(type="image", photo_id=photo["id"], source="working", x=w / 2, y=w / 2, width=w, height=w * 1.25)
    doc = StickerDoc(width_mm=60, height_mm=70, layers=[layer])
    for scale in (0.25, 1.0):
        res = render_sticker(doc, ctx, scale)
        assert res.min_effective_dpi == pytest.approx(203.2, rel=0.02)
