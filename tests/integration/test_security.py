import io

import pytest


def test_csrf_required_for_state_changes(raw_client):
    r = raw_client.post("/api/projects", json={"name": "x"})
    assert r.status_code == 403
    r = raw_client.post("/api/projects", json={"name": "x"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    assert raw_client.get("/api/projects").status_code == 200


def test_foreign_host_and_origin_rejected(client):
    assert client.get("/api/projects", headers={"Host": "evil.example"}).status_code == 400
    r = client.post("/api/projects", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/projects", json={"name": "x"}, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 201


def test_security_headers(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert b'name="csrf-token"' in r.data


def test_no_remote_resources_in_page(client):
    html = client.get("/").data.decode()
    assert "http://" not in html and "https://" not in html


def test_path_traversal_rejected(client, project):
    pid = project["id"]
    for url in (f"/api/projects/..%2F..%2Fetc/thumbnail", f"/api/projects/{pid}/photos/..%2Fx/image",
                f"/api/projects/{pid}/exports/..%2F..%2F/files/x", "/fonts/..%2F..%2Fetc%2Fpasswd"):
        r = client.get(url)
        assert r.status_code in (400, 404), url
    r = client.get(f"/api/projects/{pid}/exports/abc/files/../../project.json")
    assert r.status_code in (400, 404)


def test_unknown_export_file_not_served(client, project):
    pid = project["id"]
    client.application.extensions["oss"].repo.add_export("ex_1", pid, "x", "folder1", ["a.png"], {})
    assert client.get(f"/api/projects/{pid}/exports/ex_1/files/project.json").status_code == 404


def test_svg_responses_are_sandboxed(client):
    r = client.get("/api/assets/star_basic/svg")
    assert r.status_code == 200 and "sandbox" in r.headers["Content-Security-Policy"]


def test_errors_do_not_leak_tracebacks(client, monkeypatch):
    from app.routes import themes

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(themes, "services", boom)
    r = client.get("/api/themes")
    assert r.status_code == 500
    assert "secret" not in r.get_data(as_text=True) and "Traceback" not in r.get_data(as_text=True)


def test_delete_requires_confirmation(client, project):
    pid = project["id"]
    assert client.delete(f"/api/projects/{pid}", json={"confirmName": "nope"}).status_code == 400
    assert client.delete(f"/api/projects/{pid}", json={"confirmName": "Test project"}).status_code == 200


def test_delete_all_local_data(client, project):
    assert client.post("/api/system/delete-all-data", json={"confirm": "yes"}).status_code == 400
    assert client.post("/api/system/delete-all-data", json={"confirm": "DELETE"}).status_code == 200
    assert client.get("/api/projects").get_json()["projects"] == []


def test_debugger_disabled_by_default(app):
    assert app.debug is False


def test_default_binding_is_localhost(app):
    assert app.extensions["oss"].settings.host == "127.0.0.1"


def test_uploaded_svg_asset_sanitized(client):
    evil = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script><circle r="3"/></svg>'
    r = client.post("/api/assets", data={"file": (io.BytesIO(evil), "evil.svg")}, content_type="multipart/form-data")
    assert r.status_code == 201
    aid = r.get_json()["asset"]["id"]
    body = client.get(f"/api/assets/{aid}/svg").get_data(as_text=True)
    assert "script" not in body and "onload" not in body


@pytest.mark.parametrize("bad", ["../x", "a b", "x" * 80])
def test_bad_ids(client, bad):
    assert client.get(f"/api/jobs/{bad}").status_code in (400, 404)


def test_quit_disabled_outside_desktop_launcher(client):
    assert client.post("/api/system/quit").status_code == 400


def test_asset_png_and_svg_endpoints(client):
    import json as _json
    from urllib.parse import quote

    from PIL import Image

    colors = quote(_json.dumps({"primary": "#00ff00"}))
    r = client.get("/api/assets/crown_gold/png?w=64&colors=" + colors)
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.data))
    assert img.size[0] == 64 and img.mode == "RGBA"
    svg = client.get("/api/assets/crown_gold/svg?colors=" + colors).get_data(as_text=True)
    assert "#00ff00" in svg
    assert client.get("/api/patterns/dots.svg?color=%23ff0000").status_code == 200
    assert client.get("/fonts.css").status_code == 200
