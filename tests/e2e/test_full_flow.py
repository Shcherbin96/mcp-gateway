"""E2E tests against the full docker-compose stack."""

import asyncio
import os
import re
import subprocess

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = os.environ.get("E2E_GATEWAY_URL", "http://localhost:8000")
IDP = os.environ.get("E2E_IDP_URL", "http://localhost:9000")
ADMIN_TOKEN = os.environ.get("E2E_ADMIN_TOKEN", "e2e-admin-token")
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
TIMEOUT = httpx.Timeout(30.0)


@pytest.fixture(scope="session")
def seeded_creds() -> tuple[str, str]:
    """Extract the demo OAuth client credentials from gateway container logs."""
    explicit_id = os.environ.get("E2E_CLIENT_ID")
    explicit_secret = os.environ.get("E2E_CLIENT_SECRET")
    if explicit_id and explicit_secret:
        return explicit_id, explicit_secret
    try:
        out = subprocess.check_output(
            ["docker", "compose", "-f", "docker-compose.test.yml", "logs", "gateway"],
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            text=True,
            timeout=10,
        )
    except Exception as e:
        pytest.skip(f"cannot read docker logs: {e}")
    cid_match = re.search(r"OAuth client_id:\s*(\S+)", out)
    sec_match = re.search(r"OAuth client_secret:\s*(\S+)", out)
    if not cid_match or not sec_match:
        pytest.skip("seed credentials not found in gateway logs")
    return cid_match.group(1), sec_match.group(1)


async def _exchange_token(client: httpx.AsyncClient, client_id: str, secret: str) -> str:
    tok = await client.post(
        f"{IDP}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        },
    )
    tok.raise_for_status()
    return tok.json()["access_token"]


async def test_get_customer_unauthorized():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{GATEWAY}/mcp/call/get_customer",
            json={"customer_id": "C001"},
        )
        assert r.status_code == 401


async def test_refund_requires_approval_then_rejected(seeded_creds):
    """E2E: call refund_payment, find approval via /api/approvals/pending, reject, expect 403."""
    client_id, secret = seeded_creds
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        token = await _exchange_token(c, client_id, secret)

        async def call_refund():
            return await c.post(
                f"{GATEWAY}/mcp/call/refund_payment",
                json={"customer_id": "C001", "amount": 50000},
                headers={"Authorization": f"Bearer {token}"},
            )

        async def reject_after_delay():
            await asyncio.sleep(2)
            async with httpx.AsyncClient(timeout=TIMEOUT) as c2:
                lst = await c2.get(f"{GATEWAY}/api/approvals/pending", headers=ADMIN_HEADERS)
                lst.raise_for_status()
                pending = lst.json()["approvals"]
                assert pending, "expected at least one pending approval"
                approval_id = pending[0]["id"]
                d = await c2.post(
                    f"{GATEWAY}/approvals/{approval_id}/decide?decision=rejected",
                    headers=ADMIN_HEADERS,
                )
                d.raise_for_status()

        result, _ = await asyncio.gather(call_refund(), reject_after_delay())
        assert result.status_code == 403
