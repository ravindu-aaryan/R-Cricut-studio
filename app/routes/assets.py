"""Asset library, patterns and reusable presets."""
from __future__ import annotations

import json

from flask import Blueprint, Response, jsonify, request

from ..errors import AppError
from ..extensions import services
from ..models.base import new_id
from ..utils.paths import require_safe_id, safe_join
from ..utils.validation import as_float, is_hex_color
from ._common import body, png_response

bp = Blueprint("assets", __name__, url_prefix="/api")


def _colors() -> dict:
    raw = request.args.get("colors")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {str(k)[:20]: v for k, v in data.items() if isinstance(v, str) and is_hex_color(v)} if isinstance(data, dict) else {}


@bp.get("/assets")
def list_assets():
    svc = services()
    from ..services.asset_service import CATEGORIES

    return jsonify({"assets": svc.assets.list(request.args.get("q", "")[:80], request.args.get("category", "")),
                    "categories": CATEGORIES})


@bp.get("/assets/<asset_id>/svg")
def asset_svg(asset_id: str):
    require_safe_id(asset_id, "asset id")
    svc = services()
    entry = svc.assets.get(asset_id)
    if entry.get("kind") != "svg":
        raise AppError("Not an SVG asset.")
    resp = Response(svc.assets.svg_text(asset_id, _colors()), mimetype="image/svg+xml")
    # Sanitised already; a sandboxing CSP makes any leftover script inert anyway.
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"
    return resp


@bp.get("/assets/<asset_id>/png")
def asset_png(asset_id: str):
    require_safe_id(asset_id, "asset id")
    svc = services()
    w = int(as_float(request.args.get("w"), 256, 8, 2048))
    h = int(as_float(request.args.get("h"), 0, 0, 2048))
    if not h:
        entry = svc.assets.get(asset_id)
        h = max(8, int(w / float(entry.get("aspect") or 1)))
    img = svc.jobs.run_sync("asset-png", lambda handle: svc.assets.raster(asset_id, w, h, _colors()), timeout=20)
    return png_response(img)


@bp.post("/assets")
def import_asset():
    svc = services()
    f = request.files.get("file")
    if f is None:
        raise AppError("Choose a PNG or SVG file.")
    data = f.read(20_000_001)
    tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
    entry = svc.assets.import_asset(data, f.filename or "asset", name=request.form.get("name", ""),
                                    category=request.form.get("category", "custom"), tags=tags)
    return jsonify({"asset": entry}), 201


@bp.delete("/assets/<asset_id>")
def delete_asset(asset_id: str):
    services().assets.delete_user_asset(asset_id)
    return jsonify({"deleted": asset_id})


@bp.get("/patterns")
def patterns():
    return jsonify({"patterns": services().assets.patterns()})


@bp.get("/patterns/<pattern_id>.svg")
def pattern_svg(pattern_id: str):
    require_safe_id(pattern_id, "pattern id")
    color = request.args.get("color", "#ffffff")
    bg = request.args.get("bg")
    svg = services().assets.pattern_svg(pattern_id, color if is_hex_color(color) else "#ffffff",
                                        bg if bg and is_hex_color(bg) else None)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return resp


# ---------------------------------------------------------------- presets
def _presets_dir():
    d = services().settings.library_dir / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


@bp.get("/presets")
def list_presets():
    out = []
    for f in sorted(_presets_dir().glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return jsonify({"presets": out})


@bp.post("/presets")
def save_preset():
    data = body()
    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        raise AppError("Select one or more layers to save as a preset.")
    from ..models.layer import Layer

    clean = [Layer.from_dict(l).to_dict() for l in layers[:60]]
    preset = {"id": new_id("pre_"), "name": str(data.get("name") or "My preset")[:60], "layers": clean,
              "size": data.get("size") if isinstance(data.get("size"), dict) else None}
    safe_join(_presets_dir(), f"{preset['id']}.json").write_text(json.dumps(preset), encoding="utf-8")
    return jsonify({"preset": preset}), 201


@bp.delete("/presets/<preset_id>")
def delete_preset(preset_id: str):
    require_safe_id(preset_id, "preset id")
    safe_join(_presets_dir(), f"{preset_id}.json").unlink(missing_ok=True)
    return jsonify({"deleted": preset_id})
