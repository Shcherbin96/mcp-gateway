"""Audit log reader — filtered, paginated, tenant-isolated queries."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from gateway.db.models import AuditLog


@dataclass
class AuditFilter:
    tenant_id: UUID
    agent_id: UUID | None = None
    tool: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    result_status: str | None = None


@dataclass
class AuditPage:
    entries: list[AuditLog]
    total: int
    limit: int
    offset: int


class AuditReader:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def query(self, f: AuditFilter, *, limit: int = 50, offset: int = 0) -> AuditPage:
        stmt = select(AuditLog).where(AuditLog.tenant_id == f.tenant_id)
        if f.agent_id:
            stmt = stmt.where(AuditLog.agent_id == f.agent_id)
        if f.tool:
            stmt = stmt.where(AuditLog.tool == f.tool)
        if f.result_status:
            stmt = stmt.where(AuditLog.result_status == f.result_status)
        if f.from_ts:
            stmt = stmt.where(AuditLog.created_at >= f.from_ts)
        if f.to_ts:
            stmt = stmt.where(AuditLog.created_at <= f.to_ts)

        async with self._sf() as session:
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar_one()
            stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
            entries = (await session.execute(stmt)).scalars().all()
        return AuditPage(entries=list(entries), total=total, limit=limit, offset=offset)
