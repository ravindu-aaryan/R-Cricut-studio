"""Bulk import: many images (or a ZIP) into ready-made stickers, and templates.

A bulk-imported sticker is a transparent PNG (or SVG) stored as a user asset,
plus a sticker document with one asset layer. Options per batch:

* ``trim``            crop away fully transparent margins
* ``remove_white``    key out a plain near-white background (colour key)
* ``shape``/``border`` the die-cut or shaped border applied to each sticker
* ``size_mm``         the sticker's longest side

Templates are sticker documents saved without photo-specific pixels; a new
sticker is made from a template by swapping in a chosen photo/asset.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..models.base import new_id
from ..models.layer import Layer
from ..models.sticker import Border, ShapeSpec, StickerDoc
from ..utils.paths import require_safe_id, safe_join, sanitize_filename
from ..utils.svg_sanitize import SvgSanitizeError, sanitize_svg
from ..utils.validation import ValidationError, validate_image_bytes

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif")
SVG_EXTS = (".svg",)
MAX_FILES = 300
MAX_ZIP_UNCOMPRESSED = 600_000_000

ProgressFn = Callable[[float, str], None]


@dataclass
class ImportOptions:
    shape: str = "silhouette"
    size_mm: float = 60.0
    border_mm: float = 3.0
    border_color: str = "#ffffff"
    outline_mm: float = 0.0
    outline_color: str = "#ff4f8b"
    trim: bool = True
    remove_white: bool = False
    white_tolerance: float = 36.0
    add_to_project: bool = True
    category: str = "custom"


def _looks_svg(name: str, data: bytes) -> bool:
    return name.lower().endswith(SVG_EXTS) or data.lstrip()[:5] in (b"<?xml", b"<svg ") or b"<svg" in data[:512]


def expand_files(files: list[tuple[str, bytes]], max_bytes: int) -> list[tuple[str, bytes]]:
    """Expand any ZIP entries into their contained image/SVG files."""
    out: list[tuple[str, bytes]] = []
    for name, data in files:
        if name.lower().endswith(".zip") or data[:4] == b"PK\x03\x04":
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                raise ValidationError(f"{name}: not a valid ZIP file.")
            with zf:
                if sum(i.file_size for i in zf.infolist()) > MAX_ZIP_UNCOMPRESSED:
                    raise ValidationError(f"{name}: the ZIP expands to too much data.")
                for info in sorted(zf.infolist(), key=lambda i: i.filename):
                    base = info.filename.rsplit("/", 1)[-1]
                    if info.is_dir() or base.startswith(".") or "__MACOSX" in info.filename:
                        continue
                    if base.lower().endswith(IMAGE_EXTS + SVG_EXTS) and info.file_size <= max_bytes:
                        out.append((base, zf.read(info)))
        else:
            out.append((name.rsplit("/", 1)[-1], data))
        if len(out) > MAX_FILES:
            raise ValidationError(f"Too many files (limit {MAX_FILES}). Split the upload into smaller batches.")
    return out


def _trim(img: Image.Image) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def remove_white_background(img: Image.Image, tolerance: float) -> Image.Image:
    """Make near-white pixels connected to the border transparent (flood from edges).

    Only removes a plain backdrop; white *inside* the subject is kept.
    """
    import cv2

    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    rgb = arr[..., :3].astype(np.int16)
    near_white = (np.abs(255 - rgb).max(axis=2) <= tolerance) & (arr[..., 3] > 0)
    h, w = near_white.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flood = (near_white * 255).astype(np.uint8)
    # Flood from every border pixel that is near-white.
    seeds = np.argwhere(near_white)
    border = [(int(x), int(y)) for y, x in seeds if y in (0, h - 1) or x in (0, w - 1)]
    if not border:
        return rgba
    ff = flood.copy()
    for x, y in border[:: max(1, len(border) // 400)]:
        if ff[y, x]:
            cv2.floodFill(ff, mask, (x, y), 128)
    bg = ff == 128
    out = arr.copy()
    # Feather the 1px edge so it is not jagged.
    alpha = np.where(bg, 0, arr[..., 3]).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.6)
    out[..., 3] = np.minimum(arr[..., 3], alpha)
    return Image.fromarray(out, "RGBA")


def prepare_image(data: bytes, name: str, opts: ImportOptions, *, max_bytes: int, max_pixels: int, max_side: int) -> tuple[Image.Image | str, bool]:
    """Validate and preprocess one file. Returns (image-or-svgtext, is_svg)."""
    if _looks_svg(name, data):
        try:
            return sanitize_svg(data, max_bytes=max_bytes), True
        except (ValueError, SvgSanitizeError) as exc:
            raise ValidationError(f"{name}: {exc}")
    info = validate_image_bytes(data, max_bytes=max_bytes, max_pixels=max_pixels, max_side=max_side)
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        img = im.convert("RGBA")
    if opts.remove_white and not info.has_alpha:
        img = remove_white_background(img, opts.white_tolerance)
    if opts.trim:
        img = _trim(img)
    if img.width < 2 or img.height < 2:
        raise ValidationError(f"{name}: image is empty after processing.")
    return img, False


def make_sticker_doc(asset: dict, opts: ImportOptions, name: str) -> dict:
    """A sticker document with one asset layer sized to ``size_mm``."""
    aspect = float(asset.get("aspect") or 1.0)
    if aspect >= 1:
        w_mm, h_mm = opts.size_mm, opts.size_mm / aspect
    else:
        w_mm, h_mm = opts.size_mm * aspect, opts.size_mm
    dpi = 300
    W, H = w_mm / 25.4 * dpi, h_mm / 25.4 * dpi
    outlines = []
    if opts.outline_mm > 0:
        from ..models.sticker import Outline

        outlines = [Outline(width_mm=opts.outline_mm, color=opts.outline_color, gap_mm=0.0)]
    doc = StickerDoc(
        name=name[:60] or "Sticker", width_mm=round(w_mm, 2), height_mm=round(h_mm, 2), dpi=dpi,
        shape=ShapeSpec(type=opts.shape if opts.shape in ("silhouette", "circle", "oval", "rounded", "rect", "square", "heart", "star", "speech") else "silhouette",
                        corner_radius_mm=min(w_mm, h_mm) * 0.12),
        border=Border(width_mm=max(0.0, opts.border_mm), color=opts.border_color, outlines=outlines, smoothing=0.55),
        layers=[Layer(type="asset", asset_id=asset["id"], name=name[:60] or "Sticker", x=W / 2, y=H / 2, width=W, height=H)],
        variant={"source": "import", "note": "Imported image placed as a sticker. No new content was generated."},
    )
    return doc.to_dict()


@dataclass
class ImportResult:
    stickers: list[dict] = field(default_factory=list)
    assets: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def import_stickers(files: list[tuple[str, bytes]], opts: ImportOptions, asset_library, *,
                    max_bytes: int, max_pixels: int, max_side: int,
                    progress: ProgressFn = lambda p, m: None, cancelled: Callable[[], bool] = lambda: False) -> ImportResult:
    """Import many files as stickers. Each becomes a user asset plus a sticker doc."""
    entries = expand_files(files, max_bytes)
    if not entries:
        raise ValidationError("No image or SVG files were found in the upload.")
    result = ImportResult()
    for i, (name, data) in enumerate(entries):
        if cancelled():
            break
        progress(i / len(entries), f"Importing {name}")
        try:
            prepared, is_svg = prepare_image(data, name, opts, max_bytes=max_bytes, max_pixels=max_pixels, max_side=max_side)
            stem = sanitize_filename(name, "sticker").rsplit(".", 1)[0].replace("_", " ")[:60] or "Sticker"
            if is_svg:
                asset = asset_library.import_asset(prepared.encode("utf-8"), f"{stem}.svg", name=stem, category=opts.category, tags=["import"])
            else:
                buf = io.BytesIO()
                prepared.save(buf, "PNG")
                asset = asset_library.import_asset(buf.getvalue(), f"{stem}.png", name=stem, category=opts.category, tags=["import"])
            result.assets.append(asset)
            result.stickers.append(make_sticker_doc(asset, opts, stem))
        except ValidationError as exc:
            result.errors.append({"file": name[:120], "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            result.errors.append({"file": name[:120], "error": f"{type(exc).__name__}: {exc}"})
    progress(1.0, "Done")
    return result


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

def _strip_photo_layers(doc: dict) -> tuple[dict, bool]:
    """Return a copy of the sticker doc with photo layers turned into placeholders."""
    doc = json.loads(json.dumps(doc))
    has_slot = False

    def walk(layers):
        nonlocal has_slot
        for l in layers:
            if l.get("type") == "image":
                l["type"] = "shape"
                l["shape"] = "rounded"
                l["fill"] = "#e8e4f3"
                l["stroke"] = "#b9b0d8"
                l["strokeWidth"] = 2
                l["name"] = "Photo slot"
                l["photoSlot"] = True
                for k in ("photoId", "crop", "treatment", "source"):
                    l.pop(k, None)
                has_slot = True
            walk(l.get("children") or [])

    walk(doc.get("layers", []))
    return doc, has_slot


def make_template(doc: dict, name: str, theme_id: str | None) -> dict:
    stripped, has_slot = _strip_photo_layers(doc)
    return {
        "id": new_id("tpl_"), "name": (name or doc.get("name") or "Template")[:60], "themeId": theme_id,
        "widthMm": doc.get("widthMm", 60), "heightMm": doc.get("heightMm", 60), "hasPhotoSlot": has_slot,
        "shape": (doc.get("shape") or {}).get("type", "silhouette"), "sticker": stripped, "version": 1,
    }


def instantiate_template(template: dict, *, photo: dict | None = None, asset: dict | None = None, name: str = "") -> dict:
    """Make a sticker document from a template, filling photo slots with a photo or asset.

    The slot's position, size and rotation are kept; only the content changes.
    """
    doc = json.loads(json.dumps(template["sticker"]))
    doc["id"] = new_id("st_")
    doc["name"] = (name or template.get("name") or "Sticker")[:60]

    def fill(layers):
        for l in layers:
            if l.get("photoSlot"):
                w, h = l.get("width", 100), l.get("height", 100)
                lx, ly, lrot = l.get("x", 0), l.get("y", 0), l.get("rotation", 0)
                if photo is not None:
                    box = photo.get("subjectBox") if photo.get("mask") else None
                    crop = {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]} if box else {"x": 0, "y": 0, "w": 1, "h": 1}
                    pw, ph = crop["w"] * photo.get("width", 1000), crop["h"] * photo.get("height", 1000)
                    s = min(w / max(1, pw), h / max(1, ph))
                    l.clear()
                    l.update({"id": new_id("ly_"), "type": "image", "name": photo.get("name", "Photo"), "photoId": photo["id"],
                              "source": "subject" if photo.get("mask") else "working", "crop": crop,
                              "x": lx, "y": ly, "width": pw * s, "height": ph * s, "keepAspect": True,
                              "rotation": lrot, "scaleX": 1, "scaleY": 1, "opacity": 1, "visible": True})
                elif asset is not None:
                    l.clear()
                    l.update({"id": new_id("ly_"), "type": "asset", "assetId": asset["id"], "name": asset.get("name", "Art"),
                              "x": lx, "y": ly, "width": w, "height": h, "rotation": lrot, "scaleX": 1, "scaleY": 1,
                              "opacity": 1, "visible": True, "colors": {}})
                # Without a photo or asset the slot stays as a visible placeholder.
            else:
                l["id"] = new_id("ly_")
            fill(l.get("children") or [])

    fill(doc.get("layers", []))
    return doc


def _iter(layers):
    for l in layers or []:
        yield l
        yield from _iter(l.get("children") or [])


class TemplateStore:
    """App-wide sticker templates, stored as JSON files in the library folder."""

    def __init__(self, templates_dir: Path):
        self.dir = templates_dir

    def _path(self, tid: str) -> Path:
        require_safe_id(tid, "template id")
        return safe_join(self.dir, f"{tid}.json")

    def list(self) -> list[dict]:
        if not self.dir.exists():
            return []
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
                out.append({k: t.get(k) for k in ("id", "name", "themeId", "widthMm", "heightMm", "hasPhotoSlot", "shape")})
            except (ValueError, KeyError):
                continue
        return out

    def get(self, tid: str) -> dict:
        path = self._path(tid)
        if not path.exists():
            raise ValidationError("Template not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, template: dict) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        require_safe_id(template["id"], "template id")
        self._path(template["id"]).write_text(json.dumps(template), encoding="utf-8")
        return template

    def delete(self, tid: str) -> None:
        self._path(tid).unlink(missing_ok=True)

    def export_bundle(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("templates.json", json.dumps({"format": "oss-templates", "version": 1,
                                                     "templates": [self.get(t["id"]) for t in self.list()]}, indent=1))
        return buf.getvalue()

    def import_bundle(self, data: bytes, max_bytes: int = 30_000_000) -> list[dict]:
        if len(data) > max_bytes:
            raise ValidationError("The template file is too large.")
        templates: list[dict] = []
        if data[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "templates.json" not in z.namelist():
                    raise ValidationError("This ZIP does not contain templates.json.")
                payload = json.loads(z.read("templates.json"))
                templates = payload.get("templates", [])
        else:
            try:
                payload = json.loads(data)
            except ValueError:
                raise ValidationError("Not a valid template file (expected JSON or a template ZIP).")
            templates = payload.get("templates", payload if isinstance(payload, list) else [payload])
        from ..models.sticker import StickerDoc

        saved = []
        for t in templates[:200]:
            if not isinstance(t, dict) or "sticker" not in t:
                continue
            StickerDoc.from_dict(t["sticker"])  # validate shape of the embedded doc
            t["id"] = new_id("tpl_")
            saved.append(self.save(make_template(t["sticker"], t.get("name", "Template"), t.get("themeId"))))
        if not saved:
            raise ValidationError("No valid templates were found in the file.")
        return saved
