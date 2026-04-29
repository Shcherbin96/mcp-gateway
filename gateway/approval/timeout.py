"""Background task that marks expired pending approvals as TIMEOUT."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from gateway.approval.store import PENDING, TIMEOUT
from gateway.db.models import ApprovalRequest
from gateway.observability.logging import get_logger

log = get_logger(__name__)


class TimeoutReaper:
    def __init__(self, session_factory, timeout_seconds: int, broadcaster=None):
        self._sf = session_factory
        self._timeout = timeout_seconds
        self._broadcaster = broadcaster
        self._task: asyncio.Task | None = None

    async def _tick(self):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._timeout)
        async with self._sf() as session:
            res = await session.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.status == PENDING,
                    ApprovalRequest.created_at < cutoff,
                )
            )
            ids = [r[0] for r in res]
            if ids:
                await session.execute(
                    update(ApprovalRequest)
                    .where(
                        ApprovalRequest.id.in_(ids),
                        ApprovalRequest.status == PENDING,
                    )
                    .values(
                        status=TIMEOUT,
                        decided_by="system",
                        decision_reason="timeout",
                    )
                )
                await session.commit()
                log.info("approvals_timed_out", count=len(ids))
                if self._broadcaster:
                    for i in ids:
                        await self._broadcaster.notify_decided(
                            approval_id=i, status=TIMEOUT
                        )

    async def _run(self):
        while True:
            try:
                await self._tick()
            except Exception as e:
                log.error("reaper_tick_failed", error=str(e))
            await asyncio.sleep(10)

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
