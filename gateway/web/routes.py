"""Web UI router — audit log + approvals dashboard (HTMX + JSON API + WS)."""

from collections.abc import Awaitable, Callable
from uuid import UUID

TenantResolver = UUID | Callable[[], Awaitable[UUID | None]]

from fastapi import (
    APIRouter,
    Body,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
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
from gateway.db.models import ApprovalRequest, Tenant


def _require_admin(authorization: str | None = Header(default=None)) -> str:
    """Bearer-token auth for admin endpoints. Returns the admin user identity."""
    settings = get_settings()
    if settings.web_admin_token is None:
        raise HTTPException(status_code=503, detail="admin auth not configured")
    if authorization != f"Bearer {settings.web_admin_token}":
        raise HTTPException(status_code=401, detail="unauthorized")
    return settings.web_admin_user


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def make_router(
    *,
    templates: Jinja2Templates,
    audit_reader: AuditReader,
    approval_store: ApprovalStore,
    broadcaster: WebSocketBroadcaster,
    session_factory,
    default_tenant_id: TenantResolver,  # MVP fallback: single tenant. UUID or async callable.
) -> APIRouter:
    r = APIRouter()
    settings = get_settings()

    async def _default_tenant() -> UUID:
        if callable(default_tenant_id):
            tid = await default_tenant_id()
            if tid is None:
                raise HTTPException(status_code=503, detail="no tenant seeded yet")
            return tid
        return default_tenant_id

    async def _tenant_exists(tid: UUID) -> bool:
        async with session_factory() as s:
            res = await s.execute(select(Tenant.id).where(Tenant.id == tid))
            return res.scalar_one_or_none() is not None

    async def _resolve_tenant(
        explicit: str | None,
        cookie_tenant: str | None,
    ) -> UUID:
        """Resolution order: explicit query/form param -> cookie -> first tenant fallback.

        Validates the candidate UUID actually exists in ``tenants`` before using
        it; an unknown UUID raises 404 to avoid leaking data via random guesses
        falling back silently to the default tenant.
        """
        explicit_uuid = _parse_uuid(explicit)
        if explicit is not None and explicit != "":
            # Caller explicitly supplied something — it MUST be valid+existing.
            if explicit_uuid is None or not await _tenant_exists(explicit_uuid):
                raise HTTPException(status_code=404, detail="tenant not found")
            return explicit_uuid

        cookie_uuid = _parse_uuid(cookie_tenant)
        if cookie_uuid is not None and await _tenant_exists(cookie_uuid):
            return cookie_uuid

        return await _default_tenant()

    @r.get("/api/tenants")
    async def list_tenants(_admin: str = Depends(_require_admin)):
        async with session_factory() as s:
            res = await s.execute(select(Tenant.id, Tenant.name).order_by(Tenant.name))
            return {"tenants": [{"id": str(row.id), "name": row.name} for row in res]}

    @r.post("/api/tenants/select")
    async def select_tenant(
        payload: dict = Body(...),
        _admin: str = Depends(_require_admin),
    ):
        raw = payload.get("tenant_id") if isinstance(payload, dict) else None
        candidate = _parse_uuid(raw if isinstance(raw, str) else None)
        if candidate is None or not await _tenant_exists(candidate):
            raise HTTPException(status_code=404, detail="tenant not found")
        response = Response(status_code=204)
        response.set_cookie(
            key="tenant_id",
            value=str(candidate),
            max_age=60 * 60 * 24 * 30,  # 30 days
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @r.get("/audit", response_class=HTMLResponse)
    async def audit_page(request: Request):
        return templates.TemplateResponse(
            request,
            "audit.html",
            {"admin_token": settings.web_admin_token or ""},
        )

    @r.get("/audit/rows", response_class=HTMLResponse)
    async def audit_rows(
        request: Request,
        agent_id: str | None = None,
        tool: str | None = None,
        result_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        tenant_id: str | None = None,
        cookie_tenant: str | None = Cookie(default=None, alias="tenant_id"),
        _admin: str = Depends(_require_admin),
    ):
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        tid = await _resolve_tenant(tenant_id, cookie_tenant)
        f = AuditFilter(
            tenant_id=tid,
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
        tenant_id: str | None = None,
        cookie_tenant: str | None = Cookie(default=None, alias="tenant_id"),
        _admin: str = Depends(_require_admin),
    ):
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        tid = await _resolve_tenant(tenant_id, cookie_tenant)
        f = AuditFilter(
            tenant_id=tid,
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
        return templates.TemplateResponse(
            request,
            "approvals.html",
            {"admin_token": settings.web_admin_token or ""},
        )

    @r.get("/approvals/list", response_class=HTMLResponse)
    async def approvals_list(
        request: Request,
        tenant_id: str | None = None,
        cookie_tenant: str | None = Cookie(default=None, alias="tenant_id"),
        admin: str = Depends(_require_admin),
    ):
        tid = await _resolve_tenant(tenant_id, cookie_tenant)
        async with session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.tenant_id == tid,
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
    async def pending_api(
        tenant_id: str | None = None,
        cookie_tenant: str | None = Cookie(default=None, alias="tenant_id"),
        _admin: str = Depends(_require_admin),
    ):
        tid = await _resolve_tenant(tenant_id, cookie_tenant)
        async with session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.tenant_id == tid,
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
        reason_q: str | None = Query(default=None, alias="reason"),
        reason_f: str | None = Form(default=None, alias="reason"),
        tenant_id: str | None = None,
        cookie_tenant: str | None = Cookie(default=None, alias="tenant_id"),
        admin: str = Depends(_require_admin),
    ):
        if decision not in ("approved", "rejected"):
            return HTMLResponse("invalid decision", status_code=400)
        # Form body wins over query param when both supplied. Empty string is
        # treated as "no reason" — DB column is nullable.
        reason = reason_f if reason_f not in (None, "") else reason_q
        if reason is not None:
            reason = reason.strip() or None
            if reason is not None and len(reason) > 500:
                reason = reason[:500]
        tid = await _resolve_tenant(tenant_id, cookie_tenant)
        # decided_by is taken from the authenticated admin identity, never the
        # caller — preventing audit forgery via query-param spoofing.
        # tenant_id filter prevents cross-tenant decision via UUID guess.
        ok = await approval_store.decide(
            approval_id,
            decision=decision,
            decided_by=admin,
            reason=reason,
            tenant_id=tid,
        )
        if ok:
            await broadcaster.notify_decided(
                approval_id=approval_id, status=decision, reason=reason
            )
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
