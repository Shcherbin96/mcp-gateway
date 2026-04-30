"""Unit tests for mock OAuth IdP service."""

import pytest
from fastapi.testclient import TestClient

from mocks.idp.main import app

pytestmark = pytest.mark.unit


def test_metadata_endpoint():
    client = TestClient(app)
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    assert r.json()["registration_endpoint"].endswith("/register")


def test_jwks_returns_key():
    client = TestClient(app)
    r = client.get("/jwks")
    keys = r.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["alg"] == "RS256"


def test_register_then_token():
    client = TestClient(app)
    reg = client.post(
        "/register",
        json={"client_name": "test", "tenant_id": "t1", "scopes": ["tool:get_customer"]},
    ).json()
    tok = client.post(
        "/token",
        data={
            "grant_type": "client_credentials",
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
        },
    )
    assert tok.status_code == 200
    assert tok.json()["token_type"] == "Bearer"
