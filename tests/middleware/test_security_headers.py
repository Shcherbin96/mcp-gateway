"""Verify security headers are present on every response."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.middleware.security_headers import install

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get("/x")
    def _x() -> dict:
        return {"ok": True}

    install(app)
    return TestClient(app)


def test_basic_security_headers_present(client: TestClient) -> None:
    r = client.get("/x")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in r.headers["permissions-policy"]
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"


def test_csp_locks_down_object_and_frame_ancestors(client: TestClient) -> None:
    r = client.get("/x")
    csp = r.headers["content-security-policy"]
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


def test_hsts_only_on_https(client: TestClient) -> None:
    # TestClient defaults to http://; HSTS must NOT be set on http traffic
    # to avoid breaking local dev with http://localhost.
    r = client.get("/x")
    assert "strict-transport-security" not in r.headers
