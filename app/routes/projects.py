"""Project management: create, open, save, save as, rename, duplicate, archive, delete, recovery, archives."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from ..errors import AppError
from ..extensions import services
from ..utils.disk import ensure_free_space
from ..utils.paths import require_safe_id, sanitize_filename
from ._common import body, job_response

bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@bp.get("")
def list_projects():
    svc = services()
    archived = request.args.get("archived") == "1"
    return jsonify({"projects": svc.projects.list(include_archived=archived, query=request.args.get("q", "")[:80]),
                    "projectsDir": str(svc.settings.projects_dir)})


@bp.post("")
def create_project():
    data = body()
    doc = services().projects.create(str(data.get("name", "")), data.get("themeId"))
    return jsonify({"document": doc}), 201


@bp.get("/<pid>")
def open_project(pid: str):
    require_safe_id(pid)
    return jsonify(services().projects.open(pid))


@bp.put("/<pid>")
def save_project(pid: str):
    require_safe_id(pid)
    data = body()
    doc = data.get("document")
    if not isinstance(doc, dict):
        raise AppError("Missing document.")
    autosave = request.args.get("autosave") == "1"
    saved = services().projects.save(pid, doc, autosave=autosave)
    return jsonify({"document": saved, "autosave": autosave})


@bp.post("/<pid>/recover")
def recover(pid: str):
    svc = services()
    doc = svc.projects.load(pid, prefer_autosave=True)
    saved = svc.projects.save(pid, doc)
    return jsonify({"document": saved})


@bp.post("/<pid>/discard-autosave")
def discard_autosave(pid: str):
    services().projects.discard_autosave(pid)
    return jsonify({"ok": True})


@bp.post("/<pid>/rename")
def rename(pid: str):
    doc = services().projects.rename(pid, str(body().get("name", "")))
    return jsonify({"document": doc})


@bp.post("/<pid>/duplicate")
def duplicate(pid: str):
    data = body()
    doc = services().projects.duplicate(pid, data.get("name"), data.get("document"))
    return jsonify({"document": doc}), 201


@bp.post("/<pid>/archive")
def archive(pid: str):
    services().projects.set_archived(pid, bool(body().get("archived", True)))
    return jsonify({"ok": True})


@bp.delete("/<pid>")
def delete(pid: str):
    svc = services()
    doc = svc.projects.load(pid)
    if body().get("confirmName") != doc.get("name"):
        raise AppError("Type the project name to confirm deletion.")
    for job in svc.jobs.list(pid):
        svc.jobs.cancel(job.id)
    svc.projects.delete(pid)
    return jsonify({"deleted": pid})


@bp.get("/<pid>/thumbnail")
def thumbnail(pid: str):
    d = services().projects.project_dir(pid)
    p = d / "thumbs" / "project.png"
    if not p.exists():
        raise AppError("No thumbnail yet.", 404)
    return send_file(p, mimetype="image/png", max_age=0)


@bp.post("/<pid>/thumbnail")
def set_thumbnail(pid: str):
    """Store a project thumbnail rendered from the first sticker (small PNG data URL)."""
    from ._common import decode_data_url_image

    d = services().projects.project_dir(pid)
    img = decode_data_url_image(body().get("image"), max_bytes=3_000_000)
    if img is None:
        raise AppError("Missing image.")
    img = img.convert("RGBA")
    img.thumbnail((320, 320))
    img.save(d / "thumbs" / "project.png", "PNG")
    return jsonify({"ok": True})


@bp.post("/<pid>/archive-file")
def export_archive(pid: str):
    svc = services()
    ensure_free_space(svc.projects.project_dir(pid))

    def work(handle):
        folder, out = svc.projects.export_dir(pid, "archive")
        doc = svc.projects.load(pid)
        name = sanitize_filename(doc.get("name", "project"), "project") + ".ossproj"
        handle.progress(0.1, "Collecting project files")
        svc.projects.export_archive(pid, svc.assets, out / name)
        svc.repo.add_export(folder.replace(".", "_"), pid, "archive", folder, [name], {})
        return {"exportId": folder.replace(".", "_"), "folder": folder, "files": [name]}

    return job_response(svc.jobs.submit("archive", work, project_id=pid))


@bp.post("/import")
def import_archive():
    svc = services()
    f = request.files.get("file")
    if f is None:
        raise AppError("Choose a .ossproj file to import.")
    data = f.read()
    ensure_free_space(svc.settings.projects_dir, needed_bytes=len(data) * 2)
    doc = svc.projects.import_archive(data, svc.assets)
    return jsonify({"document": doc}), 201


@bp.get("/<pid>/exports")
def export_history(pid: str):
    svc = services()
    svc.projects.project_dir(pid)
    return jsonify({"exports": svc.repo.list_exports(pid)})
