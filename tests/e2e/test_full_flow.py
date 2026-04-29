"""E2E tests against the full docker-compose stack."""

import asyncio
import os

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = os.environ.get("E2E_GATEWAY_URL", "http://localhost:8000")
IDP = os.environ.get("E2E_IDP_URL", "http://localhost:9000")
TIMEOUT = httpx.Timeout(30.0)


async def _get_token(client: httpx.AsyncClient, scopes: list[str]) -> str:
    reg = await client.post(
        f"{IDP}/register",
        json={
            "client_name": "e2e",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "scopes": scopes,
        },
    )
    reg.raise_for_status()
    creds = reg.json()
    tok = await client.post(
        f"{IDP}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
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


async def test_refund_requires_approval_then_rejected():
    """E2E: call refund_payment, find approval via /api/approvals/pending, reject, expect 403."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        token = await _get_token(c, ["tool:refund_payment"])

        async def call_refund():
            return await c.post(
                f"{GATEWAY}/mcp/call/refund_payment",
                json={"customer_id": "C001", "amount": 50000},
                headers={"Authorization": f"Bearer {token}"},
            )

        async def reject_after_delay():
            await asyncio.sleep(2)
            async with httpx.AsyncClient(timeout=TIMEOUT) as c2:
                lst = await c2.get(f"{GATEWAY}/api/approvals/pending")
                lst.raise_for_status()
                pending = lst.json()["approvals"]
                assert pending, "expected at least one pending approval"
                approval_id = pending[0]["id"]
                d = await c2.post(
                    f"{GATEWAY}/approvals/{approval_id}/decide"
                    f"?decision=rejected&decided_by=e2e"
                )
                d.raise_for_status()

        result, _ = await asyncio.gather(call_refund(), reject_after_delay())
        assert result.status_code == 403
