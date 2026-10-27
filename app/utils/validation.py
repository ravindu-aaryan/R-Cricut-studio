"""Validation of uploaded images and assets.

Validation inspects the real file contents (magic bytes + a full decode),
never the client-supplied name or MIME type alone.
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

# Pillow's own decompression-bomb guard is kept on as a second safety net.
Image.MAX_IMAGE_PIXELS = 200_000_000

SUPPORTED_IMAGE_FORMATS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "TIFF": "tiff",
}

try:  # HEIC is supported only when a local decoder is installed.
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    SUPPORTED_IMAGE_FORMATS["HEIF"] = "heic"
    HEIC_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional package
    HEIC_AVAILABLE = False


class ValidationError(ValueError):
    """Raised for user-correctable input problems. Message is user-facing."""


@dataclass(frozen=True)
class ImageInfo:
    format: str
    extension: str
    width: int
    height: int
    mode: str
    has_alpha: bool
    size_bytes: int


def _sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
        return "HEIF"
    return None


def validate_image_bytes(data: bytes, *, max_bytes: int, max_pixels: int, max_side: int) -> ImageInfo:
    """Validate raw upload bytes and return basic information.

    Raises ``ValidationError`` with a friendly message for anything the
    application cannot or should not process.
    """
    if not data:
        raise ValidationError("The file is empty.")
    if len(data) > max_bytes:
        raise ValidationError(
            f"The file is too large ({len(data) / 1e6:.1f} MB). The limit is {max_bytes / 1e6:.0f} MB."
        )
    sniffed = _sniff(data)
    if sniffed is None:
        raise ValidationError("Unsupported file type. Use JPEG, PNG, WebP or TIFF images.")
    if sniffed == "HEIF" and not HEIC_AVAILABLE:
        raise ValidationError("HEIC photos need the optional pillow-heif decoder, which is not installed.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format or sniffed
                width, height = probe.size
                mode = probe.mode
                if width * height > max_pixels or max(width, height) > max_side:
                    raise ValidationError(
                        f"The image is too large ({width}×{height} px). "
                        f"The limit is {max_side} px per side and {max_pixels / 1e6:.0f} megapixels."
                    )
                probe.verify()
            # verify() leaves the image unusable; decode fully to catch truncation.
            with Image.open(io.BytesIO(data)) as full:
                full.load()
                has_alpha = full.mode in ("RGBA", "LA", "PA") or (
                    full.mode == "P" and "transparency" in full.info
                )
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("The image has too many pixels to process safely.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationError(f"The image appears to be corrupt or incomplete ({type(exc).__name__}).")
    if fmt not in SUPPORTED_IMAGE_FORMATS:
        raise ValidationError(f"Unsupported image format: {fmt}.")
    if fmt != sniffed and not (fmt == "MPO" and sniffed == "JPEG"):
        raise ValidationError("The file contents do not match a supported image type.")
    return ImageInfo(
        format=fmt,
        extension=SUPPORTED_IMAGE_FORMATS[fmt],
        width=width,
        height=height,
        mode=mode,
        has_alpha=has_alpha,
        size_bytes=len(data),
    )


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def as_float(value, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def is_hex_color(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("#"):
        return False
    body = value[1:]
    return len(body) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in body)


def parse_color(value: str, default: tuple[int, int, int, int] = (0, 0, 0, 255)) -> tuple[int, int, int, int]:
    """Parse ``#rgb``, ``#rrggbb`` or ``#rrggbbaa`` into an RGBA tuple."""
    if not is_hex_color(value):
        return default
    body = value[1:]
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    r, g, b = (int(body[i : i + 2], 16) for i in (0, 2, 4))
    a = int(body[6:8], 16) if len(body) == 8 else 255
    return r, g, b, a
