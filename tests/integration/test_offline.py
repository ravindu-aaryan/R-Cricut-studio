"""Run the core workflow with every non-loopback network connection blocked.

The socket guard replaces ``socket.connect`` and DNS resolution for the
duration of the test, so any attempt to reach the internet (for example a
model download or a telemetry call) fails loudly instead of silently
succeeding. ``scripts/verify_offline.py`` additionally runs the browser
workflow inside a network namespace with no network device at all.
"""
import socket

import pytest

from tests.integration.test_workflow import test_full_workflow as workflow

ATTEMPTS = []


@pytest.fixture()
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and (host.startswith("127.") or host in ("localhost", "::1") or self.family == socket.AF_UNIX):
            return real_connect(self, address)
        ATTEMPTS.append(address)
        raise OSError(f"network access blocked during offline test: {address}")

    def guarded_getaddrinfo(host, *a, **k):
        if host in ("localhost", "127.0.0.1", "::1", None):
            return real_getaddrinfo(host, *a, **k)
        ATTEMPTS.append(host)
        raise socket.gaierror(f"DNS blocked during offline test: {host}")

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    ATTEMPTS.clear()
    yield ATTEMPTS


def test_guard_blocks_internet(no_network):
    with pytest.raises(OSError):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
    assert no_network


def test_core_workflow_works_offline(no_network, client, project, photo, cutout):
    workflow(client, project, photo, cutout)
    assert no_network == [], f"unexpected network attempts: {no_network}"


def test_status_reports_offline(no_network, client):
    s = client.get("/api/status").get_json()
    assert s["offline"]["networkRequestsMade"] is False and s["offline"]["telemetry"] is False
    assert s["gpuRequired"] is False and not s["missingResources"]
