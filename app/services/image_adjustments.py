"""Non-destructive photo adjustments and filters.

Every function takes an RGBA ``PIL.Image`` and returns a new image; the
input is never modified. ``apply_adjustments`` runs a parameter dict (as
stored in the project document) through the pipeline in a fixed order, so
the same parameters always produce the same result from the original.

The alpha channel is carried through unchanged by colour operations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from ..utils.validation import as_float, parse_color

DEFAULT_ADJUSTMENTS: dict[str, Any] = {
    "brightness": 0.0,   # -1..1
    "contrast": 0.0,     # -1..1
    "saturation": 0.0,   # -1..1
    "temperature": 0.0,  # -1 (cool) .. 1 (warm)
    "exposure": 0.0,     # stops, -2..2
    "highlights": 0.0,   # -1..1
    "shadows": 0.0,      # -1..1
    "sharpness": 0.0,    # 0..2
    "blur": 0.0,         # radius px at preview scale is scaled by caller
    "filter": "none",    # none|grayscale|sepia|bw|posterize|cartoon|duotone
    "posterizeLevels": 5,
    "duotoneDark": "#2b1055",
    "duotoneLight": "#ffd36e",
    "bwThreshold": 128,
    "vignette": 0.0,     # 0..1
}

FILTERS = ("none", "grayscale", "sepia", "bw", "posterize", "cartoon", "duotone")


def _split(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    img = img.convert("RGBA")
    return img.convert("RGB"), img.getchannel("A")


def _merge(rgb: Image.Image, alpha: Image.Image) -> Image.Image:
    out = rgb.convert("RGB")
    out.putalpha(alpha)
    return out


def _to_float(rgb: Image.Image) -> np.ndarray:
    return np.asarray(rgb, dtype=np.float32) / 255.0


def _from_float(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


def brightness(img: Image.Image, amount: float) -> Image.Image:
    rgb, a = _split(img)
    return _merge(ImageEnhance.Brightness(rgb).enhance(1.0 + amount), a)


def contrast(img: Image.Image, amount: float) -> Image.Image:
    rgb, a = _split(img)
    return _merge(ImageEnhance.Contrast(rgb).enhance(1.0 + amount), a)


def saturation(img: Image.Image, amount: float) -> Image.Image:
    rgb, a = _split(img)
    return _merge(ImageEnhance.Color(rgb).enhance(1.0 + amount), a)


def sharpness(img: Image.Image, amount: float) -> Image.Image:
    rgb, a = _split(img)
    return _merge(ImageEnhance.Sharpness(rgb).enhance(1.0 + amount), a)


def exposure(img: Image.Image, stops: float) -> Image.Image:
    rgb, a = _split(img)
    arr = _to_float(rgb)
    # Work in approximately linear light so exposure behaves like a camera.
    lin = np.power(arr, 2.2) * (2.0 ** stops)
    return _merge(_from_float(np.power(np.clip(lin, 0, 1), 1 / 2.2)), a)


def temperature(img: Image.Image, amount: float) -> Image.Image:
    rgb, a = _split(img)
    arr = _to_float(rgb)
    k = 0.12 * amount
    arr[..., 0] *= 1 + k
    arr[..., 2] *= 1 - k
    arr[..., 1] *= 1 + k * 0.15
    return _merge(_from_float(arr), a)


def highlights_shadows(img: Image.Image, highlights: float, shadows: float) -> Image.Image:
    rgb, a = _split(img)
    arr = _to_float(rgb)
    lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    shadow_w = np.clip(1.0 - lum / 0.5, 0, 1)[..., None] ** 2
    high_w = np.clip((lum - 0.5) / 0.5, 0, 1)[..., None] ** 2
    arr = arr + shadows * 0.35 * shadow_w * (1 - arr) * 1.0 + highlights * 0.35 * high_w * (arr if highlights < 0 else (1 - arr))
    return _merge(_from_float(arr), a)


def blur(img: Image.Image, radius: float) -> Image.Image:
    if radius <= 0:
        return img.copy()
    rgb, a = _split(img)
    return _merge(rgb.filter(ImageFilter.GaussianBlur(radius)), a)


def grayscale(img: Image.Image) -> Image.Image:
    rgb, a = _split(img)
    return _merge(ImageOps.grayscale(rgb).convert("RGB"), a)


def sepia(img: Image.Image) -> Image.Image:
    rgb, a = _split(img)
    arr = _to_float(rgb)
    m = np.array([[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]], dtype=np.float32)
    return _merge(_from_float(arr @ m.T), a)


def black_and_white(img: Image.Image, threshold: int = 128) -> Image.Image:
    rgb, a = _split(img)
    g = ImageOps.grayscale(rgb).point(lambda v: 255 if v >= threshold else 0)
    return _merge(g.convert("RGB"), a)


def posterize(img: Image.Image, levels: int = 5) -> Image.Image:
    rgb, a = _split(img)
    levels = int(max(2, min(16, levels)))
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    q = np.round(arr * (levels - 1)) / (levels - 1)
    return _merge(_from_float(q), a)


def cartoon(img: Image.Image, levels: int = 6) -> Image.Image:
    """Cartoon-like look: edge-preserving smoothing, colour quantisation, ink edges.

    Purely conventional filtering (bilateral filter + adaptive threshold);
    no generative model is involved.
    """
    import cv2

    rgb, a = _split(img)
    arr = np.asarray(rgb)
    smooth = arr
    for _ in range(2):
        smooth = cv2.bilateralFilter(smooth, d=9, sigmaColor=60, sigmaSpace=9)
    levels = int(max(3, min(12, levels)))
    q = (np.round(smooth.astype(np.float32) / 255 * (levels - 1)) / (levels - 1) * 255).astype(np.uint8)
    gray = cv2.medianBlur(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), 7)
    block = max(3, (min(arr.shape[:2]) // 60) | 1)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, 6)
    out = cv2.bitwise_and(q, q, mask=edges)
    return _merge(Image.fromarray(out, "RGB"), a)


def duotone(img: Image.Image, dark: str, light: str) -> Image.Image:
    rgb, a = _split(img)
    g = ImageOps.grayscale(rgb)
    d, l = parse_color(dark)[:3], parse_color(light)[:3]
    return _merge(ImageOps.colorize(g, black=d, white=l), a)


def vignette(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img.copy()
    rgb, a = _split(img)
    w, h = rgb.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = (xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)
    r = np.sqrt(nx * nx + ny * ny) / np.sqrt(2)
    mask = 1.0 - amount * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6
    arr = _to_float(rgb) * mask[..., None]
    return _merge(_from_float(arr), a)


def apply_filter(img: Image.Image, params: dict) -> Image.Image:
    name = params.get("filter", "none")
    if name == "grayscale":
        return grayscale(img)
    if name == "sepia":
        return sepia(img)
    if name == "bw":
        return black_and_white(img, int(as_float(params.get("bwThreshold"), 128, 1, 254)))
    if name == "posterize":
        return posterize(img, int(as_float(params.get("posterizeLevels"), 5, 2, 16)))
    if name == "cartoon":
        return cartoon(img, int(as_float(params.get("posterizeLevels"), 6, 3, 12)))
    if name == "duotone":
        return duotone(img, params.get("duotoneDark", "#2b1055"), params.get("duotoneLight", "#ffd36e"))
    return img


def normalize_adjustments(params: dict | None) -> dict:
    out = dict(DEFAULT_ADJUSTMENTS)
    for key, value in (params or {}).items():
        if key in out:
            out[key] = value
    if out["filter"] not in FILTERS:
        out["filter"] = "none"
    return out


def is_identity(params: dict | None) -> bool:
    p = normalize_adjustments(params)
    return all(p[k] == DEFAULT_ADJUSTMENTS[k] for k in DEFAULT_ADJUSTMENTS)


def apply_adjustments(img: Image.Image, params: dict | None, *, scale: float = 1.0,
                      protect_mask: Image.Image | None = None) -> Image.Image:
    """Apply the full adjustment pipeline.

    ``scale`` adjusts pixel-radius parameters (blur) so previews and full
    renders look alike. ``protect_mask`` (L mode, 255 = protected) keeps the
    original pixels inside the region, e.g. to leave a face untouched by
    colour filters.
    """
    p = normalize_adjustments(params)
    src = img.convert("RGBA")
    out = src
    if p["exposure"]:
        out = exposure(out, as_float(p["exposure"], 0, -3, 3))
    if p["brightness"]:
        out = brightness(out, as_float(p["brightness"], 0, -1, 1))
    if p["contrast"]:
        out = contrast(out, as_float(p["contrast"], 0, -1, 1))
    if p["highlights"] or p["shadows"]:
        out = highlights_shadows(out, as_float(p["highlights"], 0, -1, 1), as_float(p["shadows"], 0, -1, 1))
    if p["saturation"]:
        out = saturation(out, as_float(p["saturation"], 0, -1, 1))
    if p["temperature"]:
        out = temperature(out, as_float(p["temperature"], 0, -1, 1))
    out = apply_filter(out, p)
    if p["sharpness"]:
        out = sharpness(out, as_float(p["sharpness"], 0, 0, 3))
    if p["blur"]:
        out = blur(out, as_float(p["blur"], 0, 0, 50) * scale)
    if p["vignette"]:
        out = vignette(out, as_float(p["vignette"], 0, 0, 1))
    if protect_mask is not None and out is not src:
        m = protect_mask.convert("L").resize(out.size)
        rgb = Image.composite(src.convert("RGB"), out.convert("RGB"), m)
        out = _merge(rgb, out.getchannel("A"))
    return out
