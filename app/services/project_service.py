"""Project folders, documents, versions, autosave/recovery and archives.

Layout of a project folder (all paths inside the document are relative)::

    <id>/project.json            current saved document
    <id>/project.autosave.json   newer unsaved state (crash recovery)
    <id>/originals/              untouched uploads
    <id>/working/                orientation-corrected, geometry-edited copies
    <id>/previews/  thumbs/      reduced copies for the UI
    <id>/masks/  subjects/       extraction masks and transparent subjects
    <id>/renders/                cached sticker previews
    <id>/exports/<timestamp>/    export results
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..models.base import new_id
from ..models.layout import Sheet
from ..models.sticker import StickerDoc
from ..repositories.project_repository import ProjectRepository
from ..utils.image_dimensions import a4, mm_to_px_int
from ..utils.paths import UnsafePathError, require_safe_id, safe_join, sanitize_filename
from ..version import APP_VERSION, PROJECT_FORMAT_VERSION

PROJECT_SUBDIRS = ("originals", "working", "previews", "thumbs", "masks", "subjects", "renders", "exports")
ORIGINAL_RE = re.compile(r"^originals/ph_[a-f0-9]{12}\.(jpg|png|webp|tiff|heic)$")
EDITABLE_PHOTO_FIELDS = ("name", "adjustments", "background", "faceRegions", "protectFace")
MAX_DOC_BYTES = 25_000_000
ARCHIVE_EXT = ".ossproj"
MAX_ARCHIVE_UNCOMPRESSED = 2_000_000_000


class ProjectError(ValueError):
    pass


class ProjectNotFound(ProjectError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_document(pid: str, name: str, theme_id: str | None) -> dict:
    return {
        "formatVersion": PROJECT_FORMAT_VERSION,
        "appVersion": APP_VERSION,
        "id": pid,
        "name": name,
        "createdAt": utcnow(),
        "updatedAt": utcnow(),
        "themeId": theme_id or "birthday",
        "photos": [],
        "stickers": [],
        "sheets": [Sheet(name="Sheet 1").to_dict()],
        "presets": [],
        "collection": {},
        "exportSettings": {"dpi": 300, "cutOffsetMm": 0.0, "includeCutLinesInPdf": False, "transparentPng": False},
        "settings": {"defaultStickerMm": 60},
    }


# --------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------

def _migrate_1_to_2(doc: dict) -> dict:
    """v1 stored a single list of items per sheet; v2 supports multiple pages."""
    for sheet in doc.get("sheets", []):
        if "items" in sheet and "pages" not in sheet:
            sheet["pages"] = [{"id": new_id("pg_"), "items": sheet.pop("items")}]
    for sticker in doc.get("stickers", []):
        border = sticker.get("border") or {}
        if "outline" in border and "outlines" not in border:
            ol = border.pop("outline")
            border["outlines"] = [ol] if ol else []
        sticker["border"] = border
    doc.setdefault("presets", [])
    return doc


MIGRATIONS = {1: _migrate_1_to_2}


def migrate_document(doc: dict) -> dict:
    version = int(doc.get("formatVersion", 1))
    if version > PROJECT_FORMAT_VERSION:
        raise ProjectError(
            f"This project was made with a newer version of the app (format {version}). Please update the app.")
    while version < PROJECT_FORMAT_VERSION:
        doc = MIGRATIONS[version](doc)
        version += 1
    doc["formatVersion"] = PROJECT_FORMAT_VERSION
    return doc


def normalize_document(doc: dict) -> dict:
    """Round-trip stickers and sheets through the typed model to validate them."""
    doc["stickers"] = [StickerDoc.from_dict(s).to_dict() for s in doc.get("stickers") or []]
    doc["sheets"] = [Sheet.from_dict(s).to_dict() for s in doc.get("sheets") or []] or [Sheet(name="Sheet 1").to_dict()]
    for key in ("photos", "presets"):
        if not isinstance(doc.get(key), list):
            doc[key] = []
    return doc


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

class ProjectService:
    def __init__(self, projects_dir: Path, repo: ProjectRepository):
        self.root = projects_dir
        self.repo = repo
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def lock(self, pid: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(pid, threading.RLock())

    def project_dir(self, pid: str) -> Path:
        require_safe_id(pid, "project id")
        d = safe_join(self.root, pid)
        if not d.is_dir():
            raise ProjectNotFound("Project not found.")
        return d

    # ---------------------------------------------------------------- CRUD
    def create(self, name: str, theme_id: str | None = None) -> dict:
        name = (name or "").strip()[:80] or "Untitled project"
        pid = new_id("pr_")
        d = safe_join(self.root, pid)
        for sub in PROJECT_SUBDIRS:
            (d / sub).mkdir(parents=True, exist_ok=True)
        doc = empty_document(pid, name, theme_id)
        self._write_json(d / "project.json", doc)
        self.repo.insert(pid, name, doc["themeId"])
        self.repo.update_meta(pid, sheet_count=1)
        return doc

    def load(self, pid: str, *, prefer_autosave: bool = False) -> dict:
        d = self.project_dir(pid)
        path = d / "project.json"
        if prefer_autosave and (d / "project.autosave.json").exists():
            path = d / "project.autosave.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            backup = d / "project.json.bak"
            if backup.exists():
                doc = json.loads(backup.read_text(encoding="utf-8"))
            else:
                raise ProjectError("The project file is damaged and no backup is available.")
        doc = migrate_document(doc)
        doc["id"] = pid
        return doc

    def open(self, pid: str) -> dict:
        doc = self.load(pid)
        self.repo.update_meta(pid, opened_at=time.time())
        return {"document": doc, "recovery": self.recovery_info(pid)}

    def recovery_info(self, pid: str) -> dict | None:
        d = self.project_dir(pid)
        auto = d / "project.autosave.json"
        if not auto.exists():
            return None
        saved_mtime = (d / "project.json").stat().st_mtime if (d / "project.json").exists() else 0
        if auto.stat().st_mtime <= saved_mtime:
            return None
        return {"autosavedAt": datetime.fromtimestamp(auto.stat().st_mtime, timezone.utc).isoformat(),
                "savedAt": datetime.fromtimestamp(saved_mtime, timezone.utc).isoformat()}

    def discard_autosave(self, pid: str) -> None:
        (self.project_dir(pid) / "project.autosave.json").unlink(missing_ok=True)

    def save(self, pid: str, incoming: dict, *, autosave: bool = False) -> dict:
        """Save a document from the editor.

        Photo records are authoritative on the server (they reference files);
        only their editable fields are taken from the incoming document.
        """
        d = self.project_dir(pid)
        raw = json.dumps(incoming)
        if len(raw) > MAX_DOC_BYTES:
            raise ProjectError("The project document is too large.")
        with self.lock(pid):
            current = self.load(pid, prefer_autosave=autosave)
            doc = migrate_document(dict(incoming))
            doc["photos"] = self._merge_photos(current.get("photos", []), incoming.get("photos") or [])
            doc["id"] = pid
            doc["createdAt"] = current.get("createdAt", utcnow())
            doc["updatedAt"] = utcnow()
            doc["appVersion"] = APP_VERSION
            doc["name"] = (str(doc.get("name") or current.get("name") or "Untitled project")).strip()[:80]
            doc = normalize_document(doc)
            if autosave:
                self._write_json(d / "project.autosave.json", doc)
            else:
                if (d / "project.json").exists():
                    shutil.copy2(d / "project.json", d / "project.json.bak")
                self._write_json(d / "project.json", doc)
                (d / "project.autosave.json").unlink(missing_ok=True)
            self.repo.update_meta(pid, name=doc["name"], updated_at=time.time(), theme_id=doc.get("themeId"),
                                  photo_count=len(doc["photos"]), sticker_count=len(doc["stickers"]),
                                  sheet_count=len(doc["sheets"]))
        return doc

    def update_server_side(self, pid: str, mutate) -> dict:
        """Apply a server-side change (e.g. photo import) to saved and autosaved docs."""
        d = self.project_dir(pid)
        with self.lock(pid):
            doc = self.load(pid)
            mutate(doc)
            doc["updatedAt"] = utcnow()
            doc = normalize_document(doc)
            self._write_json(d / "project.json", doc)
            auto = d / "project.autosave.json"
            if auto.exists():
                try:
                    adoc = migrate_document(json.loads(auto.read_text(encoding="utf-8")))
                    mutate(adoc)
                    self._write_json(auto, normalize_document(adoc))
                except (ValueError, OSError):
                    auto.unlink(missing_ok=True)
            self.repo.update_meta(pid, updated_at=time.time(), photo_count=len(doc["photos"]),
                                  sticker_count=len(doc["stickers"]), sheet_count=len(doc["sheets"]))
        return doc

    def _merge_photos(self, current: list[dict], incoming: list[dict]) -> list[dict]:
        by_id = {p["id"]: dict(p) for p in current}
        order = [p.get("id") for p in incoming if isinstance(p, dict) and p.get("id") in by_id]
        for p in incoming:
            if isinstance(p, dict) and p.get("id") in by_id:
                for key in EDITABLE_PHOTO_FIELDS:
                    if key in p:
                        by_id[p["id"]][key] = p[key]
        # Photos deleted on the client are removed with a dedicated API call,
        # so any server photo missing from the incoming list is kept.
        rest = [pid for pid in by_id if pid not in order]
        return [by_id[i] for i in order + rest]

    def rename(self, pid: str, name: str) -> dict:
        name = (name or "").strip()[:80]
        if not name:
            raise ProjectError("Please enter a project name.")
        self.update_server_side(pid, lambda doc: doc.__setitem__("name", name))
        self.repo.update_meta(pid, name=name)
        return self.load(pid)

    def duplicate(self, pid: str, new_name: str | None = None, document: dict | None = None) -> dict:
        src = self.project_dir(pid)
        doc = document or self.load(pid)
        new_pid = new_id("pr_")
        dst = safe_join(self.root, new_pid)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("exports", "project.autosave.json", "*.tmp"))
        (dst / "exports").mkdir(exist_ok=True)
        doc = dict(doc)
        doc["id"] = new_pid
        doc["name"] = (new_name or f"{doc.get('name', 'Project')} copy").strip()[:80]
        doc["createdAt"] = doc["updatedAt"] = utcnow()
        if document is not None:
            doc["photos"] = self._merge_photos(self.load(pid).get("photos", []), document.get("photos") or [])
        doc = normalize_document(migrate_document(doc))
        self._write_json(dst / "project.json", doc)
        self.repo.insert(new_pid, doc["name"], doc.get("themeId"))
        self.repo.update_meta(new_pid, photo_count=len(doc["photos"]), sticker_count=len(doc["stickers"]),
                              sheet_count=len(doc["sheets"]))
        return doc

    def set_archived(self, pid: str, archived: bool) -> None:
        self.project_dir(pid)
        self.repo.update_meta(pid, archived=1 if archived else 0)

    def delete(self, pid: str) -> None:
        d = self.project_dir(pid)
        shutil.rmtree(d)
        self.repo.delete(pid)

    def list(self, include_archived: bool = False, query: str = "") -> list[dict]:
        out = []
        for row in self.repo.list(include_archived=include_archived, query=query):
            d = self.root / row["id"]
            if not d.is_dir():
                continue  # folder removed outside the app
            row["hasThumbnail"] = (d / "thumbs" / "project.png").exists()
            row["recoveryAvailable"] = (d / "project.autosave.json").exists()
            out.append(row)
        return out

    def reindex(self) -> int:
        """Register project folders that exist on disk but not in SQLite."""
        known = {r["id"] for r in self.repo.list(include_archived=True)}
        added = 0
        for d in self.root.iterdir() if self.root.exists() else []:
            if d.is_dir() and d.name not in known and (d / "project.json").exists():
                try:
                    doc = self.load(d.name)
                except ProjectError:
                    continue
                self.repo.insert(d.name, doc.get("name", "Recovered project"), doc.get("themeId"))
                added += 1
        return added

    # ---------------------------------------------------------------- files
    def photo(self, doc: dict, photo_id: str) -> dict:
        for p in doc.get("photos", []):
            if p["id"] == photo_id:
                if not ORIGINAL_RE.match(p.get("original", "")):
                    raise UnsafePathError("Invalid photo record.")
                return p
        raise ProjectError("Photo not found.")

    @staticmethod
    def _write_json(path: Path, doc: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    # ---------------------------------------------------------------- archives
    def manifest(self, doc: dict, files: list[str], user_assets: list[dict]) -> dict:
        canvases = []
        for s in doc.get("stickers", []):
            st = StickerDoc.from_dict(s)
            canvases.append({"stickerId": st.id, "widthMm": st.width_mm, "heightMm": st.height_mm, "dpi": st.dpi,
                             "widthPx": st.width_px, "heightPx": st.height_px, "layers": len(st.layers),
                             "shape": st.shape.type, "themeId": st.theme_id})
        pages = []
        for sh in doc.get("sheets", []):
            sheet = Sheet.from_dict(sh)
            size = a4(sheet.orientation)
            pages.append({"sheetId": sheet.id, "orientation": sheet.orientation, "widthMm": size.width_mm,
                          "heightMm": size.height_mm, "dpi": sheet.dpi,
                          "widthPx": mm_to_px_int(size.width_mm, sheet.dpi),
                          "heightPx": mm_to_px_int(size.height_mm, sheet.dpi), "pages": len(sheet.pages)})
        return {
            "manifestVersion": 1,
            "projectFormatVersion": doc.get("formatVersion", PROJECT_FORMAT_VERSION),
            "appVersion": APP_VERSION,
            "application": "Offline Sticker Studio",
            "exportedAt": utcnow(),
            "projectId": doc["id"],
            "name": doc.get("name"),
            "themeId": doc.get("themeId"),
            "canvases": canvases,
            "pages": pages,
            "assetReferences": sorted({l.get("assetId") for s in doc.get("stickers", []) for l in _walk(s.get("layers", []))
                                       if l.get("assetId")}),
            "userAssets": user_assets,
            "exportSettings": doc.get("exportSettings", {}),
            "files": files,
        }

    def export_archive(self, pid: str, asset_library, out_path: Path) -> Path:
        """Write a self-contained ``.ossproj`` (zip) with document, photos and user assets."""
        d = self.project_dir(pid)
        doc = self.load(pid)
        files: list[str] = []
        user_assets = []
        used = {l.get("assetId") for s in doc.get("stickers", []) for l in _walk(s.get("layers", []))}
        used |= {s.get("shape", {}).get("customAssetId") for s in doc.get("stickers", [])}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for sub in ("originals", "working", "masks", "subjects", "thumbs", "previews"):
                for f in sorted((d / sub).glob("*")):
                    if f.is_file() and not f.name.endswith(".tmp"):
                        rel = f"{sub}/{f.name}"
                        z.write(f, rel)
                        files.append(rel)
            for aid in sorted(a for a in used if a):
                try:
                    entry = asset_library.get(aid)
                except Exception:
                    continue
                if entry.get("builtin"):
                    continue
                rel = f"assets/{entry['file']}"
                z.write(asset_library.path_of(entry), rel)
                files.append(rel)
                user_assets.append({k: entry.get(k) for k in ("id", "name", "category", "tags", "kind", "aspect", "file")})
            z.writestr("project.json", json.dumps(doc, indent=1, ensure_ascii=False))
            z.writestr("manifest.json", json.dumps(self.manifest(doc, files, user_assets), indent=1, ensure_ascii=False))
        return out_path

    def import_archive(self, data: bytes, asset_library, max_bytes: int = 1_500_000_000) -> dict:
        if len(data) > max_bytes:
            raise ProjectError("The archive is too large.")
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ProjectError("This is not a valid Offline Sticker Studio project archive.") from None
        with z:
            names = z.namelist()
            if "project.json" not in names or "manifest.json" not in names:
                raise ProjectError("The archive has no project document.")
            total = sum(i.file_size for i in z.infolist())
            if total > MAX_ARCHIVE_UNCOMPRESSED:
                raise ProjectError("The archive expands to too much data.")
            allowed = re.compile(r"^(originals|working|masks|subjects|thumbs|previews|assets)/[A-Za-z0-9_.-]+$")
            doc = migrate_document(json.loads(z.read("project.json")))
            manifest = json.loads(z.read("manifest.json"))
            new_pid = new_id("pr_")
            dst = safe_join(self.root, new_pid)
            for sub in PROJECT_SUBDIRS:
                (dst / sub).mkdir(parents=True, exist_ok=True)
            try:
                user_assets = {a["id"]: a for a in manifest.get("userAssets", []) if isinstance(a, dict) and "id" in a}
                for info in z.infolist():
                    name = info.filename
                    if name in ("project.json", "manifest.json") or name.endswith("/"):
                        continue
                    if not allowed.match(name) or ".." in name:
                        continue  # ignore anything unexpected
                    if name.startswith("assets/"):
                        fname = name.split("/", 1)[1]
                        entry = next((a for a in user_assets.values() if a.get("file") == fname), None)
                        if entry:
                            asset_library.register_existing(entry, z.read(info))
                        continue
                    target = safe_join(dst, *name.split("/"))
                    with z.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out, 1024 * 1024)
                doc["photos"] = [p for p in doc.get("photos", []) if ORIGINAL_RE.match(p.get("original", ""))
                                 and (dst / p["original"]).exists()]
                doc["id"] = new_pid
                doc["name"] = sanitize_filename(doc.get("name") or "Imported project", "Imported project").replace("_", " ")[:80]
                doc = normalize_document(doc)
                self._write_json(dst / "project.json", doc)
            except Exception:
                shutil.rmtree(dst, ignore_errors=True)
                raise
        self.repo.insert(new_pid, doc["name"], doc.get("themeId"))
        self.repo.update_meta(new_pid, photo_count=len(doc["photos"]), sticker_count=len(doc["stickers"]),
                              sheet_count=len(doc["sheets"]))
        return doc

    def export_dir(self, pid: str, kind: str) -> tuple[str, Path]:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = f"{stamp}-{sanitize_filename(kind)}-{new_id()[:4]}"
        path = self.project_dir(pid) / "exports" / folder
        path.mkdir(parents=True, exist_ok=True)
        return folder, path


def _walk(layers: list[dict]):
    for l in layers or []:
        yield l
        yield from _walk(l.get("children") or [])
