"""Shared helpers for route modules."""
from __future__ import annotations

import base64
import io
import json

from flask import Response, jsonify, request
from PIL import Image

from ..errors import AppError
from ..extensions import services
from ..services.sticker_service import RenderContext


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        if request.content_length:
            raise AppError("Expected a JSON body.")
        return {}
    if not isinstance(data, dict):
        raise AppError("Expected a JSON object.")
    return data


def png_response(img: Image.Image, *, headers: dict | None = None, dpi: int | None = None) -> Response:
    buf = io.BytesIO()
    kwargs = {"dpi": (dpi, dpi)} if dpi else {}
    img.save(buf, "PNG", compress_level=3, **kwargs)
    resp = Response(buf.getvalue(), mimetype="image/png")
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def job_response(job, status: int = 202):
    resp = jsonify({"job": job.to_dict()})
    resp.status_code = status
    return resp


def decode_data_url_image(value: str | None, max_bytes: int = 30_000_000) -> Image.Image | None:
    """Decode a ``data:image/png;base64,...`` value sent by the editor."""
    if not value:
        return None
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        raise AppError("Expected a PNG data URL.")
    raw = base64.b64decode(value.split(",", 1)[1], validate=False)
    if len(raw) > max_bytes:
        raise AppError("Mask data is too large.")
    img = Image.open(io.BytesIO(raw))
    if img.format != "PNG" or img.width * img.height > 40_000_000:
        raise AppError("Invalid mask image.")
    img.load()
    return img


def render_context(pid: str, doc: dict) -> RenderContext:
    svc = services()
    photos = {p["id"]: p for p in doc.get("photos", [])}
    for p in photos.values():
        svc.projects.photo(doc, p["id"])  # validates stored paths
    return RenderContext(svc.projects.project_dir(pid), photos, svc.assets, svc.fonts,
                         low_res_dpi=svc.settings.low_resolution_warning_dpi)


def info_header(data: dict) -> str:
    return base64.b64encode(json.dumps(data).encode()).decode()
