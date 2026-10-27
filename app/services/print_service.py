"""Print rendering of sheets to raster PNG and vector-page PDF.

The PDF page is exactly A4 (595.276 × 841.890 pt portrait). Each sticker is
placed as a transparent image at its physical size; nothing is scaled to
fit the page. Print with "Actual size" / 100 % scaling.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from ..models.layout import Sheet, SheetPage
from ..utils.image_dimensions import mm_to_pt, mm_to_px, mm_to_px_int
from ..utils.validation import parse_color
from .svg_cut_service import CutPath

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]


@dataclass
class PlacedSticker:
    image: Image.Image  # RGBA, finished sticker artwork
    paths: list[CutPath]  # cut paths in mm, relative to the sticker's top-left at design size
    design_w_mm: float
    design_h_mm: float
    name: str = "Sticker"


# provider(sticker_id, width_mm, height_mm, dpi) -> PlacedSticker rendered for that size
StickerProvider = Callable[[str, float, float, int], PlacedSticker]


class ExportCancelled(Exception):
    pass


def _noop(_p: float, _m: str) -> None:
    pass


def render_page_png(sheet: Sheet, page: SheetPage, provider: StickerProvider, *, dpi: int | None = None,
                    transparent: bool = False, draw_cut_lines: bool = False, show_printable: bool = False,
                    progress: ProgressFn = _noop, cancelled: CancelFn = lambda: False) -> Image.Image:
    dpi = int(dpi or sheet.dpi)
    pw, ph = sheet.page_size.px(dpi)
    bg = (0, 0, 0, 0) if transparent else parse_color(sheet.background, (255, 255, 255, 255))
    page_img = Image.new("RGBA", (pw, ph), bg)
    n = len(page.items)
    for i, it in enumerate(page.items):
        if cancelled():
            raise ExportCancelled()
        placed = provider(it.sticker_id, it.width_mm, it.height_mm, dpi)
        w_px, h_px = max(1, mm_to_px_int(it.width_mm, dpi)), max(1, mm_to_px_int(it.height_mm, dpi))
        img = placed.image
        if img.size != (w_px, h_px):
            img = img.resize((w_px, h_px), Image.Resampling.LANCZOS)
        if it.rotation % 360:
            img = img.convert("RGBa").rotate(-it.rotation, resample=Image.Resampling.BICUBIC, expand=True).convert("RGBA")
        cx = mm_to_px(it.x_mm + it.width_mm / 2, dpi)
        cy = mm_to_px(it.y_mm + it.height_mm / 2, dpi)
        page_img.alpha_composite(_clip_paste(img, int(round(cx - img.width / 2)), int(round(cy - img.height / 2)), (pw, ph)))
        progress((i + 1) / max(1, n), f"Placed sticker {i + 1} of {n}")
    if draw_cut_lines or show_printable:
        d = ImageDraw.Draw(page_img)
        k = dpi / 25.4
        if show_printable:
            x0, y0, x1, y1 = sheet.printable_rect()
            d.rectangle((x0 * k, y0 * k, x1 * k, y1 * k), outline=(0, 160, 255, 255), width=max(1, dpi // 150))
        if draw_cut_lines:
            for it in page.items:
                placed = provider(it.sticker_id, it.width_mm, it.height_mm, dpi)
                for poly in transformed_paths(placed, it):
                    pts = [(x * k, y * k) for x, y in poly]
                    d.line(pts + [pts[0]], fill=(255, 0, 255, 255), width=max(1, dpi // 150))
    return page_img


def _clip_paste(img: Image.Image, x: int, y: int, size: tuple[int, int]) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(img, (x, y))
    return layer


def transformed_paths(placed: PlacedSticker, it) -> list[list[tuple[float, float]]]:
    """Cut paths mapped to page millimetres (scale to item size, rotate about its centre)."""
    sx = it.width_mm / (placed.design_w_mm or it.width_mm)
    sy = it.height_mm / (placed.design_h_mm or it.height_mm)
    cx, cy = it.x_mm + it.width_mm / 2, it.y_mm + it.height_mm / 2
    a = math.radians(it.rotation)
    c, s = math.cos(a), math.sin(a)
    out = []
    for p in placed.paths:
        poly = []
        for x, y in p.points:
            lx, ly = x * sx - it.width_mm / 2, y * sy - it.height_mm / 2
            poly.append((cx + lx * c - ly * s, cy + lx * s + ly * c))
        out.append(poly)
    return out


def save_png_with_dpi(img: Image.Image, path: Path, dpi: int, *, flatten: bool = False) -> None:
    out = img
    if flatten:
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        out = bg.convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, "PNG", dpi=(dpi, dpi))


def register_pdf_font(font_path: Path | None) -> str:
    """Register a bundled TTF with ReportLab (subset-embedded in the PDF)."""
    if not font_path or not font_path.exists():
        return "Helvetica"
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "OSS-" + font_path.stem
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(font_path)))
    return name


def render_pdf(sheet: Sheet, provider: StickerProvider, out_path: Path, *, title: str = "Sticker sheet",
               cut_lines: bool | None = None, label_font: Path | None = None,
               progress: ProgressFn = _noop, cancelled: CancelFn = lambda: False) -> dict:
    """Write a multi-page PDF. Returns page size information for verification."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    page_w_pt, page_h_pt = sheet.page_size.pt()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(out_path), pagesize=(page_w_pt, page_h_pt), pageCompression=1)
    c.setTitle(title)
    c.setCreator("Offline Sticker Studio")
    c.setProducer("Offline Sticker Studio (ReportLab)")
    c.setSubject("A4 sticker sheet. Print at 100% / Actual size.")
    font_name = register_pdf_font(label_font) if sheet.label else "Helvetica"
    draw_cuts = sheet.show_cut_lines if cut_lines is None else cut_lines
    total = sum(len(p.items) for p in sheet.pages) or 1
    done = 0
    for page_idx, page in enumerate(sheet.pages):
        if sheet.background and sheet.background.lower() not in ("#ffffff", "#fff", "#ffffffff"):
            r, g, b, _ = parse_color(sheet.background)
            c.setFillColorRGB(r / 255, g / 255, b / 255)
            c.rect(0, 0, page_w_pt, page_h_pt, stroke=0, fill=1)
        for it in page.items:
            if cancelled():
                raise ExportCancelled()
            placed = provider(it.sticker_id, it.width_mm, it.height_mm, sheet.dpi)
            buf = io.BytesIO()
            placed.image.save(buf, "PNG")
            buf.seek(0)
            w_pt, h_pt = mm_to_pt(it.width_mm), mm_to_pt(it.height_mm)
            cx_pt = mm_to_pt(it.x_mm + it.width_mm / 2)
            cy_pt = page_h_pt - mm_to_pt(it.y_mm + it.height_mm / 2)
            c.saveState()
            c.translate(cx_pt, cy_pt)
            if it.rotation % 360:
                c.rotate(-it.rotation)  # page is y-up; our rotation is clockwise on screen
            c.drawImage(ImageReader(buf), -w_pt / 2, -h_pt / 2, width=w_pt, height=h_pt, mask="auto")
            c.restoreState()
            done += 1
            progress(done / total, f"PDF: sticker {done} of {total}")
        if draw_cuts:
            c.saveState()
            c.setStrokeColorRGB(1, 0, 1)
            c.setLineWidth(0.25)
            for it in page.items:
                placed = provider(it.sticker_id, it.width_mm, it.height_mm, sheet.dpi)
                for poly in transformed_paths(placed, it):
                    path = c.beginPath()
                    x0, y0 = poly[0]
                    path.moveTo(mm_to_pt(x0), page_h_pt - mm_to_pt(y0))
                    for x, y in poly[1:]:
                        path.lineTo(mm_to_pt(x), page_h_pt - mm_to_pt(y))
                    path.close()
                    c.drawPath(path, stroke=1, fill=0)
            c.restoreState()
        if sheet.label:
            x0, y0, x1, y1 = sheet.printable_rect()
            c.setFont(font_name, 8)
            c.setFillColorRGB(0.35, 0.35, 0.4)
            label = sheet.label if len(sheet.pages) == 1 else f"{sheet.label} — page {page_idx + 1}/{len(sheet.pages)}"
            c.drawString(mm_to_pt(x0 + 2), page_h_pt - mm_to_pt(y1 - 2.5), label[:120])
        c.showPage()
    c.save()
    return {"pages": len(sheet.pages), "pageWidthPt": page_w_pt, "pageHeightPt": page_h_pt}
