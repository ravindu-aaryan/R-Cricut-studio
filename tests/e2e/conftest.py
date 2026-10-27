"""Start the real application server (waitress via app.py) for browser tests."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e-data")
    port = _free_port()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--no-browser", "--port", str(port), "--data-dir", str(data)],
                            cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=1) as r:
                if r.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start:\n" + (proc.stdout.read() if proc.stdout else ""))
    yield {"base": base, "data": data}
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def page(server):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment without a browser
            pytest.skip(f"Chromium not available: {exc}")
        context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        external, errors = [], []

        def route(r):
            url = r.request.url
            if url.startswith(server["base"]) or url.startswith(("data:", "blob:")):
                r.continue_()
            else:
                external.append(url)
                r.abort()

        context.route("**/*", route)
        pg = context.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.external_requests = external  # type: ignore[attr-defined]
        pg.js_errors = errors  # type: ignore[attr-defined]
        pg.base = server["base"]  # type: ignore[attr-defined]
        yield pg
        context.close()
        browser.close()
