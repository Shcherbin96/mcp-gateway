"""Postgres LISTEN/NOTIFY helper for the approval flow.

Uses a raw asyncpg connection (NOT SQLAlchemy) because asyncpg's
``add_listener`` API operates on the underlying connection directly.

Channel: ``mcp_approval_decided``. Payload: the approval id (UUID hex).
NOTIFY is fired by :meth:`ApprovalStore.decide` in the same transaction
that mutates the row, so a wake-up implies the row has been updated.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

import asyncpg

from gateway.observability.logging import get_logger

log = get_logger(__name__)

CHANNEL = "mcp_approval_decided"


def _to_asyncpg_dsn(database_url: str) -> str:
    """Strip SQLAlchemy driver prefix so asyncpg accepts the URL."""
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_url[len("postgresql+asyncpg://") :]
    return database_url


async def listen_for_approval(database_url: str, approval_id: UUID, timeout: float) -> str | None:
    """Listen on ``mcp_approval_decided`` for the given id; return payload or None.

    The payload published by NOTIFY is ``"<id>:<status>"`` (e.g.
    ``"abc...:approved"``); we return only the status portion. If the
    timeout elapses with no matching notification, returns ``None``.
    """
    target_id = approval_id.hex
    event = asyncio.Event()
    received_status: dict[str, str] = {}

    def _handler(_conn: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            id_part, _, status = payload.partition(":")
        except Exception:  # noqa: BLE001 — defensive parse
            return
        # asyncpg may strip dashes; compare hex-only forms.
        if id_part.replace("-", "") == target_id:
            received_status["status"] = status
            event.set()

    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(_to_asyncpg_dsn(database_url))
        await conn.add_listener(CHANNEL, _handler)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return received_status.get("status")
        except TimeoutError:
            return None
    except Exception as e:  # noqa: BLE001 — listener is best-effort
        log.warning("listen_for_approval_failed", error=str(e), approval_id=str(approval_id))
        return None
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.remove_listener(CHANNEL, _handler)
            with contextlib.suppress(Exception):
                await conn.close()
