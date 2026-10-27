"""Cut-path extraction and SVG generation.

Cut contours are traced from the hard cut mask of each sticker, which is
already expanded by the configured cut offset. A contour traced from a
binary mask cannot self-intersect; simplification can, so every
simplified path is checked and re-simplified more gently if needed.
Units in the SVG are millimetres (``width="..mm"`` with a matching viewBox),
so cutting software imports them at true physical size.
"""
from __future__ import annotations

import base64
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

SVG_NS = "http://www.w3.org/2000/svg"
CUT_COLOR = "#ff00ff"


@dataclass
class CutPath:
    points: list[tuple[float, float]]  # millimetres
    is_hole: bool = False

    def to_d(self, dx: float = 0.0, dy: float = 0.0, transform=None) -> str:
        pts = self.points if transform is None else [transform(x, y) for x, y in self.points]
        head = pts[0]
        parts = [f"M{head[0] + dx:.3f},{head[1] + dy:.3f}"]
        parts += [f"L{x + dx:.3f},{y + dy:.3f}" for x, y in pts[1:]]
        return " ".join(parts) + " Z"


def _segments_intersect(poly: np.ndarray) -> bool:
    """True when any two non-adjacent edges of a closed polygon intersect."""
    n = len(poly)
    if n < 4:
        return False
    a = poly
    b = np.roll(poly, -1, axis=0)
    for i in range(n):
        p, q = a[i], b[i]
        js = np.arange(i + 2, n if i > 0 else n - 1)
        if js.size == 0:
            continue
        r, s = a[js], b[js]

        def orient(u, v, w):
            return np.sign((v[..., 0] - u[..., 0]) * (w[..., 1] - u[..., 1]) - (v[..., 1] - u[..., 1]) * (w[..., 0] - u[..., 0]))

        o1 = orient(p, q, r)
        o2 = orient(p, q, s)
        o3 = orient(r, s, np.broadcast_to(p, r.shape))
        o4 = orient(r, s, np.broadcast_to(q, r.shape))
        if np.any((o1 * o2 < 0) & (o3 * o4 < 0)):
            return True
    return False


def chaikin(points: np.ndarray, iterations: int = 1) -> np.ndarray:
    pts = points
    for _ in range(iterations):
        nxt = np.roll(pts, -1, axis=0)
        q = 0.75 * pts + 0.25 * nxt
        r = 0.25 * pts + 0.75 * nxt
        pts = np.empty((len(pts) * 2, 2), pts.dtype)
        pts[0::2], pts[1::2] = q, r
    return pts


def trace_cut_paths(mask: np.ndarray, px_per_mm: float, *, tolerance_mm: float = 0.08, smooth: int = 1,
                    min_area_mm2: float = 1.0, include_holes: bool = False) -> list[CutPath]:
    """Trace a 0/255 mask into simplified closed paths in millimetres."""
    binary = np.where(mask >= 128, 255, 0).astype(np.uint8)
    mode = cv2.RETR_CCOMP if include_holes else cv2.RETR_EXTERNAL
    contours, hierarchy = cv2.findContours(binary, mode, cv2.CHAIN_APPROX_NONE)
    paths: list[CutPath] = []
    min_area_px = min_area_mm2 * px_per_mm * px_per_mm
    for idx, c in enumerate(contours):
        if cv2.contourArea(c) < min_area_px:
            continue
        is_hole = bool(include_holes and hierarchy is not None and hierarchy[0][idx][3] >= 0)
        raw = c.reshape(-1, 2).astype(np.float64) + 0.5  # pixel centres
        eps_px = tolerance_mm * px_per_mm
        pts = raw
        for attempt in range(4):
            approx = cv2.approxPolyDP(raw.astype(np.float32).reshape(-1, 1, 2), eps_px, True).reshape(-1, 2).astype(np.float64)
            if len(approx) >= 3:
                cand = chaikin(approx, smooth) if smooth else approx
                if not _segments_intersect(cand):
                    pts = cand
                    break
            eps_px /= 2
        else:
            pts = raw  # traced contour of a binary mask is always simple
        paths.append(CutPath([(float(x) / px_per_mm, float(y) / px_per_mm) for x, y in pts], is_hole))
    return paths


def png_data_uri(img: Image.Image, dpi: int = 300) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(dpi, dpi))
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _svg_root(width_mm: float, height_mm: float, title: str) -> ET.Element:
    ET.register_namespace("", SVG_NS)
    root = ET.Element(f"{{{SVG_NS}}}svg", {
        "version": "1.1", "width": f"{width_mm:.3f}mm", "height": f"{height_mm:.3f}mm",
        "viewBox": f"0 0 {width_mm:.3f} {height_mm:.3f}",
    })
    t = ET.SubElement(root, f"{{{SVG_NS}}}title")
    t.text = title
    return root


def _cut_group(root: ET.Element, label: str = "Cut lines") -> ET.Element:
    return ET.SubElement(root, f"{{{SVG_NS}}}g", {
        "id": "cut-lines", "data-label": label, "fill": "none", "stroke": CUT_COLOR,
        "stroke-width": "0.25", "stroke-linejoin": "round", "fill-rule": "evenodd",
    })


def sticker_svg(image: Image.Image, paths: list[CutPath], px_per_mm: float, *, title: str = "Sticker",
                include_artwork: bool = True, include_cut: bool = True, dpi: int = 300) -> str:
    """One sticker: embedded PNG artwork plus a separate cut-path group."""
    w_mm, h_mm = image.width / px_per_mm, image.height / px_per_mm
    root = _svg_root(w_mm, h_mm, title)
    if include_artwork:
        g = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "artwork"})
        ET.SubElement(g, f"{{{SVG_NS}}}image", {
            "x": "0", "y": "0", "width": f"{w_mm:.3f}", "height": f"{h_mm:.3f}",
            "preserveAspectRatio": "none", "href": png_data_uri(image, dpi),
        })
    if include_cut and paths:
        g = _cut_group(root)
        d = " ".join(p.to_d() for p in paths)
        ET.SubElement(g, f"{{{SVG_NS}}}path", {"id": "cut", "d": d})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


@dataclass
class Placement:
    image: Image.Image
    paths: list[CutPath]  # mm, in the sticker's own coordinates
    x_mm: float  # unrotated box top-left on the page
    y_mm: float
    width_mm: float
    height_mm: float
    rotation: float
    name: str = "Sticker"
    design_w_mm: float = 0.0  # size the path coordinates refer to
    design_h_mm: float = 0.0


def _placement_transform(p: Placement):
    import math

    sx = p.width_mm / (p.design_w_mm or p.width_mm)
    sy = p.height_mm / (p.design_h_mm or p.height_mm)
    cx, cy = p.x_mm + p.width_mm / 2, p.y_mm + p.height_mm / 2
    a = math.radians(p.rotation)
    c, s = math.cos(a), math.sin(a)

    def tf(x, y):
        lx, ly = x * sx - p.width_mm / 2, y * sy - p.height_mm / 2
        return cx + lx * c - ly * s, cy + lx * s + ly * c

    return tf


def sheet_svg(page_w_mm: float, page_h_mm: float, placements: list[Placement], *, title: str = "Sticker sheet",
              include_artwork: bool = True, include_cut: bool = True) -> str:
    root = _svg_root(page_w_mm, page_h_mm, title)
    if include_artwork:
        art = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "artwork"})
        for i, p in enumerate(placements):
            cx, cy = p.x_mm + p.width_mm / 2, p.y_mm + p.height_mm / 2
            ET.SubElement(art, f"{{{SVG_NS}}}image", {
                "id": f"art-{i + 1}", "x": f"{p.x_mm:.3f}", "y": f"{p.y_mm:.3f}",
                "width": f"{p.width_mm:.3f}", "height": f"{p.height_mm:.3f}", "preserveAspectRatio": "none",
                "transform": f"rotate({p.rotation:.3f} {cx:.3f} {cy:.3f})" if p.rotation else "",
                "href": png_data_uri(p.image),
            })
        for el in art:
            if not el.get("transform"):
                del el.attrib["transform"]
    if include_cut:
        g = _cut_group(root)
        for i, p in enumerate(placements):
            if not p.paths:
                continue
            tf = _placement_transform(p)
            d = " ".join(cp.to_d(transform=tf) for cp in p.paths)
            ET.SubElement(g, f"{{{SVG_NS}}}path", {"id": f"cut-{i + 1}", "d": d, "data-name": p.name})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def paths_bbox(paths: list[CutPath]) -> tuple[float, float, float, float]:
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    return min(xs), min(ys), max(xs), max(ys)
