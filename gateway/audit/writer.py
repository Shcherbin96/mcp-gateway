"""Audit log writer — append-only inserts."""

from uuid import UUID

from gateway.db.models import AuditLog


class AuditWriter:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def write(
        self,
        *,
        tenant_id: UUID | None,
        agent_id: UUID | None,
        tool: str | None,
        params: dict,
        result_status: str,
        result: dict | None = None,
        approval_id: UUID | None = None,
        trace_id: str | None = None,
    ) -> None:
        async with self._sf() as session:
            entry = AuditLog(
                tenant_id=tenant_id,
                agent_id=agent_id,
                tool=tool,
                params_json=params,
                result_status=result_status,
                result_json=result or {},
                approval_id=approval_id,
                trace_id=trace_id,
            )
            session.add(entry)
            await session.commit()
