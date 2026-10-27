"""Themes."""
from __future__ import annotations

from flask import Blueprint, jsonify

from ..extensions import services
from ._common import body

bp = Blueprint("themes", __name__, url_prefix="/api/themes")


@bp.get("")
def list_themes():
    return jsonify({"themes": services().themes.list()})


@bp.get("/<theme_id>")
def get_theme(theme_id: str):
    return jsonify({"theme": services().themes.get(theme_id)})


@bp.post("")
def save_theme():
    svc = services()
    ids = {a["id"] for a in svc.assets.list()}
    return jsonify({"theme": svc.themes.save_custom(body(), ids)}), 201


@bp.delete("/<theme_id>")
def delete_theme(theme_id: str):
    services().themes.delete_custom(theme_id)
    return jsonify({"deleted": theme_id})
