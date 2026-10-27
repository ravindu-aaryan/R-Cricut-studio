"""Error types and JSON error handlers. Tracebacks are logged, never returned."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .services.asset_service import AssetError
from .services.job_service import JobTimeout
from .services.project_service import ProjectError, ProjectNotFound
from .services.theme_service import ThemeError
from .utils.paths import UnsafePathError
from .utils.svg_sanitize import SvgSanitizeError
from .utils.validation import ValidationError

log = logging.getLogger("oss.errors")


class AppError(Exception):
    status = 400

    def __init__(self, message: str, status: int | None = None, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code
        if status:
            self.status = status


def _json(message: str, status: int, code: str):
    resp = jsonify({"error": {"message": message, "code": code}})
    resp.status_code = status
    return resp


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(e: AppError):
        return _json(e.message, e.status, e.code)

    @app.errorhandler(ValidationError)
    @app.errorhandler(SvgSanitizeError)
    def _validation(e):
        return _json(str(e), 400, "invalid")

    @app.errorhandler(ProjectNotFound)
    def _nf(e):
        return _json(str(e), 404, "not_found")

    @app.errorhandler(ProjectError)
    @app.errorhandler(ThemeError)
    @app.errorhandler(AssetError)
    def _domain(e):
        return _json(str(e), 400, "invalid")

    @app.errorhandler(UnsafePathError)
    def _unsafe(e):
        log.warning("rejected unsafe path for %s", request.path)
        return _json("Invalid identifier.", 400, "unsafe_path")

    @app.errorhandler(JobTimeout)
    def _timeout(e):
        return _json(str(e), 503, "timeout")

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(e):
        return _json("The upload is too large.", 413, "too_large")

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        if request.path.startswith("/api/"):
            return _json(e.description or e.name, e.code or 500, e.name.lower().replace(" ", "_"))
        return e

    @app.errorhandler(Exception)
    def _unexpected(e: Exception):
        log.exception("unhandled error on %s %s", request.method, request.path)
        if app.debug:
            raise e
        return _json("Something went wrong. Details were written to the local log file.", 500, "internal")
