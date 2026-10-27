"""Session, settings, offline/dependency status, fonts and local-data deletion."""
from __future__ import annotations

import importlib.metadata as md
import os
import platform
import shutil
import subprocess
import sys

from flask import Blueprint, jsonify, send_file

from ..config import save_user_settings
from ..errors import AppError
from ..extensions import services
from ..services.segmentation_service import model_status
from ..utils.paths import require_safe_id
from ..utils.validation import HEIC_AVAILABLE
from ..version import APP_NAME, APP_VERSION, PROJECT_FORMAT_VERSION
from ._common import body

bp = Blueprint("system", __name__)

PACKAGES = ("Flask", "Pillow", "numpy", "opencv-python-headless", "reportlab", "resvg_py", "defusedxml",
            "onnxruntime", "pillow-heif", "waitress")


def _version(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


@bp.get("/api/session")
def session():
    svc = services()
    return jsonify({
        "csrfToken": svc.csrf_token, "app": APP_NAME, "version": APP_VERSION,
        "projectFormatVersion": PROJECT_FORMAT_VERSION,
        "settings": svc.settings.public_dict(), "preferences": svc.repo.all_settings(),
    })


@bp.get("/api/status")
def status():
    svc = services()
    s = svc.settings
    usage = shutil.disk_usage(s.data_dir)
    resources = {
        "frontend": (s.frontend_dir / "templates" / "index.html").exists(),
        "konva": (s.frontend_dir / "static" / "vendor" / "konva-9.3.22.min.js").exists(),
        "fonts": len(list((s.assets_dir / "fonts").glob("*.ttf"))),
        "themes": len(svc.themes.list()),
        "assets": len(svc.assets.list()),
        "patterns": len(svc.assets.patterns()),
    }
    missing = [k for k, v in resources.items() if not v]
    return jsonify({
        "app": APP_NAME, "version": APP_VERSION,
        "python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
        "cpus": os.cpu_count(), "workers": svc.jobs.max_workers,
        "packages": {p: _version(p) for p in PACKAGES},
        "segmentationModel": model_status(s.models_dir),
        "heicSupport": HEIC_AVAILABLE,
        "gpuRequired": False,
        "offline": {
            "networkRequestsMade": False,
            "telemetry": False,
            "serverBinding": s.host,
            "note": "The app never contacts the internet. All processing happens on this computer.",
        },
        "storage": {"dataDir": str(s.data_dir), "projectsDir": str(s.projects_dir), "libraryDir": str(s.library_dir),
                    "database": str(s.db_path), "logs": str(s.log_dir), "freeBytes": usage.free, "totalBytes": usage.total},
        "resources": resources, "missingResources": missing,
        "limits": {"maxUploadMb": s.max_upload_mb, "maxImageSidePx": s.max_image_side_px,
                   "maxImageMegapixels": s.max_image_megapixels},
    })


@bp.put("/api/settings")
def update_settings():
    svc = services()
    data = body()
    prefs = data.pop("preferences", None)
    changed = save_user_settings(svc.settings, data)
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            if isinstance(k, str) and len(k) < 64:
                svc.repo.set_setting(k, v)
    return jsonify({"changed": changed, "settings": svc.settings.public_dict(), "preferences": svc.repo.all_settings()})


@bp.post("/api/system/delete-all-data")
def delete_all_data():
    """Delete every project, imported asset and preference (requires confirmation)."""
    svc = services()
    if body().get("confirm") != "DELETE":
        raise AppError('Type DELETE to confirm.')
    for job in svc.jobs.list():
        svc.jobs.cancel(job.id)
    shutil.rmtree(svc.settings.projects_dir, ignore_errors=True)
    shutil.rmtree(svc.settings.library_dir, ignore_errors=True)
    shutil.rmtree(svc.settings.temp_dir, ignore_errors=True)
    svc.repo.delete_all()
    (svc.settings.data_dir / "settings.json").unlink(missing_ok=True)
    svc.settings.ensure_dirs()
    return jsonify({"deleted": True})


@bp.get("/api/fonts")
def fonts():
    return jsonify({"fonts": services().fonts.list()})


@bp.get("/fonts/<face_id>")
def font_file(face_id: str):
    require_safe_id(face_id, "font id")
    face = services().fonts.faces.get(face_id)
    if face is None:
        raise AppError("Font not found.", 404)
    mimetype = "font/otf" if face.path.suffix.lower() == ".otf" else "font/ttf"
    return send_file(face.path, mimetype=mimetype, max_age=86400)


@bp.post("/api/system/reveal")
def reveal():
    """Open a project or export folder in the system file manager (local only)."""
    svc = services()
    data = body()
    pid = require_safe_id(str(data.get("projectId", "")), "project id")
    target = svc.projects.project_dir(pid)
    folder = data.get("folder")
    if folder:
        require_safe_id(str(folder).replace(".", "_"), "folder")
        target = target / "exports" / str(folder)
        if not target.is_dir():
            raise AppError("Folder not found.", 404)
    if svc.settings.testing:
        return jsonify({"path": str(target), "opened": False})
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        elif os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
        opened = True
    except Exception:
        opened = False
    return jsonify({"path": str(target), "opened": opened})


@bp.get("/fonts.css")
def fonts_css():
    """@font-face rules for every available font, served locally."""
    from flask import Response

    rules = []
    for face in services().fonts.faces.values():
        fmt = "opentype" if face.path.suffix.lower() == ".otf" else "truetype"
        family = face.family.replace('"', "")
        rules.append(f'@font-face {{ font-family: "{family}"; src: url("/fonts/{face.id}") format("{fmt}"); '
                     f'font-weight: {face.weight}; font-style: normal; font-display: swap; }}')
    resp = Response("\n".join(rules), mimetype="text/css")
    resp.headers["Cache-Control"] = "max-age=3600"
    return resp


@bp.post("/api/system/quit")
def quit_app():
    """Stop the local server (desktop launcher only). Unsaved work is autosaved by the UI first."""
    import os
    import threading

    svc = services()
    if not svc.settings.allow_quit:
        raise AppError("Quitting is only available in the desktop app.", 400)
    svc.jobs.shutdown()
    threading.Timer(0.4, lambda: os._exit(0)).start()
    return jsonify({"quitting": True})
