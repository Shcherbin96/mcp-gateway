"""Stdio MCP proxy → HTTP MCP Gateway.

Claude Desktop launches this as a stdio MCP server. It speaks JSON-RPC 2.0
over stdin/stdout per the MCP spec, translating ``tools/list`` and ``tools/call``
into HTTP requests against the gateway with a bearer token.

This is the production pattern: a trusted local proxy holds long-lived OAuth
credentials and exposes them only to Claude Desktop via stdio. The gateway
sees a normal authenticated HTTP client.

Usage (claude_desktop_config.json):

    {
      "mcpServers": {
        "mcp-gateway": {
          "command": "/path/to/.venv/bin/python",
          "args": ["-m", "gateway.mcp_stdio_proxy"],
          "env": {
            "MCP_GATEWAY_URL": "http://localhost:8000",
            "MCP_GATEWAY_OAUTH_ISSUER": "http://localhost:9000",
            "MCP_GATEWAY_CLIENT_ID": "client-...",
            "MCP_GATEWAY_CLIENT_SECRET": "..."
          }
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "mcp-gateway-proxy"
SERVER_VERSION = "0.1.0"

GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL", "http://localhost:8000").rstrip("/")
ISSUER = os.environ.get("MCP_GATEWAY_OAUTH_ISSUER", "http://localhost:9000").rstrip("/")
CLIENT_ID = os.environ.get("MCP_GATEWAY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("MCP_GATEWAY_CLIENT_SECRET", "")
STATIC_TOKEN = os.environ.get("MCP_GATEWAY_TOKEN", "")  # bypass token exchange if pre-set

# Token cache (keep the proxy long-lived; refresh on expiry).
_token: str | None = None
_token_exp: float = 0.0


def _log(msg: str) -> None:
    """Diagnostics go to stderr — stdout is reserved for JSON-RPC frames."""
    print(f"[mcp-proxy] {msg}", file=sys.stderr, flush=True)


async def _get_token(client: httpx.AsyncClient) -> str:
    """Fetch a fresh JWT, cached until ~30s before expiry."""
    global _token, _token_exp
    if STATIC_TOKEN:
        return STATIC_TOKEN
    now = time.monotonic()
    if _token and now < _token_exp - 30:
        return _token
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("Either MCP_GATEWAY_TOKEN or CLIENT_ID + CLIENT_SECRET must be set")
    resp = await client.post(
        f"{ISSUER}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    _token = payload["access_token"]
    _token_exp = now + payload.get("expires_in", 3600)
    _log(f"acquired token (expires_in={payload.get('expires_in')})")
    return _token


async def handle_initialize(req_id: Any) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    }


async def handle_tools_list(req_id: Any, client: httpx.AsyncClient) -> dict:
    resp = await client.get(f"{GATEWAY_URL}/mcp/tools", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    tools = [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "inputSchema": t.get("inputSchema", {"type": "object"}),
        }
        for t in data.get("tools", [])
    ]
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}


async def handle_tools_call(req_id: Any, params: dict, client: httpx.AsyncClient) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not name:
        return _error(req_id, -32602, "missing tool name")
    token = await _get_token(client)
    resp = await client.post(
        f"{GATEWAY_URL}/mcp/call/{name}",
        json=arguments,
        headers={"Authorization": f"Bearer {token}"},
        timeout=600,  # approval flow may block for minutes
    )
    body: Any
    try:
        body = resp.json()
    except Exception:
        body = {"text": resp.text}
    is_error = resp.status_code >= 400
    text = json.dumps(body, indent=2, ensure_ascii=False)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        },
    }


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _route(msg: dict, client: httpx.AsyncClient) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        return await handle_initialize(req_id)
    if method == "notifications/initialized":
        return None  # notification, no response
    if method == "tools/list":
        return await handle_tools_list(req_id, client)
    if method == "tools/call":
        return await handle_tools_call(req_id, params, client)
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if req_id is not None:
        return _error(req_id, -32601, f"method not found: {method}")
    return None


async def main_async() -> None:
    _log(f"started — gateway={GATEWAY_URL} issuer={ISSUER}")
    async with httpx.AsyncClient() as client:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
        while True:
            line = await reader.readline()
            if not line:
                _log("stdin closed, exiting")
                return
            try:
                msg = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError as e:
                _log(f"bad JSON on stdin: {e}")
                continue
            try:
                response = await _route(msg, client)
            except Exception as e:
                _log(f"handler error: {e}")
                response = _error(msg.get("id"), -32603, str(e))
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
