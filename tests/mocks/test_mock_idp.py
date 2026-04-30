"""Unit tests for mock OAuth IdP service."""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from mocks.idp.main import DEFAULT_AUDIENCE, ISSUER, PUBLIC_PEM, app

pytestmark = pytest.mark.unit


def test_metadata_endpoint():
    client = TestClient(app)
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["registration_endpoint"].endswith("/register")
    assert "authorization_code" in body["grant_types_supported"]
    assert body["code_challenge_methods_supported"] == ["S256"]


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


# --- authorization_code + PKCE ---------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _register(client: TestClient, redirect_uris: list[str]) -> dict:
    return client.post(
        "/register",
        json={
            "client_name": "auth-code-test",
            "tenant_id": "ignored-for-auth-code",
            "scopes": ["tool:get_customer"],
            "redirect_uris": redirect_uris,
        },
    ).json()


def test_authorize_get_renders_login_form():
    client = TestClient(app)
    redirect_uri = "https://app.example.com/callback"
    reg = _register(client, [redirect_uri])
    _, challenge = _pkce_pair()

    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "tool:get_customer",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "<form" in body
    assert 'name="username"' in body
    assert 'name="password"' in body
    # Hidden OAuth params round-trip
    assert challenge in body
    assert "xyz" in body


def test_authorize_get_rejects_missing_pkce():
    client = TestClient(app)
    redirect_uri = "https://app.example.com/callback"
    reg = _register(client, [redirect_uri])

    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "tool:get_customer",
            "state": "xyz",
        },
    )
    assert r.status_code == 400


def test_authorize_full_flow():
    redirect_uri = "https://app.example.com/callback"
    verifier, challenge = _pkce_pair()
    with TestClient(app, follow_redirects=False) as client:
        reg = _register(client, [redirect_uri])

        post = client.post(
            "/authorize",
            data={
                "response_type": "code",
                "client_id": reg["client_id"],
                "redirect_uri": redirect_uri,
                "scope": "tool:get_customer",
                "state": "state-123",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "username": "alice",
                "password": "wonderland",
            },
        )
        assert post.status_code == 302, post.text
        location = post.headers["location"]
        parsed = urlparse(location)
        assert parsed.path == "/callback"
        qs = parse_qs(parsed.query)
        assert "code" in qs
        assert qs["state"] == ["state-123"]
        code = qs["code"][0]

        tok = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": reg["client_id"],
                "client_secret": reg["client_secret"],
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        body = tok.json()
        decoded = jwt.decode(
            body["access_token"],
            PUBLIC_PEM,
            algorithms=["RS256"],
            audience=DEFAULT_AUDIENCE,
            issuer=ISSUER,
        )
        assert decoded["sub"] == "alice"
        assert decoded["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert "role:support_agent" in decoded["scopes"]
        assert "tool:get_customer" in decoded["scopes"]


def test_token_authorization_code_pkce_mismatch():
    redirect_uri = "https://app.example.com/callback"
    _, challenge = _pkce_pair()
    with TestClient(app, follow_redirects=False) as client:
        reg = _register(client, [redirect_uri])

        post = client.post(
            "/authorize",
            data={
                "response_type": "code",
                "client_id": reg["client_id"],
                "redirect_uri": redirect_uri,
                "scope": "tool:get_customer",
                "state": "s",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "username": "bob",
                "password": "thebuilder",
            },
        )
        assert post.status_code == 302
        code = parse_qs(urlparse(post.headers["location"]).query)["code"][0]

        tok = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": reg["client_id"],
                "client_secret": reg["client_secret"],
                "code_verifier": "totally-wrong-verifier-value-here",
            },
        )
        assert tok.status_code == 400
        assert "PKCE" in tok.text or "pkce" in tok.text.lower()
