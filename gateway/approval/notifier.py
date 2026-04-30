"""Approval notifier protocol + composite fan-out."""

import asyncio
from typing import Protocol
from uuid import UUID


class ApprovalNotifier(Protocol):
    async def notify_pending(
        self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict
    ) -> None: ...

    async def notify_decided(
        self,
        *,
        approval_id: UUID,
        status: str,
        tool: str | None = None,
        reason: str | None = None,
    ) -> None: ...


class CompositeNotifier:
    def __init__(self, notifiers: list[ApprovalNotifier]):
        self._notifiers = notifiers

    async def notify_pending(self, **kwargs):
        await asyncio.gather(
            *(n.notify_pending(**kwargs) for n in self._notifiers),
            return_exceptions=True,
        )

    async def notify_decided(self, **kwargs):
        await asyncio.gather(
            *(n.notify_decided(**kwargs) for n in self._notifiers),
            return_exceptions=True,
        )
