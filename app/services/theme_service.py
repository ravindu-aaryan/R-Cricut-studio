"""Theme engine: themes are JSON files plus references to local assets.

Built-in themes live in ``assets/themes/<id>/theme.json``. Custom themes
created by the user are stored in ``<data>/library/themes/<id>.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models.base import new_id
from ..utils.paths import require_safe_id, safe_join
from ..utils.validation import is_hex_color

REQUIRED_KEYS = ("id", "name", "description", "palette", "typography", "decorations", "frames", "border",
                 "shadow", "layoutPresets", "suggestedSizesMm", "textPresets", "license")


class ThemeError(ValueError):
    pass


class ThemeService:
    def __init__(self, themes_dir: Path, custom_dir: Path):
        self.themes_dir = themes_dir
        self.custom_dir = custom_dir
        self._builtin: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        self._builtin = {}
        if not self.themes_dir.exists():
            return
        for f in sorted(self.themes_dir.glob("*/theme.json")):
            theme = json.loads(f.read_text(encoding="utf-8"))
            theme["builtin"] = True
            self._builtin[theme["id"]] = theme

    def _custom(self) -> dict[str, dict]:
        out = {}
        if self.custom_dir.exists():
            for f in sorted(self.custom_dir.glob("*.json")):
                try:
                    t = json.loads(f.read_text(encoding="utf-8"))
                    t["builtin"] = False
                    out[t["id"]] = t
                except (ValueError, KeyError):
                    continue
        return out

    def list(self) -> list[dict]:
        themes = list(self._builtin.values()) + list(self._custom().values())
        return sorted(themes, key=lambda t: (t.get("order", 999), t["name"]))

    def get(self, theme_id: str) -> dict:
        if theme_id in self._builtin:
            return self._builtin[theme_id]
        custom = self._custom()
        if theme_id in custom:
            return custom[theme_id]
        raise ThemeError(f"Theme not found: {theme_id}")

    def save_custom(self, data: dict, asset_ids: set[str]) -> dict:
        """Create or update a user theme after validating every field."""
        base = self._builtin.get("custom") or {}
        tid = data.get("id") if data.get("id") and not data.get("id") in self._builtin else new_id("th_")
        require_safe_id(tid, "theme id")
        palette = [c for c in data.get("palette", []) if is_hex_color(c)][:8] or base.get("palette", ["#ff6fa5"])
        theme = {
            **{k: base.get(k) for k in REQUIRED_KEYS},
            "id": tid,
            "name": str(data.get("name") or "My theme").strip()[:60],
            "description": str(data.get("description") or "A custom theme.").strip()[:240],
            "palette": palette,
            "colors": {
                "primary": palette[0], "secondary": palette[1 % len(palette)], "accent": palette[2 % len(palette)],
                "text": data.get("colors", {}).get("text") if is_hex_color(data.get("colors", {}).get("text", "")) else "#2d2140",
            },
            "typography": {
                "heading": str(data.get("typography", {}).get("heading") or "Luckiest Guy")[:60],
                "body": str(data.get("typography", {}).get("body") or "Poppins")[:60],
            },
            "decorations": [a for a in data.get("decorations", []) if a in asset_ids][:60],
            "frames": [a for a in data.get("frames", []) if a in asset_ids][:20],
            "textPresets": [str(t)[:60] for t in data.get("textPresets", []) if str(t).strip()][:20] or ["Custom text"],
            "license": {"assets": "Your own selection of bundled and imported assets."},
            "order": 900,
        }
        for key in ("border", "shadow", "layoutPresets", "suggestedSizesMm", "backgrounds", "shapes", "accessorySets"):
            if key in data:
                theme[key] = data[key]
            elif key in base:
                theme[key] = base[key]
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        safe_join(self.custom_dir, f"{tid}.json").write_text(json.dumps(theme, indent=2), encoding="utf-8")
        theme["builtin"] = False
        return theme

    def delete_custom(self, theme_id: str) -> None:
        require_safe_id(theme_id, "theme id")
        if theme_id in self._builtin:
            raise ThemeError("Built-in themes cannot be deleted.")
        safe_join(self.custom_dir, f"{theme_id}.json").unlink(missing_ok=True)

    @staticmethod
    def validate(theme: dict) -> list[str]:
        problems = [f"missing '{k}'" for k in REQUIRED_KEYS if k not in theme]
        if not all(is_hex_color(c) for c in theme.get("palette", [])):
            problems.append("palette contains an invalid colour")
        return problems
