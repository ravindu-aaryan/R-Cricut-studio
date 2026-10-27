import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services import outline_service as ol


def art_disc(size=300, r=80, holes=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size // 2
    d.ellipse((c - r, c - r, c + r, c + r), fill=(200, 40, 40, 255))
    if holes:
        d.ellipse((c - 20, c - 20, c + 20, c + 20), fill=(0, 0, 0, 0))
    return img


def test_expand_is_exact_distance():
    m = np.zeros((200, 200), np.uint8)
    m[100, 100] = 255
    grown = ol.expand(m, 30)
    ys, xs = np.nonzero(grown)
    assert xs.max() - 100 == 30 and 100 - xs.min() == 30
    shrunk = ol.expand(ol.expand(m, 40), -10)
    assert np.count_nonzero(shrunk) < np.count_nonzero(ol.expand(m, 40))


def test_border_width_matches_request():
    art = art_disc()
    spec = ol.StickerSpec(border_px=25, smoothing=0)
    res = ol.build_sticker(art, spec)
    # Disc diameter 160 + 2 * 25 border = 210 px cut width.
    ys, xs = np.nonzero(res.cut_mask)
    assert xs.max() - xs.min() + 1 == pytest.approx(211, abs=3)


def test_outline_layers_grow_outward_with_gap():
    art = art_disc()
    spec = ol.StickerSpec(border_px=20, smoothing=0, outlines=(ol.OutlineLayer(6, (255, 0, 0, 255)), ol.OutlineLayer(5, (0, 0, 255, 255), gap_px=4)))
    res = ol.build_sticker(art, spec)
    ys, xs = np.nonzero(res.cut_mask)
    assert xs.max() - xs.min() + 1 == pytest.approx(161 + 2 * (20 + 6 + 4 + 5), abs=4)
    arr = np.asarray(res.image)
    row = arr[arr.shape[0] // 2]
    reds = [i for i in range(len(row)) if row[i][0] > 200 and row[i][2] < 60 and row[i][3] > 200]
    blues = [i for i in range(len(row)) if row[i][2] > 200 and row[i][0] < 60 and row[i][3] > 200]
    assert blues and reds and min(blues) < min(reds)  # blue ring is outermost
    gap = [i for i in range(min(blues), min(reds)) if row[i][3] < 40]
    assert gap, "transparent gap between outline layers"


def test_art_is_never_overwritten():
    art = art_disc()
    res = ol.build_sticker(art, ol.StickerSpec(border_px=15, outlines=(ol.OutlineLayer(4, (0, 0, 255, 255)),)))
    ox, oy = res.art_offset  # may be negative: transparent art padding is trimmed
    out = np.asarray(res.image)
    src = np.asarray(art)
    ys, xs = np.nonzero(src[..., 3] == 255)
    assert np.array_equal(out[ys + oy, xs + ox][:, :3], src[ys, xs][:, :3])


def test_holes_filled_or_kept():
    art = art_disc(holes=True)
    filled = ol.build_sticker(art, ol.StickerSpec(border_px=5, fill_holes=True))
    assert filled.cut_mask[filled.cut_mask.shape[0] // 2, filled.cut_mask.shape[1] // 2] == 255
    kept = ol.build_sticker(art, ol.StickerSpec(border_px=5, fill_holes=False, smoothing=0))
    assert kept.cut_mask[kept.cut_mask.shape[0] // 2, kept.cut_mask.shape[1] // 2] == 0


def test_disconnected_pieces_are_bridged():
    art = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)
    d.ellipse((20, 50, 120, 150), fill=(0, 200, 0, 255))
    d.ellipse((250, 50, 350, 150), fill=(0, 0, 200, 255))
    joined = ol.build_sticker(art, ol.StickerSpec(border_px=10, bridge_gaps=True))
    assert joined.pieces == 1
    separate = ol.build_sticker(art, ol.StickerSpec(border_px=10, bridge_gaps=False))
    assert separate.pieces == 2 and separate.warnings


@pytest.mark.parametrize("shape", ["circle", "oval", "rounded", "rect", "square", "heart", "star", "speech"])
def test_shape_masks(shape):
    m = ol.shape_mask(shape, (300, 200), (0, 0, 300, 200), corner_radius=30)
    assert m.shape == (200, 300)
    frac = (m > 127).mean()
    assert 0.2 < frac <= 1.0
    if shape == "circle":
        ys, xs = np.nonzero(m > 127)
        assert xs.max() - xs.min() == pytest.approx(ys.max() - ys.min(), abs=2)


def test_shape_sticker_clips_art_and_fills_background():
    art = Image.new("RGBA", (300, 300), (255, 0, 0, 255))
    bg = Image.new("RGBA", (300, 300), (0, 255, 0, 255))
    res = ol.build_sticker(art, ol.StickerSpec(shape="circle", border_px=20, background=bg))
    arr = np.asarray(res.image)
    h, w = arr.shape[:2]
    assert arr[2, 2, 3] == 0  # outside the circle is transparent
    assert tuple(arr[h // 2, w // 2, :3]) == (255, 0, 0)
    assert res.cut_mask[h // 2, 5] in (0, 255)


def test_cut_offset_changes_cut_only():
    art = art_disc()
    base = ol.build_sticker(art, ol.StickerSpec(border_px=10))
    inset = ol.build_sticker(art, ol.StickerSpec(border_px=10, cut_offset_px=-4))
    assert np.count_nonzero(inset.cut_mask) < np.count_nonzero(base.cut_mask)


def test_empty_art_raises():
    with pytest.raises(ValueError):
        ol.build_sticker(Image.new("RGBA", (50, 50)), ol.StickerSpec())
