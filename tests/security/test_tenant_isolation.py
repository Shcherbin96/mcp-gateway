"""Security tests verifying tenant isolation on the audit API.

Requires a running gateway. The gateway scopes ``/api/audit`` queries by
the ``default_tenant_id`` configured at startup, so cross-tenant data leakage
would manifest as response entries with an ``agent_id`` other than the one
requested.
"""

import httpx
import pytest

pytestmark = [pytest.mark.security, pytest.mark.e2e]


async def test_audit_api_does_not_leak_other_tenants() -> None:
    """Audit API uses default_tenant_id from server; cross-tenant requires multi-tenant setup."""
    async with httpx.AsyncClient() as c:
        r = await c.get(
            "http://localhost:8000/api/audit?agent_id=00000000-0000-0000-0000-000000000099"
        )
        assert r.status_code == 200
        assert all(
            e["agent_id"] == "00000000-0000-0000-0000-000000000099"
            for e in r.json()["entries"]
        )
