"""Export orchestration: individual stickers, sheets (PNG/PDF/SVG) and archives.

Exports are written into ``<project>/exports/<timestamp>-<kind>/`` and
recorded in the export history. Every export also writes a small
``export-info.json`` describing sizes and DPI, which the tests use to
verify physical dimensions.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from ..models.layout import Sheet
from ..models.sticker import StickerDoc
from ..utils.image_dimensions import MM_PER_INCH, mm_to_px_int
from ..utils.paths import sanitize_filename
from . import print_service, svg_cut_service
from .print_service import PlacedSticker
from .sticker_service import RenderContext, render_sticker

ProgressFn = Callable[[float, str], None]

EXPORT_KINDS = ("stickers-png", "sheet-png", "sheet-pdf", "sheet-svg", "cut-svg", "stickers-svg", "archive", "cricut-bundle")


@dataclass
class ExportOptions:
    kind: str
    sticker_ids: list[str] | None = None
    sheet_id: str | None = None
    dpi: int = 300
    transparent: bool = False
    cut_lines: bool = False
    cut_offset_mm: float | None = None
    include_holes: bool = False


class StickerCache:
    """Renders stickers once per requested size during an export."""

    def __init__(self, doc: dict, ctx: RenderContext, cut_offset_mm: float | None = None, include_holes: bool = False):
        self.stickers = {s["id"]: StickerDoc.from_dict(s) for s in doc.get("stickers", [])}
        self.ctx = ctx
        self.cut_offset_mm = cut_offset_mm
        self.include_holes = include_holes
        self._design: dict[str, tuple[float, float]] = {}
        self._cache: dict[tuple, PlacedSticker] = {}

    def doc(self, sid: str) -> StickerDoc:
        if sid not in self.stickers:
            raise KeyError(f"Sticker {sid} not found")
        st = self.stickers[sid]
        if self.cut_offset_mm is not None:
            st.cut_offset_mm = self.cut_offset_mm
        return st

    def design_size(self, sid: str) -> tuple[float, float]:
        if sid not in self._design:
            self._design[sid] = render_sticker(self.doc(sid), self.ctx, 0.25).size_mm
        return self._design[sid]

    def full(self, sid: str, dpi: int = 300):
        """Finished sticker at its design size and the requested DPI."""
        st = self.doc(sid)
        return render_sticker(st, self.ctx, dpi / st.dpi)

    def provider(self, sid: str, width_mm: float, height_mm: float, dpi: int) -> PlacedSticker:
        key = (sid, round(width_mm, 3), round(height_mm, 3), dpi)
        if key not in self._cache:
            st = self.doc(sid)
            dw, dh = self.design_size(sid)
            scale = (width_mm / dw) * (dpi / st.dpi)
            res = render_sticker(st, self.ctx, scale)
            px_per_design_mm = res.image.width / dw
            paths = svg_cut_service.trace_cut_paths(res.cut_mask, px_per_design_mm, include_holes=self.include_holes)
            self._cache[key] = PlacedSticker(res.image, paths, dw, dh, st.name)
        return self._cache[key]


def _sheet(doc: dict, sheet_id: str | None) -> Sheet:
    sheets = [Sheet.from_dict(s) for s in doc.get("sheets", [])]
    for s in sheets:
        if sheet_id is None or s.id == sheet_id:
            return s
    raise KeyError("Sheet not found")


def _unique(name: str, used: set[str]) -> str:
    stem, dot, ext = name.rpartition(".")
    candidate, n = name, 2
    while candidate in used:
        candidate = f"{stem}-{n}.{ext}" if dot else f"{name}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def export(doc: dict, ctx: RenderContext, opts: ExportOptions, out_dir: Path, *, font_path: Path | None = None,
           progress: ProgressFn = lambda p, m: None, cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Run one export and return ``{"files": [...], "info": {...}}``."""
    if opts.kind not in EXPORT_KINDS or opts.kind == "archive":
        raise ValueError(f"Unsupported export kind: {opts.kind}")
    dpi = int(max(72, min(600, opts.dpi)))
    cache = StickerCache(doc, ctx, opts.cut_offset_mm, opts.include_holes)
    files: list[str] = []
    used: set[str] = set()
    info: dict = {"kind": opts.kind, "dpi": dpi, "items": []}

    def check():
        if cancelled():
            raise print_service.ExportCancelled()

    if opts.kind in ("stickers-png", "stickers-svg", "cricut-bundle"):
        ids = opts.sticker_ids or list(cache.stickers)
        if not ids:
            raise ValueError("There are no stickers to export.")
        zip_name = "stickers.zip"
        zpath = out_dir / zip_name
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for n, sid in enumerate(ids):
                check()
                st = cache.doc(sid)
                res = cache.full(sid, dpi)
                base = sanitize_filename(f"{n + 1:02d}-{st.name}", default=f"sticker-{n + 1}")
                w_mm, h_mm = res.image.width / dpi * MM_PER_INCH, res.image.height / dpi * MM_PER_INCH
                entry = {"stickerId": sid, "name": st.name, "widthPx": res.image.width, "heightPx": res.image.height,
                         "widthMm": round(w_mm, 3), "heightMm": round(h_mm, 3), "warnings": res.warnings}
                if opts.kind in ("stickers-png", "cricut-bundle"):
                    fname = _unique(f"{base}.png", used)
                    print_service.save_png_with_dpi(res.image, out_dir / fname, dpi)
                    z.write(out_dir / fname, fname)
                    files.append(fname)
                    entry["png"] = fname
                if opts.kind in ("stickers-svg", "cricut-bundle"):
                    paths = svg_cut_service.trace_cut_paths(res.cut_mask, dpi / MM_PER_INCH, include_holes=opts.include_holes)
                    svg = svg_cut_service.sticker_svg(res.image, paths, dpi / MM_PER_INCH, title=st.name, dpi=dpi)
                    fname = _unique(f"{base}.svg", used)
                    (out_dir / fname).write_text(svg, encoding="utf-8")
                    z.write(out_dir / fname, fname)
                    files.append(fname)
                    cut = svg_cut_service.sticker_svg(res.image, paths, dpi / MM_PER_INCH, title=f"{st.name} cut",
                                                      include_artwork=False)
                    cname = _unique(f"{base}-cut.svg", used)
                    (out_dir / cname).write_text(cut, encoding="utf-8")
                    z.write(out_dir / cname, cname)
                    files.append(cname)
                    entry["svg"], entry["cutSvg"], entry["cutPaths"] = fname, cname, len(paths)
                info["items"].append(entry)
                progress((n + 1) / len(ids), f"Exported {n + 1} of {len(ids)}")
        files.append(zip_name)
    else:
        sheet = _sheet(doc, opts.sheet_id)
        sheet.dpi = dpi
        if not any(p.items for p in sheet.pages):
            raise ValueError("The sheet is empty. Add stickers to the sheet first.")
        pw, ph = sheet.page_size.width_mm, sheet.page_size.height_mm
        info.update({"orientation": sheet.orientation, "pageWidthMm": pw, "pageHeightMm": ph,
                     "pageWidthPx": mm_to_px_int(pw, dpi), "pageHeightPx": mm_to_px_int(ph, dpi),
                     "pages": len(sheet.pages)})
        safe_sheet = sanitize_filename(sheet.name, default="sheet")
        if opts.kind == "sheet-png":
            for i, page in enumerate(sheet.pages):
                check()
                img = print_service.render_page_png(
                    sheet, page, cache.provider, dpi=dpi, transparent=opts.transparent, draw_cut_lines=opts.cut_lines,
                    progress=lambda p, m, i=i: progress((i + p) / len(sheet.pages), m), cancelled=cancelled)
                fname = _unique(f"{safe_sheet}-page{i + 1}.png", used)
                print_service.save_png_with_dpi(img, out_dir / fname, dpi, flatten=not opts.transparent)
                files.append(fname)
        elif opts.kind == "sheet-pdf":
            fname = _unique(f"{safe_sheet}.pdf", used)
            res = print_service.render_pdf(sheet, cache.provider, out_dir / fname, title=sheet.name,
                                           cut_lines=opts.cut_lines, label_font=font_path, progress=progress, cancelled=cancelled)
            info.update(res)
            files.append(fname)
        elif opts.kind in ("sheet-svg", "cut-svg"):
            for i, page in enumerate(sheet.pages):
                check()
                placements = []
                for it in page.items:
                    placed = cache.provider(it.sticker_id, it.width_mm, it.height_mm, dpi)
                    placements.append(svg_cut_service.Placement(
                        placed.image, placed.paths, it.x_mm, it.y_mm, it.width_mm, it.height_mm, it.rotation,
                        placed.name, placed.design_w_mm, placed.design_h_mm))
                svg = svg_cut_service.sheet_svg(pw, ph, placements, title=sheet.name,
                                                include_artwork=opts.kind == "sheet-svg", include_cut=True)
                suffix = "cut" if opts.kind == "cut-svg" else "artwork-and-cut"
                fname = _unique(f"{safe_sheet}-page{i + 1}-{suffix}.svg", used)
                (out_dir / fname).write_text(svg, encoding="utf-8")
                files.append(fname)
                progress((i + 1) / len(sheet.pages), f"SVG page {i + 1}")
    (out_dir / "export-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    files.append("export-info.json")
    return {"files": files, "info": info}


def contact_preview(images: list[Image.Image], max_side: int = 900) -> Image.Image:
    """Small preview image for the export dialog."""
    if not images:
        return Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    img = images[0].copy()
    img.thumbnail((max_side, max_side))
    return img
