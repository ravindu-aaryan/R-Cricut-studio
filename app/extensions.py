"""Service container attached to the Flask app (``current_app.extensions['oss']``)."""
from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from .config import Settings
from .repositories.project_repository import ProjectRepository
from .services.asset_service import AssetLibrary
from .services.job_service import JobManager
from .services.project_service import ProjectService
from .services.text_service import FontRegistry
from .services.theme_service import ThemeService


@dataclass
class Services:
    settings: Settings
    repo: ProjectRepository
    projects: ProjectService
    assets: AssetLibrary
    themes: ThemeService
    fonts: FontRegistry
    jobs: JobManager
    csrf_token: str


def services() -> Services:
    return current_app.extensions["oss"]
