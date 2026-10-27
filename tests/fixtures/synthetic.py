"""Synthetic test images. No real photographs are used in automated tests."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter


def figure_image(size=(800, 1000), bg=(90, 160, 210)) -> Image.Image:
    """A simple 'person' figure (head + body) on a textured background."""
    w, h = size
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    for i in range(0, h, 40):  # background stripes make segmentation non-trivial
        d.rectangle((0, i, w, i + 18), fill=(bg[0] - 20, bg[1] - 15, bg[2] - 10))
    cx = w // 2
    d.ellipse((cx - 250, int(h * 0.48), cx + 250, int(h * 1.25)), fill=(230, 80, 60))  # shirt
    d.ellipse((cx - 140, int(h * 0.14), cx + 140, int(h * 0.50)), fill=(240, 200, 160))  # face
    d.ellipse((cx - 150, int(h * 0.10), cx + 150, int(h * 0.26)), fill=(70, 45, 30))  # hair
    d.ellipse((cx - 70, int(h * 0.30), cx - 40, int(h * 0.33)), fill=(40, 40, 40))  # eyes
    d.ellipse((cx + 40, int(h * 0.30), cx + 70, int(h * 0.33)), fill=(40, 40, 40))
    d.arc((cx - 60, int(h * 0.36), cx + 60, int(h * 0.43)), 10, 170, fill=(150, 40, 40), width=6)
    return img.filter(ImageFilter.GaussianBlur(0.8))


def jpeg_bytes(img: Image.Image, orientation: int | None = None, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    kwargs = {}
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs["exif"] = exif.tobytes()
    img.convert("RGB").save(buf, "JPEG", quality=quality, **kwargs)
    return buf.getvalue()


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def transparent_subject(size=(400, 500)) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse((w * 0.2, h * 0.05, w * 0.8, h * 0.5), fill=(240, 200, 160, 255))
    d.rectangle((w * 0.15, h * 0.45, w * 0.85, h * 0.98), fill=(60, 120, 220, 255))
    return img


def webp_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=90)
    return buf.getvalue()


def tiff_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "TIFF")
    return buf.getvalue()
