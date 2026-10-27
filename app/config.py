"""Application configuration.

Settings come from ``config/default_settings.json`` and can be overridden by
a user ``settings.json`` inside the data directory and by environment
variables (``OSS_DATA_DIR``, ``OSS_PORT``, ``OSS_HOST``).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def resource_root() -> Path:
    """Directory containing bundled resources (works inside PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """Per-user data directory; projects never leave this machine."""
    if getattr(sys, "frozen", False):
        home = Path.home()
        if sys.platform == "darwin":
            return home / "Library" / "Application Support" / "OfflineStickerStudio"
        if os.name == "nt":
            return Path(os.environ.get("APPDATA", home)) / "OfflineStickerStudio"
        return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "offline-sticker-studio"
    return resource_root() / "data"


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 5173
    data_dir: Path = field(default_factory=default_data_dir)
    max_upload_mb: float = 40
    max_image_side_px: int = 12000
    max_image_megapixels: float = 80
    preview_max_side_px: int = 1600
    thumbnail_max_side_px: int = 320
    max_worker_threads: int = 2
    job_timeout_seconds: int = 300
    autosave_interval_seconds: int = 20
    default_dpi: int = 300
    low_resolution_warning_dpi: int = 150
    default_sticker_mm: float = 60
    ui: dict = field(default_factory=dict)
    debug: bool = False
    testing: bool = False
    allow_quit: bool = False  # set by the desktop launcher so the UI can stop the server

    # ---- derived locations -------------------------------------------------
    @property
    def resources(self) -> Path:
        return resource_root()

    @property
    def assets_dir(self) -> Path:
        return self.resources / "assets"

    @property
    def frontend_dir(self) -> Path:
        return self.resources / "frontend"

    @property
    def models_dir(self) -> Path:
        return self.resources / "models"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def templates_dir(self) -> Path:
        return self.library_dir / "templates"

    @property
    def library_dir(self) -> Path:
        """User-imported decorations, backgrounds and presets."""
        return self.data_dir / "library"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.sqlite3"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def max_image_pixels(self) -> int:
        return int(self.max_image_megapixels * 1_000_000)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.projects_dir, self.library_dir, self.temp_dir, self.log_dir,
                  self.library_dir / "decorations", self.library_dir / "backgrounds", self.library_dir / "presets",
                  self.library_dir / "templates"):
            d.mkdir(parents=True, exist_ok=True)

    def public_dict(self) -> dict:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["projects_dir"] = str(self.projects_dir)
        d["library_dir"] = str(self.library_dir)
        d["db_path"] = str(self.db_path)
        return d

    # Settings the user may change from the UI (and persist).
    EDITABLE = ("max_upload_mb", "preview_max_side_px", "max_worker_threads", "job_timeout_seconds",
                "autosave_interval_seconds", "default_dpi", "low_resolution_warning_dpi",
                "default_sticker_mm", "ui")


def _apply(settings: Settings, values: dict) -> None:
    for key, value in values.items():
        if key == "data_dir":
            if value:
                settings.data_dir = Path(value).expanduser()
        elif hasattr(settings, key) and not key.startswith("_"):
            setattr(settings, key, value)


def load_settings(overrides: dict | None = None) -> Settings:
    settings = Settings()
    defaults = resource_root() / "config" / "default_settings.json"
    if defaults.exists():
        _apply(settings, json.loads(defaults.read_text(encoding="utf-8")))
    if os.environ.get("OSS_DATA_DIR"):
        settings.data_dir = Path(os.environ["OSS_DATA_DIR"]).expanduser()
    if overrides and overrides.get("data_dir"):
        settings.data_dir = Path(overrides["data_dir"])
    user_file = settings.data_dir / "settings.json"
    if user_file.exists():
        try:
            user = json.loads(user_file.read_text(encoding="utf-8"))
            _apply(settings, {k: v for k, v in user.items() if k in Settings.EDITABLE})
        except (OSError, ValueError):
            pass
    if os.environ.get("OSS_PORT"):
        settings.port = int(os.environ["OSS_PORT"])
    if os.environ.get("OSS_HOST"):
        settings.host = os.environ["OSS_HOST"]
    if overrides:
        _apply(settings, {k: v for k, v in overrides.items() if k != "data_dir"})
    settings.max_worker_threads = max(1, min(8, int(settings.max_worker_threads)))
    return settings


def save_user_settings(settings: Settings, values: dict) -> dict:
    """Persist the editable subset of settings into the data directory."""
    changed = {}
    for key in Settings.EDITABLE:
        if key in values:
            current = getattr(settings, key)
            value = values[key]
            if isinstance(current, (int, float)) and not isinstance(current, bool):
                value = type(current)(value)
            setattr(settings, key, value)
            changed[key] = value
    path = settings.data_dir / "settings.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    existing.update(changed)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return changed
