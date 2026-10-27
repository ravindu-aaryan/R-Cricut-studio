"""Photo import, image variants, geometric edits, adjustments preview and subject extraction."""
from __future__ import annotations


import numpy as np
from flask import Blueprint, jsonify, request, send_file
from PIL import Image

from ..errors import AppError
from ..extensions import services
from ..services import image_adjustments, photo_service, segmentation_service
from ..services.sticker_service import apply_photo_background
from ..utils.paths import require_safe_id
from ..utils.validation import ValidationError, as_float
from ._common import body, decode_data_url_image, job_response, png_response

bp = Blueprint("photos", __name__, url_prefix="/api/projects/<pid>/photos")

VARIANTS = ("preview", "thumb", "working", "subject", "subject_preview", "mask", "original", "hints")


def _limits():
    s = services().settings
    return photo_service.Limits(s.max_upload_bytes, s.max_image_pixels, s.max_image_side_px,
                                s.preview_max_side_px, s.thumbnail_max_side_px)


@bp.post("")
def upload(pid: str):
    """Import one or more photos. Validation is immediate; processing runs as a job."""
    svc = services()
    d = svc.projects.project_dir(pid)
    files = request.files.getlist("files")
    if not files:
        raise AppError("Choose one or more photos to import.")
    if len(files) > 50:
        raise AppError("Import at most 50 photos at a time.")
    payloads = []
    errors = []
    limits = _limits()
    for f in files:
        data = f.read(limits.max_bytes + 1)
        try:
            photo_service.validate_only(data, limits)
            payloads.append((f.filename or "photo", data))
        except ValidationError as exc:
            errors.append({"file": (f.filename or "file")[:120], "error": str(exc)})
    if not payloads:
        raise AppError(errors[0]["error"] if len(errors) == 1 else "None of the files could be imported.", code="invalid") \
            if errors else AppError("No files.")

    def work(handle):
        imported = []
        for i, (name, data) in enumerate(payloads):
            handle.check()
            handle.progress(i / len(payloads), f"Importing {name}")
            try:
                photo = photo_service.import_photo(data, name, d, limits)
            except ValidationError as exc:
                errors.append({"file": name[:120], "error": str(exc)})
                continue
            svc.projects.update_server_side(pid, lambda doc, p=photo: doc["photos"].append(p))
            imported.append(photo)
        return {"photos": imported, "errors": errors}

    return job_response(svc.jobs.submit("import", work, project_id=pid))


def _photo(pid: str, photo_id: str) -> tuple[dict, dict]:
    require_safe_id(photo_id, "photo id")
    svc = services()
    doc = svc.projects.load(pid, prefer_autosave=False)
    return doc, svc.projects.photo(doc, photo_id)


@bp.get("/<photo_id>/image")
def image(pid: str, photo_id: str):
    variant = request.args.get("variant", "preview")
    if variant not in VARIANTS:
        raise AppError("Unknown image variant.")
    _doc, photo = _photo(pid, photo_id)
    d = services().projects.project_dir(pid)
    paths = photo_service.photo_paths(d, photo)
    if variant == "subject_preview" and not paths["subject_preview"].exists():
        variant = "preview"
    path = paths[variant]
    if not path.exists():
        raise AppError("This image is not available yet.", 404)
    mimetype = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "tiff": "image/tiff",
                "heic": "image/heic"}.get(path.suffix.lstrip("."), "image/png")
    resp = send_file(path, mimetype=mimetype, max_age=0, conditional=True)
    if variant == "original":
        resp.headers["Content-Disposition"] = f'attachment; filename="{photo["originalName"]}"'
    return resp


@bp.get("/<photo_id>")
def info(pid: str, photo_id: str):
    _doc, photo = _photo(pid, photo_id)
    return jsonify({"photo": photo})


@bp.delete("/<photo_id>")
def delete(pid: str, photo_id: str):
    svc = services()
    doc, photo = _photo(pid, photo_id)
    users = [s["name"] for s in doc.get("stickers", []) if any(_uses(l, photo_id) for l in s.get("layers", []))]
    if users and not request.args.get("force"):
        raise AppError(f"This photo is used by {len(users)} sticker(s): {', '.join(users[:3])}. Delete them first "
                       "or remove the photo anyway.", 409, "in_use")
    d = svc.projects.project_dir(pid)
    for p in photo_service.photo_paths(d, photo).values():
        p.unlink(missing_ok=True)
    svc.projects.update_server_side(pid, lambda doc: doc.__setitem__("photos", [p for p in doc["photos"] if p["id"] != photo_id]))
    return jsonify({"deleted": photo_id})


def _uses(layer: dict, photo_id: str) -> bool:
    return layer.get("photoId") == photo_id or any(_uses(c, photo_id) for c in layer.get("children") or [])


@bp.post("/<photo_id>/edits")
def set_edits(pid: str, photo_id: str):
    """Change crop/rotate/flip/resize. Rebuilds the working copy from the untouched original."""
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    data = body().get("edits") or {}
    edits = dict(photo_service.DEFAULT_EDITS)
    edits["rotate"] = int(as_float(data.get("rotate"), 0)) % 360 // 90 * 90
    edits["angle"] = as_float(data.get("angle"), 0, -45, 45)
    edits["flipH"] = bool(data.get("flipH"))
    edits["flipV"] = bool(data.get("flipV"))
    crop = data.get("crop")
    if crop:
        edits["crop"] = {k: as_float(crop.get(k), 0 if k in "xy" else 1, 0, 1) for k in ("x", "y", "w", "h")}
    edits["resizeMaxSide"] = int(as_float(data.get("resizeMaxSide"), 0, 0, 20000)) or None
    d = svc.projects.project_dir(pid)

    def work(handle):
        p = dict(photo)
        p["edits"] = edits
        handle.progress(0.2, "Rebuilding working copy")
        photo_service.rebuild_working(d, p, _limits())
        geometry_changed = edits != (photo.get("edits") or photo_service.DEFAULT_EDITS)
        if geometry_changed:
            # Masks and face regions were aligned to the old geometry.
            paths = photo_service.photo_paths(d, p)
            for key in ("mask", "subject", "subject_preview", "hints"):
                paths[key].unlink(missing_ok=True)
            p["mask"], p["maskMethod"], p["subjectBox"] = None, None, None
            handle.progress(0.7, "Looking for faces")
            prev = Image.open(paths["preview"])
            scale = p["width"] / prev.size[0]
            p["faceRegions"] = [{"x": int(x * scale), "y": int(y * scale), "w": int(w * scale), "h": int(h * scale), "source": "auto"}
                                for (x, y, w, h) in photo_service.detect_faces(prev)]
        p["_rev"] = (photo.get("_rev") or 0) + 1

        def mutate(doc):
            doc["photos"] = [p if q["id"] == photo_id else q for q in doc["photos"]]

        svc.projects.update_server_side(pid, mutate)
        return {"photo": p, "maskCleared": geometry_changed}

    return job_response(svc.jobs.submit("edit-photo", work, project_id=pid))


@bp.post("/<photo_id>/adjusted")
def adjusted_preview(pid: str, photo_id: str):
    """Preview of colour adjustments + background replacement on the preview-size image."""
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    data = body()
    params = image_adjustments.normalize_adjustments(data.get("adjustments"))
    background = data.get("background") or photo.get("background") or {"type": "keep"}
    protect = bool(data.get("protectFace", photo.get("protectFace", True)))
    faces = data.get("faceRegions", photo.get("faceRegions") or [])
    d = svc.projects.project_dir(pid)
    paths = photo_service.photo_paths(d, photo)
    max_side = int(as_float(data.get("maxSide"), 900, 64, 1600))
    use_subject = data.get("source") == "subject" and paths["subject_preview"].exists()

    def work(handle):
        with Image.open(paths["subject_preview"] if use_subject else paths["preview"]) as im:
            img = photo_service.normalize_mode(im.copy()).convert("RGBA")
        img.thumbnail((max_side, max_side))
        if paths["mask"].exists() and not use_subject:
            img = apply_photo_background(img, paths["mask"], background, svc.assets)
        mask = None
        if protect and faces:
            k = img.width / max(1, photo["width"])
            mask = photo_service.face_mask(img.size, [{kk: r[kk] * k for kk in ("x", "y", "w", "h")} for r in faces])
        return image_adjustments.apply_adjustments(img, params, scale=img.width / 1000.0, protect_mask=mask)

    img = svc.jobs.run_sync("adjust-preview", work, timeout=30, project_id=pid)
    return png_response(img)


@bp.post("/<photo_id>/faces/detect")
def detect_faces(pid: str, photo_id: str):
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    paths = photo_service.photo_paths(svc.projects.project_dir(pid), photo)

    def work(handle):
        prev = Image.open(paths["preview"])
        scale = photo["width"] / prev.size[0]
        return [{"x": int(x * scale), "y": int(y * scale), "w": int(w * scale), "h": int(h * scale), "source": "auto"}
                for (x, y, w, h) in photo_service.detect_faces(prev)]

    return jsonify({"faceRegions": svc.jobs.run_sync("faces", work, timeout=30, project_id=pid)})


@bp.post("/<photo_id>/segment")
def segment(pid: str, photo_id: str):
    """Start subject extraction. Coordinates from the editor are in preview pixels."""
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    data = body()
    method = data.get("method", "grabcut")
    if method not in ("manual", "grabcut", "colorkey", "model"):
        raise AppError("Unknown extraction method.")
    if method == "model" and not segmentation_service.model_status(svc.settings.models_dir)["available"]:
        raise AppError("No offline segmentation model is installed. Use GrabCut or manual selection.")
    d = svc.projects.project_dir(pid)
    paths = photo_service.photo_paths(d, photo)
    W, H = photo["width"], photo["height"]
    pw = photo.get("previewWidth") or W
    k = W / pw
    rect = None
    if data.get("rect"):
        r = data["rect"]
        rect = tuple(int(as_float(r.get(key), 0) * k) for key in ("x", "y", "w", "h"))
    hints_img = decode_data_url_image(data.get("hints"))
    manual_img = decode_data_url_image(data.get("mask"))
    ro = data.get("refine") or {}
    refine = segmentation_service.RefineOptions(
        feather_px=as_float(ro.get("feather"), 1.0, 0, 20),
        remove_holes_area=int(as_float(ro.get("fillHoles"), 400, 0, 1_000_000)),
        remove_specks_area=int(as_float(ro.get("removeSpecks"), 400, 0, 1_000_000)),
        smooth=as_float(ro.get("smooth"), 0.0, 0, 1),
        grow_px=int(as_float(ro.get("grow"), 0, -60, 60)),
        edge_refine=bool(ro.get("edgeRefine", True)),
        keep_largest_only=bool(ro.get("keepLargest", False)),
    )
    iterations = int(as_float(data.get("iterations"), 5, 1, 12))

    def work(handle):
        working = photo_service.load_working(d, photo)
        hints = segmentation_service.hints_from_rgba(hints_img, working.size) if hints_img is not None else None
        manual = None
        if manual_img is not None:
            manual = np.asarray(manual_img.convert("L").resize(working.size, Image.Resampling.BILINEAR))
        if hints_img is not None:
            hints_img.save(paths["hints"], "PNG")
        try:
            mask = segmentation_service.run_segmentation(
                method, working, rect=rect, hints=hints, manual_mask=manual, models_dir=svc.settings.models_dir,
                refine=refine, iterations=iterations, progress=handle.progress, cancelled=handle.cancelled)
        except segmentation_service.SegmentationCancelled:
            handle.check()
            raise
        handle.check()
        bbox = segmentation_service.alpha_bbox(mask)
        if bbox is None:
            raise ValueError("No subject was found. Mark the subject with the Keep brush and try again.")
        photo_service.save_png(Image.fromarray(mask, "L"), paths["mask"])
        subject = segmentation_service.extract_subject(working, mask)
        photo_service.save_png(subject, paths["subject"])
        photo_service.save_png(photo_service.fit_within(subject, svc.settings.preview_max_side_px), paths["subject_preview"])
        p = dict(photo)
        p["mask"] = f"masks/{photo_id}.png"
        p["maskMethod"] = method
        p["subjectBox"] = {"x": bbox[0] / W, "y": bbox[1] / H, "w": bbox[2] / W, "h": bbox[3] / H}
        p["_rev"] = (photo.get("_rev") or 0) + 1
        coverage = float((mask > 127).mean())
        svc.projects.update_server_side(pid, lambda doc: doc.__setitem__(
            "photos", [p if q["id"] == photo_id else q for q in doc["photos"]]))
        note = None
        if method in ("grabcut", "colorkey") and (coverage > 0.92 or coverage < 0.01):
            note = "Automatic extraction may have missed the subject. Refine it with the Keep and Remove brushes."
        return {"photo": p, "coverage": coverage, "note": note}

    return job_response(svc.jobs.submit("segment", work, project_id=pid))


@bp.post("/<photo_id>/mask/clear")
def clear_mask(pid: str, photo_id: str):
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    paths = photo_service.photo_paths(svc.projects.project_dir(pid), photo)
    for key in ("mask", "subject", "subject_preview", "hints"):
        paths[key].unlink(missing_ok=True)
    p = {**photo, "mask": None, "maskMethod": None, "subjectBox": None, "_rev": (photo.get("_rev") or 0) + 1}
    svc.projects.update_server_side(pid, lambda doc: doc.__setitem__("photos", [p if q["id"] == photo_id else q for q in doc["photos"]]))
    return jsonify({"photo": p})


@bp.post("/<photo_id>/export-subject")
def export_subject(pid: str, photo_id: str):
    """Save the transparent subject PNG into the project's exports folder."""
    svc = services()
    _doc, photo = _photo(pid, photo_id)
    paths = photo_service.photo_paths(svc.projects.project_dir(pid), photo)
    if not paths["subject"].exists():
        raise AppError("Extract the subject first.")
    folder, out = svc.projects.export_dir(pid, "subject")
    name = f"{photo.get('name', 'subject')}-subject.png"
    from ..utils.paths import sanitize_filename

    name = sanitize_filename(name, "subject.png")
    import shutil

    shutil.copy2(paths["subject"], out / name)
    svc.repo.add_export(folder, pid, "subject-png", folder, [name], {"photoId": photo_id})
    return jsonify({"exportId": folder, "folder": folder, "files": [name]})


