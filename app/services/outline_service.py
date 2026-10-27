"""Sticker shapes, die-cut borders, outline layers and shadows.

Everything works on alpha masks with morphological operations and an exact
Euclidean distance transform, so borders follow the subject silhouette at
a constant physical width. The original artwork is always composited *on
top* of the border, so the border never overwrites the subject.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ..utils.validation import parse_color

SUPERSAMPLE = 4


# --------------------------------------------------------------------------
# Geometric shapes
# --------------------------------------------------------------------------

def _fit_box(w: float, h: float, square: bool) -> tuple[float, float, float, float]:
    if square:
        s = min(w, h)
        return (w - s) / 2, (h - s) / 2, s, s
    return 0.0, 0.0, w, h


def shape_polygon(shape: str, w: float, h: float, *, corner_radius: float = 0.0, star_points: int = 5) -> list[tuple[float, float]]:
    """Outline of a geometric shape inside a ``w`` x ``h`` box, as points."""
    if shape in ("circle", "square"):
        x0, y0, bw, bh = _fit_box(w, h, True)
    else:
        x0, y0, bw, bh = 0.0, 0.0, w, h
    pts: list[tuple[float, float]] = []
    if shape in ("circle", "oval"):
        n = 256
        for i in range(n):
            t = 2 * math.pi * i / n
            pts.append((x0 + bw / 2 + bw / 2 * math.cos(t), y0 + bh / 2 + bh / 2 * math.sin(t)))
    elif shape in ("rect", "square", "rounded"):
        r = 0.0 if shape != "rounded" and shape != "square" else max(0.0, min(corner_radius, bw / 2, bh / 2))
        if shape == "rect":
            r = 0.0
        pts = _rounded_rect(x0, y0, bw, bh, r)
    elif shape == "heart":
        n = 360
        raw = []
        for i in range(n):
            t = 2 * math.pi * i / n
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            raw.append((x, y))
        pts = _fit_points(raw, x0, y0, bw, bh)
    elif shape == "star":
        n = max(3, min(24, int(star_points)))
        raw = []
        for i in range(2 * n):
            r = 1.0 if i % 2 == 0 else 0.5
            t = -math.pi / 2 + math.pi * i / n
            raw.append((r * math.cos(t), r * math.sin(t)))
        pts = _fit_points(raw, x0, y0, bw, bh)
        pts = _round_polygon(pts, max(1.0, min(bw, bh) * 0.03))
    elif shape == "speech":
        body_h = bh * 0.80
        r = min(bw, body_h) * 0.22
        body = _rounded_rect(x0, y0, bw, body_h, r)
        # Insert a tail on the bottom edge, near the left.
        tail = [(x0 + bw * 0.38, y0 + body_h), (x0 + bw * 0.18, y0 + bh), (x0 + bw * 0.24, y0 + body_h)]
        bottom_idx = max(range(len(body)), key=lambda i: (body[i][1] >= y0 + body_h - 0.01) * -abs(body[i][0] - (x0 + bw * 0.3)) if body[i][1] >= y0 + body_h - 0.01 else -1e9)
        pts = body[: bottom_idx + 1] + tail + body[bottom_idx + 1:]
    else:
        pts = _rounded_rect(x0, y0, bw, bh, 0)
    return pts


def _rounded_rect(x: float, y: float, w: float, h: float, r: float) -> list[tuple[float, float]]:
    if r <= 0.5:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts = []
    seg = 16
    corners = [(x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)]
    for cx, cy, start in corners:
        for i in range(seg + 1):
            a = math.radians(start + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _fit_points(raw, x0, y0, bw, bh):
    xs, ys = [p[0] for p in raw], [p[1] for p in raw]
    mnx, mxx, mny, mxy = min(xs), max(xs), min(ys), max(ys)
    sx, sy = bw / (mxx - mnx), bh / (mxy - mny)
    return [(x0 + (px - mnx) * sx, y0 + (py - mny) * sy) for px, py in raw]


def _round_polygon(pts, radius, seg=6):
    """Round sharp polygon corners (used for friendlier star points)."""
    out = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = np.array(pts[i - 1]), np.array(pts[i]), np.array(pts[(i + 1) % n])
        v1, v2 = p0 - p1, p2 - p1
        l1, l2 = np.linalg.norm(v1), np.linalg.norm(v2)
        d = min(radius, l1 / 2.5, l2 / 2.5)
        a, b = p1 + v1 / l1 * d, p1 + v2 / l2 * d
        for k in range(seg + 1):
            t = k / seg
            q = (1 - t) ** 2 * a + 2 * (1 - t) * t * p1 + t ** 2 * b
            out.append((float(q[0]), float(q[1])))
    return out


def polygon_mask(points: list[tuple[float, float]], size: tuple[int, int], offset=(0.0, 0.0)) -> np.ndarray:
    """Anti-aliased 0..255 mask of a polygon (supersampled)."""
    w, h = size
    ss = SUPERSAMPLE
    img = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(img).polygon([((x + offset[0]) * ss, (y + offset[1]) * ss) for x, y in points], fill=255)
    return np.asarray(img.resize((w, h), Image.Resampling.BOX))


def shape_mask(shape: str, size: tuple[int, int], box: tuple[float, float, float, float], **kw) -> np.ndarray:
    """Mask of ``shape`` placed in ``box`` (x, y, w, h) on a canvas of ``size``."""
    x, y, bw, bh = box
    pts = shape_polygon(shape, bw, bh, **kw)
    return polygon_mask(pts, size, offset=(x, y))


# --------------------------------------------------------------------------
# Mask morphology
# --------------------------------------------------------------------------

def binary_from_alpha(alpha: np.ndarray, threshold: int = 24) -> np.ndarray:
    return np.where(alpha >= threshold, 255, 0).astype(np.uint8)


def fill_holes(binary: np.ndarray) -> np.ndarray:
    """Fill every enclosed hole (flood fill from a padded border)."""
    h, w = binary.shape
    padded = np.zeros((h + 2, w + 2), np.uint8)
    padded[1:-1, 1:-1] = binary
    flood = padded.copy()
    ff_mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(flood, ff_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)[1:-1, 1:-1]
    return cv2.bitwise_or(binary, holes)


def expand(binary: np.ndarray, radius_px: float) -> np.ndarray:
    """Grow (radius > 0) or shrink (radius < 0) a binary mask by an exact distance."""
    if abs(radius_px) < 0.5:
        return binary.copy()
    if radius_px > 0:
        dist = cv2.distanceTransform(cv2.bitwise_not(binary), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        return np.where(dist <= radius_px, 255, 0).astype(np.uint8)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return np.where(dist > -radius_px, 255, 0).astype(np.uint8)


def smooth_binary(binary: np.ndarray, sigma_px: float) -> np.ndarray:
    if sigma_px < 0.5:
        return binary
    blurred = cv2.GaussianBlur(binary.astype(np.float32), (0, 0), sigma_px)
    return np.where(blurred >= 127.5, 255, 0).astype(np.uint8)


def antialias(binary: np.ndarray, sigma: float = 0.8) -> np.ndarray:
    """Soft edge for rendering; the hard mask remains the cut geometry."""
    return np.clip(cv2.GaussianBlur(binary.astype(np.float32), (0, 0), sigma) + 0.5, 0, 255).astype(np.uint8)


def component_count(binary: np.ndarray) -> int:
    n, _ = cv2.connectedComponents(binary, connectivity=8)
    return n - 1


def bridge_components(binary: np.ndarray, max_radius_px: float) -> np.ndarray:
    """Join separate pieces with a morphological closing so the sticker is one piece."""
    if component_count(binary) <= 1:
        return binary
    r = 2.0
    out = binary
    while r <= max_radius_px:
        k = int(r * 2) | 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        out = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        if component_count(out) <= 1:
            return out
        r *= 1.5
    # Still separate: connect each piece to the largest with a thick bridge.
    n, labels, stats, cents = cv2.connectedComponentsWithStats(out, connectivity=8)
    if n <= 2:
        return out
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    main_pts = np.column_stack(np.nonzero(labels == main))[:, ::-1]
    bridged = out.copy()
    thick = max(2, int(max_radius_px / 2))
    for i in range(1, n):
        if i == main:
            continue
        pts = np.column_stack(np.nonzero(labels == i))[:, ::-1]
        sample = pts[:: max(1, len(pts) // 200)]
        msample = main_pts[:: max(1, len(main_pts) // 400)]
        d = ((sample[:, None, :] - msample[None, :, :]) ** 2).sum(-1)
        a, b = np.unravel_index(int(np.argmin(d)), d.shape)
        cv2.line(bridged, tuple(int(v) for v in sample[a]), tuple(int(v) for v in msample[b]), 255, thick)
    return bridged


# --------------------------------------------------------------------------
# Sticker assembly
# --------------------------------------------------------------------------

@dataclass
class OutlineLayer:
    width_px: float
    color: tuple[int, int, int, int]
    gap_px: float = 0.0


@dataclass
class StickerSpec:
    shape: str = "silhouette"
    corner_radius_px: float = 0.0
    star_points: int = 5
    custom_mask: np.ndarray | None = None
    border_px: float = 30.0
    border_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    outlines: tuple[OutlineLayer, ...] = ()
    smoothing: float = 0.5
    fill_holes: bool = True
    bridge_gaps: bool = True
    background: Image.Image | None = None  # RGBA, artboard size; shape mode only
    art_shadow: dict | None = None  # {offset_px:(dx,dy), blur_px, color}
    preview_shadow: dict | None = None
    cut_offset_px: float = 0.0


@dataclass
class StickerRender:
    image: Image.Image  # RGBA, trimmed, includes border and art
    cut_mask: np.ndarray  # 0/255 hard mask of the cut line (after offset), same size as image
    art_offset: tuple[int, int]  # position of the artboard's top-left in ``image``
    pieces: int
    warnings: list[str]


def _color_layer(mask: np.ndarray, color: tuple[int, int, int, int]) -> Image.Image:
    h, w = mask.shape
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color[0], color[1], color[2]
    arr[..., 3] = (mask.astype(np.uint16) * color[3] // 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _shadow_layer(mask: np.ndarray, spec: dict) -> Image.Image:
    dx, dy = spec.get("offset_px", (0, 0))
    blur = float(spec.get("blur_px", 4))
    color = spec.get("color", (0, 0, 0, 90))
    m = mask.astype(np.float32)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    m = cv2.warpAffine(m, M, (mask.shape[1], mask.shape[0]))
    if blur > 0.3:
        m = cv2.GaussianBlur(m, (0, 0), blur)
    return _color_layer(np.clip(m, 0, 255).astype(np.uint8), color)


def padding_needed(spec: StickerSpec) -> int:
    pad = spec.border_px if spec.shape == "silhouette" else 0.0
    for o in spec.outlines:
        pad += o.gap_px + o.width_px
    pad += max(0.0, spec.cut_offset_px)
    if spec.preview_shadow:
        dx, dy = spec.preview_shadow.get("offset_px", (0, 0))
        pad += max(abs(dx), abs(dy)) + 3 * spec.preview_shadow.get("blur_px", 0)
    return int(math.ceil(pad)) + 4


def build_sticker(art: Image.Image, spec: StickerSpec) -> StickerRender:
    """Assemble border + outlines + art into a finished sticker and its cut mask."""
    warnings: list[str] = []
    art = art.convert("RGBA")
    aw, ah = art.size
    pad = padding_needed(spec)
    W, H = aw + 2 * pad, ah + 2 * pad
    canvas_art = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas_art.paste(art, (pad, pad))
    art_alpha = np.asarray(canvas_art.getchannel("A"))
    min_side = min(aw, ah)

    if spec.shape == "silhouette":
        base = binary_from_alpha(art_alpha)
        if not base.any():
            raise ValueError("The sticker is empty. Add a photo, decoration or text first.")
        if spec.fill_holes:
            base = fill_holes(base)
        inner = expand(base, spec.border_px)
        inner = smooth_binary(inner, spec.smoothing * max(1.0, spec.border_px) * 0.6)
        if spec.fill_holes:
            inner = fill_holes(inner)
        if spec.bridge_gaps and component_count(inner) > 1:
            inner = bridge_components(inner, max(spec.border_px * 3, min_side * 0.08))
            if spec.fill_holes:
                inner = fill_holes(inner)
        clip = None  # silhouette mode never clips the art
        border_region = inner
    else:
        if spec.shape == "custom" and spec.custom_mask is not None:
            m = cv2.resize(spec.custom_mask, (aw, ah), interpolation=cv2.INTER_LINEAR)
            shape_m = np.zeros((H, W), np.uint8)
            shape_m[pad:pad + ah, pad:pad + aw] = m
        else:
            shape_m = shape_mask(spec.shape, (W, H), (pad, pad, aw, ah),
                                 corner_radius=spec.corner_radius_px, star_points=spec.star_points)
        border_region = binary_from_alpha(shape_m, 128)
        inset = expand(border_region, -spec.border_px) if spec.border_px > 0 else border_region
        # Use the anti-aliased version of the inset as a soft clip for the art.
        clip = antialias(inset, 0.7)
    # Each outline ring grows outward from the previous region; an optional
    # gap leaves a transparent band between rings.
    rings: list[tuple[np.ndarray, tuple[int, int, int, int]]] = []
    current = border_region
    for o in spec.outlines:
        hole = None
        if o.gap_px > 0:
            hole = smooth_binary(expand(current, o.gap_px), spec.smoothing * o.gap_px * 0.5)
            current = hole
        current = expand(current, o.width_px)
        ring = antialias(current)
        if hole is not None:
            ring = (ring.astype(np.uint16) * (255 - antialias(hole)) // 255).astype(np.uint8)
        rings.append((ring, o.color))
    cut = current
    if spec.bridge_gaps and component_count(cut) > 1:
        cut = bridge_components(cut, max(spec.border_px * 3, min_side * 0.08))
    pieces = component_count(cut)
    if pieces > 1:
        warnings.append(f"The sticker has {pieces} separate pieces; each gets its own cut path.")

    # Paint from the outside in: preview shadow, outline rings, border, art.
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if spec.preview_shadow:
        out.alpha_composite(_shadow_layer(antialias(cut), spec.preview_shadow))
    for ring, color in reversed(rings):
        out.alpha_composite(_color_layer(ring, color))
    out.alpha_composite(_color_layer(antialias(border_region), spec.border_color))
    if spec.shape != "silhouette" and spec.background is not None:
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bg.paste(spec.background.convert("RGBA").resize((aw, ah)), (pad, pad))
        bg_arr = np.asarray(bg).copy()
        bg_arr[..., 3] = (bg_arr[..., 3].astype(np.uint16) * clip // 255).astype(np.uint8)
        out.alpha_composite(Image.fromarray(bg_arr, "RGBA"))
    art_layer = canvas_art
    if clip is not None:
        arr = np.asarray(canvas_art).copy()
        arr[..., 3] = (arr[..., 3].astype(np.uint16) * clip // 255).astype(np.uint8)
        art_layer = Image.fromarray(arr, "RGBA")
    if spec.art_shadow:
        sh_mask = np.asarray(art_layer.getchannel("A"))
        out.alpha_composite(_shadow_layer(sh_mask, spec.art_shadow))
    out.alpha_composite(art_layer)

    cut_final = expand(cut, spec.cut_offset_px) if spec.cut_offset_px else cut
    # Trim to the cut geometry plus everything painted (keeps physical size honest).
    # Exact bounds (antialiased edge pixels have alpha > 0 and are included),
    # so the physical size does not depend on the render scale.
    ys, xs = np.nonzero((np.asarray(out.getchannel("A")) > 0) | (cut_final > 0))
    x0, y0 = int(xs.min()), int(ys.min())
    x1, y1 = int(xs.max()) + 1, int(ys.max()) + 1
    trimmed = out.crop((x0, y0, x1, y1))
    return StickerRender(
        image=trimmed,
        cut_mask=cut_final[y0:y1, x0:x1].copy(),
        art_offset=(pad - x0, pad - y0),
        pieces=pieces,
        warnings=warnings,
    )


def outline_layers_from_doc(outlines: list, px_per_mm: float) -> tuple[OutlineLayer, ...]:
    out = []
    for o in outlines or []:
        width = float(getattr(o, "width_mm", 0) or 0) * px_per_mm
        if width <= 0:
            continue
        out.append(OutlineLayer(width_px=width, color=parse_color(getattr(o, "color", "#000000")),
                                gap_px=max(0.0, float(getattr(o, "gap_mm", 0) or 0)) * px_per_mm))
    return tuple(out[:6])
