"""Integration test: /approvals/{id}/decide accepts a ``reason`` form field
and persists it to ``approval_requests.decision_reason``.
"""

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.approval.store import ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.audit.reader import AuditReader
from gateway.db.models import Agent, Role, Tenant
from gateway.web.routes import make_router

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_decide_endpoint_accepts_form_reason(db_engine, monkeypatch):
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}")
        s.add(t)
        await s.flush()
        r = Role(tenant_id=t.id, name="support")
        s.add(r)
        await s.flush()
        a = Agent(tenant_id=t.id, name="a1", role_id=r.id)
        s.add(a)
        await s.commit()
        tid, aid = t.id, a.id

    store = ApprovalStore(sf)
    approval_id = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    app = FastAPI()
    templates = Jinja2Templates(directory="gateway/web/templates")
    app.include_router(
        make_router(
            templates=templates,
            audit_reader=AuditReader(sf),
            approval_store=store,
            broadcaster=WebSocketBroadcaster(),
            session_factory=sf,
            default_tenant_id=tid,
        )
    )

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                f"/approvals/{approval_id}/decide?decision=rejected",
                data={"reason": "too risky for tier-3 customer"},
                headers={"Authorization": "Bearer test-secret"},
            )
            assert resp.status_code == 200

        req = await store.get(approval_id)
        assert req is not None
        assert req.status == "rejected"
        assert req.decision_reason == "too risky for tier-3 customer"
        assert req.decided_by == "web-admin"  # default web_admin_user
    finally:
        get_settings.cache_clear()


async def test_decide_endpoint_query_reason_fallback(db_engine, monkeypatch):
    """Reason supplied via query param (no form body) still persists."""
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}")
        s.add(t)
        await s.flush()
        r = Role(tenant_id=t.id, name="support")
        s.add(r)
        await s.flush()
        a = Agent(tenant_id=t.id, name="a1", role_id=r.id)
        s.add(a)
        await s.commit()
        tid, aid = t.id, a.id

    store = ApprovalStore(sf)
    approval_id = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    app = FastAPI()
    templates = Jinja2Templates(directory="gateway/web/templates")
    app.include_router(
        make_router(
            templates=templates,
            audit_reader=AuditReader(sf),
            approval_store=store,
            broadcaster=WebSocketBroadcaster(),
            session_factory=sf,
            default_tenant_id=tid,
        )
    )

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                f"/approvals/{approval_id}/decide?decision=approved&reason=looks+good",
                headers={"Authorization": "Bearer test-secret"},
            )
            assert resp.status_code == 200

        req = await store.get(approval_id)
        assert req is not None
        assert req.status == "approved"
        assert req.decision_reason == "looks good"
    finally:
        get_settings.cache_clear()
