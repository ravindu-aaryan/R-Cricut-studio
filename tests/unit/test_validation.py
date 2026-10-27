import io

import pytest
from PIL import Image

from app.utils.validation import ValidationError, parse_color, validate_image_bytes
from tests.fixtures.synthetic import figure_image, jpeg_bytes, png_bytes, tiff_bytes, transparent_subject, webp_bytes

LIMITS = dict(max_bytes=20_000_000, max_pixels=50_000_000, max_side=10000)


@pytest.mark.parametrize("encoder,fmt", [(jpeg_bytes, "JPEG"), (png_bytes, "PNG"), (webp_bytes, "WEBP"), (tiff_bytes, "TIFF")])
def test_supported_formats(encoder, fmt):
    info = validate_image_bytes(encoder(figure_image((200, 240))), **LIMITS)
    assert info.format == fmt
    assert (info.width, info.height) == (200, 240)


def test_png_alpha_detected():
    info = validate_image_bytes(png_bytes(transparent_subject()), **LIMITS)
    assert info.has_alpha


def test_rejects_non_images():
    with pytest.raises(ValidationError, match="Unsupported"):
        validate_image_bytes(b"GIF89a" + b"0" * 100, **LIMITS)
    with pytest.raises(ValidationError, match="Unsupported"):
        validate_image_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>", **LIMITS)
    with pytest.raises(ValidationError, match="empty"):
        validate_image_bytes(b"", **LIMITS)


def test_rejects_corrupt_and_truncated():
    good = jpeg_bytes(figure_image((300, 300)))
    with pytest.raises(ValidationError, match="corrupt"):
        validate_image_bytes(good[: len(good) // 2], **LIMITS)
    with pytest.raises(ValidationError):
        validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 50, **LIMITS)


def test_size_limits():
    data = png_bytes(Image.new("RGB", (3000, 200)))
    with pytest.raises(ValidationError, match="too large"):
        validate_image_bytes(data, max_bytes=20_000_000, max_pixels=50_000_000, max_side=2000)
    with pytest.raises(ValidationError, match="too large"):
        validate_image_bytes(data, max_bytes=100, max_pixels=50_000_000, max_side=10000)


def test_mismatched_extension_irrelevant():
    # Validation uses contents, not the name: a PNG is accepted as PNG.
    info = validate_image_bytes(png_bytes(figure_image((50, 50))), **LIMITS)
    assert info.extension == "png"


def test_parse_color():
    assert parse_color("#fff") == (255, 255, 255, 255)
    assert parse_color("#11223344") == (0x11, 0x22, 0x33, 0x44)
    assert parse_color("red", (1, 2, 3, 4)) == (1, 2, 3, 4)
