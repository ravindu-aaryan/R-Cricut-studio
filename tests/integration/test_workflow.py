"""End-to-end workflow through the HTTP API: create, import, extract, design, save/reopen, layout, export."""
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from tests.conftest import wait_job

MM = 25.4


def make_stickers(client, project, photo, cutout):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/collection/generate", json={
        "photoIds": [photo["id"]], "themeId": "birthday", "shapes": ["silhouette", "circle", "heart"],
        "borders": ["classic", "double"], "count": 4, "accessoryIds": ["party_hat_stripes", "sunglasses_star"],
        "decorationIds": ["balloon_bunch", "star_basic"], "texts": ["Happy Birthday", "Maya"], "treatments": ["none", "sepia"],
        "sizeMm": 50, "seed": 7})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["stickers"]


def save(client, pid, doc):
    r = client.put(f"/api/projects/{pid}", json={"document": doc})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["document"]


def test_full_workflow(client, project, photo, cutout):
    pid = project["id"]
    # --- extraction produced a transparent subject
    assert cutout["mask"] and cutout["subjectBox"]["w"] < 1
    r = client.get(f"/api/projects/{pid}/photos/{photo['id']}/image?variant=subject")
    subject = Image.open(io.BytesIO(r.data))
    assert subject.mode == "RGBA" and np.asarray(subject.getchannel("A")).min() == 0
    original = client.get(f"/api/projects/{pid}/photos/{photo['id']}/image?variant=original").data
    assert original[:3] == b"\xff\xd8\xff"

    # --- generate stickers from local assets and save the project
    stickers = make_stickers(client, project, photo, cutout)
    assert len(stickers) == 4
    assert {s["shape"]["type"] for s in stickers} <= {"silhouette", "circle", "heart"}
    kinds = {l["type"] for s in stickers for l in s["layers"]}
    assert {"image", "text", "asset"} <= kinds
    assert all("no new photographic content" in s["variant"]["note"] for s in stickers)
    doc = client.get(f"/api/projects/{pid}").get_json()["document"]
    doc["stickers"] = stickers
    doc = save(client, pid, doc)

    # --- reopen: identical sticker documents
    reopened = client.get(f"/api/projects/{pid}").get_json()["document"]
    assert reopened["stickers"] == doc["stickers"]

    # --- render a preview
    r = client.post(f"/api/projects/{pid}/stickers/render", json={"sticker": stickers[0], "maxSide": 300})
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert max(Image.open(io.BytesIO(r.data)).size) <= 300

    # --- arrange an A4 sheet
    sizes = client.post(f"/api/projects/{pid}/layout/sizes", json={}).get_json()["sizes"]
    reqs = [{"stickerId": s["id"], "widthMm": sizes[s["id"]]["widthMm"] * 0.8, "heightMm": sizes[s["id"]]["heightMm"] * 0.8, "copies": 2} for s in stickers]
    sheet = reopened["sheets"][0]
    r = client.post(f"/api/projects/{pid}/layout/auto", json={"sheet": sheet, "requests": reqs, "mode": "pack"})
    assert r.status_code == 200, r.get_json()
    sheet["pages"] = r.get_json()["pages"]
    assert sum(len(p["items"]) for p in sheet["pages"]) == 8
    v = client.post(f"/api/projects/{pid}/layout/validate", json={"sheet": sheet}).get_json()
    assert not [w for w in v["warnings"] if w["code"] in ("overlap", "off-page", "outside-printable")]
    reopened["sheets"][0] = sheet
    save(client, pid, reopened)

    # --- exports
    def export(kind, **extra):
        job = wait_job(client, client.post(f"/api/projects/{pid}/exports", json={"kind": kind, "sheetId": sheet["id"], **extra}), timeout=180)
        assert job["status"] == "done", job
        res = job["result"]
        folder = client.application.extensions["oss"].settings.projects_dir / pid / "exports" / res["folder"]
        for f in res["files"]:
            assert (folder / f).is_file() and (folder / f).stat().st_size > 0
        return res, folder

    res, folder = export("stickers-png")
    png = next(f for f in res["files"] if f.endswith(".png"))
    im = Image.open(folder / png)
    assert im.mode == "RGBA" and round(im.info["dpi"][0]) == 300
    entry = next(i for i in res["info"]["items"] if i["png"] == png)
    assert im.width / 300 * MM == pytest.approx(entry["widthMm"], abs=0.01)
    with zipfile.ZipFile(folder / "stickers.zip") as z:
        assert len([n for n in z.namelist() if n.endswith(".png")]) == 4

    res, folder = export("sheet-png")
    page = Image.open(folder / res["files"][0])
    assert page.size == (2480, 3508) and round(page.info["dpi"][0]) == 300

    res, folder = export("sheet-pdf", cutLines=True)
    reader = PdfReader(str(folder / res["files"][0]))
    assert len(reader.pages) == len(sheet["pages"])
    box = reader.pages[0].mediabox
    assert float(box.width) == pytest.approx(595.276, abs=0.01) and float(box.height) == pytest.approx(841.89, abs=0.01)

    res, folder = export("sheet-svg")
    root = ET.parse(folder / res["files"][0]).getroot()
    assert root.get("width") == "210.000mm" and root.get("height") == "297.000mm"
    cut_group = next(g for g in root.iter() if g.get("id") == "cut-lines")
    assert len(list(cut_group)) == len(sheet["pages"][0]["items"])

    res, folder = export("cut-svg")
    text = (folder / res["files"][0]).read_text()
    assert "<image" not in text and "<path" in text

    res, folder = export("cricut-bundle")
    assert any(f.endswith("-cut.svg") for f in res["files"]) and any(f.endswith(".png") for f in res["files"])
    for f in res["files"]:
        if f.endswith(".svg"):
            ET.parse(folder / f)

    history = client.get(f"/api/projects/{pid}/exports").get_json()["exports"]
    assert len(history) == 6
    first = history[0]
    dl = client.get(f"/api/projects/{pid}/exports/{first['id']}/files/{first['files'][0]}")
    assert dl.status_code == 200 and dl.data


def test_exported_sticker_png_matches_physical_size(client, project, photo, cutout):
    pid = project["id"]
    stickers = make_stickers(client, project, photo, cutout)[:1]
    doc = client.get(f"/api/projects/{pid}").get_json()["document"]
    doc["stickers"] = stickers
    save(client, pid, doc)
    size = client.post(f"/api/projects/{pid}/layout/sizes", json={}).get_json()["sizes"][stickers[0]["id"]]
    for dpi in (150, 300):
        job = wait_job(client, client.post(f"/api/projects/{pid}/exports", json={"kind": "stickers-png", "dpi": dpi}), timeout=120)
        res = job["result"]
        folder = client.application.extensions["oss"].settings.projects_dir / pid / "exports" / res["folder"]
        im = Image.open(folder / next(f for f in res["files"] if f.endswith(".png")))
        assert im.width / dpi * MM == pytest.approx(size["widthMm"], abs=0.35)
        assert round(im.info["dpi"][0]) == dpi


def test_archive_roundtrip(client, project, photo, cutout):
    pid = project["id"]
    # include a user-imported asset in a sticker
    buf = io.BytesIO()
    Image.new("RGBA", (30, 30), (0, 200, 0, 255)).save(buf, "PNG")
    asset = client.post("/api/assets", data={"file": (io.BytesIO(buf.getvalue()), "leaf.png"), "category": "custom"},
                        content_type="multipart/form-data").get_json()["asset"]
    doc = client.get(f"/api/projects/{pid}").get_json()["document"]
    doc["stickers"] = make_stickers(client, project, photo, cutout)[:2]
    doc["stickers"][0]["layers"].append({"id": "ly_user", "type": "asset", "assetId": asset["id"], "x": 100, "y": 100, "width": 80, "height": 80})
    save(client, pid, doc)
    job = wait_job(client, client.post(f"/api/projects/{pid}/archive-file"))
    res = job["result"]
    path = client.application.extensions["oss"].settings.projects_dir / pid / "exports" / res["folder"] / res["files"][0]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        manifest = json.loads(z.read("manifest.json"))
    assert "project.json" in names and any(n.startswith("originals/") for n in names) and f"assets/{asset['id']}.png" in names
    for key in ("projectFormatVersion", "appVersion", "canvases", "pages", "assetReferences", "exportSettings", "userAssets"):
        assert key in manifest
    assert manifest["pages"][0]["widthPx"] == 2480
    assert manifest["canvases"][0]["widthMm"] == 50
    # delete the user asset, then import: it is restored from the archive
    client.delete(f"/api/assets/{asset['id']}")
    r = client.post("/api/projects/import", data={"file": (io.BytesIO(path.read_bytes()), "p.ossproj")}, content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    new = r.get_json()["document"]
    assert new["id"] != pid and len(new["stickers"]) == 2 and len(new["photos"]) == 1
    assert asset["id"] in {a["id"] for a in client.get("/api/assets").get_json()["assets"]}
    rr = client.post(f"/api/projects/{new['id']}/stickers/render", json={"sticker": new["stickers"][0], "maxSide": 200})
    assert rr.status_code == 200


def test_malicious_archive_entries_are_ignored(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("project.json", json.dumps({"formatVersion": 2, "name": "Evil", "photos": [], "stickers": [], "sheets": []}))
        z.writestr("manifest.json", json.dumps({"userAssets": []}))
        z.writestr("../../escape.txt", "x")
        z.writestr("originals/../../../escape2.txt", "x")
    r = client.post("/api/projects/import", data={"file": (io.BytesIO(buf.getvalue()), "e.ossproj")}, content_type="multipart/form-data")
    assert r.status_code == 201
    data_dir = client.application.extensions["oss"].settings.data_dir
    assert not list(data_dir.parent.rglob("escape*.txt"))


def test_photo_edits_and_adjustments(client, project, photo, cutout):
    pid = project["id"]
    r = client.post(f"/api/projects/{pid}/photos/{photo['id']}/adjusted", json={"adjustments": {"filter": "sepia"}, "maxSide": 200})
    assert r.status_code == 200 and max(Image.open(io.BytesIO(r.data)).size) == 200
    job = wait_job(client, client.post(f"/api/projects/{pid}/photos/{photo['id']}/edits", json={"edits": {"rotate": 90, "crop": {"x": 0, "y": 0, "w": 0.5, "h": 1}}}))
    p = job["result"]["photo"]
    assert job["result"]["maskCleared"] and p["mask"] is None
    assert (p["width"], p["height"]) == (photo["height"] // 2, photo["width"])


def test_import_reports_bad_files(client, project):
    r = client.post(f"/api/projects/{project['id']}/photos", data={"files": (io.BytesIO(b"not an image"), "x.jpg")}, content_type="multipart/form-data")
    assert r.status_code == 400 and "Unsupported" in r.get_json()["error"]["message"]


def test_heic_import_when_decoder_available(client, project):
    pillow_heif = pytest.importorskip("pillow_heif")
    from tests.fixtures.synthetic import figure_image

    buf = io.BytesIO()
    pillow_heif.from_pillow(figure_image((200, 250))).save(buf, quality=80)
    r = client.post(f"/api/projects/{project['id']}/photos", data={"files": (io.BytesIO(buf.getvalue()), "phone.heic")}, content_type="multipart/form-data")
    job = wait_job(client, r)
    assert job["status"] == "done" and job["result"]["photos"][0]["format"] == "HEIF"
