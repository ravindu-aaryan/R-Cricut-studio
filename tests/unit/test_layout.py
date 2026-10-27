import pytest

from app.models.layout import PTC_H_MM, PTC_W_MM, Sheet, SheetItem, SheetPage
from app.services import layout_service as ls


def items(pages):
    return [it for p in pages for it in p.items]


def no_overlaps(pages, gap=0.0):
    for p in pages:
        for i, a in enumerate(p.items):
            for b in p.items[i + 1:]:
                assert not ls.rects_overlap(a, b), (a, b)


def inside(sheet, pages):
    x0, y0, x1, y1 = sheet.content_rect()
    for it in items(pages):
        bx0, by0, bx1, by1 = it.bbox()
        assert bx0 >= x0 - 1e-6 and by0 >= y0 - 1e-6 and bx1 <= x1 + 1e-6 and by1 <= y1 + 1e-6


def test_grid_layout_counts_and_bounds():
    sheet = Sheet(margin_mm=8, gap_mm=4)
    pages = ls.grid_layout(sheet, [ls.Request("s", 50, 50, 12)])
    # content 184 x 271 mm -> 3 columns x 5 rows of 50 mm with 4 mm gaps
    assert len(pages) == 1 and len(pages[0].items) == 12
    no_overlaps(pages)
    inside(sheet, pages)
    many = ls.grid_layout(sheet, [ls.Request("s", 50, 50, 20)])
    assert len(many) == 2 and len(many[0].items) == 15


def test_pack_layout_mixed_sizes_multi_page():
    sheet = Sheet(margin_mm=5, gap_mm=3)
    reqs = [ls.Request("a", 80, 60, 3), ls.Request("b", 40, 40, 8), ls.Request("c", 30, 70, 5)]
    pages = ls.pack_layout(sheet, reqs)
    assert len(items(pages)) == 16
    no_overlaps(pages)
    inside(sheet, pages)
    for p in pages:
        for i, a in enumerate(p.items):
            for b in p.items[i + 1:]:
                ax0, ay0, ax1, ay1 = a.bbox()
                bx0, by0, bx1, by1 = b.bbox()
                sep = max(bx0 - ax1, ax0 - bx1, by0 - ay1, ay0 - by1)
                assert sep >= 3 - 1e-6


def test_pack_is_more_efficient_than_grid_for_mixed_sizes():
    sheet = Sheet(margin_mm=5, gap_mm=2)
    reqs = [ls.Request("big", 90, 90, 2), ls.Request("small", 30, 30, 20)]
    assert len(ls.pack_layout(sheet, reqs)) <= len(ls.grid_layout(sheet, reqs))


def test_oversized_sticker_is_rejected():
    with pytest.raises(ValueError, match="does not fit"):
        ls.pack_layout(Sheet(), [ls.Request("x", 300, 300)])


def test_fit_to_page():
    sheet = Sheet(margin_mm=5, gap_mm=2)
    scale, pages = ls.fit_to_page(sheet, [ls.Request("a", 100, 100, 12)])
    assert len(pages) == 1 and len(pages[0].items) == 12 and scale < 1
    no_overlaps(pages)


def test_fill_page():
    sheet = Sheet(margin_mm=5, gap_mm=2)
    pages = ls.fill_page(sheet, ["a", "b"], {"a": (40, 40), "b": (30, 50)})
    assert len(pages) == 1
    ids = {it.sticker_id for it in pages[0].items}
    assert ids == {"a", "b"} and len(pages[0].items) > 10


def test_printable_presets():
    s = Sheet()
    s.printable.preset = "cricut_ptc"
    x0, y0, x1, y1 = s.printable_rect()
    assert x1 - x0 == pytest.approx(PTC_W_MM) and y1 - y0 == pytest.approx(PTC_H_MM)
    s.printable.preset = "full"
    assert s.printable_rect() == (0, 0, 210, 297)


def test_validation_warnings():
    s = Sheet()
    info = {"a": {"name": "A", "widthMm": 50, "minEffectiveDpi": 300}, "lo": {"name": "Lo", "widthMm": 50, "minEffectiveDpi": 120}}
    s.pages = [SheetPage(items=[
        SheetItem(id="1", sticker_id="a", x_mm=20, y_mm=20, width_mm=50, height_mm=50),
        SheetItem(id="2", sticker_id="a", x_mm=40, y_mm=40, width_mm=50, height_mm=50),  # overlaps 1
        SheetItem(id="3", sticker_id="a", x_mm=1, y_mm=200, width_mm=50, height_mm=50),  # outside printable (5 mm)
        SheetItem(id="4", sticker_id="a", x_mm=180, y_mm=100, width_mm=50, height_mm=50),  # off page
        SheetItem(id="5", sticker_id="lo", x_mm=100, y_mm=150, width_mm=50, height_mm=50),  # low res
        SheetItem(id="6", sticker_id="gone", x_mm=100, y_mm=220, width_mm=20, height_mm=20),
    ])]
    codes = {(w["code"], w["itemId"]) for w in ls.validate_sheet(s, info)}
    assert ("overlap", "1") in codes
    assert ("outside-printable", "3") in codes
    assert ("off-page", "4") in codes
    assert ("low-res", "5") in codes
    assert ("missing", "6") in codes


def test_rotated_overlap_sat():
    a = SheetItem(x_mm=0, y_mm=0, width_mm=40, height_mm=10)
    b = SheetItem(x_mm=15, y_mm=-15, width_mm=40, height_mm=10, rotation=90)
    c = SheetItem(x_mm=60, y_mm=0, width_mm=10, height_mm=10)
    assert ls.rects_overlap(a, b)
    assert not ls.rects_overlap(a, c)
