"""Security tests for JWT validation attacks against the gateway.

These tests require a running gateway instance at GATEWAY (default
http://localhost:8000) and are therefore tagged as e2e in addition to
security. They will only execute in CI where the full stack is brought up
via docker compose.
"""

import base64
import json

import httpx
import pytest

pytestmark = [pytest.mark.security, pytest.mark.e2e]

GATEWAY = "http://localhost:8000"


async def test_unsigned_jwt_rejected() -> None:
    """A token using ``alg=none`` must be rejected with HTTP 401."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "x",
                    "tenant_id": "x",
                    "scopes": [],
                    "exp": 9999999999,
                    "aud": "mcp-gateway",
                    "iss": "http://mock-idp:9000",
                }
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    tok = f"{header}.{payload}."

    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{GATEWAY}/mcp/call/get_customer",
            json={"customer_id": "C001"},
            headers={"Authorization": f"Bearer {tok}"},
        )

    assert r.status_code == 401
