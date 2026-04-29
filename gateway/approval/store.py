"""Approval request persistence + atomic decision transitions."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update

from gateway.db.models import ApprovalRequest

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
TIMEOUT = "timeout"


class ApprovalStore:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create(
        self, *, tenant_id: UUID, agent_id: UUID, tool: str, params: dict
    ) -> UUID:
        async with self._session_factory() as session:
            req = ApprovalRequest(
                tenant_id=tenant_id,
                agent_id=agent_id,
                tool=tool,
                params_json=params,
                status=PENDING,
            )
            session.add(req)
            await session.commit()
            await session.refresh(req)
            return req.id

    async def get(self, req_id: UUID) -> ApprovalRequest | None:
        async with self._session_factory() as session:
            res = await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == req_id)
            )
            return res.scalar_one_or_none()

    async def decide(
        self,
        req_id: UUID,
        *,
        decision: str,
        decided_by: str,
        reason: str | None = None,
    ) -> bool:
        """Returns True if state transitioned, False if already decided."""
        async with self._session_factory() as session:
            res = await session.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.id == req_id,
                    ApprovalRequest.status == PENDING,
                )
                .values(
                    status=decision,
                    decided_by=decided_by,
                    decision_reason=reason,
                    decided_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            return res.rowcount > 0

    async def wait_for_decision(
        self, req_id: UUID, timeout: float, poll_interval: float = 1.0
    ) -> str:
        """Poll until status leaves PENDING or timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            req = await self.get(req_id)
            if req and req.status != PENDING:
                return req.status
            await asyncio.sleep(poll_interval)
        # Timeout: try to mark
        await self.decide(
            req_id, decision=TIMEOUT, decided_by="system", reason="timeout"
        )
        return TIMEOUT
