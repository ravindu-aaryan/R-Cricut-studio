"""Bulk sticker import and sticker templates."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..errors import AppError
from ..extensions import services
from ..services import import_service
from ..services.photo_service import Limits
from ..utils.disk import ensure_free_space
from ..utils.paths import require_safe_id
from ..utils.validation import as_float, is_hex_color
from ._common import body, job_response

bp = Blueprint("imports", __name__, url_prefix="/api")


def _limits() -> Limits:
    s = services().settings
    return Limits(s.max_upload_bytes, s.max_image_pixels, s.max_image_side_px, s.preview_max_side_px, s.thumbnail_max_side_px)


def _opts(form) -> import_service.ImportOptions:
    color = form.get("borderColor", "#ffffff")
    ocolor = form.get("outlineColor", "#ff4f8b")
    return import_service.ImportOptions(
        shape=form.get("shape", "silhouette"),
        size_mm=as_float(form.get("sizeMm"), 60, 10, 250),
        border_mm=as_float(form.get("borderMm"), 3, 0, 15),
        border_color=color if is_hex_color(color) else "#ffffff",
        outline_mm=as_float(form.get("outlineMm"), 0, 0, 10),
        outline_color=ocolor if is_hex_color(ocolor) else "#ff4f8b",
        trim=form.get("trim", "1") not in ("0", "false", "no"),
        remove_white=form.get("removeWhite", "0") in ("1", "true", "yes"),
        white_tolerance=as_float(form.get("whiteTolerance"), 36, 0, 120),
        category=form.get("category", "custom"),
    )


@bp.post("/projects/<pid>/stickers/import")
def import_stickers(pid: str):
    """Import many images (or a ZIP) as stickers. Runs as a background job."""
    svc = services()
    svc.projects.project_dir(pid)
    uploads = request.files.getlist("files")
    if not uploads:
        raise AppError("Choose one or more image files, or a ZIP, to import.")
    files = [(f.filename or "sticker", f.read()) for f in uploads]
    total = sum(len(d) for _, d in files)
    ensure_free_space(svc.settings.library_dir, needed_bytes=total * 4)
    if total > svc.settings.max_upload_bytes * 40:
        raise AppError("The upload is too large. Split it into smaller batches.")
    opts = _opts(request.form)
    limits = _limits()

    def work(handle):
        result = import_service.import_stickers(
            files, opts, svc.assets, max_bytes=limits.max_bytes, max_pixels=limits.max_pixels, max_side=limits.max_side,
            progress=handle.progress, cancelled=handle.cancelled)
        if opts.add_to_project and result.stickers:
            def mutate(doc):
                doc["stickers"].extend(result.stickers)
            svc.projects.update_server_side(pid, mutate)
        return {"stickers": result.stickers, "assets": result.assets, "errors": result.errors,
                "imported": len(result.stickers), "failed": len(result.errors)}

    return job_response(svc.jobs.submit("import-stickers", work, project_id=pid,
                                        timeout=max(600, svc.settings.job_timeout_seconds)))


@bp.post("/assets/import-bulk")
def import_assets_bulk():
    """Import many images/SVGs (or a ZIP) into the decoration library."""
    svc = services()
    uploads = request.files.getlist("files")
    if not uploads:
        raise AppError("Choose files or a ZIP to import.")
    files = [(f.filename or "asset", f.read()) for f in uploads]
    ensure_free_space(svc.settings.library_dir, needed_bytes=sum(len(d) for _, d in files) * 3)
    category = request.form.get("category", "custom")

    def work(handle):
        entries = import_service.expand_files(files, svc.settings.max_upload_bytes)
        assets, errors = [], []
        for i, (name, data) in enumerate(entries):
            handle.progress(i / max(1, len(entries)), f"Importing {name}")
            try:
                assets.append(svc.assets.import_asset(data, name, category=category, tags=["import"]))
            except Exception as exc:  # noqa: BLE001
                errors.append({"file": name[:120], "error": str(exc)})
        return {"assets": assets, "errors": errors, "imported": len(assets)}

    return job_response(svc.jobs.submit("import-assets", work, timeout=max(600, svc.settings.job_timeout_seconds)))


# ---------------------------------------------------------------- templates
@bp.get("/templates")
def list_templates():
    return jsonify({"templates": services().templates.list()})


@bp.get("/templates/<tid>")
def get_template(tid: str):
    require_safe_id(tid, "template id")
    return jsonify({"template": services().templates.get(tid)})


@bp.post("/templates")
def create_template():
    """Save a sticker document as a reusable template."""
    data = body()
    sticker = data.get("sticker")
    if not isinstance(sticker, dict):
        raise AppError("Missing sticker document.")
    from ..models.sticker import StickerDoc

    StickerDoc.from_dict(sticker)  # validate
    tpl = import_service.make_template(sticker, data.get("name", ""), data.get("themeId"))
    return jsonify({"template": services().templates.save(tpl)}), 201


@bp.delete("/templates/<tid>")
def delete_template(tid: str):
    require_safe_id(tid, "template id")
    services().templates.delete(tid)
    return jsonify({"deleted": tid})


@bp.get("/templates/export")
def export_templates():
    data = services().templates.export_bundle()
    return Response(data, mimetype="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="sticker-templates.zip"'})


@bp.post("/templates/import")
def import_templates():
    f = request.files.get("file")
    if f is None:
        raise AppError("Choose a template file (.zip or .json) to import.")
    saved = services().templates.import_bundle(f.read())
    return jsonify({"templates": saved, "imported": len(saved)}), 201


@bp.post("/projects/<pid>/stickers/from-template")
def from_template(pid: str):
    """Create a sticker from a template, optionally filling the photo slot."""
    svc = services()
    data = body()
    project = svc.projects.load(pid, prefer_autosave=True)
    template = svc.templates.get(data.get("templateId", ""))
    photo = asset = None
    if data.get("photoId"):
        photo = svc.projects.photo(project, data["photoId"])
    elif data.get("assetId"):
        require_safe_id(data["assetId"], "asset id")
        asset = svc.assets.get(data["assetId"])
    doc = import_service.instantiate_template(template, photo=photo, asset=asset, name=data.get("name", ""))
    return jsonify({"sticker": doc})
