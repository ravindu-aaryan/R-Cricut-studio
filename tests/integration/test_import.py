"""HTTP flow for bulk sticker import and templates."""
import io
import zipfile

from PIL import Image, ImageDraw

from tests.conftest import wait_job


def png(color=(0, 150, 0, 255), size=(160, 120), bg=(0, 0, 0, 0)):
    im = Image.new("RGBA", size, bg)
    ImageDraw.Draw(im).ellipse((20, 20, size[0] - 20, size[1] - 20), fill=color)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_bulk_sticker_import_from_files_and_zip(client, project):
    pid = project["id"]
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr("a.png", png((255, 0, 0, 255)))
        z.writestr("sub/b.png", png((0, 0, 255, 255)))
    data = {"files": [
        (io.BytesIO(png()), "green.png"),
        (io.BytesIO(png((255, 255, 255, 255), bg=(255, 255, 255, 255))), "onwhite.png"),
        (io.BytesIO(zb.getvalue()), "pack.zip"),
    ], "sizeMm": "50", "borderMm": "3", "removeWhite": "1"}
    job = wait_job(client, client.post(f"/api/projects/{pid}/stickers/import", data=data, content_type="multipart/form-data"), 120)
    assert job["status"] == "done", job
    assert job["result"]["imported"] == 4 and job["result"]["failed"] == 0
    doc = client.get(f"/api/projects/{pid}").get_json()["document"]
    assert len(doc["stickers"]) == 4
    # Each imported sticker renders.
    r = client.post(f"/api/projects/{pid}/stickers/render", json={"sticker": doc["stickers"][0], "maxSide": 200})
    assert r.status_code == 200 and r.mimetype == "image/png"


def test_bulk_import_rejects_bad_file(client, project):
    pid = project["id"]
    job = wait_job(client, client.post(f"/api/projects/{pid}/stickers/import",
                   data={"files": [(io.BytesIO(b"not an image"), "x.png")]}, content_type="multipart/form-data"))
    assert job["status"] == "done"
    assert job["result"]["imported"] == 0 and job["result"]["failed"] == 1


def test_bulk_asset_import(client):
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr("d1.png", png())
        z.writestr("d2.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>')
    before = len(client.get("/api/assets").get_json()["assets"])
    job = wait_job(client, client.post("/api/assets/import-bulk", data={"files": [(io.BytesIO(zb.getvalue()), "pack.zip")], "category": "custom"},
                   content_type="multipart/form-data"))
    assert job["status"] == "done" and job["result"]["imported"] == 2
    assert len(client.get("/api/assets").get_json()["assets"]) == before + 2


def test_templates_crud_and_from_template(client, project, photo, cutout):
    pid = project["id"]
    # make a sticker with a photo, then save as template
    res = client.post(f"/api/projects/{pid}/stickers/new", json={"photoId": photo["id"]})
    sticker = res.get_json()["sticker"]
    t = client.post("/api/templates", json={"sticker": sticker, "name": "Photo frame", "themeId": "birthday"})
    assert t.status_code == 201
    tpl = t.get_json()["template"]
    assert tpl["hasPhotoSlot"] is True
    assert [x["id"] for x in client.get("/api/templates").get_json()["templates"]] == [tpl["id"]]
    # instantiate with the photo
    made = client.post(f"/api/projects/{pid}/stickers/from-template", json={"templateId": tpl["id"], "photoId": photo["id"], "name": "From tpl"})
    assert made.status_code == 200
    doc = made.get_json()["sticker"]
    assert doc["name"] == "From tpl"
    assert any(l["type"] == "image" and l["photoId"] == photo["id"] for l in doc["layers"])
    # render it
    assert client.post(f"/api/projects/{pid}/stickers/render", json={"sticker": doc, "maxSide": 200}).status_code == 200
    # export + import bundle
    ex = client.get("/api/templates/export")
    assert ex.status_code == 200 and ex.data[:4] == b"PK\x03\x04"
    im = client.post("/api/templates/import", data={"file": (io.BytesIO(ex.data), "t.zip")}, content_type="multipart/form-data")
    assert im.status_code == 201 and im.get_json()["imported"] == 1
    assert len(client.get("/api/templates").get_json()["templates"]) == 2
    # delete
    client.delete(f"/api/templates/{tpl['id']}")
    assert tpl["id"] not in [x["id"] for x in client.get("/api/templates").get_json()["templates"]]


def test_from_template_bad_id(client, project):
    r = client.post(f"/api/projects/{project['id']}/stickers/from-template", json={"templateId": "../etc"})
    assert r.status_code == 400
