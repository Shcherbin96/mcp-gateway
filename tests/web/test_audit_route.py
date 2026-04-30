"""Integration test: audit row HTML renders entries from the DB."""

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.approval.store import ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.audit.reader import AuditReader
from gateway.audit.writer import AuditWriter
from gateway.db.models import Tenant
from gateway.web.routes import make_router

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_audit_html_renders(db_engine, monkeypatch):
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}")
        s.add(t)
        await s.commit()
        tid = t.id
    await AuditWriter(sf).write(
        tenant_id=tid,
        agent_id=None,
        tool="get_customer",
        params={"customer_id": "C1"},
        result_status="success",
    )

    app = FastAPI()
    templates = Jinja2Templates(directory="gateway/web/templates")
    app.include_router(
        make_router(
            templates=templates,
            audit_reader=AuditReader(sf),
            approval_store=ApprovalStore(sf),
            broadcaster=WebSocketBroadcaster(),
            session_factory=sf,
            default_tenant_id=tid,
        )
    )

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(
                "/audit/rows", headers={"Authorization": "Bearer test-secret"}
            )
            assert r.status_code == 200
            assert "get_customer" in r.text
    finally:
        get_settings.cache_clear()
