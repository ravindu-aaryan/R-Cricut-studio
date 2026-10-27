"""Photo import, working copies, previews and geometric edits.

The original upload is stored byte-for-byte and never modified. A working
copy (EXIF orientation applied, geometric edits applied, PNG) is derived
from it whenever the edits change, so quality never degrades through
repeated saves. Colour adjustments are not baked into the working copy;
they are applied at render time from the stored parameters.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from ..models.base import new_id
from ..utils.paths import sanitize_filename
from ..utils.validation import ImageInfo, ValidationError, validate_image_bytes

DEFAULT_EDITS = {"rotate": 0, "angle": 0.0, "flipH": False, "flipV": False, "crop": None, "resizeMaxSide": None}


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_pixels: int
    max_side: int
    preview_side: int = 1600
    thumb_side: int = 320


def photo_paths(project_dir: Path, photo: dict) -> dict[str, Path]:
    pid = photo["id"]
    return {
        "original": project_dir / photo["original"],
        "working": project_dir / "working" / f"{pid}.png",
        "preview": project_dir / "previews" / f"{pid}.png",
        "thumb": project_dir / "thumbs" / f"{pid}.png",
        "mask": project_dir / "masks" / f"{pid}.png",
        "hints": project_dir / "masks" / f"{pid}_hints.png",
        "subject": project_dir / "subjects" / f"{pid}.png",
        "subject_preview": project_dir / "subjects" / f"{pid}_preview.png",
    }


def open_original(path: Path) -> Image.Image:
    """Open an original upload with EXIF orientation applied, as RGB or RGBA."""
    with Image.open(path) as im:
        im.load()
        img = ImageOps.exif_transpose(im)
        if img is im:
            img = im.copy()
    return normalize_mode(img)


def normalize_mode(img: Image.Image) -> Image.Image:
    """Convert any mode to RGB or RGBA while keeping transparency."""
    if img.mode == "RGBA":
        return img
    if img.mode in ("LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        return img.convert("RGBA")
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(img, dtype=np.float32)
        arr = arr / max(1.0, float(arr.max())) * 255.0
        return Image.fromarray(arr.astype(np.uint8), "L").convert("RGB")
    if img.mode == "CMYK":
        return img.convert("RGB")
    return img.convert("RGB") if img.mode != "RGB" else img


def apply_geometric_edits(img: Image.Image, edits: dict | None) -> Image.Image:
    e = {**DEFAULT_EDITS, **(edits or {})}
    out = img
    rot = int(e.get("rotate") or 0) % 360
    if rot in (90, 180, 270):
        out = out.rotate(-rot, expand=True)  # clockwise
    angle = float(e.get("angle") or 0.0)
    if abs(angle) > 0.01:
        rgba = out.convert("RGBA")
        out = rgba.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
        if img.mode == "RGB":
            # Fill the corners exposed by a fine rotation with white instead of black.
            bg = Image.new("RGBA", out.size, (255, 255, 255, 255))
            bg.alpha_composite(out)
            out = bg.convert("RGB")
    if e.get("flipH"):
        out = ImageOps.mirror(out)
    if e.get("flipV"):
        out = ImageOps.flip(out)
    crop = e.get("crop")
    if crop:
        w, h = out.size
        x0 = int(round(max(0.0, min(1.0, float(crop["x"]))) * w))
        y0 = int(round(max(0.0, min(1.0, float(crop["y"]))) * h))
        x1 = int(round(max(0.0, min(1.0, float(crop["x"]) + float(crop["w"]))) * w))
        y1 = int(round(max(0.0, min(1.0, float(crop["y"]) + float(crop["h"]))) * h))
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            out = out.crop((x0, y0, x1, y1))
    max_side = e.get("resizeMaxSide")
    if max_side:
        max_side = int(max_side)
        if 32 <= max_side < max(out.size):
            # Downscale only. Upscaling would invent detail and is refused.
            out = out.copy()
            out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out


def fit_within(img: Image.Image, max_side: int) -> Image.Image:
    if max(img.size) <= max_side:
        return img.copy()
    out = img.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out


def save_png(img: Image.Image, path: Path, dpi: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    kwargs = {"optimize": False, "compress_level": 6}
    if dpi:
        kwargs["dpi"] = (dpi, dpi)
    img.save(tmp, "PNG", **kwargs)
    os.replace(tmp, path)


def make_thumbnail(img: Image.Image, side: int) -> Image.Image:
    thumb = fit_within(img, side)
    if thumb.mode != "RGBA":
        thumb = thumb.convert("RGBA")
    return thumb


def import_photo(data: bytes, original_name: str, project_dir: Path, limits: Limits) -> dict:
    """Validate and store a photo, returning its project record."""
    info: ImageInfo = validate_image_bytes(
        data, max_bytes=limits.max_bytes, max_pixels=limits.max_pixels, max_side=limits.max_side
    )
    photo_id = new_id("ph_")
    safe_name = sanitize_filename(original_name or f"photo.{info.extension}", default=f"photo.{info.extension}")
    rel_original = f"originals/{photo_id}.{info.extension}"
    orig_path = project_dir / rel_original
    orig_path.parent.mkdir(parents=True, exist_ok=True)
    orig_path.write_bytes(data)  # exact original bytes, never modified
    photo = {
        "id": photo_id,
        "name": Path(safe_name).stem[:80] or "Photo",
        "originalName": safe_name,
        "original": rel_original,
        "format": info.format,
        "sizeBytes": info.size_bytes,
        "originalWidth": info.width,
        "originalHeight": info.height,
        "hasAlpha": info.has_alpha,
        "importedAt": datetime.now(timezone.utc).isoformat(),
        "edits": dict(DEFAULT_EDITS),
        "adjustments": {},
        "background": {"type": "keep"},
        "mask": None,
        "maskMethod": None,
        "faceRegions": [],
        "protectFace": True,
    }
    try:
        rebuild_working(project_dir, photo, limits)
    except Exception:
        orig_path.unlink(missing_ok=True)
        raise
    try:
        faces = detect_faces(Image.open(photo_paths(project_dir, photo)["preview"]))
        scale = photo["width"] / max(1, Image.open(photo_paths(project_dir, photo)["preview"]).size[0])
        photo["faceRegions"] = [
            {"x": int(f[0] * scale), "y": int(f[1] * scale), "w": int(f[2] * scale), "h": int(f[3] * scale),
             "source": "auto"}
            for f in faces
        ]
    except Exception:  # face suggestions are optional
        photo["faceRegions"] = []
    return photo


def rebuild_working(project_dir: Path, photo: dict, limits: Limits) -> dict:
    """(Re)create the working copy, preview and thumbnail from the original."""
    paths = photo_paths(project_dir, photo)
    img = open_original(paths["original"])
    img = apply_geometric_edits(img, photo.get("edits"))
    save_png(img, paths["working"])
    preview = fit_within(img, limits.preview_side)
    save_png(preview, paths["preview"])
    save_png(make_thumbnail(img, limits.thumb_side), paths["thumb"])
    photo["width"], photo["height"] = img.size
    photo["previewWidth"], photo["previewHeight"] = preview.size
    photo["hasAlpha"] = img.mode == "RGBA"
    return photo


def load_working(project_dir: Path, photo: dict, max_side: int | None = None) -> Image.Image:
    path = photo_paths(project_dir, photo)["working"]
    with Image.open(path) as im:
        if max_side and max(im.size) > max_side:
            im.draft(im.mode, (max_side, max_side))
            out = im.copy()
            out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            return normalize_mode(out)
        im.load()
        return normalize_mode(im.copy())


def image_to_png_bytes(img: Image.Image, dpi: int | None = None) -> bytes:
    buf = io.BytesIO()
    kwargs = {"dpi": (dpi, dpi)} if dpi else {}
    img.save(buf, "PNG", **kwargs)
    return buf.getvalue()


_FACE_CASCADE = None


def detect_faces(img: Image.Image, max_side: int = 900) -> list[tuple[int, int, int, int]]:
    """Suggest face rectangles with OpenCV's bundled Haar cascade.

    Only used to *suggest* a protected region; users can edit or remove it.
    Returns rectangles (x, y, w, h) in ``img`` coordinates.
    """
    import cv2

    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if not os.path.exists(path):
            return []
        _FACE_CASCADE = cv2.CascadeClassifier(path)
    small = fit_within(img.convert("RGB"), max_side)
    scale = img.size[0] / small.size[0]
    gray = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    min_side = max(24, min(gray.shape) // 12)
    found = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_side, min_side))
    out = []
    for (x, y, w, h) in (found if len(found) else []):
        # Expand a little: cascades frame the face tightly; include hair and chin.
        pad_w, pad_h = 0.25 * w, 0.35 * h
        out.append((int((x - pad_w) * scale), int((y - pad_h) * scale), int((w + 2 * pad_w) * scale), int((h + 2 * pad_h) * scale)))
    return out[:6]


def face_mask(size: tuple[int, int], regions: list[dict], feather: float = 0.15) -> Image.Image | None:
    """L-mode mask with soft ellipses over protected face regions."""
    from PIL import ImageDraw, ImageFilter

    if not regions:
        return None
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for r in regions:
        d.ellipse((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]), fill=255)
    rad = max(1.0, feather * min(r["w"] for r in regions) / 2)
    return m.filter(ImageFilter.GaussianBlur(rad))


def validate_only(data: bytes, limits: Limits) -> ImageInfo:
    return validate_image_bytes(data, max_bytes=limits.max_bytes, max_pixels=limits.max_pixels, max_side=limits.max_side)


__all__ = [
    "Limits", "ValidationError", "import_photo", "rebuild_working", "load_working", "photo_paths",
    "apply_geometric_edits", "open_original", "detect_faces", "face_mask", "save_png", "fit_within",
]
