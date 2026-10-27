"""A4 sheet layout: automatic grid, space-efficient packing and validation.

All units are millimetres. Packing uses the MaxRects algorithm (best short
side fit) with optional 90° rotation; the gap is enforced by inflating
every item and the container by the gap width.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..models.layout import Sheet, SheetItem, SheetPage


@dataclass
class Request:
    sticker_id: str
    width_mm: float
    height_mm: float
    copies: int = 1


@dataclass
class _Rect:
    x: float
    y: float
    w: float
    h: float


def expand_requests(requests: list[Request]) -> list[Request]:
    out = []
    for r in requests:
        for _ in range(max(0, int(r.copies))):
            out.append(Request(r.sticker_id, r.width_mm, r.height_mm, 1))
    return out


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------

def grid_layout(sheet: Sheet, requests: list[Request], *, center: bool = True) -> list[SheetPage]:
    """Uniform grid; the cell is the largest requested sticker."""
    items = expand_requests(requests)
    if not items:
        return [SheetPage()]
    x0, y0, x1, y1 = sheet.content_rect()
    W, H = x1 - x0, y1 - y0
    cw = max(r.width_mm for r in items)
    ch = max(r.height_mm for r in items)
    g = sheet.gap_mm
    cols = int((W + g + 1e-6) // (cw + g))
    rows = int((H + g + 1e-6) // (ch + g))
    if cols < 1 or rows < 1:
        raise ValueError(f"A {cw:.0f}×{ch:.0f} mm sticker does not fit in the printable area ({W:.0f}×{H:.0f} mm).")
    used_w = cols * cw + (cols - 1) * g
    used_h = rows * ch + (rows - 1) * g
    ox = x0 + ((W - used_w) / 2 if center else 0)
    oy = y0 + ((H - used_h) / 2 if center else 0)
    per_page = cols * rows
    pages: list[SheetPage] = []
    for start in range(0, len(items), per_page):
        page = SheetPage()
        for i, r in enumerate(items[start:start + per_page]):
            c, rr = i % cols, i // cols
            cx = ox + c * (cw + g) + (cw - r.width_mm) / 2
            cy = oy + rr * (ch + g) + (ch - r.height_mm) / 2
            page.items.append(SheetItem(sticker_id=r.sticker_id, x_mm=round(cx, 3), y_mm=round(cy, 3),
                                        width_mm=r.width_mm, height_mm=r.height_mm))
        pages.append(page)
    return pages


# --------------------------------------------------------------------------
# MaxRects packing
# --------------------------------------------------------------------------

class MaxRects:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.free = [_Rect(0, 0, w, h)]

    def insert(self, w: float, h: float, allow_rotate: bool) -> tuple[_Rect, bool] | None:
        best = None
        for f in self.free:
            for rot in ((False, True) if allow_rotate else (False,)):
                iw, ih = (h, w) if rot else (w, h)
                if iw <= f.w + 1e-9 and ih <= f.h + 1e-9:
                    short = min(f.w - iw, f.h - ih)
                    long_ = max(f.w - iw, f.h - ih)
                    score = (short, long_, f.y, f.x)
                    if best is None or score < best[0]:
                        best = (score, _Rect(f.x, f.y, iw, ih), rot)
        if best is None:
            return None
        placed = best[1]
        self._split(placed)
        return placed, best[2]

    def _split(self, used: _Rect) -> None:
        new_free = []
        for f in self.free:
            if used.x >= f.x + f.w or used.x + used.w <= f.x or used.y >= f.y + f.h or used.y + used.h <= f.y:
                new_free.append(f)
                continue
            if used.x > f.x:
                new_free.append(_Rect(f.x, f.y, used.x - f.x, f.h))
            if used.x + used.w < f.x + f.w:
                new_free.append(_Rect(used.x + used.w, f.y, f.x + f.w - used.x - used.w, f.h))
            if used.y > f.y:
                new_free.append(_Rect(f.x, f.y, f.w, used.y - f.y))
            if used.y + used.h < f.y + f.h:
                new_free.append(_Rect(f.x, used.y + used.h, f.w, f.y + f.h - used.y - used.h))
        # Prune rectangles contained in others.
        pruned = []
        for i, a in enumerate(new_free):
            if a.w <= 1e-9 or a.h <= 1e-9:
                continue
            contained = False
            for j, b in enumerate(new_free):
                if i != j and a.x >= b.x - 1e-9 and a.y >= b.y - 1e-9 and a.x + a.w <= b.x + b.w + 1e-9 and a.y + a.h <= b.y + b.h + 1e-9:
                    if (a.x, a.y, a.w, a.h) != (b.x, b.y, b.w, b.h) or i > j:
                        contained = True
                        break
            if not contained:
                pruned.append(a)
        self.free = pruned


def pack_layout(sheet: Sheet, requests: list[Request], *, allow_rotate: bool = True) -> list[SheetPage]:
    """Space-efficient packing over as many pages as needed."""
    items = expand_requests(requests)
    if not items:
        return [SheetPage()]
    x0, y0, x1, y1 = sheet.content_rect()
    W, H = x1 - x0, y1 - y0
    g = sheet.gap_mm
    for r in items:
        fits = (r.width_mm <= W + 1e-6 and r.height_mm <= H + 1e-6) or (
            allow_rotate and r.height_mm <= W + 1e-6 and r.width_mm <= H + 1e-6)
        if not fits:
            raise ValueError(f"A {r.width_mm:.0f}×{r.height_mm:.0f} mm sticker does not fit in the printable area ({W:.0f}×{H:.0f} mm).")
    # Largest first gives much better packing.
    order = sorted(items, key=lambda r: (max(r.width_mm, r.height_mm), r.width_mm * r.height_mm), reverse=True)
    pages: list[SheetPage] = []
    remaining = order
    while remaining:
        packer = MaxRects(W + g, H + g)
        page = SheetPage()
        left = []
        for r in remaining:
            res = packer.insert(r.width_mm + g, r.height_mm + g, allow_rotate)
            if res is None:
                left.append(r)
                continue
            rect, rotated = res
            w, h = (r.height_mm, r.width_mm) if rotated else (r.width_mm, r.height_mm)
            # Items store unrotated size + rotation; position is the unrotated box
            # centred on the packed slot.
            cx, cy = x0 + rect.x + w / 2, y0 + rect.y + h / 2
            page.items.append(SheetItem(sticker_id=r.sticker_id, x_mm=round(cx - r.width_mm / 2, 3),
                                        y_mm=round(cy - r.height_mm / 2, 3), width_mm=r.width_mm,
                                        height_mm=r.height_mm, rotation=90.0 if rotated else 0.0))
        if not page.items:  # pragma: no cover - guarded by the fit check above
            raise ValueError("Could not place stickers on the page.")
        pages.append(page)
        remaining = left
    return pages


def fit_to_page(sheet: Sheet, requests: list[Request], *, allow_rotate: bool = True, max_scale: float = 4.0) -> tuple[float, list[SheetPage]]:
    """Largest uniform scale at which every requested sticker fits on one page."""
    lo, hi = 0.01, max_scale
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        scaled = [Request(r.sticker_id, r.width_mm * mid, r.height_mm * mid, r.copies) for r in requests]
        try:
            pages = pack_layout(sheet, scaled, allow_rotate=allow_rotate)
            ok = len(pages) == 1
        except ValueError:
            ok = False
        if ok:
            lo, best = mid, (mid, pages)
        else:
            hi = mid
    if best is None:
        raise ValueError("The stickers cannot fit on one page.")
    return best


def fill_page(sheet: Sheet, sticker_ids: list[str], sizes: dict[str, tuple[float, float]], mode: str = "pack",
              allow_rotate: bool = True) -> list[SheetPage]:
    """Repeat the given stickers (round-robin) until one page is full."""
    if not sticker_ids:
        return [SheetPage()]
    reqs: list[Request] = []
    best_pages = None
    for n in range(1, 400):
        sid = sticker_ids[(n - 1) % len(sticker_ids)]
        reqs.append(Request(sid, *sizes[sid], 1))
        pages = grid_layout(sheet, reqs) if mode == "grid" else pack_layout(sheet, reqs, allow_rotate=allow_rotate)
        if len(pages) > 1:
            break
        best_pages = pages
    return best_pages or [SheetPage()]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _corners(it: SheetItem) -> list[tuple[float, float]]:
    cx, cy = it.x_mm + it.width_mm / 2, it.y_mm + it.height_mm / 2
    a = math.radians(it.rotation)
    c, s = math.cos(a), math.sin(a)
    hw, hh = it.width_mm / 2, it.height_mm / 2
    return [(cx + dx * c - dy * s, cy + dx * s + dy * c) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


def rects_overlap(a: SheetItem, b: SheetItem, tolerance: float = 0.05) -> bool:
    """Separating-axis test for two (possibly rotated) rectangles."""
    pa, pb = _corners(a), _corners(b)
    for poly in (pa, pb):
        for i in range(4):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % 4]
            nx, ny = y2 - y1, x1 - x2
            length = math.hypot(nx, ny) or 1
            nx, ny = nx / length, ny / length
            proj_a = [px * nx + py * ny for px, py in pa]
            proj_b = [px * nx + py * ny for px, py in pb]
            if max(proj_a) <= min(proj_b) + tolerance or max(proj_b) <= min(proj_a) + tolerance:
                return False
    return True


def validate_sheet(sheet: Sheet, sticker_info: dict[str, dict], *, low_res_dpi: float = 150.0) -> list[dict]:
    """Return warnings: overlaps, items outside the printable area, low resolution, missing stickers."""
    warnings: list[dict] = []
    px0, py0, px1, py1 = sheet.printable_rect()
    pw, ph = sheet.page_size.width_mm, sheet.page_size.height_mm
    for pi, page in enumerate(sheet.pages):
        for i, it in enumerate(page.items):
            info = sticker_info.get(it.sticker_id)
            if info is None:
                warnings.append({"level": "error", "code": "missing", "page": pi, "itemId": it.id,
                                 "message": "This item refers to a sticker that no longer exists."})
                continue
            x0, y0, x1, y1 = it.bbox()
            if x0 < -0.01 or y0 < -0.01 or x1 > pw + 0.01 or y1 > ph + 0.01:
                warnings.append({"level": "error", "code": "off-page", "page": pi, "itemId": it.id,
                                 "message": f"'{info.get('name', 'Sticker')}' extends beyond the edge of the page."})
            elif x0 < px0 - 0.01 or y0 < py0 - 0.01 or x1 > px1 + 0.01 or y1 > py1 + 0.01:
                warnings.append({"level": "warning", "code": "outside-printable", "page": pi, "itemId": it.id,
                                 "message": f"'{info.get('name', 'Sticker')}' extends outside the printable area."})
            dpi = info.get("minEffectiveDpi")
            design_w = info.get("widthMm")
            if dpi and design_w:
                eff = dpi * design_w / max(0.1, it.width_mm)
                if eff < low_res_dpi:
                    warnings.append({"level": "warning", "code": "low-res", "page": pi, "itemId": it.id,
                                     "message": f"'{info.get('name', 'Sticker')}' will print at about {eff:.0f} DPI "
                                                "and may look blurry. Print it smaller or use a larger photo."})
                elif eff < 300 * 0.98:
                    warnings.append({"level": "info", "code": "upscaled", "page": pi, "itemId": it.id,
                                     "message": f"'{info.get('name', 'Sticker')}' photo pixels are enlarged "
                                                f"(about {eff:.0f} DPI)."})
            for j in range(i + 1, len(page.items)):
                other = page.items[j]
                if rects_overlap(it, other):
                    warnings.append({"level": "warning", "code": "overlap", "page": pi, "itemId": it.id,
                                     "otherId": other.id, "message": "Two stickers overlap. Cutting may fail."})
    return warnings
