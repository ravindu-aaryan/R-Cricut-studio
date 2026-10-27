import json

import pytest

from app.models.layout import Sheet
from app.models.sticker import StickerDoc
from app.repositories.project_repository import ProjectRepository
from app.services.project_service import ProjectError, ProjectService, migrate_document


@pytest.fixture()
def svc(tmp_path):
    return ProjectService(tmp_path / "projects", ProjectRepository(tmp_path / "db.sqlite3"))


def sample_sticker():
    return {"id": "st_1", "name": "S", "widthMm": 50, "heightMm": 40, "shape": {"type": "heart"},
            "border": {"widthMm": 2, "color": "#fff", "outlines": [{"widthMm": 1, "color": "#f00", "gapMm": 0.5}]},
            "layers": [
                {"id": "l1", "type": "text", "text": "Hello", "x": 10, "y": 20, "fontFamily": "Bangers", "curve": 40},
                {"id": "g1", "type": "group", "x": 5, "y": 5, "children": [{"id": "c1", "type": "shape", "shape": "star"}]},
            ],
            "futureField": {"kept": True}}


def test_sticker_roundtrip_preserves_data_and_unknown_fields():
    doc = StickerDoc.from_dict(sample_sticker())
    out = doc.to_dict()
    again = StickerDoc.from_dict(out).to_dict()
    assert out == again
    assert out["futureField"] == {"kept": True}
    assert out["layers"][1]["children"][0]["shape"] == "star"
    assert out["border"]["outlines"][0]["gapMm"] == 0.5
    assert doc.width_px == 591


def test_sticker_values_are_clamped():
    d = StickerDoc.from_dict({"widthMm": 9999, "heightMm": -3, "dpi": 5000, "shape": {"type": "weird"}})
    assert d.width_mm == 297 and d.height_mm == 5 and d.dpi == 600 and d.shape.type == "silhouette"


def test_unknown_layer_type_rejected():
    with pytest.raises(ValueError):
        StickerDoc.from_dict({"layers": [{"type": "iframe"}]})


def test_sheet_roundtrip():
    s = Sheet.from_dict({"orientation": "landscape", "pages": [{"items": [{"stickerId": "a", "xMm": 1, "yMm": 2, "widthMm": 3, "heightMm": 4}]}]})
    d = s.to_dict()
    assert d["pages"][0]["items"][0]["stickerId"] == "a"
    assert Sheet.from_dict(d).to_dict() == d
    assert s.page_size.width_mm == 297


def test_migration_v1_to_v2():
    v1 = {"formatVersion": 1, "photos": [], "stickers": [{"border": {"outline": {"widthMm": 1, "color": "#000"}}}],
          "sheets": [{"items": [{"stickerId": "a"}]}]}
    v2 = migrate_document(v1)
    assert v2["formatVersion"] == 2
    assert v2["sheets"][0]["pages"][0]["items"][0]["stickerId"] == "a"
    assert v2["stickers"][0]["border"]["outlines"][0]["widthMm"] == 1


def test_newer_format_rejected():
    with pytest.raises(ProjectError, match="newer version"):
        migrate_document({"formatVersion": 99})


def test_create_save_reopen(svc):
    doc = svc.create("My project", "space")
    doc["stickers"].append(sample_sticker())
    svc.save(doc["id"], doc)
    reopened = svc.open(doc["id"])["document"]
    assert reopened["name"] == "My project" and reopened["themeId"] == "space"
    assert reopened["stickers"][0]["layers"][0]["text"] == "Hello"
    assert svc.repo.get(doc["id"])["sticker_count"] == 1


def test_autosave_and_recovery(svc):
    doc = svc.create("P", None)
    doc["name"] = "Changed"
    svc.save(doc["id"], doc, autosave=True)
    assert svc.recovery_info(doc["id"]) is not None
    assert svc.load(doc["id"])["name"] == "P"
    assert svc.load(doc["id"], prefer_autosave=True)["name"] == "Changed"
    svc.save(doc["id"], svc.load(doc["id"], prefer_autosave=True))
    assert svc.recovery_info(doc["id"]) is None
    assert svc.load(doc["id"])["name"] == "Changed"


def test_client_cannot_rewrite_photo_paths(svc):
    doc = svc.create("P", None)
    pid = doc["id"]
    photo = {"id": "ph_0123456789ab", "original": "originals/ph_0123456789ab.jpg", "name": "x", "adjustments": {}}
    svc.update_server_side(pid, lambda d: d["photos"].append(photo))
    evil = svc.load(pid)
    evil["photos"][0]["original"] = "../../../../etc/passwd"
    evil["photos"][0]["adjustments"] = {"brightness": 0.5}
    evil["photos"].append({"id": "ph_injected0000", "original": "/etc/passwd"})
    saved = svc.save(pid, evil)
    assert saved["photos"][0]["original"] == "originals/ph_0123456789ab.jpg"
    assert saved["photos"][0]["adjustments"] == {"brightness": 0.5}
    assert len(saved["photos"]) == 1


def test_rename_duplicate_archive_delete(svc):
    doc = svc.create("Original", None)
    svc.rename(doc["id"], "Renamed")
    assert svc.load(doc["id"])["name"] == "Renamed"
    copy = svc.duplicate(doc["id"], "Copy")
    assert copy["id"] != doc["id"] and svc.load(copy["id"])["name"] == "Copy"
    svc.set_archived(doc["id"], True)
    assert doc["id"] not in [p["id"] for p in svc.list()]
    assert doc["id"] in [p["id"] for p in svc.list(include_archived=True)]
    svc.delete(doc["id"])
    assert svc.repo.get(doc["id"]) is None
    with pytest.raises(ProjectError):
        svc.load(doc["id"])


def test_damaged_document_falls_back_to_backup(svc):
    doc = svc.create("Safe", None)
    svc.save(doc["id"], doc)  # creates project.json.bak
    (svc.project_dir(doc["id"]) / "project.json").write_text("{ broken", encoding="utf-8")
    assert svc.load(doc["id"])["name"] == "Safe"


def test_reindex_finds_orphan_folders(svc, tmp_path):
    doc = svc.create("Orphan", None)
    svc.repo.delete(doc["id"])
    assert svc.reindex() == 1
    assert svc.repo.get(doc["id"])["name"] == "Orphan"


def test_schema_migrations_idempotent(tmp_path):
    r = ProjectRepository(tmp_path / "x.sqlite3")
    assert r.migrate() == 2
    r.set_setting("k", {"a": 1})
    assert ProjectRepository(tmp_path / "x.sqlite3").get_setting("k") == {"a": 1}
    _ = json
