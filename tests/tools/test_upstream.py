"""Tests for UpstreamClient: HTTP, retry, no-retry-on-4xx, circuit breaker."""

import httpx
import pytest
import respx

from gateway.tools.exceptions import UpstreamClientError, UpstreamUnavailable
from gateway.tools.upstream import UpstreamClient

pytestmark = pytest.mark.unit


@pytest.fixture
async def client():
    c = UpstreamClient("http://test.local", "k", "test", timeout=1)
    yield c
    await c.aclose()


@respx.mock
async def test_get_returns_json(client):
    respx.get("http://test.local/x").respond(200, json={"ok": True})
    assert await client.get("/x") == {"ok": True}


@respx.mock
async def test_retry_on_5xx(client):
    route = respx.get("http://test.local/x").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert await client.get("/x") == {"ok": True}
    assert route.call_count == 3


@respx.mock
async def test_no_retry_on_4xx(client):
    route = respx.get("http://test.local/x").respond(404, json={"err": "nf"})
    with pytest.raises(UpstreamClientError) as exc:
        await client.get("/x")
    assert exc.value.status == 404
    assert route.call_count == 1


@respx.mock
async def test_circuit_opens_after_failures():
    c = UpstreamClient("http://t.local", "k", "svc", timeout=1)
    respx.get("http://t.local/x").respond(500)
    for _ in range(5):
        with pytest.raises(Exception):
            await c.get("/x")
    # Circuit now open — should fail fast
    with pytest.raises(UpstreamUnavailable):
        await c.get("/x")
    await c.aclose()
