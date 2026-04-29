"""Web UI router — audit log + approvals dashboard (HTMX + JSON API + WS)."""

from uuid import UUID

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from gateway.approval.store import PENDING, ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.audit.reader import AuditFilter, AuditReader
from gateway.db.models import ApprovalRequest


def make_router(
    *,
    templates: Jinja2Templates,
    audit_reader: AuditReader,
    approval_store: ApprovalStore,
    broadcaster: WebSocketBroadcaster,
    session_factory,
    default_tenant_id: UUID,  # MVP: single tenant filter for UI
) -> APIRouter:
    r = APIRouter()

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
    ):
        f = AuditFilter(
            tenant_id=default_tenant_id,
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
    ):
        f = AuditFilter(
            tenant_id=default_tenant_id,
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
    async def approvals_list(request: Request):
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
            {"approvals": approvals, "user": "web-user"},
        )

    @r.get("/api/approvals/pending")
    async def pending_api():
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
        decided_by: str = Query("web-user"),
        reason: str | None = None,
    ):
        if decision not in ("approved", "rejected"):
            return HTMLResponse("invalid decision", status_code=400)
        ok = await approval_store.decide(
            approval_id, decision=decision, decided_by=decided_by, reason=reason
        )
        if ok:
            await broadcaster.notify_decided(approval_id=approval_id, status=decision)
        return HTMLResponse("")  # remove the row

    @r.websocket("/approvals/ws")
    async def ws(websocket: WebSocket):
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await broadcaster.disconnect(websocket)

    return r
