"""Integration test: tenant selector lets admins scope queries per request."""

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


def _build_app(sf, default_tid):
    app = FastAPI()
    templates = Jinja2Templates(directory="gateway/web/templates")
    app.include_router(
        make_router(
            templates=templates,
            audit_reader=AuditReader(sf),
            approval_store=ApprovalStore(sf),
            broadcaster=WebSocketBroadcaster(),
            session_factory=sf,
            default_tenant_id=default_tid,
        )
    )
    return app


async def test_tenant_selector_scopes_audit_per_request(db_engine, monkeypatch):
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        ta = Tenant(name=f"alpha-{uuid4()}")
        tb = Tenant(name=f"bravo-{uuid4()}")
        s.add_all([ta, tb])
        await s.commit()
        tid_a, tid_b = ta.id, tb.id

    writer = AuditWriter(sf)
    await writer.write(
        tenant_id=tid_a,
        agent_id=None,
        tool="get_customer",
        params={"customer_id": "A1"},
        result_status="success",
    )
    await writer.write(
        tenant_id=tid_b,
        agent_id=None,
        tool="get_invoice",
        params={"invoice_id": "B1"},
        result_status="success",
    )

    app = _build_app(sf, tid_a)
    auth = {"Authorization": "Bearer test-secret"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # Tenant A — sees only A's entry
            r = await c.get(f"/api/audit?tenant_id={tid_a}", headers=auth)
            assert r.status_code == 200
            tools_a = {e["tool"] for e in r.json()["entries"]}
            assert tools_a == {"get_customer"}

            # Tenant B — sees only B's entry
            r = await c.get(f"/api/audit?tenant_id={tid_b}", headers=auth)
            assert r.status_code == 200
            tools_b = {e["tool"] for e in r.json()["entries"]}
            assert tools_b == {"get_invoice"}

            # Random UUID — 404, never leaks default tenant data
            bogus = uuid4()
            r = await c.get(f"/api/audit?tenant_id={bogus}", headers=auth)
            assert r.status_code == 404

            # Malformed UUID — also 404 (explicit caller intent)
            r = await c.get("/api/audit?tenant_id=not-a-uuid", headers=auth)
            assert r.status_code == 404

            # No tenant_id — falls back to default (tenant A)
            r = await c.get("/api/audit", headers=auth)
            assert r.status_code == 200
            assert {e["tool"] for e in r.json()["entries"]} == {"get_customer"}

            # Cookie-based selection works without query param
            c.cookies.set("tenant_id", str(tid_b))
            r = await c.get("/api/audit", headers=auth)
            assert r.status_code == 200
            assert {e["tool"] for e in r.json()["entries"]} == {"get_invoice"}

            # Bogus cookie falls back to default (security: silent fallback OK,
            # since cookie is set by us; we never trust user input over it)
            c.cookies.set("tenant_id", str(uuid4()))
            r = await c.get("/api/audit", headers=auth)
            assert r.status_code == 200
            assert {e["tool"] for e in r.json()["entries"]} == {"get_customer"}
            c.cookies.clear()
    finally:
        get_settings.cache_clear()


async def test_list_tenants_endpoint(db_engine, monkeypatch):
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        ta = Tenant(name=f"zeta-{uuid4()}")
        tb = Tenant(name=f"alpha-{uuid4()}")
        s.add_all([ta, tb])
        await s.commit()

    app = _build_app(sf, ta.id)
    auth = {"Authorization": "Bearer test-secret"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # Unauthorized
            r = await c.get("/api/tenants")
            assert r.status_code == 401

            # Authorized — names sorted
            r = await c.get("/api/tenants", headers=auth)
            assert r.status_code == 200
            names = [t["name"] for t in r.json()["tenants"]]
            assert names == sorted(names)
    finally:
        get_settings.cache_clear()


async def test_select_tenant_sets_cookie(db_engine, monkeypatch):
    monkeypatch.setenv("MCP_WEB_ADMIN_TOKEN", "test-secret")
    from gateway.config import get_settings

    get_settings.cache_clear()

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"select-{uuid4()}")
        s.add(t)
        await s.commit()
        tid = t.id

    app = _build_app(sf, tid)
    auth = {"Authorization": "Bearer test-secret"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # Bogus tenant -> 404
            r = await c.post(
                "/api/tenants/select",
                json={"tenant_id": str(uuid4())},
                headers=auth,
            )
            assert r.status_code == 404

            # Malformed -> 404
            r = await c.post(
                "/api/tenants/select",
                json={"tenant_id": "nope"},
                headers=auth,
            )
            assert r.status_code == 404

            # Valid tenant -> 204 + cookie
            r = await c.post(
                "/api/tenants/select",
                json={"tenant_id": str(tid)},
                headers=auth,
            )
            assert r.status_code == 204
            assert "tenant_id" in r.cookies or any(ck.name == "tenant_id" for ck in c.cookies.jar)
    finally:
        get_settings.cache_clear()
