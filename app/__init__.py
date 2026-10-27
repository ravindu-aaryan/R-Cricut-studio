"""Offline Sticker Studio – Flask application factory."""
from __future__ import annotations

import atexit
import logging
import shutil

from flask import Flask, abort, jsonify, render_template, request

from .config import Settings, load_settings
from .errors import register_error_handlers
from .extensions import Services
from .logging_setup import configure_logging
from .repositories.project_repository import ProjectRepository
from .services.asset_service import AssetLibrary
from .services.job_service import JobManager
from .services.project_service import ProjectService
from .services.text_service import FontRegistry
from .services.theme_service import ThemeService
from .utils import security
from .version import APP_NAME, APP_VERSION

log = logging.getLogger("oss")

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def create_app(overrides: dict | None = None) -> Flask:
    settings: Settings = load_settings(overrides)
    settings.ensure_dirs()
    configure_logging(settings.log_dir, settings.debug)
    _clean_temp(settings)

    app = Flask(
        __name__,
        template_folder=str(settings.frontend_dir / "templates"),
        static_folder=str(settings.frontend_dir / "static"),
        static_url_path="/static",
    )
    app.config.update(
        MAX_CONTENT_LENGTH=max(settings.max_upload_bytes * 12, 600 * 1024 * 1024),
        JSON_SORT_KEYS=False,
        TESTING=settings.testing,
        DEBUG=settings.debug,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    app.debug = settings.debug

    repo = ProjectRepository(settings.db_path)
    projects = ProjectService(settings.projects_dir, repo)
    projects.reindex()
    fonts = FontRegistry(settings.assets_dir / "fonts", include_system=not settings.testing)
    assets = AssetLibrary(settings.assets_dir, settings.library_dir, settings.assets_dir / "fonts")
    themes = ThemeService(settings.assets_dir / "themes", settings.library_dir / "themes")
    jobs = JobManager(settings.max_worker_threads, settings.job_timeout_seconds)
    atexit.register(jobs.shutdown)
    app.extensions["oss"] = Services(settings, repo, projects, assets, themes, fonts, jobs, security.new_token())

    allowed_hosts = set(LOCAL_HOSTS)
    if settings.host not in ("0.0.0.0", "::"):
        allowed_hosts.add(settings.host)
    app.config["ALLOWED_HOSTS"] = allowed_hosts

    @app.before_request
    def _guard():
        # DNS-rebinding protection: only answer to local host names.
        if not security.host_allowed(request.host, allowed_hosts):
            abort(400, "Unexpected Host header.")
        if request.method not in security.SAFE_METHODS:
            if not security.origin_allowed(request.headers.get("Origin"), allowed_hosts):
                abort(403, "Cross-origin requests are not allowed.")
            if request.path.startswith("/api/"):
                token = app.extensions["oss"].csrf_token
                if not security.tokens_match(token, request.headers.get(security.CSRF_HEADER)):
                    abort(403, "Missing or invalid CSRF token. Reload the page.")

    @app.after_request
    def _headers(resp):
        for k, v in security.security_headers().items():
            resp.headers.setdefault(k, v)
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    register_error_handlers(app)

    from .routes import register_blueprints

    register_blueprints(app)

    @app.get("/")
    def index():
        return render_template("index.html", csrf_token=app.extensions["oss"].csrf_token,
                               app_name=APP_NAME, app_version=APP_VERSION)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "app": APP_NAME, "version": APP_VERSION})

    log.info("%s %s started; data directory: %s", APP_NAME, APP_VERSION, settings.data_dir)
    return app


def _clean_temp(settings: Settings) -> None:
    """Remove temporary files left behind by a previous run."""
    if settings.temp_dir.exists():
        shutil.rmtree(settings.temp_dir, ignore_errors=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
