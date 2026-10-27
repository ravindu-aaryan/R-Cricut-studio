import numpy as np
import pytest
from PIL import Image

from app.services import image_adjustments as adj
from tests.fixtures.synthetic import figure_image, transparent_subject


@pytest.fixture()
def rgba():
    img = transparent_subject((120, 150))
    base = figure_image((120, 150)).convert("RGBA")
    base.putalpha(img.getchannel("A"))
    return base


def test_identity_returns_equal_pixels(rgba):
    out = adj.apply_adjustments(rgba, {})
    assert np.array_equal(np.asarray(out), np.asarray(rgba))
    assert adj.is_identity({}) and not adj.is_identity({"brightness": 0.2})


@pytest.mark.parametrize("params", [
    {"brightness": 0.3}, {"contrast": -0.4}, {"saturation": 0.5}, {"temperature": 0.6}, {"exposure": 1.0},
    {"highlights": -0.5, "shadows": 0.5}, {"sharpness": 1.5}, {"blur": 3}, {"vignette": 0.6},
    {"filter": "grayscale"}, {"filter": "sepia"}, {"filter": "bw"}, {"filter": "posterize", "posterizeLevels": 4},
    {"filter": "cartoon"}, {"filter": "duotone"},
])
def test_each_adjustment_keeps_size_and_alpha(rgba, params):
    out = adj.apply_adjustments(rgba, params)
    assert out.size == rgba.size and out.mode == "RGBA"
    assert np.array_equal(np.asarray(out.getchannel("A")), np.asarray(rgba.getchannel("A")))
    assert not np.array_equal(np.asarray(out.convert("RGB")), np.asarray(rgba.convert("RGB")))


def test_grayscale_is_neutral(rgba):
    arr = np.asarray(adj.apply_adjustments(rgba, {"filter": "grayscale"}).convert("RGB")).astype(int)
    assert np.abs(arr[..., 0] - arr[..., 1]).max() <= 1


def test_posterize_levels(rgba):
    arr = np.asarray(adj.posterize(rgba, 3).convert("RGB"))
    assert len(np.unique(arr[..., 0])) <= 3


def test_face_protection_keeps_original_pixels(rgba):
    mask = Image.new("L", rgba.size, 0)
    mask.paste(255, (30, 30, 90, 90))
    out = adj.apply_adjustments(rgba, {"filter": "sepia", "saturation": 0.8}, protect_mask=mask)
    a, b = np.asarray(out.convert("RGB")), np.asarray(rgba.convert("RGB"))
    assert np.array_equal(a[40:80, 40:80], b[40:80, 40:80])
    assert not np.array_equal(a[0:20, 0:20], b[0:20, 0:20]) or (b[0:20, 0:20] == 0).all()


def test_unknown_filter_ignored(rgba):
    p = adj.normalize_adjustments({"filter": "deepdream", "nonsense": 1})
    assert p["filter"] == "none" and "nonsense" not in p


def test_subject_and_background_targets(rgba):
    subject = Image.new("L", rgba.size, 0)
    subject.paste(255, (0, 0, 60, 150))  # left half is "subject"
    base = np.asarray(rgba.convert("RGB"))
    only_subject = np.asarray(adj.apply_adjustments(rgba, {"filter": "sepia", "target": "subject"}, subject_mask=subject).convert("RGB"))
    assert np.array_equal(only_subject[:, 70:], base[:, 70:])
    assert not np.array_equal(only_subject[:, :50], base[:, :50])
    only_bg = np.asarray(adj.apply_adjustments(rgba, {"filter": "sepia", "target": "background"}, subject_mask=subject).convert("RGB"))
    assert np.array_equal(only_bg[:, :50], base[:, :50])
