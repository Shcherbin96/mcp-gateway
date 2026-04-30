"""Web UI router — audit log + approvals dashboard (HTMX + JSON API + WS)."""

from collections.abc import Awaitable, Callable
from uuid import UUID

TenantResolver = UUID | Callable[[], Awaitable[UUID | None]]

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from gateway.approval.store import PENDING, ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.audit.reader import AuditFilter, AuditReader
from gateway.config import get_settings
from gateway.db.models import ApprovalRequest


def _require_admin(authorization: str | None = Header(default=None)) -> str:
    """Bearer-token auth for admin endpoints. Returns the admin user identity."""
    settings = get_settings()
    if settings.web_admin_token is None:
        raise HTTPException(status_code=503, detail="admin auth not configured")
    if authorization != f"Bearer {settings.web_admin_token}":
        raise HTTPException(status_code=401, detail="unauthorized")
    return settings.web_admin_user


def make_router(
    *,
    templates: Jinja2Templates,
    audit_reader: AuditReader,
    approval_store: ApprovalStore,
    broadcaster: WebSocketBroadcaster,
    session_factory,
    default_tenant_id: TenantResolver,  # MVP: single tenant. Pass UUID or async callable.
) -> APIRouter:
    r = APIRouter()
    settings = get_settings()

    async def _tenant_id() -> UUID:
        if callable(default_tenant_id):
            tid = await default_tenant_id()
            if tid is None:
                raise HTTPException(status_code=503, detail="no tenant seeded yet")
            return tid
        return default_tenant_id

    @r.get("/audit", response_class=HTMLResponse)
    async def audit_page(request: Request):
        return templates.TemplateResponse(request, "audit.html", {})

    @r.get("/audit/rows", response_class=HTMLResponse)
    async def audit_rows(
        request: Request,
        agent_id: str | None = None,
        tool: str | None = None,
        result_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        _admin: str = Depends(_require_admin),
    ):
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        f = AuditFilter(
            tenant_id=await _tenant_id(),
            agent_id=UUID(agent_id) if agent_id else None,
            tool=tool or None,
            result_status=result_status or None,
        )
        page = await audit_reader.query(f, limit=limit, offset=offset)
        return templates.TemplateResponse(
            request,
            "_audit_rows.html",
            {"entries": page.entries, "total": page.total},
        )

    @r.get("/api/audit")
    async def audit_api(
        agent_id: str | None = None,
        tool: str | None = None,
        result_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        _admin: str = Depends(_require_admin),
    ):
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        f = AuditFilter(
            tenant_id=await _tenant_id(),
            agent_id=UUID(agent_id) if agent_id else None,
            tool=tool or None,
            result_status=result_status or None,
        )
        page = await audit_reader.query(f, limit=limit, offset=offset)
        return {
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "entries": [
                {
                    "id": e.id,
                    "tenant_id": str(e.tenant_id) if e.tenant_id else None,
                    "agent_id": str(e.agent_id) if e.agent_id else None,
                    "tool": e.tool,
                    "params": e.params_json,
                    "result_status": e.result_status,
                    "result": e.result_json,
                    "approval_id": str(e.approval_id) if e.approval_id else None,
                    "trace_id": e.trace_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in page.entries
            ],
        }

    @r.get("/approvals", response_class=HTMLResponse)
    async def approvals_page(request: Request):
        return templates.TemplateResponse(request, "approvals.html", {})

    @r.get("/approvals/list", response_class=HTMLResponse)
    async def approvals_list(
        request: Request,
        admin: str = Depends(_require_admin),
    ):
        async with session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.tenant_id == default_tenant_id,
                    ApprovalRequest.status == PENDING,
                )
                .order_by(ApprovalRequest.created_at.desc())
            )
            approvals = res.scalars().all()
        return templates.TemplateResponse(
            request,
            "_approvals_list.html",
            {"approvals": approvals, "user": admin},
        )

    @r.get("/api/approvals/pending")
    async def pending_api(_admin: str = Depends(_require_admin)):
        async with session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.tenant_id == default_tenant_id,
                    ApprovalRequest.status == PENDING,
                )
                .order_by(ApprovalRequest.created_at.desc())
            )
            approvals = res.scalars().all()
        return {
            "approvals": [
                {
                    "id": str(a.id),
                    "tool": a.tool,
                    "agent_id": str(a.agent_id),
                    "params": a.params_json,
                    "created_at": a.created_at.isoformat(),
                }
                for a in approvals
            ]
        }

    @r.post("/approvals/{approval_id}/decide", response_class=HTMLResponse)
    async def decide(
        approval_id: UUID,
        decision: str = Query(...),
        reason: str | None = None,
        admin: str = Depends(_require_admin),
    ):
        if decision not in ("approved", "rejected"):
            return HTMLResponse("invalid decision", status_code=400)
        # decided_by is taken from the authenticated admin identity, never the
        # caller — preventing audit forgery via query-param spoofing.
        # tenant_id filter prevents cross-tenant decision via UUID guess.
        ok = await approval_store.decide(
            approval_id,
            decision=decision,
            decided_by=admin,
            reason=reason,
            tenant_id=await _tenant_id(),
        )
        if ok:
            await broadcaster.notify_decided(approval_id=approval_id, status=decision)
        return HTMLResponse("")  # remove the row

    @r.websocket("/approvals/ws")
    async def ws(websocket: WebSocket, token: str = Query(default="")):
        # WebSocket auth via query param (browsers can't easily set headers).
        if settings.web_admin_token is None:
            await websocket.close(code=4503)
            return
        if token != settings.web_admin_token:
            await websocket.close(code=4401)
            return
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await broadcaster.disconnect(websocket)

    return r
