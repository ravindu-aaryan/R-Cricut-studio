"""Shared fixtures. Tests use synthetic images only, never real photographs."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fixtures.synthetic import figure_image, jpeg_bytes  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    from app import create_app

    application = create_app({"data_dir": str(tmp_path / "data"), "testing": True})
    yield application
    application.extensions["oss"].jobs.shutdown()


@pytest.fixture()
def client(app):
    c = app.test_client()
    token = app.extensions["oss"].csrf_token
    c.environ_base["HTTP_X_CSRF_TOKEN"] = token
    return c


@pytest.fixture()
def raw_client(app):
    """A client that does not send the CSRF header."""
    return app.test_client()


def wait_job(client, resp, timeout=60):
    assert resp.status_code == 202, resp.get_json()
    job = resp.get_json()["job"]
    deadline = time.time() + timeout
    while job["status"] in ("queued", "running"):
        assert time.time() < deadline, "job timed out"
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").get_json()["job"]
    return job


@pytest.fixture()
def project(client):
    r = client.post("/api/projects", json={"name": "Test project", "themeId": "birthday"})
    assert r.status_code == 201
    return r.get_json()["document"]


@pytest.fixture()
def photo(client, project):
    data = jpeg_bytes(figure_image())
    r = client.post(f"/api/projects/{project['id']}/photos", data={"files": (io.BytesIO(data), "figure.jpg")},
                    content_type="multipart/form-data")
    job = wait_job(client, r)
    assert job["status"] == "done", job
    return job["result"]["photos"][0]


@pytest.fixture()
def cutout(client, project, photo):
    pw, ph = photo["previewWidth"], photo["previewHeight"]
    r = client.post(f"/api/projects/{project['id']}/photos/{photo['id']}/segment",
                    json={"method": "grabcut", "rect": {"x": pw * 0.06, "y": ph * 0.06, "w": pw * 0.88, "h": ph * 0.94}})
    job = wait_job(client, r)
    assert job["status"] == "done", job
    return job["result"]["photo"]
