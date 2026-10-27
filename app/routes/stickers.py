"""Sticker rendering previews, cut-path previews, new-sticker templates and collections."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify

from ..errors import AppError
from ..extensions import services
from ..models.layer import Layer
from ..models.sticker import StickerDoc
from ..services import svg_cut_service, variation_service
from ..services.sticker_service import render_sticker
from ..utils.image_dimensions import mm_to_px
from ..utils.validation import as_float
from ._common import body, info_header, png_response, render_context

bp = Blueprint("stickers", __name__, url_prefix="/api/projects/<pid>")


def _doc_from(data: dict) -> StickerDoc:
    raw = data.get("sticker")
    if not isinstance(raw, dict):
        raise AppError("Missing sticker document.")
    try:
        return StickerDoc.from_dict(raw)
    except (ValueError, TypeError) as exc:
        raise AppError(f"Invalid sticker document: {exc}") from None


@bp.post("/stickers/render")
def render(pid: str):
    """Render a (possibly unsaved) sticker document to PNG.

    ``maxSide`` limits the preview size; ``mode`` is "sticker" (finished
    with border) or "art" (artboard only). Info about physical size and
    warnings is returned in the ``X-Sticker-Info`` header (base64 JSON).
    """
    svc = services()
    data = body()
    doc_model = _doc_from(data)
    project = svc.projects.load(pid, prefer_autosave=True)
    ctx = render_context(pid, project)
    max_side = as_float(data.get("maxSide"), 600, 32, 4000)
    mode = data.get("mode", "sticker")
    preview_shadow = bool(data.get("previewShadow", True))
    scale = min(1.0, max_side / max(doc_model.width_px, doc_model.height_px))
    if mode == "sticker":
        # Leave room for the border so the finished sticker fits max_side.
        pad = doc_model.border.width_mm + sum(o.width_mm + o.gap_mm for o in doc_model.border.outlines)
        scale = min(1.0, max_side / max(1.0, mm_to_px(max(doc_model.width_mm, doc_model.height_mm) + 2 * pad, doc_model.dpi)))

    def work(handle):
        res = render_sticker(doc_model, ctx, scale, preview_shadow=preview_shadow, art_only=(mode == "art"))
        info = {
            "widthMm": round(res.size_mm[0], 2), "heightMm": round(res.size_mm[1], 2),
            "widthPx": res.image.width, "heightPx": res.image.height, "scale": scale,
            "warnings": res.warnings, "pieces": res.pieces,
            "minEffectiveDpi": round(res.min_effective_dpi, 1) if res.min_effective_dpi else None,
            "artOffset": res.art_offset, "pxPerMm": res.px_per_mm,
        }
        if data.get("withCut"):
            paths = svg_cut_service.trace_cut_paths(res.cut_mask, res.px_per_mm)
            info["cutPaths"] = [p.to_d() for p in paths]
        return res.image, info

    img, info = svc.jobs.run_sync("render", work, timeout=60, project_id=pid)
    return png_response(img, headers={"X-Sticker-Info": info_header(info),
                                      "Access-Control-Expose-Headers": "X-Sticker-Info"})


@bp.post("/stickers/cut-preview")
def cut_preview(pid: str):
    """SVG of the sticker artwork with its cut path overlaid, for inspection."""
    svc = services()
    data = body()
    doc_model = _doc_from(data)
    project = svc.projects.load(pid, prefer_autosave=True)
    ctx = render_context(pid, project)
    max_side = as_float(data.get("maxSide"), 700, 64, 3000)
    scale = min(1.0, max_side / max(doc_model.width_px, doc_model.height_px))

    def work(handle):
        res = render_sticker(doc_model, ctx, scale)
        paths = svg_cut_service.trace_cut_paths(res.cut_mask, res.px_per_mm)
        return svg_cut_service.sticker_svg(res.image, paths, res.px_per_mm, title=doc_model.name,
                                           dpi=int(doc_model.dpi * scale)), len(paths)

    svg, n = svc.jobs.run_sync("cut-preview", work, timeout=60, project_id=pid)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["X-Cut-Paths"] = str(n)
    return resp


@bp.post("/stickers/new")
def new_sticker(pid: str):
    """Create a sticker document for a photo using the project's theme defaults."""
    svc = services()
    data = body()
    project = svc.projects.load(pid, prefer_autosave=True)
    theme_id = data.get("themeId") or project.get("themeId") or "birthday"
    try:
        theme = svc.themes.get(theme_id)
    except Exception:
        theme = svc.themes.get("birthday")
    default_size = (project.get("settings") or {}).get("defaultStickerMm") or svc.settings.default_sticker_mm
    size = as_float(data.get("sizeMm"), default_size, 10, 250)
    photo_id = data.get("photoId")
    if photo_id:
        photo = svc.projects.photo(project, photo_id)
        opts = variation_service.CollectionOptions(photo_ids=[photo_id], theme_id=theme_id, count=1, size_mm=size,
                                                   compositions=["hero"], texts=[], seed=1)
        doc = variation_service.generate_collection(opts, theme, [photo], {})[0]
        doc["name"] = photo.get("name", "Sticker")
    else:
        doc = StickerDoc(name="Blank sticker", width_mm=size, height_mm=size, theme_id=theme_id,
                         border=variation_service.border_for("classic", theme)).to_dict()
        W = mm_to_px(size, 300)
        doc["layers"] = [Layer(type="text", name="Text", text=(theme.get("textPresets") or ["Hello!"])[0],
                               font_family=(theme.get("typography") or {}).get("heading", "Luckiest Guy"),
                               font_size=W * 0.14, fill=(theme.get("colors") or {}).get("text", "#2d2140"),
                               stroke="#ffffff", stroke_width=W * 0.014, x=W / 2, y=W / 2,
                               width=W * 0.8, height=W * 0.2).to_dict()]
    return jsonify({"sticker": doc})


@bp.post("/collection/generate")
def generate(pid: str):
    """Generate a deterministic set of sticker variants (documents only; fast)."""
    svc = services()
    data = body()
    project = svc.projects.load(pid, prefer_autosave=True)
    photo_ids = [p for p in data.get("photoIds", []) if isinstance(p, str)]
    photos = [svc.projects.photo(project, p) for p in photo_ids]
    theme = svc.themes.get(data.get("themeId") or project.get("themeId") or "birthday")
    assets = {a["id"]: a for a in svc.assets.list()}
    opts = variation_service.CollectionOptions(
        photo_ids=photo_ids, theme_id=theme["id"],
        shapes=[s for s in data.get("shapes", ["silhouette"]) if isinstance(s, str)],
        border_styles=[s for s in data.get("borders", ["classic"]) if isinstance(s, str)],
        count=int(as_float(data.get("count"), 6, 1, 48)),
        accessory_ids=[a for a in data.get("accessoryIds", []) if isinstance(a, str)],
        decoration_ids=[a for a in data.get("decorationIds", []) if isinstance(a, str)],
        backgrounds=[b for b in data.get("backgrounds", []) if isinstance(b, dict)],
        texts=[str(t)[:80] for t in data.get("texts", []) if str(t).strip()][:24],
        treatments=[t for t in data.get("treatments", ["none"]) if isinstance(t, str)],
        compositions=[c for c in data.get("compositions", list(variation_service.COMPOSITIONS)) if isinstance(c, str)],
        size_mm=as_float(data.get("sizeMm"), 60, 15, 200),
        seed=int(as_float(data.get("seed"), 1, 0, 2**31)),
        randomize=bool(data.get("randomize", False)),
        use_face_anchors=bool(data.get("useFaceAnchors", True)),
    )
    try:
        docs = variation_service.generate_collection(opts, theme, photos, assets)
    except ValueError as exc:
        raise AppError(str(exc)) from None
    return jsonify({"stickers": docs, "options": {**data, "seed": opts.seed},
                    "note": "Variants combine your photos with local graphics. No new poses, faces or outfits are generated."})


