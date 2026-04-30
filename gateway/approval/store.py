"""Approval request persistence + atomic decision transitions.

``decide()`` issues ``NOTIFY mcp_approval_decided, '<id>:<status>'`` in the
same transaction that mutates the row, so any listener that wakes up will
see the new status. ``wait_for_decision()`` races a Postgres LISTEN against
a (slower) poll loop as a safety net for failover gaps.
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text, update

from gateway.approval.notify_pg import CHANNEL, listen_for_approval
from gateway.config import get_settings
from gateway.db.models import ApprovalRequest

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
TIMEOUT = "timeout"


class ApprovalStore:
    def __init__(self, session_factory, database_url: str | None = None):
        self._session_factory = session_factory
        # Lazy: only resolve when wait_for_decision needs the LISTEN URL.
        self._database_url = database_url

    def _get_database_url(self) -> str:
        if self._database_url is None:
            self._database_url = get_settings().database_url
        return self._database_url

    async def create(self, *, tenant_id: UUID, agent_id: UUID, tool: str, params: dict) -> UUID:
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
            res = await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == req_id))
            return res.scalar_one_or_none()

    async def decide(
        self,
        req_id: UUID,
        *,
        decision: str,
        decided_by: str,
        reason: str | None = None,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Returns True if state transitioned, False if already decided.

        On a successful transition, fires ``NOTIFY mcp_approval_decided`` with
        payload ``"<id_hex>:<decision>"`` in the same transaction so any
        listener observes the new row state.

        When ``tenant_id`` is provided, the update is additionally scoped to
        that tenant, preventing cross-tenant decisions via UUID guess.
        """
        async with self._session_factory() as session:
            stmt = update(ApprovalRequest).where(
                ApprovalRequest.id == req_id,
                ApprovalRequest.status == PENDING,
            )
            if tenant_id is not None:
                stmt = stmt.where(ApprovalRequest.tenant_id == tenant_id)
            stmt = stmt.values(
                status=decision,
                decided_by=decided_by,
                decision_reason=reason,
                decided_at=datetime.now(UTC),
            )
            res = await session.execute(stmt)
            transitioned = res.rowcount > 0
            if transitioned:
                # Same transaction: NOTIFY is buffered until commit, so listeners
                # see the row update before the wake-up. Postgres NOTIFY does not
                # accept parameter binds, but the payload is fully constructed
                # from controlled values (UUID hex + a small enum), so safe to
                # interpolate. We escape single quotes defensively anyway.
                safe_decision = decision.replace("'", "''")
                payload = f"{req_id.hex}:{safe_decision}"
                await session.execute(text(f"NOTIFY {CHANNEL}, '{payload}'"))
            await session.commit()
            return transitioned

    async def wait_for_decision(
        self, req_id: UUID, timeout: float, poll_interval: float | None = None
    ) -> str:
        """Race LISTEN/NOTIFY against a (slower) poll fallback; first wins.

        ``poll_interval`` defaults to settings.approval_poll_interval_seconds
        (5.0s) — much less aggressive than before since NOTIFY normally fires
        in milliseconds. Polling exists only to bridge brief failover gaps.
        """
        if poll_interval is None:
            poll_interval = get_settings().approval_poll_interval_seconds

        # Fast path: maybe already decided before we got here.
        req = await self.get(req_id)
        if req and req.status != PENDING:
            return req.status

        listen_task = asyncio.create_task(
            listen_for_approval(self._get_database_url(), req_id, timeout)
        )
        poll_task = asyncio.create_task(self._poll_loop(req_id, timeout, poll_interval))
        tasks: set[asyncio.Task] = {listen_task, poll_task}

        try:
            # Loop on FIRST_COMPLETED: an early None from the listener (e.g.
            # connection refused) must NOT cancel the poll fallback. Only a
            # real status wins; otherwise we keep waiting on the rest.
            while tasks:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    tasks.discard(t)
                    result = t.result()
                    if result is not None and result != PENDING:
                        for other in tasks:
                            other.cancel()
                            with contextlib.suppress(asyncio.CancelledError, Exception):
                                await other
                        return result
        except Exception:
            for t in (listen_task, poll_task):
                if not t.done():
                    t.cancel()
            raise

        # Both returned None (timeout) — mark timeout authoritatively.
        await self.decide(req_id, decision=TIMEOUT, decided_by="system", reason="timeout")
        return TIMEOUT

    async def _poll_loop(self, req_id: UUID, timeout: float, poll_interval: float) -> str | None:
        """Poll until status leaves PENDING or until ``timeout`` elapses."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            req = await self.get(req_id)
            if req and req.status != PENDING:
                return req.status
            await asyncio.sleep(poll_interval)
        return None
