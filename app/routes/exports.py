"""Exports: start jobs, list history, download and preview exported files."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from ..errors import AppError
from ..extensions import services
from ..services import export_service
from ..utils.disk import ensure_free_space
from ..utils.paths import require_safe_id, safe_join
from ..utils.validation import as_float
from ._common import body, job_response, render_context

bp = Blueprint("exports", __name__, url_prefix="/api/projects/<pid>/exports")

MIMETYPES = {".png": "image/png", ".pdf": "application/pdf", ".svg": "image/svg+xml", ".zip": "application/zip",
             ".json": "application/json", ".ossproj": "application/zip"}


@bp.post("")
def start_export(pid: str):
    svc = services()
    data = body()
    kind = data.get("kind")
    if kind not in export_service.EXPORT_KINDS or kind == "archive":
        raise AppError("Unknown export type.")
    ensure_free_space(svc.projects.project_dir(pid))
    project = svc.projects.load(pid, prefer_autosave=True)
    if isinstance(data.get("document"), dict):
        # Export exactly what is on screen (saved first so the export is reproducible).
        project = svc.projects.save(pid, data["document"], autosave=True)
    opts = export_service.ExportOptions(
        kind=kind,
        sticker_ids=[s for s in data.get("stickerIds", []) if isinstance(s, str)] or None,
        sheet_id=data.get("sheetId"),
        dpi=int(as_float(data.get("dpi"), 300, 72, 600)),
        transparent=bool(data.get("transparent", False)),
        cut_lines=bool(data.get("cutLines", False)),
        cut_offset_mm=as_float(data["cutOffsetMm"], 0, -5, 5) if data.get("cutOffsetMm") not in (None, "") else None,
        include_holes=bool(data.get("includeHoles", False)),
    )
    ctx = render_context(pid, project)
    font = svc.settings.assets_dir / "fonts" / "Poppins-Regular.ttf"

    def work(handle):
        folder, out_dir = svc.projects.export_dir(pid, kind)
        try:
            result = export_service.export(project, ctx, opts, out_dir, font_path=font,
                                           progress=handle.progress, cancelled=handle.cancelled)
        except Exception:
            import shutil

            shutil.rmtree(out_dir, ignore_errors=True)
            raise
        svc.repo.add_export(folder, pid, kind, folder, result["files"], {k: v for k, v in data.items() if k != "document"})
        return {"exportId": folder, "folder": folder, "files": result["files"], "info": result["info"],
                "path": str(out_dir)}

    return job_response(svc.jobs.submit(f"export-{kind}", work, project_id=pid, timeout=max(600, svc.settings.job_timeout_seconds)))


@bp.get("/<export_id>/files/<path:filename>")
def download(pid: str, export_id: str, filename: str):
    svc = services()
    require_safe_id(export_id, "export id")
    record = svc.repo.get_export(export_id)
    if record is None or record["project_id"] != pid:
        raise AppError("Export not found.", 404)
    if filename not in record["files"]:
        raise AppError("File not found.", 404)
    folder = safe_join(svc.projects.project_dir(pid) / "exports", record["folder"])
    path = safe_join(folder, filename)
    if not path.is_file():
        raise AppError("The file was moved or deleted.", 404)
    inline = request.args.get("inline") == "1"
    mimetype = MIMETYPES.get(path.suffix.lower(), "application/octet-stream")
    resp = send_file(path, mimetype=mimetype, as_attachment=not inline, download_name=path.name, max_age=0)
    if path.suffix.lower() == ".svg":
        resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"
    return resp


@bp.get("/<export_id>")
def get_export(pid: str, export_id: str):
    svc = services()
    require_safe_id(export_id, "export id")
    record = svc.repo.get_export(export_id)
    if record is None or record["project_id"] != pid:
        raise AppError("Export not found.", 404)
    folder = svc.projects.project_dir(pid) / "exports" / record["folder"]
    record["path"] = str(folder)
    return jsonify({"export": record})
