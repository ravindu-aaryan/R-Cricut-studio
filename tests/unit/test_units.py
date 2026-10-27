import math

import pytest

from app.utils.image_dimensions import A4_PORTRAIT_MM, a4, effective_dpi, mm_to_pt, mm_to_px, mm_to_px_int, pt_to_mm, px_to_mm


def test_mm_to_px_formula():
    assert mm_to_px(25.4, 300) == pytest.approx(300)
    assert mm_to_px(10, 300) == pytest.approx(10 / 25.4 * 300)
    assert mm_to_px_int(60, 300) == 709


def test_roundtrip():
    for mm in (1, 12.5, 60, 210, 297):
        assert px_to_mm(mm_to_px(mm, 300), 300) == pytest.approx(mm)
        assert pt_to_mm(mm_to_pt(mm)) == pytest.approx(mm)


def test_a4_dimensions_at_300_dpi():
    assert A4_PORTRAIT_MM == (210.0, 297.0)
    assert a4("portrait").px(300) == (2480, 3508)
    assert a4("landscape").px(300) == (3508, 2480)


def test_a4_points():
    w, h = a4("portrait").pt()
    assert w == pytest.approx(595.2756, abs=1e-3)
    assert h == pytest.approx(841.8898, abs=1e-3)


def test_invalid_orientation():
    with pytest.raises(ValueError):
        a4("sideways")


def test_effective_dpi():
    assert effective_dpi(709, 60) == pytest.approx(300, abs=0.5)
    assert math.isinf(effective_dpi(100, 0))
