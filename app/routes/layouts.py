"""A4 sheet layout: automatic arrangement, validation, sticker sizes and page previews."""
from __future__ import annotations

from flask import Blueprint, jsonify

from ..errors import AppError
from ..extensions import services
from ..models.layout import Sheet
from ..services import layout_service, print_service
from ..services.export_service import StickerCache
from ..utils.validation import as_float
from ._common import body, png_response, render_context

bp = Blueprint("layouts", __name__, url_prefix="/api/projects/<pid>/layout")


def _sheet(data: dict) -> Sheet:
    raw = data.get("sheet")
    if not isinstance(raw, dict):
        raise AppError("Missing sheet.")
    return Sheet.from_dict(raw)


def _sizes(pid: str, project: dict, ids: list[str]) -> dict[str, dict]:
    svc = services()
    ctx = render_context(pid, project)
    cache = StickerCache(project, ctx)

    def work(handle):
        out = {}
        for sid in ids:
            if sid not in cache.stickers:
                continue
            res = cache.full(sid, 75)  # quick probe; sizes are physical so DPI does not matter
            st = cache.stickers[sid]
            out[sid] = {"name": st.name, "widthMm": round(res.size_mm[0], 3), "heightMm": round(res.size_mm[1], 3),
                        "minEffectiveDpi": round(res.min_effective_dpi * st.dpi / 75, 1) if res.min_effective_dpi else None,
                        "warnings": res.warnings}
            handle.progress(len(out) / max(1, len(ids)))
        return out

    return svc.jobs.run_sync("sticker-sizes", work, timeout=120, project_id=pid)


@bp.post("/sizes")
def sizes(pid: str):
    """Finished physical size (mm) and resolution information for stickers."""
    project = services().projects.load(pid, prefer_autosave=True)
    if isinstance(body().get("stickers"), list):
        project["stickers"] = body()["stickers"]
    ids = [s for s in body().get("stickerIds", []) if isinstance(s, str)] or [s["id"] for s in project.get("stickers", [])]
    return jsonify({"sizes": _sizes(pid, project, ids)})


@bp.post("/auto")
def auto(pid: str):
    """Arrange stickers: mode "grid", "pack", "fill" (repeat to fill a page) or "fit" (scale to one page)."""
    data = body()
    sheet = _sheet(data)
    mode = data.get("mode", "pack")
    allow_rotate = bool(data.get("allowRotate", True))
    reqs = []
    for r in data.get("requests", []):
        try:
            reqs.append(layout_service.Request(str(r["stickerId"]), as_float(r["widthMm"], 50, 2, 300),
                                               as_float(r["heightMm"], 50, 2, 300), int(as_float(r.get("copies"), 1, 0, 200))))
        except (KeyError, TypeError):
            raise AppError("Invalid layout request.") from None
    try:
        if mode == "grid":
            pages = layout_service.grid_layout(sheet, reqs)
            scale = 1.0
        elif mode == "fit":
            scale, pages = layout_service.fit_to_page(sheet, reqs, allow_rotate=allow_rotate)
        elif mode == "fill":
            sizes = {r.sticker_id: (r.width_mm, r.height_mm) for r in reqs}
            pages = layout_service.fill_page(sheet, list(dict.fromkeys(r.sticker_id for r in reqs)), sizes,
                                             mode="grid" if data.get("fillMode") == "grid" else "pack", allow_rotate=allow_rotate)
            scale = 1.0
        else:
            pages = layout_service.pack_layout(sheet, reqs, allow_rotate=allow_rotate)
            scale = 1.0
    except ValueError as exc:
        raise AppError(str(exc)) from None
    return jsonify({"pages": Sheet(pages=pages).to_dict()["pages"], "scale": scale})


@bp.post("/validate")
def validate(pid: str):
    svc = services()
    data = body()
    sheet = _sheet(data)
    project = svc.projects.load(pid, prefer_autosave=True)
    if isinstance(data.get("stickers"), list):
        project["stickers"] = data["stickers"]
    ids = list({it.sticker_id for p in sheet.pages for it in p.items})
    info = _sizes(pid, project, ids)
    warnings = layout_service.validate_sheet(sheet, info, low_res_dpi=svc.settings.low_resolution_warning_dpi)
    return jsonify({"warnings": warnings, "sizes": info})


@bp.post("/preview")
def preview(pid: str):
    """Low-resolution raster preview of one page, exactly as it will print."""
    svc = services()
    data = body()
    sheet = _sheet(data)
    page_idx = int(as_float(data.get("page"), 0, 0, 999))
    if page_idx >= len(sheet.pages):
        raise AppError("No such page.")
    project = svc.projects.load(pid, prefer_autosave=True)
    if isinstance(data.get("stickers"), list):
        project["stickers"] = data["stickers"]
    ctx = render_context(pid, project)
    cache = StickerCache(project, ctx)
    dpi = int(as_float(data.get("dpi"), 60, 20, 150))

    def work(handle):
        return print_service.render_page_png(sheet, sheet.pages[page_idx], cache.provider, dpi=dpi,
                                             draw_cut_lines=bool(data.get("cutLines")), show_printable=bool(data.get("showPrintable")),
                                             progress=handle.progress, cancelled=handle.cancelled)

    return png_response(svc.jobs.run_sync("sheet-preview", work, timeout=120, project_id=pid))
