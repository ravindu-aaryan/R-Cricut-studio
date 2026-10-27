"""Local subject extraction (background removal).

Three engines, all offline:

* ``manual``  – the user paints the mask directly (keep / remove brushes).
* ``grabcut`` – OpenCV GrabCut seeded by a rectangle and optional
  foreground/background hint strokes.
* ``model``   – an optional, locally installed ONNX salient-object model
  (U²-Net family). Never downloaded at runtime; if it is missing the UI
  says so and the other engines remain available.

All engines produce a single-channel alpha mask aligned to the working
image, which is then cleaned up by :func:`refine_mask`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

HINT_UNKNOWN, HINT_FG, HINT_BG = 0, 1, 2
MODEL_FILENAMES = ("u2netp.onnx", "u2net.onnx", "silueta.onnx", "u2net_human_seg.onnx")


class SegmentationCancelled(Exception):
    pass


def _noop_progress(_p: float, _m: str) -> None:
    pass


def _never() -> bool:
    return False


@dataclass
class RefineOptions:
    feather_px: float = 1.0
    remove_holes_area: int = 400  # fill background holes smaller than this (px at full res)
    remove_specks_area: int = 400  # drop foreground islands smaller than this
    smooth: float = 0.0  # 0..1 morphological smoothing of the outline
    grow_px: int = 0  # positive grows, negative shrinks
    edge_refine: bool = True  # guided filter for hair / fine detail
    keep_largest_only: bool = False


# --------------------------------------------------------------------------
# Hints and helpers
# --------------------------------------------------------------------------

def hints_from_rgba(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """Decode a hint drawing (red = keep, blue = remove) into hint labels."""
    arr = np.asarray(img.convert("RGBA").resize(size, Image.Resampling.NEAREST))
    hints = np.zeros(arr.shape[:2], np.uint8)
    painted = arr[..., 3] > 64
    hints[painted & (arr[..., 0] > 127) & (arr[..., 2] < 128)] = HINT_FG
    hints[painted & (arr[..., 2] > 127) & (arr[..., 0] < 128)] = HINT_BG
    return hints


def _downscale(arr: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = arr.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s >= 1.0:
        return arr, 1.0
    return cv2.resize(arr, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_AREA), s


def guided_filter(guide: np.ndarray, src: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Fast guided filter (He et al.) on a grey guide; src and output in 0..1."""
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
    ksize = (2 * radius + 1, 2 * radius + 1)
    mean = lambda x: cv2.boxFilter(x, -1, ksize, borderType=cv2.BORDER_REFLECT)  # noqa: E731
    mI, mp = mean(I), mean(p)
    cov = mean(I * p) - mI * mp
    var = mean(I * I) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return mean(a) * I + mean(b)


def border_color_estimate(rgb: np.ndarray) -> tuple[np.ndarray, float]:
    """Median colour of the image border and how uniform it is (0 = uniform)."""
    h, w = rgb.shape[:2]
    t = max(2, min(h, w) // 40)
    strip = np.concatenate([rgb[:t].reshape(-1, 3), rgb[-t:].reshape(-1, 3), rgb[:, :t].reshape(-1, 3), rgb[:, -t:].reshape(-1, 3)])
    med = np.median(strip, axis=0)
    spread = float(np.median(np.linalg.norm(strip.astype(np.float32) - med, axis=1)))
    return med, spread


# --------------------------------------------------------------------------
# Engines
# --------------------------------------------------------------------------

def grabcut(rgb_full: np.ndarray, rect: tuple[int, int, int, int] | None = None, hints: np.ndarray | None = None,
            *, iterations: int = 5, work_side: int = 900, progress: ProgressFn = _noop_progress,
            cancelled: CancelFn = _never) -> np.ndarray:
    """Run GrabCut at a working resolution and return a full-size 0..255 mask."""
    H, W = rgb_full.shape[:2]
    rgb, s = _downscale(rgb_full, work_side)
    h, w = rgb.shape[:2]
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    if rect is not None:
        x, y, rw, rh = (int(round(v * s)) for v in rect)
        x, y = max(0, x), max(0, y)
        rw, rh = max(2, min(w - x, rw)), max(2, min(h - y, rh))
        # A rectangle drawn almost to the photo edge means "the subject continues
        # past the edge" (e.g. a body cut off at the bottom): snap it to the edge.
        snap = 0.03
        if x < w * snap:
            rw, x = rw + x, 0
        if y < h * snap:
            rh, y = rh + y, 0
        if x + rw > w * (1 - snap):
            rw = w - x
        if y + rh > h * (1 - snap):
            rh = h - y
        mask[:] = cv2.GC_BGD
        mask[y:y + rh, x:x + rw] = cv2.GC_PR_FGD
    else:
        m = max(2, int(min(h, w) * 0.04))
        mask[m:h - m, m:w - m] = cv2.GC_PR_FGD
        mask[:m], mask[-m:], mask[:, :m], mask[:, -m:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
    if hints is not None:
        hs = cv2.resize(hints, (w, h), interpolation=cv2.INTER_NEAREST)
        mask[hs == HINT_FG] = cv2.GC_FGD
        mask[hs == HINT_BG] = cv2.GC_BGD
    if not np.any((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)):
        raise ValueError("The selection contains no foreground. Draw a larger rectangle or mark the subject.")
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    iterations = int(max(1, min(12, iterations)))
    for i in range(iterations):
        if cancelled():
            raise SegmentationCancelled()
        cv2.grabCut(bgr, mask, None, bgd, fgd, 1, cv2.GC_INIT_WITH_MASK)
        progress(0.1 + 0.7 * (i + 1) / iterations, f"GrabCut pass {i + 1} of {iterations}")
    out = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if s < 1.0:
        out = cv2.resize(out, (W, H), interpolation=cv2.INTER_LINEAR)
        if hints is not None:
            hf = cv2.resize(hints, (W, H), interpolation=cv2.INTER_NEAREST)
            out[hf == HINT_FG] = 255
            out[hf == HINT_BG] = 0
    return out


def color_key(rgb_full: np.ndarray, tolerance: float = 40.0) -> np.ndarray:
    """Remove a plain backdrop by colour distance from the border colour."""
    med, _spread = border_color_estimate(rgb_full)
    dist = np.linalg.norm(rgb_full.astype(np.float32) - med.astype(np.float32), axis=2)
    soft = np.clip((dist - tolerance * 0.6) / max(1.0, tolerance * 0.8), 0, 1)
    return (soft * 255).astype(np.uint8)


def find_model(models_dir: Path) -> Path | None:
    for name in MODEL_FILENAMES:
        p = models_dir / name
        if p.exists() and p.stat().st_size > 1_000_000:
            return p
    return None


def model_status(models_dir: Path) -> dict:
    try:
        import onnxruntime  # type: ignore  # noqa: F401

        runtime = True
    except Exception:
        runtime = False
    path = find_model(models_dir)
    return {
        "runtimeInstalled": runtime,
        "modelFile": path.name if path else None,
        "available": bool(runtime and path),
        "searched": [str(models_dir / n) for n in MODEL_FILENAMES],
    }


_SESSIONS: dict[str, object] = {}


def model_segment(rgb_full: np.ndarray, models_dir: Path, *, progress: ProgressFn = _noop_progress) -> np.ndarray:
    """Salient-object mask from a local U²-Net-style ONNX model."""
    import onnxruntime as ort  # type: ignore

    path = find_model(models_dir)
    if path is None:
        raise FileNotFoundError("No segmentation model is installed.")
    key = str(path)
    if key not in _SESSIONS:
        progress(0.1, "Loading local model")
        _SESSIONS[key] = ort.InferenceSession(key, providers=["CPUExecutionProvider"])
    sess = _SESSIONS[key]
    H, W = rgb_full.shape[:2]
    x = cv2.resize(rgb_full, (320, 320), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    progress(0.4, "Running local model")
    inp = sess.get_inputs()[0].name  # type: ignore[attr-defined]
    pred = sess.run(None, {inp: x})[0][0, 0]  # type: ignore[attr-defined]
    pred = (pred - pred.min()) / max(1e-6, float(pred.max() - pred.min()))
    return cv2.resize((pred * 255).astype(np.uint8), (W, H), interpolation=cv2.INTER_LINEAR)


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------

def remove_small_components(binary: np.ndarray, min_area: int, keep_largest_only: bool = False) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return binary
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool)
    if keep_largest_only:
        keep[1 + int(np.argmax(areas))] = True
    else:
        keep[1:] = areas >= min_area
        if not keep[1:].any():
            keep[1 + int(np.argmax(areas))] = True
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def fill_small_holes(binary: np.ndarray, max_area: int) -> np.ndarray:
    inv = cv2.bitwise_not(binary)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    out = binary.copy()
    h, w = binary.shape
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        touches_border = x == 0 or y == 0 or x + cw == w or y + ch == h
        if not touches_border and area <= max_area:
            out[labels == i] = 255
    return out


def refine_mask(mask: np.ndarray, rgb: np.ndarray | None = None, options: RefineOptions | None = None) -> np.ndarray:
    """Clean up a raw 0..255 mask: specks, holes, smoothing, grow/shrink, edges, feather."""
    o = options or RefineOptions()
    h, w = mask.shape[:2]
    scale = max(h, w) / 1000.0
    binary = np.where(mask >= 128, 255, 0).astype(np.uint8)
    if o.remove_specks_area > 0 or o.keep_largest_only:
        binary = remove_small_components(binary, int(o.remove_specks_area * scale * scale), o.keep_largest_only)
    if o.remove_holes_area > 0:
        binary = fill_small_holes(binary, int(o.remove_holes_area * scale * scale))
    if o.smooth > 0:
        k = max(3, int(o.smooth * 12 * scale) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    if o.grow_px:
        k = abs(int(o.grow_px)) * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.dilate(binary, kernel) if o.grow_px > 0 else cv2.erode(binary, kernel)
    alpha = binary.astype(np.float32) / 255.0
    if o.edge_refine and rgb is not None and rgb.shape[:2] == (h, w):
        # Guided filtering lets the alpha follow fine image structure such as
        # hair strands, but only within a band around the hard edge.
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        r = max(2, int(round(4 * scale)))
        refined = np.clip(guided_filter(gray, alpha, r, 1e-3), 0, 1)
        band_k = max(3, (r * 2) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (band_k, band_k))
        band = cv2.dilate(binary, kernel) != cv2.erode(binary, kernel)
        alpha = np.where(band, refined, alpha)
    if o.feather_px > 0:
        sigma = max(0.3, float(o.feather_px))
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigma)
    return (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)


def decontaminate_edges(rgb: np.ndarray, alpha: np.ndarray, radius: int = 6) -> np.ndarray:
    """Replace background colour bleeding into soft edges with nearby subject colour.

    Uses normalised convolution: colours of confidently-opaque pixels are
    blurred outward and used for partially transparent edge pixels, which
    removes the halo of old background around hair and outlines.
    """
    a = alpha.astype(np.float32) / 255.0
    solid = (a > 0.95).astype(np.float32)
    if solid.sum() == 0:
        return rgb
    k = max(3, radius * 2 + 1)
    w = cv2.GaussianBlur(solid, (k, k), 0)
    est = cv2.GaussianBlur(rgb.astype(np.float32) * solid[..., None], (k, k), 0) / np.maximum(w[..., None], 1e-4)
    edge = (a < 0.95) & (a > 0.0) & (w > 1e-3)
    out = rgb.astype(np.float32).copy()
    t = np.clip(1.0 - a, 0, 1)[..., None]
    out[edge] = (out * (1 - t) + est * t)[edge]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def extract_subject(rgb: Image.Image, alpha: np.ndarray, decontaminate: bool = True) -> Image.Image:
    """Combine the working image and a mask into a transparent RGBA subject."""
    img = rgb.convert("RGBA")
    a = Image.fromarray(alpha, "L")
    if a.size != img.size:
        a = a.resize(img.size, Image.Resampling.BILINEAR)
    # Respect any transparency already in the source image.
    a_arr = np.minimum(np.asarray(a), np.asarray(img.getchannel("A")))
    colors = np.asarray(img.convert("RGB"))
    if decontaminate:
        colors = decontaminate_edges(colors, a_arr, radius=max(3, min(img.size) // 200))
    out = Image.fromarray(colors, "RGB").convert("RGBA")
    out.putalpha(Image.fromarray(a_arr, "L"))
    return out


def alpha_bbox(alpha: np.ndarray, threshold: int = 8) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(alpha > threshold)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def run_segmentation(method: str, image: Image.Image, *, rect=None, hints: np.ndarray | None = None,
                     manual_mask: np.ndarray | None = None, models_dir: Path | None = None,
                     refine: RefineOptions | None = None, iterations: int = 5,
                     progress: ProgressFn = _noop_progress, cancelled: CancelFn = _never) -> np.ndarray:
    """Entry point used by the job system. Returns the refined full-size mask."""
    rgb_img = image.convert("RGB")
    rgb = np.asarray(rgb_img)
    progress(0.05, "Preparing image")
    if method == "manual":
        if manual_mask is None:
            raise ValueError("Paint the subject first.")
        raw = cv2.resize(manual_mask, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    elif method == "grabcut":
        raw = grabcut(rgb, rect, hints, iterations=iterations, progress=progress, cancelled=cancelled)
    elif method == "colorkey":
        raw = color_key(rgb)
    elif method == "model":
        if models_dir is None:
            raise FileNotFoundError("No segmentation model is installed.")
        raw = model_segment(rgb, models_dir, progress=progress)
        if hints is not None:
            hf = cv2.resize(hints, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
            raw[hf == HINT_FG] = 255
            raw[hf == HINT_BG] = 0
    else:
        raise ValueError(f"Unknown extraction method: {method}")
    if cancelled():
        raise SegmentationCancelled()
    progress(0.85, "Refining edges")
    # Respect any transparency already present in the source.
    if image.mode == "RGBA":
        raw = np.minimum(raw, np.asarray(image.getchannel("A")))
    refined = refine_mask(raw, rgb, refine)
    progress(1.0, "Done")
    return refined
