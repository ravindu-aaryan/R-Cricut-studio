"""Bulk sticker import, white-background removal and templates."""
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.models.sticker import StickerDoc
from app.services import import_service as imp
from app.services.asset_service import AssetLibrary
from app.utils.validation import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def png(color=(200, 40, 40, 255), size=(160, 120), bg=(0, 0, 0, 0)):
    im = Image.new("RGBA", size, bg)
    ImageDraw.Draw(im).ellipse((20, 20, size[0] - 20, size[1] - 20), fill=color)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def lib(tmp_path):
    return AssetLibrary(ROOT / "assets", tmp_path / "lib", ROOT / "assets" / "fonts")


def test_expand_zip_and_filter(tmp_path):
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr("a.png", png())
        z.writestr("nested/b.png", png())
        z.writestr("__MACOSX/c.png", b"junk")
        z.writestr("notes.txt", b"ignore me")
    files = imp.expand_files([("pack.zip", zb.getvalue()), ("solo.png", png())], 10_000_000)
    names = sorted(n for n, _ in files)
    assert names == ["a.png", "b.png", "solo.png"]


def test_remove_white_background_keeps_interior():
    im = Image.new("RGBA", (120, 120), (255, 255, 255, 255))
    ImageDraw.Draw(im).ellipse((20, 20, 100, 100), fill=(200, 40, 40, 255))
    ImageDraw.Draw(im).ellipse((50, 50, 70, 70), fill=(255, 255, 255, 255))  # white eye inside
    out = imp.remove_white_background(im, 36)
    a = np.asarray(out.getchannel("A"))
    assert a[2, 2] == 0           # corner removed
    assert a[60, 60] > 200        # interior white kept (not connected to border)
    assert a[40, 40] > 200        # subject body kept


def test_prepare_trims_and_detects_svg():
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((40, 50, 110, 130), fill=(0, 0, 200, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out, is_svg = imp.prepare_image(buf.getvalue(), "x.png", imp.ImportOptions(trim=True), max_bytes=10**7, max_pixels=10**8, max_side=10000)
    assert not is_svg and out.size == (71, 81)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'
    text, is_svg = imp.prepare_image(svg, "a.svg", imp.ImportOptions(), max_bytes=10**7, max_pixels=10**8, max_side=10000)
    assert is_svg and "<circle" in text


def test_import_stickers_builds_valid_docs(lib):
    files = [("red.png", png()), ("blue.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>')]
    result = imp.import_stickers(files, imp.ImportOptions(size_mm=50, border_mm=2), lib,
                                 max_bytes=10**7, max_pixels=10**8, max_side=10000)
    assert len(result.stickers) == 2 and not result.errors
    for s in result.stickers:
        doc = StickerDoc.from_dict(s)           # round-trips through the typed model
        assert doc.layers[0].type == "asset" and doc.border.width_mm == 2
        assert max(doc.width_mm, doc.height_mm) == pytest.approx(50, abs=0.1)
    assert {a["id"] for a in result.assets} == {s["layers"][0]["assetId"] for s in result.stickers}


def test_import_reports_bad_files(lib):
    result = imp.import_stickers([("broken.png", b"\x89PNG\r\nnope")], imp.ImportOptions(), lib,
                                 max_bytes=10**7, max_pixels=10**8, max_side=10000)
    assert result.stickers == [] and result.errors and "broken.png" in result.errors[0]["file"]


def test_too_many_files():
    with pytest.raises(ValidationError, match="Too many"):
        imp.expand_files([(f"{i}.png", b"img-bytes") for i in range(imp.MAX_FILES + 2)], 10_000_000)


# ---------------------------------------------------------------- templates
def photo_sticker():
    from app.models.layer import Layer
    return StickerDoc(width_mm=60, height_mm=60, layers=[
        Layer(type="image", photo_id="ph_old", source="subject", x=350, y=300, width=400, height=500,
              crop={"x": 0, "y": 0, "w": 1, "h": 1}, rotation=5),
        Layer(type="text", text="Hello", x=350, y=620)]).to_dict()


def test_make_template_strips_photo():
    tpl = imp.make_template(photo_sticker(), "T1", "birthday")
    assert tpl["hasPhotoSlot"] is True
    slot = tpl["sticker"]["layers"][0]
    assert slot["type"] == "shape" and slot["photoSlot"] is True and "photoId" not in slot


def test_instantiate_template_fills_photo_slot_keeping_transform():
    tpl = imp.make_template(photo_sticker(), "T", None)
    photo = {"id": "ph_new", "name": "Kid", "width": 800, "height": 1000, "mask": "m", "subjectBox": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}}
    doc = imp.instantiate_template(tpl, photo=photo, name="Made")
    img = next(l for l in doc["layers"] if l["type"] == "image")
    assert img["photoId"] == "ph_new" and img["x"] == 350 and img["y"] == 300 and img["rotation"] == 5
    assert doc["name"] == "Made" and doc["id"].startswith("st_")
    StickerDoc.from_dict(doc)


def test_instantiate_with_asset():
    tpl = imp.make_template(photo_sticker(), "T", None)
    doc = imp.instantiate_template(tpl, asset={"id": "u_abc", "name": "Art"})
    img = next(l for l in doc["layers"] if l.get("assetId"))
    assert img["type"] == "asset" and img["assetId"] == "u_abc"


def test_template_store_roundtrip(tmp_path):
    store = imp.TemplateStore(tmp_path / "templates")
    t = store.save(imp.make_template(photo_sticker(), "Mine", "space"))
    assert [x["id"] for x in store.list()] == [t["id"]]
    bundle = store.export_bundle()
    assert bundle[:4] == b"PK\x03\x04"
    store2 = imp.TemplateStore(tmp_path / "t2")
    imported = store2.import_bundle(bundle)
    assert len(imported) == 1 and imported[0]["name"] == "Mine" and imported[0]["id"] != t["id"]
    store.delete(t["id"])
    assert store.list() == []


def test_import_bundle_plain_json(tmp_path):
    store = imp.TemplateStore(tmp_path / "t")
    payload = json.dumps({"templates": [imp.make_template(photo_sticker(), "J", None)]}).encode()
    assert len(store.import_bundle(payload)) == 1
    with pytest.raises(ValidationError):
        store.import_bundle(b"not json")
