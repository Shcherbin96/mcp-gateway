"""WebSocket broadcaster — fan out approval events to connected dashboards."""

import asyncio
import json
from uuid import UUID

from fastapi import WebSocket


class WebSocketBroadcaster:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)

    async def _broadcast(self, message: dict):
        async with self._lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def notify_pending(self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict):
        await self._broadcast(
            {
                "type": "pending",
                "approval_id": str(approval_id),
                "agent_id": str(agent_id),
                "tool": tool,
                "params": params,
            }
        )

    async def notify_decided(self, *, approval_id: UUID, status: str, tool: str | None = None):
        # `tool` is accepted for Protocol parity but not broadcast — dashboards
        # already have the tool name from the original `pending` event.
        del tool
        await self._broadcast(
            {
                "type": "decided",
                "approval_id": str(approval_id),
                "status": status,
            }
        )
