"""Background job progress and cancellation."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..errors import AppError
from ..extensions import services
from ..utils.paths import require_safe_id

bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@bp.get("/<job_id>")
def get_job(job_id: str):
    require_safe_id(job_id, "job id")
    job = services().jobs.get(job_id)
    if job is None:
        raise AppError("Job not found.", 404)
    return jsonify({"job": job.to_dict()})


@bp.post("/<job_id>/cancel")
def cancel(job_id: str):
    require_safe_id(job_id, "job id")
    if not services().jobs.cancel(job_id):
        raise AppError("Job not found.", 404)
    return jsonify({"cancelled": job_id})


@bp.get("")
def list_jobs():
    pid = request.args.get("projectId")
    return jsonify({"jobs": [j.to_dict() for j in services().jobs.list(pid)]})
