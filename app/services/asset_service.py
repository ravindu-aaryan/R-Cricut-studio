"""Local asset library: decorations, frames, patterns and user imports.

Built-in assets live in ``assets/`` (read-only, shipped with the app).
User imports live in ``<data>/library`` and are sanitised on import.
SVG assets are rasterised locally with resvg; recolourable regions are
marked with ``data-recolor="primary|secondary|accent"`` attributes.
"""
from __future__ import annotations

import io
import json
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..models.base import new_id
from ..utils.paths import require_safe_id, safe_join, sanitize_filename
from ..utils.svg_sanitize import SVG_NS, sanitize_svg
from ..utils.validation import ValidationError, is_hex_color, validate_image_bytes

ET.register_namespace("", SVG_NS)

CATEGORIES = [
    "crowns", "party-hats", "hats", "balloons", "confetti", "stars", "hearts", "sunglasses", "bowties",
    "gentleman", "flowers", "cakes", "gifts", "ribbons", "banners", "frames", "speech", "school", "sports",
    "seasonal", "festive", "space", "jungle", "dinosaur", "fantasy", "animals", "superhero", "wedding",
    "shapes", "badges", "custom",
]


class AssetError(ValueError):
    pass


class AssetLibrary:
    def __init__(self, assets_dir: Path, library_dir: Path, font_dir: Path | None = None):
        self.assets_dir = assets_dir
        self.library_dir = library_dir
        self.font_dir = font_dir
        self._lock = threading.Lock()
        self._builtin: dict[str, dict] = {}
        self._patterns: dict[str, dict] = {}
        self.reload()

    # ---------------------------------------------------------------- index
    def reload(self) -> None:
        self._builtin = {}
        for sub in ("decorations", "frames"):
            idx = self.assets_dir / sub / "index.json"
            if idx.exists():
                for entry in json.loads(idx.read_text(encoding="utf-8")):
                    entry = {**entry, "builtin": True, "dir": sub}
                    self._builtin[entry["id"]] = entry
        self._patterns = {}
        idx = self.assets_dir / "patterns" / "index.json"
        if idx.exists():
            for entry in json.loads(idx.read_text(encoding="utf-8")):
                self._patterns[entry["id"]] = entry

    def _user_index_path(self) -> Path:
        return self.library_dir / "index.json"

    def _user_index(self) -> dict[str, dict]:
        p = self._user_index_path()
        if not p.exists():
            return {}
        try:
            return {e["id"]: e for e in json.loads(p.read_text(encoding="utf-8"))}
        except (ValueError, KeyError):
            return {}

    def _save_user_index(self, entries: dict[str, dict]) -> None:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._user_index_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(list(entries.values()), indent=2), encoding="utf-8")
        tmp.replace(self._user_index_path())

    def list(self, query: str = "", category: str = "") -> list[dict]:
        entries = list(self._builtin.values()) + [{**e, "builtin": False} for e in self._user_index().values()]
        q = query.strip().lower()
        out = []
        for e in entries:
            if category and e.get("category") != category:
                continue
            if q:
                hay = " ".join([e.get("name", ""), e.get("category", ""), " ".join(e.get("tags", []))]).lower()
                if not all(term in hay for term in q.split()):
                    continue
            out.append(self.public(e))
        return out

    def public(self, e: dict) -> dict:
        return {k: e.get(k) for k in ("id", "name", "category", "tags", "kind", "recolor", "defaultColors",
                                       "aspect", "license", "builtin", "author")}

    def get(self, asset_id: str) -> dict:
        if asset_id in self._builtin:
            return self._builtin[asset_id]
        user = self._user_index().get(asset_id)
        if user is None:
            raise AssetError(f"Asset not found: {asset_id}")
        return {**user, "builtin": False}

    def path_of(self, entry: dict) -> Path:
        if entry.get("builtin"):
            return safe_join(self.assets_dir / entry["dir"], entry["file"])
        return safe_join(self.library_dir / "decorations", entry["file"])

    def patterns(self) -> list[dict]:
        return list(self._patterns.values())

    def pattern_svg(self, pattern_id: str, color: str, bg: str | None = None) -> str:
        entry = self._patterns.get(pattern_id)
        if not entry:
            raise AssetError(f"Pattern not found: {pattern_id}")
        text = (self.assets_dir / "patterns" / entry["file"]).read_text(encoding="utf-8")
        return recolor_svg(sanitize_svg(text), {"pattern": color, "background": bg or "none"})

    # ---------------------------------------------------------------- content
    def svg_text(self, asset_id: str, colors: dict | None = None) -> str:
        entry = self.get(asset_id)
        if entry.get("kind") != "svg":
            raise AssetError("Not an SVG asset")
        text = _read_sanitized(str(self.path_of(entry)))
        merged = {**(entry.get("defaultColors") or {}), **{k: v for k, v in (colors or {}).items() if is_hex_color(v)}}
        return recolor_svg(text, merged) if merged else text

    def raster(self, asset_id: str, width: int, height: int, colors: dict | None = None) -> Image.Image:
        width, height = max(1, int(width)), max(1, int(height))
        if width * height > 60_000_000:
            raise AssetError("Requested asset size is too large")
        entry = self.get(asset_id)
        key = json.dumps(colors or {}, sort_keys=True)
        if entry.get("kind") == "svg":
            return _raster_svg_cached(str(self.path_of(entry)), key, json.dumps(entry.get("defaultColors") or {}),
                                      width, height, str(self.font_dir or "")).copy()
        with Image.open(self.path_of(entry)) as im:
            im.load()
            return im.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)

    def natural_size(self, asset_id: str) -> tuple[float, float]:
        entry = self.get(asset_id)
        aspect = float(entry.get("aspect") or 1.0)
        return (200.0, 200.0 / aspect) if aspect >= 1 else (200.0 * aspect, 200.0)

    # ---------------------------------------------------------------- imports
    def import_asset(self, data: bytes, filename: str, *, name: str = "", category: str = "custom",
                     tags: list[str] | None = None, max_bytes: int = 20_000_000) -> dict:
        """Validate, sanitise and store a user PNG/SVG asset."""
        safe = sanitize_filename(filename, default="asset")
        is_svg = safe.lower().endswith(".svg") or data.lstrip()[:5] in (b"<?xml", b"<svg ") or b"<svg" in data[:512]
        asset_id = new_id("u_")
        dest_dir = self.library_dir / "decorations"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if is_svg:
            try:
                clean = sanitize_svg(data, max_bytes=max_bytes)
            except ValueError as exc:
                raise ValidationError(str(exc)) from None
            file = f"{asset_id}.svg"
            (dest_dir / file).write_text(clean, encoding="utf-8")
            try:
                img = rasterize_svg(clean, 256, None)
            except Exception as exc:
                (dest_dir / file).unlink(missing_ok=True)
                raise ValidationError(f"The SVG could not be rendered: {exc}") from None
            kind, aspect = "svg", img.width / max(1, img.height)
        else:
            info = validate_image_bytes(data, max_bytes=max_bytes, max_pixels=40_000_000, max_side=8000)
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                rgba = im.convert("RGBA")
            file = f"{asset_id}.png"
            rgba.save(dest_dir / file, "PNG")
            kind, aspect = "png", info.width / max(1, info.height)
            if not info.has_alpha:
                tags = list(tags or []) + ["opaque"]
        entry = {
            "id": asset_id, "name": (name or Path(safe).stem)[:80], "category": category if category in CATEGORIES else "custom",
            "tags": [t[:30] for t in (tags or [])][:12], "kind": kind, "file": file, "aspect": round(aspect, 4),
            "recolor": [], "defaultColors": {}, "license": "User supplied", "author": "You",
            "importedAt": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            idx = self._user_index()
            idx[asset_id] = entry
            self._save_user_index(idx)
        return self.public({**entry, "builtin": False})

    def register_existing(self, entry: dict, data: bytes) -> None:
        """Restore a user asset from a project archive (keeps its id)."""
        asset_id = require_safe_id(entry["id"], "asset id")
        if asset_id in self._builtin or asset_id in self._user_index():
            return
        dest_dir = self.library_dir / "decorations"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if entry.get("kind") == "svg":
            file = f"{asset_id}.svg"
            (dest_dir / file).write_text(sanitize_svg(data), encoding="utf-8")
        else:
            validate_image_bytes(data, max_bytes=20_000_000, max_pixels=40_000_000, max_side=8000)
            file = f"{asset_id}.png"
            (dest_dir / file).write_bytes(data)
        clean = {k: entry.get(k) for k in ("name", "category", "tags", "kind", "aspect")}
        clean.update({"id": asset_id, "file": file, "recolor": [], "defaultColors": {}, "license": "User supplied", "author": "You"})
        with self._lock:
            idx = self._user_index()
            idx[asset_id] = clean
            self._save_user_index(idx)

    def delete_user_asset(self, asset_id: str) -> None:
        require_safe_id(asset_id, "asset id")
        with self._lock:
            idx = self._user_index()
            entry = idx.pop(asset_id, None)
            if entry is None:
                raise AssetError("Only imported assets can be deleted.")
            safe_join(self.library_dir / "decorations", entry["file"]).unlink(missing_ok=True)
            self._save_user_index(idx)


def recolor_svg(svg_text: str, colors: dict) -> str:
    """Replace fills/strokes of elements tagged ``data-recolor="<slot>"``."""
    root = ET.fromstring(svg_text)
    for el in root.iter():
        slot = el.get("data-recolor")
        if not slot or slot not in colors:
            continue
        color = colors[slot]
        target = "stroke" if el.get("stroke") and not el.get("fill") else "fill"
        if el.get("fill") == "none" and el.get("stroke"):
            target = "stroke"
        el.set(target, color)
        style = el.get("style")
        if style and target in style:
            el.set("style", ";".join(d for d in style.split(";") if not d.strip().startswith(target + ":")))
    return ET.tostring(root, encoding="unicode")


@lru_cache(maxsize=64)
def _read_sanitized(path: str) -> str:
    return sanitize_svg(Path(path).read_text(encoding="utf-8"))


def rasterize_svg(svg_text: str, width: int, height: int | None, font_dir: str | None = None) -> Image.Image:
    """Render SVG text to RGBA. With both sizes given the aspect is stretched to fit."""
    import resvg_py

    root = ET.fromstring(svg_text)
    if height is not None:
        root.set("preserveAspectRatio", "none")
        root.set("width", str(width))
        root.set("height", str(height))
        text = ET.tostring(root, encoding="unicode")
        png = resvg_py.svg_to_bytes(svg_string=text, width=width, height=height, skip_system_fonts=True,
                                    font_dirs=[font_dir] if font_dir else None)
    else:
        png = resvg_py.svg_to_bytes(svg_string=svg_text, width=width, skip_system_fonts=True,
                                    font_dirs=[font_dir] if font_dir else None)
    img = Image.open(io.BytesIO(bytes(png)))
    img.load()
    img = img.convert("RGBA")
    if height is not None and img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    return img


@lru_cache(maxsize=256)
def _raster_svg_cached(path: str, colors_key: str, defaults_key: str, width: int, height: int, font_dir: str) -> Image.Image:
    text = _read_sanitized(path)
    colors = {**json.loads(defaults_key), **{k: v for k, v in json.loads(colors_key).items() if is_hex_color(v)}}
    if colors:
        text = recolor_svg(text, colors)
    return rasterize_svg(text, width, height, font_dir or None)
