"""Render sticker documents (layers + shape + border) to images.

This is the authoritative renderer used for previews, exports and print.
Each layer's content is rasterised at the final pixel scale and then
placed with a single affine transform (premultiplied alpha, bicubic), so
vector assets and text stay sharp at any output size.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..models.layer import Layer
from ..models.sticker import StickerDoc
from ..utils.image_dimensions import MM_PER_INCH
from ..utils.validation import as_float, parse_color
from . import image_adjustments, outline_service
from .asset_service import AssetLibrary, rasterize_svg
from .photo_service import face_mask, normalize_mode, photo_paths
from .text_service import FontRegistry, render_text


@dataclass
class RenderContext:
    project_dir: Path
    photos: dict[str, dict]
    assets: AssetLibrary
    fonts: FontRegistry
    low_res_dpi: float = 150.0
    _cache: dict = field(default_factory=dict)

    def photo_image(self, photo_id: str, source: str) -> tuple[Image.Image, dict]:
        photo = self.photos.get(photo_id)
        if photo is None:
            raise KeyError(f"Photo {photo_id} is not in this project")
        key = (photo_id, source, photo.get("_rev"))
        if key not in self._cache:
            paths = photo_paths(self.project_dir, photo)
            path = paths["subject"] if source == "subject" and paths["subject"].exists() else paths["working"]
            with Image.open(path) as im:
                im.load()
                img = normalize_mode(im.copy()).convert("RGBA")
            if source != "subject" and paths["mask"].exists():
                img = apply_photo_background(img, paths["mask"], photo.get("background") or {}, self.assets)
            self._cache[key] = img
        return self._cache[key], photo


@dataclass
class RenderResult:
    image: Image.Image
    cut_mask: np.ndarray
    px_per_mm: float
    warnings: list[str]
    min_effective_dpi: float | None
    pieces: int
    art_offset: tuple[int, int]

    @property
    def size_mm(self) -> tuple[float, float]:
        return self.image.width / self.px_per_mm, self.image.height / self.px_per_mm


# --------------------------------------------------------------------------
# Backgrounds
# --------------------------------------------------------------------------

def render_background(bg: dict, size: tuple[int, int], assets: AssetLibrary | None, scale: float = 1.0) -> Image.Image | None:
    t = (bg or {}).get("type", "none")
    w, h = size
    if t == "solid":
        return Image.new("RGBA", size, parse_color(bg.get("color", "#ffffff")))
    if t == "gradient":
        c1 = np.array(parse_color(bg.get("color", "#ffffff")), np.float32)
        c2 = np.array(parse_color(bg.get("color2", "#ffd6e7")), np.float32)
        ang = math.radians(as_float(bg.get("angle"), 90))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dx, dy = math.sin(ang), -math.cos(ang)
        proj = (xx - w / 2) * dx + (yy - h / 2) * dy
        half = (abs(dx) * w + abs(dy) * h) / 2 or 1
        t_ = np.clip((proj / half + 1) / 2, 0, 1)[..., None]
        arr = c1 * (1 - t_) + c2 * t_
        return Image.fromarray(arr.astype(np.uint8), "RGBA")
    if t == "pattern" and assets is not None and bg.get("patternId"):
        base = Image.new("RGBA", size, parse_color(bg.get("color", "#ffffff")))
        tile_px = max(8, int(round(110 * scale * as_float(bg.get("patternScale"), 1, 0.2, 5))))
        svg = assets.pattern_svg(bg["patternId"], bg.get("patternColor", "#ffffff"))
        tile = rasterize_svg(svg, tile_px, tile_px)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        for y in range(0, h, tile_px):
            for x in range(0, w, tile_px):
                layer.paste(tile, (x, y))
        base.alpha_composite(layer)
        return base
    return None


def apply_photo_background(img: Image.Image, mask_path: Path, bg: dict, assets: AssetLibrary) -> Image.Image:
    """Replace the photo background (outside the subject mask) non-destructively."""
    t = (bg or {}).get("type", "keep")
    if t == "keep":
        return img
    with Image.open(mask_path) as m:
        mask = m.convert("L").resize(img.size)
    if t == "transparent":
        out = img.copy()
        out.putalpha(Image.fromarray(np.minimum(np.asarray(mask), np.asarray(img.getchannel("A"))), "L"))
        return out
    backdrop = render_background(bg, img.size, assets, scale=max(img.size) / 700)
    if backdrop is None:
        return img
    subject = img.copy()
    subject.putalpha(mask)
    backdrop.alpha_composite(subject)
    return backdrop


# --------------------------------------------------------------------------
# Affine helpers
# --------------------------------------------------------------------------

def _T(x, y):
    return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], np.float64)


def _R(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)


def _S(sx, sy):
    return np.array([[sx, 0, 0], [0, sy, 0], [0, 0, 1]], np.float64)


def layer_matrix(layer: Layer) -> np.ndarray:
    """Map the layer's centre-origin local space into its parent space."""
    sx = layer.scale_x * (-1 if layer.flip_x else 1)
    sy = layer.scale_y * (-1 if layer.flip_y else 1)
    return _T(layer.x, layer.y) @ _R(layer.rotation) @ _S(sx, sy)


def _paste_transformed(canvas: Image.Image, content: Image.Image, M: np.ndarray, opacity: float) -> None:
    """Composite ``content`` (pixel space) onto ``canvas`` with affine ``M``."""
    w, h = content.size
    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float64).T
    pts = M @ corners
    x0, y0 = math.floor(pts[0].min()) - 1, math.floor(pts[1].min()) - 1
    x1, y1 = math.ceil(pts[0].max()) + 1, math.ceil(pts[1].max()) + 1
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(canvas.width, x1), min(canvas.height, y1)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    Mi = np.linalg.inv(_T(-cx0, -cy0) @ M)
    data = (Mi[0, 0], Mi[0, 1], Mi[0, 2], Mi[1, 0], Mi[1, 1], Mi[1, 2])
    pre = content.convert("RGBa")
    is_identity = abs(M[0, 0] - 1) < 1e-9 and abs(M[1, 1] - 1) < 1e-9 and abs(M[0, 1]) < 1e-9 and abs(M[1, 0]) < 1e-9 \
        and abs(M[0, 2] - round(M[0, 2])) < 1e-9 and abs(M[1, 2] - round(M[1, 2])) < 1e-9
    if is_identity:
        region = Image.new("RGBa", (cx1 - cx0, cy1 - cy0), (0, 0, 0, 0))
        region.paste(pre, (int(round(M[0, 2])) - cx0, int(round(M[1, 2])) - cy0))
    else:
        region = pre.transform((cx1 - cx0, cy1 - cy0), Image.Transform.AFFINE, data, resample=Image.Resampling.BICUBIC)
    region = region.convert("RGBA")
    if opacity < 1.0:
        a = np.asarray(region.getchannel("A"), np.float32) * max(0.0, opacity)
        region.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    canvas.alpha_composite(region, (cx0, cy0))


# --------------------------------------------------------------------------
# Layer content
# --------------------------------------------------------------------------

class _Stats:
    def __init__(self):
        self.min_dpi: float | None = None
        self.warnings: list[str] = []


def _image_content(layer: Layer, ctx: RenderContext, rw: int, rh: int, out_dpi: float, stats: _Stats) -> Image.Image:
    src, photo = ctx.photo_image(layer.photo_id or "", layer.source)
    crop = layer.crop or {"x": 0, "y": 0, "w": 1, "h": 1}
    sw, sh = src.size
    box = (
        int(round(max(0, min(1, crop["x"])) * sw)), int(round(max(0, min(1, crop["y"])) * sh)),
        int(round(max(0, min(1, crop["x"] + crop["w"])) * sw)), int(round(max(0, min(1, crop["y"] + crop["h"])) * sh)),
    )
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        box = (0, 0, sw, sh)
    piece = src.crop(box)
    eff = out_dpi * piece.width / max(1, rw)
    stats.min_dpi = eff if stats.min_dpi is None else min(stats.min_dpi, eff)
    if eff < ctx.low_res_dpi:
        stats.warnings.append(
            f"Photo '{photo.get('name', 'photo')}' prints at about {eff:.0f} DPI, which may look soft. "
            "Use a larger photo or print the sticker smaller.")
    protect = None
    regions = photo.get("faceRegions") or []
    if photo.get("protectFace", True) and regions:
        full = face_mask((sw, sh), regions)
        if full is not None:
            protect = full.crop(box)
    resample = Image.Resampling.LANCZOS if piece.width > rw else Image.Resampling.BICUBIC
    piece = piece.resize((rw, rh), resample)
    params = {**(photo.get("adjustments") or {}), **{k: v for k, v in (layer.treatment or {}).items() if v is not None}}
    if not image_adjustments.is_identity(params):
        piece = image_adjustments.apply_adjustments(piece, params, scale=rw / 1000.0,
                                                    protect_mask=protect.resize((rw, rh)) if protect else None)
    return piece


def _shape_content(layer: Layer, rw: int, rh: int, k: float) -> Image.Image:
    ss = 3
    img = Image.new("RGBA", (rw * ss, rh * ss), (0, 0, 0, 0))
    sw = max(0.0, as_float(layer.stroke_width, 0, 0, 200)) * k * ss
    inset = sw / 2
    shape = layer.shape if layer.shape in ("rect", "rounded", "circle", "oval", "heart", "star", "speech", "square") else "rect"
    pts = outline_service.shape_polygon(shape, rw * ss - 2 * inset, rh * ss - 2 * inset,
                                        corner_radius=as_float(layer.corner_radius, 0) * k * ss, star_points=5)
    pts = [(x + inset, y + inset) for x, y in pts]
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=parse_color(layer.fill, (255, 200, 0, 255)))
    if sw >= 1:
        d.line(pts + [pts[0]], fill=parse_color(layer.stroke, (0, 0, 0, 255)), width=int(round(sw)), joint="curve")
    return img.resize((rw, rh), Image.Resampling.BOX)


def _render_layer(canvas: Image.Image, layer: Layer, parent: np.ndarray, ctx: RenderContext, out_dpi: float,
                  stats: _Stats, opacity: float = 1.0) -> None:
    if not layer.visible:
        return
    M = parent @ layer_matrix(layer)
    op = opacity * max(0.0, min(1.0, float(layer.opacity)))
    if layer.type == "group":
        if op >= 0.999:
            for child in layer.children:
                _render_layer(canvas, child, M, ctx, out_dpi, stats, 1.0)
        else:  # flatten the group first so its opacity applies uniformly
            tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            for child in layer.children:
                _render_layer(tmp, child, M, ctx, out_dpi, stats, 1.0)
            _paste_transformed(canvas, tmp, np.eye(3), op)
        return
    kx = math.hypot(M[0, 0], M[1, 0])
    ky = math.hypot(M[0, 1], M[1, 1])
    if layer.type == "text":
        k = max(1e-3, (kx + ky) / 2)
        content = render_text(layer, ctx.fonts, k)
        w_local, h_local = content.width / k, content.height / k
    else:
        w_local, h_local = max(1.0, float(layer.width)), max(1.0, float(layer.height))
        rw = max(1, int(math.ceil(w_local * kx)))
        rh = max(1, int(math.ceil(h_local * ky)))
        if rw * rh > 80_000_000:
            raise ValueError("A layer is too large to render.")
        if layer.type == "image":
            content = _image_content(layer, ctx, rw, rh, out_dpi, stats)
        elif layer.type == "asset":
            content = ctx.assets.raster(layer.asset_id or "", rw, rh, layer.colors)
        else:
            content = _shape_content(layer, rw, rh, (kx + ky) / 2)
    # Content pixel space -> local centred space -> canvas.
    to_local = _T(-w_local / 2, -h_local / 2) @ _S(w_local / content.width, h_local / content.height)
    _paste_transformed(canvas, content, M @ to_local, op)


def render_artboard(doc: StickerDoc, ctx: RenderContext, scale: float = 1.0, stats: _Stats | None = None) -> Image.Image:
    w = max(1, int(round(doc.width_px * scale)))
    h = max(1, int(round(doc.height_px * scale)))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    stats = stats or _Stats()
    base = _S(w / doc.width_px, h / doc.height_px)
    out_dpi = doc.dpi * scale
    for layer in doc.layers:
        _render_layer(canvas, layer, base, ctx, out_dpi, stats)
    return canvas


def sticker_spec(doc: StickerDoc, ctx: RenderContext, px_per_mm: float, size: tuple[int, int],
                 preview_shadow: bool) -> outline_service.StickerSpec:
    b, sh, shape = doc.border, doc.shadow, doc.shape
    custom_mask = None
    if shape.type == "custom" and shape.custom_asset_id:
        try:
            custom_mask = np.asarray(ctx.assets.raster(shape.custom_asset_id, size[0], size[1]).getchannel("A"))
        except Exception:
            custom_mask = None
    shadow_px = {
        "offset_px": (sh.offset_x_mm * px_per_mm, sh.offset_y_mm * px_per_mm),
        "blur_px": max(0.0, sh.blur_mm) * px_per_mm,
        "color": (*parse_color(sh.color)[:3], int(255 * max(0.0, min(1.0, sh.opacity)))),
    }
    background = None
    if shape.type != "silhouette":
        background = render_background(dc_bg(doc), size, ctx.assets, scale=px_per_mm / (300 / MM_PER_INCH))
    return outline_service.StickerSpec(
        shape=shape.type if shape.type != "custom" or custom_mask is not None else "rounded",
        corner_radius_px=max(0.0, shape.corner_radius_mm) * px_per_mm,
        star_points=shape.star_points,
        custom_mask=custom_mask,
        border_px=max(0.0, b.width_mm) * px_per_mm,
        border_color=parse_color(b.color, (255, 255, 255, 255)),
        outlines=outline_service.outline_layers_from_doc(b.outlines, px_per_mm),
        smoothing=max(0.0, min(1.0, b.smoothing)),
        fill_holes=b.fill_holes,
        bridge_gaps=b.bridge_gaps,
        background=background,
        art_shadow=shadow_px if sh.enabled and sh.target == "art" else None,
        preview_shadow=shadow_px if (sh.enabled and sh.target == "sticker" and preview_shadow) else None,
        cut_offset_px=doc.cut_offset_mm * px_per_mm,
    )


def dc_bg(doc: StickerDoc) -> dict:
    bg = doc.background
    return {"type": bg.type, "color": bg.color, "color2": bg.color2, "angle": bg.angle, "patternId": bg.pattern_id,
            "patternColor": bg.pattern_color, "patternScale": bg.pattern_scale}


def render_sticker(doc: StickerDoc, ctx: RenderContext, scale: float = 1.0, *, preview_shadow: bool = False,
                   art_only: bool = False) -> RenderResult:
    """Render the finished sticker (art + border + outlines) and its cut mask."""
    stats = _Stats()
    art = render_artboard(doc, ctx, scale, stats)
    px_per_mm = doc.dpi / MM_PER_INCH * scale
    if art_only:
        alpha = np.asarray(art.getchannel("A"))
        return RenderResult(art, np.where(alpha > 24, 255, 0).astype(np.uint8), px_per_mm, stats.warnings,
                            stats.min_dpi, 1, (0, 0))
    spec = sticker_spec(doc, ctx, px_per_mm, art.size, preview_shadow)
    built = outline_service.build_sticker(art, spec)
    warnings = list(dict.fromkeys(stats.warnings + built.warnings))
    return RenderResult(built.image, built.cut_mask, px_per_mm, warnings, stats.min_dpi, built.pieces, built.art_offset)


def finished_size_mm(doc: StickerDoc, ctx: RenderContext) -> tuple[float, float]:
    """Physical size of the finished sticker (art + border) at design scale."""
    probe = render_sticker(doc, ctx, 0.25)
    return probe.size_mm


def scale_for_size(design_mm: tuple[float, float], target_w_mm: float, target_h_mm: float) -> float:
    """Uniform scale that makes a sticker of ``design_mm`` fit the target box.

    Scaling is uniform for the whole sticker, border included, exactly like
    resizing a printed image.
    """
    w, h = design_mm
    return max(0.02, min(target_w_mm / max(w, 1e-6), target_h_mm / max(h, 1e-6)))
