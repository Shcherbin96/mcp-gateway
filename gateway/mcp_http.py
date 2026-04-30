"""MCP Streamable HTTP transport — single endpoint at ``/mcp/rpc``.

Implements the MCP 2025-06-18 Streamable HTTP transport so MCP clients
(Claude Desktop, Cursor, Continue) can talk to the gateway directly without
the stdio proxy. The endpoint accepts a JSON-RPC 2.0 request body, routes
it through the standard pipeline (authenticate → authorize → approve →
execute → audit), and returns a JSON-RPC 2.0 envelope.

Spec reference: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http

Design notes:
- We do not implement server-initiated streaming (text/event-stream) — every
  response is plain ``application/json``. ``GET /mcp/rpc`` returns 405.
- ``Mcp-Session-Id`` is generated on ``initialize`` and echoed otherwise.
- All request errors surface as JSON-RPC error envelopes with HTTP 200,
  except a body that is not parseable as JSON (HTTP 400, per spec).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from gateway.observability.logging import get_logger
from gateway.tools.dispatch import invoke_tool

log = get_logger(__name__)

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "mcp-gateway"
SERVER_VERSION = "0.1.0"

# JSON-RPC 2.0 error codes
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def _envelope_result(req_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _envelope_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[len("Bearer ") :].strip()
    return None


def _session_header(request: Request, *, fresh: bool = False) -> dict[str, str]:
    """Return the Mcp-Session-Id header dict — echo client's value or mint a new one."""
    existing = request.headers.get("mcp-session-id")
    if fresh or not existing:
        return {"Mcp-Session-Id": uuid4().hex}
    return {"Mcp-Session-Id": existing}


def _tools_catalog(registry) -> list[dict]:
    return [
        {
            "name": m.name,
            "description": m.description,
            "inputSchema": m.input_schema,
        }
        for m in registry.list()
    ]


async def _handle_initialize(req_id: Any) -> dict:
    return _envelope_result(
        req_id,
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    )


async def _handle_tools_list(req_id: Any, request: Request) -> dict:
    tools = _tools_catalog(request.app.state.registry)
    return _envelope_result(req_id, {"tools": tools})


async def _handle_tools_call(req_id: Any, params: dict, request: Request) -> dict:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not name or not isinstance(name, str):
        return _envelope_error(req_id, JSONRPC_INVALID_PARAMS, "missing or invalid 'name'")
    if not isinstance(arguments, dict):
        return _envelope_error(req_id, JSONRPC_INVALID_PARAMS, "'arguments' must be an object")

    token = _extract_token(request)
    client_ip = request.client.host if request.client else None

    outcome = await invoke_tool(
        app_state=request.app.state,
        tool_name=name,
        payload=arguments,
        token=token,
        client_ip=client_ip,
    )

    if outcome.rate_limited:
        return _envelope_error(
            req_id,
            JSONRPC_INTERNAL_ERROR,
            "rate_limit_exceeded",
            {"retry_after": outcome.retry_after},
        )

    body_text = json.dumps(outcome.body, indent=2, ensure_ascii=False)
    return _envelope_result(
        req_id,
        {
            "content": [{"type": "text", "text": body_text}],
            "isError": outcome.is_error,
        },
    )


def make_mcp_http_router() -> APIRouter:
    """Build the FastAPI router exposing MCP Streamable HTTP at ``/mcp/rpc``."""
    router = APIRouter(tags=["MCP"])

    @router.get(
        "/mcp/rpc",
        summary="MCP Streamable HTTP (server→client streaming not supported)",
        include_in_schema=True,
    )
    async def mcp_get() -> JSONResponse:
        # Spec allows servers to reject GET. We don't issue server-initiated
        # notifications, so refuse cleanly with a JSON-RPC-shaped error body.
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": JSONRPC_INVALID_REQUEST,
                    "message": (
                        "GET not supported — this server does not issue "
                        "server-initiated streams. Use POST."
                    ),
                },
            },
            status_code=405,
            headers={"Allow": "POST"},
        )

    @router.post(
        "/mcp/rpc",
        summary="MCP Streamable HTTP — JSON-RPC 2.0 (initialize / tools/list / tools/call / ping)",
    )
    async def mcp_post(request: Request) -> Response:
        # Body must be JSON-parseable; otherwise HTTP 400 per spec.
        try:
            raw = await request.body()
            msg = json.loads(raw or b"null")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(
                _envelope_error(None, JSONRPC_PARSE_ERROR, "parse error"),
                status_code=400,
            )

        if not isinstance(msg, dict):
            # Batch (list) is permitted by the JSON-RPC spec but not required by
            # MCP and not supported here — surface a clear error.
            return JSONResponse(
                _envelope_error(None, JSONRPC_INVALID_REQUEST, "expected JSON-RPC object"),
                status_code=200,
            )

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        # Notifications (no id) — return 202 Accepted with empty body per spec.
        if req_id is None and isinstance(method, str) and method.startswith("notifications/"):
            return Response(status_code=202, headers=_session_header(request))

        if not isinstance(method, str):
            return JSONResponse(
                _envelope_error(req_id, JSONRPC_INVALID_REQUEST, "missing 'method'"),
                headers=_session_header(request),
            )

        try:
            if method == "initialize":
                envelope = await _handle_initialize(req_id)
                return JSONResponse(envelope, headers=_session_header(request, fresh=True))
            if method == "tools/list":
                envelope = await _handle_tools_list(req_id, request)
                return JSONResponse(envelope, headers=_session_header(request))
            if method == "tools/call":
                if not isinstance(params, dict):
                    return JSONResponse(
                        _envelope_error(
                            req_id, JSONRPC_INVALID_PARAMS, "'params' must be an object"
                        ),
                        headers=_session_header(request),
                    )
                envelope = await _handle_tools_call(req_id, params, request)
                return JSONResponse(envelope, headers=_session_header(request))
            if method == "ping":
                return JSONResponse(
                    _envelope_result(req_id, {}),
                    headers=_session_header(request),
                )
            return JSONResponse(
                _envelope_error(req_id, JSONRPC_METHOD_NOT_FOUND, f"method not found: {method}"),
                headers=_session_header(request),
            )
        except Exception as e:  # noqa: BLE001 — convert any handler crash to JSON-RPC error
            log.error("mcp_rpc_handler_error", method=method, error=str(e))
            return JSONResponse(
                _envelope_error(req_id, JSONRPC_INTERNAL_ERROR, str(e)),
                headers=_session_header(request),
            )

    return router
