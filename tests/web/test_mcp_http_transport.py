"""Unit tests for the MCP Streamable HTTP transport at ``/mcp/rpc``.

These tests assemble a minimal FastAPI app with stubbed dependencies so the
transport contract (JSON-RPC envelopes, session header, method routing) can
be verified without touching Postgres or the JWT validator.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from gateway.mcp_http import make_mcp_http_router
from gateway.middleware.chain import CallContext, Pipeline
from gateway.middleware.rate_limit import RateLimiter
from gateway.tools.crm import build_crm_tools
from gateway.tools.payments import build_payment_tools
from gateway.tools.registry import ToolRegistry
from gateway.tools.upstream import UpstreamClient

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _build_registry() -> ToolRegistry:
    """Real registry seeded with the production tool definitions.

    We only need the metadata for tools/list and an authorize-failed path for
    tools/call — the upstream clients never get hit because authentication
    fails first.
    """
    crm = UpstreamClient("http://crm.invalid", "k", "crm")
    pay = UpstreamClient("http://payments.invalid", "k", "payments")
    reg = ToolRegistry()
    for meta, handler in build_crm_tools(crm) + build_payment_tools(pay):
        reg.register(meta, handler)
    return reg


def _make_app() -> FastAPI:
    app = FastAPI()

    async def fail_auth(ctx: CallContext) -> None:
        ctx.error = RuntimeError("missing token")
        ctx.result_status = "auth_failed"

    async def noop_audit(ctx: CallContext) -> None:
        return None

    app.state.registry = _build_registry()
    app.state.pipeline = Pipeline(steps=[fail_auth])
    app.state.audit_step: Callable[[CallContext], Awaitable[None]] = noop_audit  # type: ignore[attr-defined]
    app.state.rate_limiter = RateLimiter(rate_per_minute=600, burst=100)

    app.include_router(make_mcp_http_router())
    return app


async def _post(app: FastAPI, body: dict, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/mcp/rpc", json=body, headers=headers or {})


async def test_initialize_returns_session_id() -> None:
    app = _make_app()
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    r = await _post(app, body)

    assert r.status_code == 200
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2025-06-18"
    assert data["result"]["capabilities"] == {"tools": {}}
    assert data["result"]["serverInfo"]["name"] == "mcp-gateway"
    # Session id minted fresh on initialize.
    assert "mcp-session-id" in {k.lower() for k in r.headers}
    assert r.headers["mcp-session-id"]


async def test_tools_list_returns_catalog() -> None:
    app = _make_app()
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    r = await _post(app, body, headers={"Mcp-Session-Id": "abc"})

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 7
    tools = data["result"]["tools"]
    # 3 CRM tools + 2 payments tools = 5.
    assert len(tools) == 5
    names = {t["name"] for t in tools}
    assert {"get_customer", "list_orders", "update_order", "refund_payment", "charge_card"} <= names
    # Existing session id is echoed back, not regenerated.
    assert r.headers["mcp-session-id"] == "abc"


async def test_tools_call_unauthorized_returns_jsonrpc_error() -> None:
    app = _make_app()
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "get_customer", "arguments": {"customer_id": "C1"}},
    }
    # No Authorization header — pipeline's stub auth step sets auth_failed.
    r = await _post(app, body)

    # MCP spec: tool errors travel inside the JSON-RPC result envelope, HTTP 200.
    assert r.status_code == 200
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 99
    # tools/call wraps the error body inside content+isError, never as JSON-RPC error.
    assert "result" in data
    assert data["result"]["isError"] is True
    assert "missing token" in data["result"]["content"][0]["text"]
